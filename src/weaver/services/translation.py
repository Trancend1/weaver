"""Translation context assembly and Phase 4 orchestration."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterable, Sequence
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from weaver.core.config import load_project_config
from weaver.core.ir import BlockIR, DocumentIR
from weaver.errors import ConfigError, ProviderError, ProviderUnavailable
from weaver.providers import LLMProvider, build_provider
from weaver.providers.types import (
    CharacterContext,
    GlossaryTerm,
    TranslationContext,
    TranslationRequest,
)
from weaver.readers import read_source
from weaver.services.glossary import raise_on_glossary_conflicts
from weaver.storage.characters import list_characters
from weaver.storage.db import connect_database, transaction
from weaver.storage.glossary import list_glossary_terms
from weaver.storage.projects import ProjectRecord, get_project
from weaver.storage.segments import (
    SegmentRecord,
    list_segments_for_translation,
    sync_document_segments,
    update_segment_status,
)
from weaver.storage.translations import (
    list_previous_translated_segments,
    record_translation,
)
from weaver.storage.volumes import list_volumes

MAX_GLOSSARY_TERMS_PER_SEGMENT = 20
MAX_CHARACTERS_PER_SEGMENT = 20
MAX_CONTEXT_SEGMENTS = 5
MAX_CONTEXT_TOKENS = 600
DRY_RUN_TOKENS_PER_CHAR = 0.25  # 1 token ≈ 4 source characters

VALID_HONORIFIC_POLICIES = frozenset({"preserve", "localize", "hybrid"})

ProgressCallback = Callable[[int, int, SegmentRecord, bool, int | None, int | None], None]


@dataclass(frozen=True)
class TranslationRunSummary:
    """Outcome of a `weaver translate` run."""

    total_segments: int
    selected_segments: int
    translated_segments: int
    failed_segments: int
    pending_segments: int
    stale_segments: int
    input_tokens: int
    output_tokens: int


def build_context(
    *,
    normalized_source_text: str,
    glossary_terms: Iterable[GlossaryTerm],
    previous_segments: Sequence[tuple[str, str]],
    honorific_policy: str = "preserve",
    characters: Iterable[CharacterContext] = (),
) -> TranslationContext:
    """Assemble a `TranslationContext` for one segment.

    Filters `glossary_terms` to entries whose `source` appears as a substring
    of the segment's normalized source text, capped at 20 entries
    (PROMPT_DESIGN.md §Glossary Filtering). Trims `previous_segments` to the
    most recent 5 entries within a 600-token estimate (oldest-first ordering
    preserved). Tokens are estimated as 1 token ≈ 4 characters.

    Args:
        normalized_source_text: Normalized source text of the current segment,
            used for substring glossary matching.
        glossary_terms: All approved glossary terms for the project.
        previous_segments: (source, translation) pairs from earlier segments
            in the same chapter, ordered oldest-first.
        honorific_policy: One of `preserve` | `localize` | `hybrid`.

    Returns:
        Immutable TranslationContext ready for prompt rendering.

    Raises:
        ValueError: If `honorific_policy` is not a recognized value.
    """

    if honorific_policy not in VALID_HONORIFIC_POLICIES:
        raise ValueError(
            f"honorific_policy must be one of {sorted(VALID_HONORIFIC_POLICIES)}, "
            f"got {honorific_policy!r}"
        )

    filtered_glossary = _filter_glossary(glossary_terms, normalized_source_text)
    filtered_characters = _filter_characters(characters, normalized_source_text)
    trimmed_window = _trim_window(previous_segments)

    return TranslationContext(
        previous_segments=trimmed_window,
        glossary_terms=filtered_glossary,
        honorific_policy=honorific_policy,
        characters=filtered_characters,
    )


def _filter_glossary(
    terms: Iterable[GlossaryTerm], normalized_source: str
) -> tuple[GlossaryTerm, ...]:
    matches: list[GlossaryTerm] = []
    for term in terms:
        if not term.source:
            continue
        haystack = normalized_source if term.case_sensitive else normalized_source.casefold()
        needle = term.source if term.case_sensitive else term.source.casefold()
        if needle in haystack:
            matches.append(term)
        if len(matches) >= MAX_GLOSSARY_TERMS_PER_SEGMENT:
            break
    return tuple(matches)


def _filter_characters(
    characters: Iterable[CharacterContext], normalized_source: str
) -> tuple[CharacterContext, ...]:
    matches: list[CharacterContext] = []
    for character in characters:
        if not character.jp_name:
            continue
        if character.jp_name in normalized_source:
            matches.append(character)
        if len(matches) >= MAX_CHARACTERS_PER_SEGMENT:
            break
    return tuple(matches)


def load_character_contexts(
    connection: sqlite3.Connection, *, project_id: int
) -> tuple[CharacterContext, ...]:
    """Load a project's characters as prompt-ready contexts (storage → DTO)."""

    return tuple(
        CharacterContext(
            jp_name=record.jp_name,
            en_name=record.en_name,
            gender=record.gender,
            role=record.role,
            notes=record.notes,
        )
        for record in list_characters(connection, project_id=project_id)
    )


def _trim_window(
    previous_segments: Sequence[tuple[str, str]],
) -> tuple[tuple[str, str], ...]:
    if not previous_segments:
        return ()
    tail = list(previous_segments[-MAX_CONTEXT_SEGMENTS:])
    while tail and _estimate_tokens(tail) > MAX_CONTEXT_TOKENS:
        tail.pop(0)
    return tuple((str(source), str(translation)) for source, translation in tail)


def _estimate_tokens(window: Sequence[tuple[str, str]]) -> int:
    total_chars = sum(len(source) + len(translation) for source, translation in window)
    return total_chars // 4


def translate_project(
    project_toml: Path,
    *,
    cwd: Path | None = None,
    retry_failed: bool = False,
    dry_run: bool = False,
    first_n: int | None = None,
    provider: LLMProvider | None = None,
    provider_override: dict[str, Any] | None = None,
    progress_callback: ProgressCallback | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> TranslationRunSummary:
    """Translate selected project segments through the configured provider.

    Args:
        project_toml: Weaver project file.
        cwd: Working directory used to resolve relative project paths.
        retry_failed: Select failed segments instead of pending segments.
        dry_run: When True, count selected segments and estimate input tokens
            without contacting the provider or mutating the database. Returned
            `input_tokens` is an estimate (1 token ≈ 4 source characters);
            `translated_segments` is always 0.
        provider: Optional provider injection for tests.
        provider_override: Optional dict merged onto the configured `[provider]`
            section (e.g. `{"type": "gemini", "model": "gemini-1.5-flash"}`) so
            a single run can target a different provider/model without editing
            project.toml. Ignored when `provider` is supplied directly.
        first_n: When set, translate only the first N selected segments. The
            remaining segments stay in their current status. Composes with
            ``retry_failed`` and ``dry_run``.
        progress_callback: Optional callback invoked after each selected segment
            with `(index, total, segment, translated, input_tokens,
            output_tokens)`. In dry-run mode the callback receives
            `translated=False` and the per-segment estimated input tokens.
        should_cancel: Optional predicate checked before each segment. When it
            returns True the loop stops cleanly, leaving already-translated
            segments committed and the rest in their prior status (cooperative
            cancel, ADR `0019`). CLI passes None (no behavior change); the web
            cockpit passes the JobManager cancel flag.

    Returns:
        TranslationRunSummary with current database counts and token totals.
    """

    base_dir = cwd or Path.cwd()
    data = load_project_config(project_toml)
    project_config = data["project"]
    provider_config = _merge_provider_config(data["provider"], provider_override)
    translation_config = data["translation"]
    db_path = _resolve_path(str(project_config["database_path"]), base_dir, project_toml.parent)
    source_path = _resolve_path(str(project_config["source_file"]), base_dir, project_toml.parent)

    document = read_source(source_path)
    block_by_id = _index_blocks(document)

    if dry_run:
        return _dry_run_summary(
            db_path=db_path,
            block_by_id=block_by_id,
            retry_failed=retry_failed,
            first_n=first_n,
            progress_callback=progress_callback,
        )

    active_provider = build_provider(provider_config) if provider is None else provider
    status = active_provider.healthcheck()
    if not status.healthy:
        detail = status.message or "no detail returned"
        raise ProviderUnavailable(
            f"Provider {active_provider.name} is unavailable: {detail}. "
            "Likely cause: API key missing/invalid, network unreachable, or "
            "local Ollama not running. "
            "Next command: run `weaver inspect --healthcheck <project.toml>`."
        )
    provider_model = str(provider_config["model"])
    honorific_policy = str(translation_config.get("honorifics", "preserve"))
    if honorific_policy not in VALID_HONORIFIC_POLICIES:
        valid = ", ".join(sorted(VALID_HONORIFIC_POLICIES))
        raise ConfigError(
            f"Invalid honorifics value `{honorific_policy}`. "
            f"Likely cause: project.toml [translation] honorifics must be one of: {valid}. "
            "Next command: edit project.toml and correct the value."
        )

    translated_count = 0
    input_tokens = 0
    output_tokens = 0

    with closing(connect_database(db_path)) as connection:
        project = _load_single_project(connection)
        raise_on_glossary_conflicts(connection, project_id=project.id)
        volume_id = _source_volume_id(connection, project_id=project.id, source_path=source_path)
        with transaction(connection):
            sync_document_segments(
                connection, project_id=project.id, volume_id=volume_id, document=document
            )

        glossary_terms = list_glossary_terms(connection, project_id=project.id)
        characters = load_character_contexts(connection, project_id=project.id)
        selected = list_segments_for_translation(
            connection, project_id=project.id, retry_failed=retry_failed
        )
        if first_n is not None:
            selected = selected[:first_n]
        total_selected = len(selected)

        for index, segment in enumerate(selected, start=1):
            if should_cancel is not None and should_cancel():
                break
            block = block_by_id.get(segment.id)
            if block is None:
                raise ConfigError(
                    f"Segment `{segment.id}` is missing from the current source EPUB. "
                    "Likely cause: project state and source file are out of sync. "
                    "Next command: rerun `weaver init <input.epub>` for this source."
                )

            translated, response_input_tokens, response_output_tokens = translate_one_segment(
                connection=connection,
                segment=segment,
                source_text=block.source_text,
                normalized_source_text=block.normalized_source_text,
                project=project,
                glossary_terms=glossary_terms,
                honorific_policy=honorific_policy,
                provider=active_provider,
                provider_model=provider_model,
                characters=characters,
            )
            if translated:
                translated_count += 1
                input_tokens += response_input_tokens or 0
                output_tokens += response_output_tokens or 0
            if progress_callback is not None:
                progress_callback(
                    index,
                    total_selected,
                    segment,
                    translated,
                    response_input_tokens,
                    response_output_tokens,
                )

        counts = _read_segment_counts(connection)

    return TranslationRunSummary(
        total_segments=counts["total"],
        selected_segments=total_selected,
        translated_segments=translated_count,
        failed_segments=counts["failed"],
        pending_segments=counts["pending"],
        stale_segments=counts["stale"],
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def _merge_provider_config(base: dict[str, Any], override: dict[str, Any] | None) -> dict[str, Any]:
    if not override:
        return base
    return {**base, **{k: v for k, v in override.items() if v is not None}}


def _dry_run_summary(
    *,
    db_path: Path,
    block_by_id: dict[str, BlockIR],
    retry_failed: bool,
    first_n: int | None,
    progress_callback: ProgressCallback | None,
) -> TranslationRunSummary:
    with closing(connect_database(db_path)) as connection:
        project = _load_single_project(connection)
        selected = list_segments_for_translation(
            connection, project_id=project.id, retry_failed=retry_failed
        )
        if first_n is not None:
            selected = selected[:first_n]
        counts = _read_segment_counts(connection)

    total_selected = len(selected)
    estimated_input_tokens = 0
    for index, segment in enumerate(selected, start=1):
        block = block_by_id.get(segment.id)
        source_chars = len(block.normalized_source_text) if block is not None else 0
        segment_estimate = int(source_chars * DRY_RUN_TOKENS_PER_CHAR)
        estimated_input_tokens += segment_estimate
        if progress_callback is not None:
            progress_callback(index, total_selected, segment, False, segment_estimate, None)

    return TranslationRunSummary(
        total_segments=counts["total"],
        selected_segments=total_selected,
        translated_segments=0,
        failed_segments=counts["failed"],
        pending_segments=counts["pending"],
        stale_segments=counts["stale"],
        input_tokens=estimated_input_tokens,
        output_tokens=0,
    )


def translate_one_segment(
    *,
    connection: sqlite3.Connection,
    segment: SegmentRecord,
    source_text: str,
    normalized_source_text: str,
    project: ProjectRecord,
    glossary_terms: Iterable[GlossaryTerm],
    honorific_policy: str,
    provider: LLMProvider,
    provider_model: str,
    characters: Iterable[CharacterContext] = (),
) -> tuple[bool, int | None, int | None]:
    """Translate one segment in a single transaction.

    Sets the segment to ``in_progress``, assembles its context (rolling window +
    filtered glossary), calls the provider, and records the result: on success a
    new translation attempt plus status ``translated``; on ``ProviderError`` the
    status becomes ``failed`` and no attempt is recorded. Source text is never
    mutated.

    Args:
        connection: Open writable SQLite connection.
        segment: Stored segment row being translated.
        source_text: Raw source text handed to the provider.
        normalized_source_text: Normalized source text for glossary matching and
            the provider request.
        project: Owning project (supplies source/target languages).
        glossary_terms: Approved glossary terms for the project.
        honorific_policy: One of `preserve` | `localize` | `hybrid`.
        provider: Built, healthchecked provider.
        provider_model: Model name recorded with the attempt.

    Returns:
        ``(translated, input_tokens, output_tokens)``. Tokens are None on failure
        or when the provider does not report usage.
    """

    with transaction(connection):
        update_segment_status(connection, segment_id=segment.id, status="in_progress")
        previous_segments = list_previous_translated_segments(
            connection,
            chapter_id=segment.chapter_id,
            before_block_order=segment.block_order,
            limit=MAX_CONTEXT_SEGMENTS,
        )
        context = build_context(
            normalized_source_text=normalized_source_text,
            glossary_terms=glossary_terms,
            previous_segments=previous_segments,
            honorific_policy=honorific_policy,
            characters=characters,
        )
        request = TranslationRequest(
            segment_id=segment.id,
            source_text=source_text,
            normalized_source_text=normalized_source_text,
            source_language=project.source_lang,
            target_language=project.target_lang,
            context=context,
            provider_model=provider_model,
        )
        try:
            response = provider.translate(request)
        except ProviderError:
            update_segment_status(connection, segment_id=segment.id, status="failed")
            return False, None, None

        record_translation(
            connection,
            segment_id=segment.id,
            text=response.translation,
            source_hash=segment.source_hash,
            provider=provider.name,
            model=provider_model,
            raw_response=response.raw_response,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
        )
        update_segment_status(connection, segment_id=segment.id, status="translated")
        return True, response.input_tokens, response.output_tokens


def _load_single_project(connection: sqlite3.Connection) -> ProjectRecord:
    row = connection.execute("SELECT id FROM projects ORDER BY id LIMIT 1").fetchone()
    if row is None:
        raise ConfigError(
            "Project database has no project row. "
            "Likely cause: database was not initialized by `weaver init`. "
            "Next command: run `weaver init <input.epub>`."
        )
    return get_project(connection, int(row["id"]))


def _source_volume_id(connection: sqlite3.Connection, *, project_id: int, source_path: Path) -> int:
    """Resolve the volume the translate source belongs to.

    Translate re-reads the project's single ``source_file`` and re-syncs it; that
    file maps to one volume. Match by source path, falling back to the first
    volume (legacy single-source projects always have one after migration).
    """

    volumes = list_volumes(connection, project_id)
    if not volumes:
        raise ConfigError(
            "Project has no volume to translate. "
            "Likely cause: database predates the volume model and was not migrated. "
            "Next command: run `weaver inspect <project.toml>` to migrate, then retry."
        )
    target = str(source_path)
    return next((volume.id for volume in volumes if volume.source_path == target), volumes[0].id)


def _index_blocks(document: DocumentIR) -> dict[str, BlockIR]:
    return {block.id: block for chapter in document.chapters for block in chapter.blocks}


def _read_segment_counts(connection: sqlite3.Connection) -> dict[str, int]:
    status_counts = {
        str(row["status"]): int(row["count"])
        for row in connection.execute(
            "SELECT status, COUNT(*) AS count FROM segments GROUP BY status"
        ).fetchall()
    }
    total = sum(status_counts.values())
    return {
        "total": total,
        "pending": status_counts.get("pending", 0),
        "failed": status_counts.get("failed", 0),
        "stale": status_counts.get("stale", 0),
    }


def _resolve_path(path_value: str, cwd: Path, project_toml_dir: Path) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    cwd_path = cwd / path
    if cwd_path.exists():
        return cwd_path
    return project_toml_dir / path
