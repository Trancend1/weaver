"""Chapter- and selection-scoped AI translation for the cockpit (Sprint 4A).

Splits into two steps so a web handler can return fast errors before backgrounding
the slow work:

- :func:`prepare_chapter_translation` (synchronous, read-only): validates the
  chapter / selection, builds and healthchecks the provider, loads glossary, and
  returns an immutable :class:`TranslationPlan`. Raises the project's typed errors
  (chapter / segment not found, empty selection, provider unavailable, glossary
  conflict, bad config) so the caller maps them to HTTP status codes.
- :func:`run_translation` (writable, background-thread friendly): translates the
  planned segments one transaction each, reusing the shared per-segment primitive.

Framework-agnostic: no web types here. Unlike ``translate_project`` this path does
not re-read the source file — it derives normalized text from the stored segment
text via :func:`normalize_japanese_text`, so it works for any volume/chapter
without depending on the project's single configured ``source_file``.

Skip-already-translated: only ``pending`` / ``failed`` / ``stale`` segments are
translated; ``translated`` / ``manual`` segments are left untouched (overwrite /
safe-retranslate is a later stage).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Sequence
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from weaver.core.config import load_project_config
from weaver.core.segment import normalize_japanese_text
from weaver.errors import (
    ChapterNotFoundError,
    ConfigError,
    ProviderUnavailable,
    SegmentNotFoundError,
)
from weaver.providers import GlossaryTerm, LLMProvider, build_provider
from weaver.providers.types import CharacterContext
from weaver.services.glossary import raise_on_glossary_conflicts
from weaver.services.project_paths import resolve_database_path
from weaver.services.translation import (
    VALID_HONORIFIC_POLICIES,
    ProgressCallback,
    load_character_contexts,
    translate_one_segment,
)
from weaver.storage.db import connect_database, connect_readonly_database
from weaver.storage.glossary import list_glossary_terms
from weaver.storage.projects import ProjectRecord, get_project
from weaver.storage.segments import (
    SegmentRecord,
    get_segment,
    list_chapter_segments,
)

# Retranslate modes (Sprint 4C). Govern which existing segments are eligible:
#   skip_existing         — only pending/failed/stale (never overwrite; 4A default)
#   retranslate_non_manual — also re-translate `translated`, but never `manual`
#   force_selected        — translate every target, including `manual`
TRANSLATE_MODES = frozenset({"skip_existing", "retranslate_non_manual", "force_selected"})
_NEEDS_TRANSLATION = frozenset({"pending", "failed", "stale"})


@dataclass(frozen=True)
class TranslationPlan:
    """A validated, ready-to-run chapter/selection translation."""

    project_toml: Path
    db_path: Path
    chapter_id: str
    mode: str  # "chapter" | "selection"
    project: ProjectRecord
    provider: LLMProvider
    provider_model: str
    honorific_policy: str
    glossary_terms: tuple[GlossaryTerm, ...]
    characters: tuple[CharacterContext, ...]
    target_segment_ids: tuple[str, ...]
    requested_count: int
    use_translation_memory: bool


@dataclass(frozen=True)
class ChapterTranslationResult:
    """Outcome of running a :class:`TranslationPlan`."""

    chapter_id: str
    selected: int
    translated: int
    reused_from_memory: int
    failed: int
    skipped: int
    input_tokens: int
    output_tokens: int
    cancelled: bool


def prepare_chapter_translation(
    project_toml: Path,
    chapter_id: str,
    *,
    segment_ids: Sequence[str] | None = None,
    mode: str = "skip_existing",
    cwd: Path | None = None,
    provider_override: dict[str, Any] | None = None,
) -> TranslationPlan:
    """Validate and plan an AI translation for one chapter or a segment selection.

    Args:
        project_toml: Path to the project's ``project.toml``.
        chapter_id: Chapter the work is scoped to.
        segment_ids: When ``None``, target the whole chapter. When provided, target
            exactly these segments (each must belong to ``chapter_id``); an empty
            sequence is rejected.
        mode: One of ``skip_existing`` (only pending/failed/stale; never overwrite),
            ``retranslate_non_manual`` (also re-translate ``translated``, never
            ``manual``), or ``force_selected`` (translate every target, including
            ``manual``). Segments excluded by the mode are reported as ``skipped``.
        cwd: Working directory used to resolve project-relative paths.
        provider_override: Optional ``{"type": ..., "model": ...}`` merged onto the
            configured ``[provider]`` block so one run can target a different
            provider/model without editing project.toml. ``None`` values are dropped.

    Returns:
        An immutable :class:`TranslationPlan`.

    Raises:
        ChapterNotFoundError: If the chapter id does not exist.
        SegmentNotFoundError: If a selected segment is missing or not in the chapter.
        ValueError: If ``segment_ids`` is provided but empty, or ``mode`` is unknown.
        ConfigError: If the honorific policy or provider model is invalid.
        GlossaryConflictError: If approved glossary terms conflict.
        ProviderUnavailable: If the configured/overridden provider is unhealthy.
    """

    if mode not in TRANSLATE_MODES:
        valid = ", ".join(sorted(TRANSLATE_MODES))
        raise ValueError(
            f"Unknown translate mode `{mode}`. "
            f"Likely cause: the request mode must be one of: {valid}. "
            "Next command: resend with a valid `mode`."
        )

    if segment_ids is not None and len(segment_ids) == 0:
        raise ValueError(
            "No segments selected for translation. "
            "Likely cause: the request carried an empty `segment_ids` list. "
            "Next command: send at least one segment id, or call the chapter "
            "translate endpoint to translate the whole chapter."
        )

    data = load_project_config(project_toml)
    provider_config = _merge_provider_config(data["provider"], provider_override)
    honorific_policy = str(data["translation"].get("honorifics", "preserve"))
    if honorific_policy not in VALID_HONORIFIC_POLICIES:
        valid = ", ".join(sorted(VALID_HONORIFIC_POLICIES))
        raise ConfigError(
            f"Invalid honorifics value `{honorific_policy}`. "
            f"Likely cause: project.toml [translation] honorifics must be one of: {valid}. "
            "Next command: edit project.toml and correct the value."
        )
    provider_model = str(provider_config.get("model", "")).strip()
    if not provider_model:
        raise ConfigError(
            "Provider configuration is missing `provider.model`. "
            "Likely cause: project.toml [provider] has no model, or the request "
            "override cleared it. "
            "Next command: set `[provider] model` in project.toml or send a model."
        )

    db_path = resolve_database_path(project_toml, cwd=cwd)
    with closing(connect_readonly_database(db_path)) as connection:
        project = _load_single_project(connection)
        if not _chapter_exists(connection, chapter_id):
            raise ChapterNotFoundError(
                f"Chapter '{chapter_id}' was not found in project '{project.name}'. "
                "Likely cause: the chapter id is wrong or its volume was removed. "
                "Next command: open the project tree (GET /projects/<name>/tree) "
                "to list chapter ids."
            )

        if segment_ids is None:
            scope = "chapter"
            chapter_segments = list_chapter_segments(connection, chapter_id=chapter_id)
            requested_count = len(chapter_segments)
            targets = [s for s in chapter_segments if _mode_allows(s.status, mode)]
        else:
            scope = "selection"
            requested_count = len(segment_ids)
            targets = _selected_targets(connection, chapter_id, segment_ids, mode)

        raise_on_glossary_conflicts(connection, project_id=project.id)
        glossary_terms = tuple(list_glossary_terms(connection, project_id=project.id))
        characters = load_character_contexts(connection, project_id=project.id)

    provider = build_provider(provider_config)
    status = provider.healthcheck()
    if not status.healthy:
        detail = status.message or "no detail returned"
        raise ProviderUnavailable(
            f"Provider {provider.name} is unavailable: {detail}. "
            "Likely cause: API key missing/invalid, network unreachable, or "
            "local Ollama not running. "
            "Next command: run `weaver inspect --healthcheck <project.toml>`."
        )

    return TranslationPlan(
        project_toml=project_toml,
        db_path=db_path,
        chapter_id=chapter_id,
        mode=scope,
        project=project,
        provider=provider,
        provider_model=provider_model,
        honorific_policy=honorific_policy,
        glossary_terms=glossary_terms,
        characters=characters,
        target_segment_ids=tuple(segment.id for segment in targets),
        requested_count=requested_count,
        # Reuse memory only on the normal translate path. Explicit retranslate
        # (retranslate_non_manual / force_selected) must hit the provider so it is
        # not a silent no-op; the memory is still refreshed on success.
        use_translation_memory=(mode == "skip_existing"),
    )


def run_translation(
    plan: TranslationPlan,
    *,
    should_cancel: Callable[[], bool] | None = None,
    progress_callback: ProgressCallback | None = None,
) -> ChapterTranslationResult:
    """Translate a plan's segments, one transaction each.

    Args:
        plan: A :class:`TranslationPlan` from :func:`prepare_chapter_translation`.
        should_cancel: Optional predicate checked before each segment; when it
            returns True the loop stops cleanly, leaving translated segments
            committed and the rest in their prior status.
        progress_callback: Optional callback invoked after each attempted segment
            with ``(index, total, segment, translated, input_tokens,
            output_tokens)``.

    Returns:
        A :class:`ChapterTranslationResult` with per-run counts and token totals.
    """

    selected = len(plan.target_segment_ids)
    translated = 0
    reused = 0
    failed = 0
    input_tokens = 0
    output_tokens = 0
    cancelled = False

    with closing(connect_database(plan.db_path)) as connection:
        for index, segment_id in enumerate(plan.target_segment_ids, start=1):
            if should_cancel is not None and should_cancel():
                cancelled = True
                break
            segment = get_segment(connection, segment_id)
            if segment is None:
                continue
            normalized = normalize_japanese_text(segment.source_text)
            ok, reused_flag, response_input_tokens, response_output_tokens = translate_one_segment(
                connection=connection,
                segment=segment,
                source_text=segment.source_text,
                normalized_source_text=normalized,
                project=plan.project,
                glossary_terms=plan.glossary_terms,
                honorific_policy=plan.honorific_policy,
                provider=plan.provider,
                provider_model=plan.provider_model,
                characters=plan.characters,
                use_translation_memory=plan.use_translation_memory,
            )
            if ok:
                translated += 1
                input_tokens += response_input_tokens or 0
                output_tokens += response_output_tokens or 0
            else:
                failed += 1
            if reused_flag:
                reused += 1
            if progress_callback is not None:
                progress_callback(
                    index,
                    selected,
                    segment,
                    ok,
                    response_input_tokens,
                    response_output_tokens,
                )

    return ChapterTranslationResult(
        chapter_id=plan.chapter_id,
        selected=selected,
        translated=translated,
        reused_from_memory=reused,
        failed=failed,
        skipped=plan.requested_count - selected,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cancelled=cancelled,
    )


def _selected_targets(
    connection: sqlite3.Connection, chapter_id: str, segment_ids: Sequence[str], mode: str
) -> list[SegmentRecord]:
    targets: list[SegmentRecord] = []
    for segment_id in segment_ids:
        segment = get_segment(connection, segment_id)
        if segment is None or segment.chapter_id != chapter_id:
            raise SegmentNotFoundError(
                f"Segment '{segment_id}' was not found in chapter '{chapter_id}'. "
                "Likely cause: the segment id is wrong or belongs to another chapter. "
                "Next command: open the chapter workspace "
                "(GET /projects/<name>/chapters/<chapter_id>/workspace) to list segment ids."
            )
        if _mode_allows(segment.status, mode):
            targets.append(segment)
    return targets


def _mode_allows(status: str, mode: str) -> bool:
    """Whether a segment with ``status`` is an eligible target under ``mode``.

    - ``skip_existing``: only untranslated work (pending/failed/stale).
    - ``retranslate_non_manual``: the above plus ``translated``; ``manual`` is
      protected and never overwritten.
    - ``force_selected``: any status, including ``manual``.
    """

    if mode == "force_selected":
        return True
    if mode == "retranslate_non_manual":
        return status in _NEEDS_TRANSLATION or status == "translated"
    return status in _NEEDS_TRANSLATION


def _load_single_project(connection: sqlite3.Connection) -> ProjectRecord:
    row = connection.execute("SELECT id FROM projects ORDER BY id LIMIT 1").fetchone()
    if row is None:
        raise ConfigError(
            "Project database has no project row. "
            "Likely cause: database was not initialized by `weaver init`. "
            "Next command: run `weaver init <input.epub>`."
        )
    return get_project(connection, int(row["id"]))


def _chapter_exists(connection: sqlite3.Connection, chapter_id: str) -> bool:
    row = connection.execute("SELECT 1 FROM chapters WHERE id = ?", (chapter_id,)).fetchone()
    return row is not None


def _merge_provider_config(base: dict[str, Any], override: dict[str, Any] | None) -> dict[str, Any]:
    if not override:
        return base
    return {**base, **{k: v for k, v in override.items() if v is not None}}
