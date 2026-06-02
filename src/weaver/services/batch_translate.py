"""Batch (chapter / volume / novel) AI translation for the cockpit (Sprint 7A).

Builds on the per-chapter pipeline (:mod:`weaver.services.workspace_translate`)
without re-implementing translation. A batch is planned once — provider built and
healthchecked a single time, glossary + characters loaded once — then run chapter
by chapter, each chapter delegating to the existing :func:`run_translation`.

Two steps mirror the chapter path so a web handler can fail fast before
backgrounding the slow work:

- :func:`prepare_batch_translation` (synchronous, read-only): resolves the scope
  to an ordered list of chapters, validates config + provider, and returns an
  immutable :class:`BatchPlan` (one :class:`TranslationPlan` per chapter, all
  sharing the single provider/glossary/characters).
- :func:`run_batch_translation` (writable, background-thread friendly): runs each
  chapter plan, aggregating counts and honouring a cooperative cancel between
  segments (inside :func:`run_translation`) and between chapters.

Framework-agnostic: no web/job/CLI types here (ADR 002/004).

Aggregate counter semantics (kept unambiguous):
    ``segments_total`` is the number of segments the batch will *attempt*
    (eligible under ``mode``) across all chapters. ``translated`` counts every
    successful attempt and *includes* ``reused_from_memory`` as a subset (a TM
    hit is a success). So on full completion ``translated + failed ==
    segments_total`` and ``reused_from_memory <= translated``. ``skipped`` counts
    mode-excluded segments and is reported separately (not part of
    ``segments_total``).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from weaver.core.config import load_project_config
from weaver.errors import ChapterNotFoundError, VolumeNotFoundError
from weaver.services.project_paths import resolve_database_path
from weaver.services.workspace_translate import (
    TRANSLATE_MODES,
    ChapterTranslationResult,
    TranslationPlan,
    build_healthy_provider,
    load_single_project,
    load_translation_context,
    run_translation,
    select_chapter_targets,
    validate_provider_config,
)
from weaver.storage.db import connect_readonly_database
from weaver.storage.projects import ProjectRecord
from weaver.storage.segments import (
    SegmentRecord,
    chapter_exists,
    list_chapter_ids_for_project,
    list_chapter_ids_for_volume,
)
from weaver.storage.volumes import get_volume

# Batch scopes. ``chapter``/``volume`` need a target id; ``novel`` is the whole
# project (one project per database).
BATCH_SCOPES = frozenset({"chapter", "volume", "novel"})


@dataclass(frozen=True)
class BatchPlan:
    """A validated, ready-to-run batch translation across one or more chapters."""

    scope: str  # "chapter" | "volume" | "novel"
    scope_id: str | None
    project: ProjectRecord
    db_path: Path
    mode: str
    provider_name: str
    provider_model: str
    chapter_plans: tuple[TranslationPlan, ...]
    chapters_total: int
    segments_total: int


@dataclass(frozen=True)
class BatchChapterOutcome:
    """Per-chapter result inside a finished batch."""

    chapter_id: str
    selected: int
    translated: int
    reused_from_memory: int
    failed: int
    skipped: int
    input_tokens: int
    output_tokens: int
    cancelled: bool


@dataclass(frozen=True)
class BatchProgressSnapshot:
    """Self-describing live snapshot of a running batch (for polling/SSE)."""

    scope: str
    scope_id: str | None
    mode: str
    provider: str
    model: str
    chapters_total: int
    chapters_done: int
    current_chapter_id: str | None
    segments_total: int
    segments_done: int
    translated: int
    reused_from_memory: int
    skipped: int
    failed: int


@dataclass(frozen=True)
class BatchTranslationResult:
    """Outcome of running a :class:`BatchPlan`."""

    scope: str
    scope_id: str | None
    mode: str
    provider: str
    model: str
    chapters_total: int
    chapters_done: int
    segments_total: int
    translated: int
    reused_from_memory: int
    skipped: int
    failed: int
    input_tokens: int
    output_tokens: int
    cancelled: bool
    started_at: str
    finished_at: str
    duration_seconds: float
    chapters: tuple[BatchChapterOutcome, ...] = field(default_factory=tuple)


BatchProgressCallback = Callable[[BatchProgressSnapshot], None]


def prepare_batch_translation(
    project_toml: Path,
    *,
    scope: str,
    target_id: str | None = None,
    mode: str = "skip_existing",
    cwd: Path | None = None,
    provider_override: dict[str, Any] | None = None,
) -> BatchPlan:
    """Validate and plan a batch translation for a chapter, volume, or novel.

    Resolves ``scope`` to an ordered list of chapters, validates config, builds
    and healthchecks the provider exactly once, loads glossary + characters once,
    and builds one :class:`TranslationPlan` per chapter (all sharing the single
    provider/glossary/characters).

    Args:
        project_toml: Path to the project's ``project.toml``.
        scope: ``"chapter"``, ``"volume"``, or ``"novel"``.
        target_id: Chapter id (``chapter`` scope) or volume id (``volume``
            scope). Ignored for ``novel``.
        mode: One of :data:`TRANSLATE_MODES`; governs overwrite/skip behavior
            per chapter (``manual`` is protected unless ``force_selected``).
        cwd: Working directory used to resolve project-relative paths.
        provider_override: Optional ``{"type": ..., "model": ...}`` merged onto
            the configured ``[provider]`` block for this run only.

    Returns:
        An immutable :class:`BatchPlan`. An empty scope (volume/novel with no
        chapters, or no eligible segments) is valid and yields a plan with zero
        chapters/segments — not an error.

    Raises:
        ValueError: If ``scope`` or ``mode`` is unknown, or a ``chapter``/
            ``volume`` scope is missing its ``target_id``.
        ChapterNotFoundError: If a ``chapter`` scope target does not exist.
        VolumeNotFoundError: If a ``volume`` scope target does not exist.
        ConfigError: If the honorific policy or provider model is invalid.
        GlossaryConflictError: If approved glossary terms conflict.
        ProviderUnavailable: If the configured/overridden provider is unhealthy.
    """

    if scope not in BATCH_SCOPES:
        valid = ", ".join(sorted(BATCH_SCOPES))
        raise ValueError(
            f"Unknown batch scope `{scope}`. "
            f"Likely cause: the request scope must be one of: {valid}. "
            "Next command: resend with a valid `scope`."
        )
    if mode not in TRANSLATE_MODES:
        valid = ", ".join(sorted(TRANSLATE_MODES))
        raise ValueError(
            f"Unknown translate mode `{mode}`. "
            f"Likely cause: the request mode must be one of: {valid}. "
            "Next command: resend with a valid `mode`."
        )
    if scope in {"chapter", "volume"} and not target_id:
        raise ValueError(
            f"Batch scope `{scope}` requires a target id. "
            f"Likely cause: the {scope} id was not supplied. "
            f"Next command: resend with the {scope} id."
        )

    data = load_project_config(project_toml)
    provider_config, provider_model, honorific_policy = validate_provider_config(
        data, provider_override
    )

    db_path = resolve_database_path(project_toml, cwd=cwd)
    # Collect per-chapter targets inside one read-only connection. Provider build
    # + healthcheck happens after, so scope errors (404) precede a 502.
    collected: list[tuple[str, tuple[str, ...], int]] = []
    with closing(connect_readonly_database(db_path)) as connection:
        project = load_single_project(connection)
        chapter_ids = _resolve_scope_chapter_ids(
            connection, scope=scope, target_id=target_id, project=project
        )
        glossary_terms, characters = load_translation_context(connection, project_id=project.id)
        for chapter_id in chapter_ids:
            targets, requested_count = select_chapter_targets(
                connection, chapter_id=chapter_id, mode=mode
            )
            collected.append(
                (chapter_id, tuple(segment.id for segment in targets), requested_count)
            )

    provider = build_healthy_provider(provider_config)
    use_translation_memory = mode == "skip_existing"
    chapter_plans = tuple(
        TranslationPlan(
            project_toml=project_toml,
            db_path=db_path,
            chapter_id=chapter_id,
            mode="chapter",
            project=project,
            provider=provider,
            provider_model=provider_model,
            honorific_policy=honorific_policy,
            glossary_terms=glossary_terms,
            characters=characters,
            target_segment_ids=target_segment_ids,
            requested_count=requested_count,
            use_translation_memory=use_translation_memory,
        )
        for chapter_id, target_segment_ids, requested_count in collected
    )
    segments_total = sum(len(plan.target_segment_ids) for plan in chapter_plans)

    return BatchPlan(
        scope=scope,
        scope_id=target_id if scope != "novel" else None,
        project=project,
        db_path=db_path,
        mode=mode,
        provider_name=provider.name,
        provider_model=provider_model,
        chapter_plans=chapter_plans,
        chapters_total=len(chapter_plans),
        segments_total=segments_total,
    )


def run_batch_translation(
    plan: BatchPlan,
    *,
    should_cancel: Callable[[], bool] | None = None,
    progress_callback: BatchProgressCallback | None = None,
) -> BatchTranslationResult:
    """Run a :class:`BatchPlan` chapter by chapter, aggregating progress.

    Cancellation is cooperative at two levels: checked before each chapter (here)
    and before each segment (inside :func:`run_translation`).

    Args:
        plan: A :class:`BatchPlan` from :func:`prepare_batch_translation`.
        should_cancel: Optional predicate; when it returns True the batch stops
            cleanly, leaving committed segments in place.
        progress_callback: Optional callback invoked with a
            :class:`BatchProgressSnapshot` after each attempted segment and after
            each chapter completes.

    Returns:
        A :class:`BatchTranslationResult` with aggregate counts, per-chapter
        outcomes, and timing.
    """

    started = datetime.now(UTC)
    chapters_done = 0
    segments_done = 0
    translated = 0
    failed = 0
    reused = 0
    skipped = 0
    input_tokens = 0
    output_tokens = 0
    cancelled = False
    current_chapter_id: str | None = None
    outcomes: list[BatchChapterOutcome] = []

    def snapshot() -> BatchProgressSnapshot:
        return BatchProgressSnapshot(
            scope=plan.scope,
            scope_id=plan.scope_id,
            mode=plan.mode,
            provider=plan.provider_name,
            model=plan.provider_model,
            chapters_total=plan.chapters_total,
            chapters_done=chapters_done,
            current_chapter_id=current_chapter_id,
            segments_total=plan.segments_total,
            segments_done=segments_done,
            translated=translated,
            reused_from_memory=reused,
            skipped=skipped,
            failed=failed,
        )

    def on_segment(
        index: int,
        total: int,
        segment: SegmentRecord,
        ok: bool,
        in_tokens: int | None,
        out_tokens: int | None,
    ) -> None:
        nonlocal segments_done, translated, failed
        segments_done += 1
        if ok:
            translated += 1
        else:
            failed += 1
        if progress_callback is not None:
            progress_callback(snapshot())

    for chapter_plan in plan.chapter_plans:
        if should_cancel is not None and should_cancel():
            cancelled = True
            break
        current_chapter_id = chapter_plan.chapter_id
        result = run_translation(
            chapter_plan,
            should_cancel=should_cancel,
            progress_callback=on_segment,
        )
        reused += result.reused_from_memory
        skipped += result.skipped
        input_tokens += result.input_tokens
        output_tokens += result.output_tokens
        chapters_done += 1
        outcomes.append(_outcome_from_result(result))
        if progress_callback is not None:
            progress_callback(snapshot())
        if result.cancelled:
            cancelled = True
            break

    finished = datetime.now(UTC)
    return BatchTranslationResult(
        scope=plan.scope,
        scope_id=plan.scope_id,
        mode=plan.mode,
        provider=plan.provider_name,
        model=plan.provider_model,
        chapters_total=plan.chapters_total,
        chapters_done=chapters_done,
        segments_total=plan.segments_total,
        translated=translated,
        reused_from_memory=reused,
        skipped=skipped,
        failed=failed,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cancelled=cancelled,
        started_at=started.isoformat(),
        finished_at=finished.isoformat(),
        duration_seconds=(finished - started).total_seconds(),
        chapters=tuple(outcomes),
    )


def _resolve_scope_chapter_ids(
    connection: sqlite3.Connection, *, scope: str, target_id: str | None, project: ProjectRecord
) -> list[str]:
    """Resolve a batch scope to an ordered list of chapter ids."""

    if scope == "chapter":
        assert target_id is not None  # guarded by caller
        if not chapter_exists(connection, target_id):
            raise ChapterNotFoundError(
                f"Chapter '{target_id}' was not found in project '{project.name}'. "
                "Likely cause: the chapter id is wrong or its volume was removed. "
                "Next command: open the project tree (GET /projects/<name>/tree) "
                "to list chapter ids."
            )
        return [target_id]

    if scope == "volume":
        assert target_id is not None  # guarded by caller
        volume_id = _parse_volume_id(target_id)
        try:
            volume = get_volume(connection, volume_id)
        except LookupError as exc:
            raise VolumeNotFoundError(
                f"Volume '{target_id}' was not found in project '{project.name}'. "
                "Likely cause: the volume id is wrong or was removed. "
                "Next command: open the project tree (GET /projects/<name>/tree) "
                "to list volume ids."
            ) from exc
        if volume.project_id != project.id:
            raise VolumeNotFoundError(
                f"Volume '{target_id}' does not belong to project '{project.name}'. "
                "Likely cause: the volume id is from another project. "
                "Next command: open the project tree (GET /projects/<name>/tree)."
            )
        return list_chapter_ids_for_volume(connection, volume_id)

    return list_chapter_ids_for_project(connection, project.id)


def _parse_volume_id(target_id: str) -> int:
    try:
        return int(target_id)
    except (TypeError, ValueError) as exc:
        raise VolumeNotFoundError(
            f"Volume id '{target_id}' is not a valid integer. "
            "Likely cause: the volume id in the request path is malformed. "
            "Next command: open the project tree (GET /projects/<name>/tree) "
            "to list volume ids."
        ) from exc


def _outcome_from_result(result: ChapterTranslationResult) -> BatchChapterOutcome:
    return BatchChapterOutcome(
        chapter_id=result.chapter_id,
        selected=result.selected,
        translated=result.translated,
        reused_from_memory=result.reused_from_memory,
        failed=result.failed,
        skipped=result.skipped,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        cancelled=result.cancelled,
    )
