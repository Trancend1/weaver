"""Volume-aware export of a Novel/Volume/Chapter project to EPUB (Sprint 8A).

Mirrors the batch-translation pattern (:mod:`weaver.services.batch_translate`): a
read-only :func:`prepare_export` validates scope/target and resolves an immutable
:class:`ExportPlan`; :func:`run_export` renders one artifact per volume and
returns an :class:`ExportResult`. Convenience entry points :func:`export_novel` /
:func:`export_volume` / :func:`export_chapter` combine the two steps.

Each volume is exported independently to its own EPUB (per-volume artifact; no
cross-EPUB merge):

- EPUB-sourced volumes reuse the write-back renderer
  (:func:`weaver.renderers.epub.render_translated_epub`), re-reading the source
  EPUB to recover its original markup and assets.
- TXT/HTML-sourced volumes are synthesized from the persisted chapter/segment
  content (:func:`weaver.renderers.epub_synthesis.synthesize_epub`); their source
  files are never re-read.

Selection rule (the "publishable" translation): a segment contributes its latest
translation only when its status is ``translated`` / ``manual`` and that attempt's
``source_hash`` matches the segment. Every other segment falls back to its source
text and is counted in :class:`FallbackByStatus`. Export never blocks on
incomplete translation, never leaves a block blank, and never silently drops
content. It is read-only: it writes no translations and calls no provider.

Framework-agnostic: no web/CLI/job types here (ADR 002/004).
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from weaver.core.ir import scope_document_to_volume
from weaver.errors import ChapterNotFoundError, ExportError, VolumeNotFoundError
from weaver.readers import read_epub
from weaver.renderers.docx import render_docx
from weaver.renderers.epub import render_translated_epub
from weaver.renderers.epub_synthesis import synthesize_epub
from weaver.renderers.html import render_html
from weaver.renderers.rendered_document import RenderChapter
from weaver.renderers.txt import render_txt
from weaver.services.epub_export_fidelity import (
    EpubExportFidelityReport,
    compare_epub_export_fidelity,
)
from weaver.services.export_bundle import bundle_filename, write_export_bundle
from weaver.services.project_paths import resolve_database_path, resolve_output_dir
from weaver.services.workspace_translate import load_single_project
from weaver.storage.db import connect_readonly_database
from weaver.storage.projects import ProjectRecord
from weaver.storage.segments import (
    get_chapter,
    list_chapter_ids_for_volume,
    list_chapter_segments,
)
from weaver.storage.translations import ExportSegmentState, list_export_segment_states
from weaver.storage.volumes import VolumeRecord, list_volumes

logger = logging.getLogger(__name__)

ExportTarget = Literal["epub", "txt", "html", "docx"]
# EPUB (8A) + TXT/HTML (8C) + DOCX (Phase D). DOCX is synthesized from resolved
# chapters (no write-back), like TXT/HTML.
EXPORT_TARGETS = frozenset({"epub", "txt", "html", "docx"})
EXPORT_SCOPES = frozenset({"novel", "volume", "chapter"})

_PUBLISHABLE_STATUSES = frozenset({"translated", "manual"})


@dataclass(frozen=True)
class FallbackByStatus:
    """Per-status counts of segments that fell back to source text on export.

    ``untranslated`` covers segments whose status is ``translated`` / ``manual``
    but whose latest attempt is missing or hash-mismatched (no publishable text).
    """

    pending: int = 0
    in_progress: int = 0
    failed: int = 0
    stale: int = 0
    skipped: int = 0
    untranslated: int = 0


@dataclass(frozen=True)
class ExportArtifact:
    """One exported file (one volume)."""

    volume_id: int
    volume_title: str
    source_format: str
    output_path: Path
    chapters_exported: int
    translated_segments: int
    fallback_segments: int
    fallback_by_status: FallbackByStatus


@dataclass(frozen=True)
class ExportResult:
    """Outcome of running an :class:`ExportPlan`."""

    target: str
    scope: str
    scope_id: str | None
    output_dir: Path
    volumes_total: int
    volumes_exported: int
    artifacts: tuple[ExportArtifact, ...]
    chapters_exported: int
    translated_segments: int
    fallback_segments: int
    generated_at: str
    cancelled: bool = False
    bundle_path: Path | None = None
    fidelity_reports: tuple[EpubExportFidelityReport, ...] = ()


@dataclass(frozen=True)
class ExportProgressSnapshot:
    """Self-describing live snapshot of a running export (for polling/SSE)."""

    target: str
    scope: str
    scope_id: str | None
    volumes_total: int
    volumes_done: int
    current_volume_id: int | None
    current_volume_title: str | None
    translated_segments: int
    fallback_segments: int


ExportProgressCallback = Callable[[ExportProgressSnapshot], None]


@dataclass(frozen=True)
class ExportVolumePlan:
    """One volume's planned export unit."""

    volume_id: int
    volume_title: str
    source_format: str
    source_path: Path
    chapter_ids: tuple[str, ...]
    output_path: Path


@dataclass(frozen=True)
class ExportPlan:
    """A validated, ready-to-run export across one or more volumes."""

    target: str
    scope: str
    scope_id: str | None
    project: ProjectRecord
    db_path: Path
    output_dir: Path
    volume_plans: tuple[ExportVolumePlan, ...]
    volumes_total: int
    chapters_total: int
    bundle: bool = False


def prepare_export(
    project_toml: Path,
    *,
    scope: str,
    target_id: str | None = None,
    target: str = "epub",
    bundle: bool = False,
    cwd: Path | None = None,
) -> ExportPlan:
    """Validate and plan an export for a novel, volume, or chapter.

    Args:
        project_toml: Path to the project's ``project.toml``.
        scope: ``"novel"``, ``"volume"``, or ``"chapter"``.
        target_id: Volume id (``volume`` scope) or chapter id (``chapter`` scope).
            Ignored for ``novel``.
        target: Output format (``epub`` | ``txt`` | ``html`` | ``docx``).
        bundle: When True, after rendering, package the per-volume artifacts into a
            single ``output/<target>/bundle-<target>.zip``.
        cwd: Working directory used to resolve project-relative paths.

    Returns:
        An immutable :class:`ExportPlan`. An empty scope (a novel/volume with no
        chapters) is valid and yields a plan with zero chapters.

    Raises:
        ValueError: If ``scope`` or ``target`` is unknown, or a ``volume`` /
            ``chapter`` scope is missing its ``target_id``.
        ChapterNotFoundError: If a ``chapter`` scope target does not exist.
        VolumeNotFoundError: If a ``volume`` scope target does not exist.
        ConfigError: If the database has no project row.
        EpubWriteError: If two planned artifacts would resolve to the same path.
    """

    if scope not in EXPORT_SCOPES:
        valid = ", ".join(sorted(EXPORT_SCOPES))
        raise ValueError(
            f"Unknown export scope `{scope}`. "
            f"Likely cause: the request scope must be one of: {valid}. "
            "Next command: resend with a valid `scope`."
        )
    if target not in EXPORT_TARGETS:
        valid = ", ".join(sorted(EXPORT_TARGETS))
        raise ValueError(
            f"Unsupported export target `{target}`. "
            f"Likely cause: only these targets are implemented: {valid}. "
            "Next command: resend with a supported `target`."
        )
    if scope in {"volume", "chapter"} and not target_id:
        raise ValueError(
            f"Export scope `{scope}` requires a target id. "
            f"Likely cause: the {scope} id was not supplied. "
            f"Next command: resend with the {scope} id."
        )

    db_path = resolve_database_path(project_toml, cwd=cwd)
    output_dir = resolve_output_dir(project_toml, cwd=cwd)
    with closing(connect_readonly_database(db_path)) as connection:
        project = load_single_project(connection)
        volumes = list_volumes(connection, project.id)
        index_by_id = {volume.id: index for index, volume in enumerate(volumes, start=1)}
        selected = _resolve_scope_volumes(
            connection, scope=scope, target_id=target_id, project=project, volumes=volumes
        )
        volume_plans = tuple(
            _build_volume_plan(
                connection,
                scope=scope,
                target_id=target_id,
                target=target,
                volume=volume,
                index=index_by_id[volume.id],
                output_dir=output_dir,
            )
            for volume in selected
        )

    _assert_unique_outputs(volume_plans)
    chapters_total = sum(len(plan.chapter_ids) for plan in volume_plans)
    return ExportPlan(
        target=target,
        scope=scope,
        scope_id=target_id if scope != "novel" else None,
        project=project,
        db_path=db_path,
        output_dir=output_dir,
        volume_plans=volume_plans,
        volumes_total=len(volume_plans),
        chapters_total=chapters_total,
        bundle=bundle,
    )


def run_export(
    plan: ExportPlan,
    *,
    should_cancel: Callable[[], bool] | None = None,
    progress_callback: ExportProgressCallback | None = None,
) -> ExportResult:
    """Render every planned volume to its EPUB and aggregate the result.

    Args:
        plan: An :class:`ExportPlan` from :func:`prepare_export`.
        should_cancel: Optional predicate checked before each volume; when it
            returns True the export stops cleanly, leaving already-written
            artifacts in place.
        progress_callback: Optional callback invoked with an
            :class:`ExportProgressSnapshot` after each volume is rendered.

    Returns:
        An :class:`ExportResult` with one artifact per volume and aggregate
        counts. Read-only on the database.
    """

    artifacts: list[ExportArtifact] = []
    fidelity_reports: list[EpubExportFidelityReport] = []
    translated_segments = 0
    fallback_segments = 0
    chapters_exported = 0
    cancelled = False

    with closing(connect_readonly_database(plan.db_path)) as connection:
        for volume_plan in plan.volume_plans:
            if should_cancel is not None and should_cancel():
                cancelled = True
                break
            artifact = _render_volume(
                connection, volume_plan, project=plan.project, target=plan.target
            )
            artifacts.append(artifact)
            if plan.target == "epub" and volume_plan.source_format == "epub":
                try:
                    report = compare_epub_export_fidelity(
                        source_epub=volume_plan.source_path,
                        exported_epub=artifact.output_path,
                    )
                    fidelity_reports.append(report)
                except Exception:  # noqa: BLE001 - non-fatal; fidelity does not block export
                    logger.warning(
                        "Fidelity check failed for volume %s",
                        volume_plan.volume_id,
                        exc_info=True,
                    )
            translated_segments += artifact.translated_segments
            fallback_segments += artifact.fallback_segments
            chapters_exported += artifact.chapters_exported
            if progress_callback is not None:
                progress_callback(
                    ExportProgressSnapshot(
                        target=plan.target,
                        scope=plan.scope,
                        scope_id=plan.scope_id,
                        volumes_total=plan.volumes_total,
                        volumes_done=len(artifacts),
                        current_volume_id=artifact.volume_id,
                        current_volume_title=artifact.volume_title,
                        translated_segments=translated_segments,
                        fallback_segments=fallback_segments,
                    )
                )

    # Optional ZIP bundle of the per-volume artifacts. Skipped on cancel (partial
    # set) and when nothing was written.
    bundle_path: Path | None = None
    if plan.bundle and artifacts and not cancelled:
        bundle_path = write_export_bundle(
            output_path=plan.output_dir / plan.target / bundle_filename(plan.target),
            artifact_paths=[artifact.output_path for artifact in artifacts],
        )

    return ExportResult(
        target=plan.target,
        scope=plan.scope,
        scope_id=plan.scope_id,
        output_dir=plan.output_dir,
        volumes_total=plan.volumes_total,
        volumes_exported=len(artifacts),
        artifacts=tuple(artifacts),
        chapters_exported=chapters_exported,
        translated_segments=translated_segments,
        fallback_segments=fallback_segments,
        generated_at=datetime.now(UTC).isoformat(),
        cancelled=cancelled,
        bundle_path=bundle_path,
        fidelity_reports=tuple(fidelity_reports),
    )


def export_novel(
    project_toml: Path,
    *,
    target: str = "epub",
    bundle: bool = False,
    cwd: Path | None = None,
) -> ExportResult:
    """Export every volume of the novel to its own artifact (one per volume).

    When ``bundle`` is True, the per-volume artifacts are also packaged into a
    single ``output/<target>/bundle-<target>.zip``.
    """

    return run_export(
        prepare_export(project_toml, scope="novel", target=target, bundle=bundle, cwd=cwd)
    )


def export_volume(
    project_toml: Path, volume_id: int, *, target: str = "epub", cwd: Path | None = None
) -> ExportResult:
    """Export one volume to its own EPUB."""

    return run_export(
        prepare_export(
            project_toml, scope="volume", target_id=str(volume_id), target=target, cwd=cwd
        )
    )


def export_chapter(
    project_toml: Path, chapter_id: str, *, target: str = "epub", cwd: Path | None = None
) -> ExportResult:
    """Export one chapter to its own EPUB."""

    return run_export(
        prepare_export(project_toml, scope="chapter", target_id=chapter_id, target=target, cwd=cwd)
    )


def _resolve_scope_volumes(
    connection: sqlite3.Connection,
    *,
    scope: str,
    target_id: str | None,
    project: ProjectRecord,
    volumes: list[VolumeRecord],
) -> list[VolumeRecord]:
    """Resolve an export scope to the ordered list of volumes to render."""

    if scope == "novel":
        return volumes

    by_id = {volume.id: volume for volume in volumes}
    if scope == "volume":
        assert target_id is not None  # guarded by caller
        volume = by_id.get(_parse_volume_id(target_id))
        if volume is None:
            raise VolumeNotFoundError(
                f"Volume '{target_id}' was not found in project '{project.name}'. "
                "Likely cause: the volume id is wrong or was removed. "
                "Next command: open the project tree (GET /projects/<name>/tree) "
                "to list volume ids."
            )
        return [volume]

    assert target_id is not None  # guarded by caller (chapter scope)
    chapter = get_chapter(connection, target_id)
    if chapter is None:
        raise ChapterNotFoundError(
            f"Chapter '{target_id}' was not found in project '{project.name}'. "
            "Likely cause: the chapter id is wrong or its volume was removed. "
            "Next command: open the project tree (GET /projects/<name>/tree) "
            "to list chapter ids."
        )
    volume = by_id.get(chapter.volume_id)
    if volume is None:
        raise VolumeNotFoundError(
            f"Volume '{chapter.volume_id}' for chapter '{target_id}' was not found. "
            "Likely cause: the chapter's volume was removed. "
            "Next command: re-import the volume or pick another chapter."
        )
    return [volume]


def _build_volume_plan(
    connection: sqlite3.Connection,
    *,
    scope: str,
    target_id: str | None,
    target: str,
    volume: VolumeRecord,
    index: int,
    output_dir: Path,
) -> ExportVolumePlan:
    """Build one volume's export plan, including its collision-safe output path.

    Artifacts go to ``<output_dir>/<target>/`` with the volume's reading-order
    ``index`` (its position among the project's volumes, not its raw
    ``volume_order`` which is not guaranteed unique) plus the unique ``volume_id``
    so duplicate orders cannot collide. The file extension matches ``target``.
    """

    target_dir = output_dir / target
    if scope == "chapter":
        assert target_id is not None
        chapter = get_chapter(connection, target_id)
        assert chapter is not None  # validated in _resolve_scope_volumes
        chapter_ids: tuple[str, ...] = (target_id,)
        filename = f"chapter-{chapter.spine_order + 1:03d}-id{volume.id}.{target}"
    else:
        chapter_ids = tuple(list_chapter_ids_for_volume(connection, volume.id))
        filename = f"volume-{index:02d}-id{volume.id}.{target}"
    return ExportVolumePlan(
        volume_id=volume.id,
        volume_title=volume.title,
        source_format=volume.source_format,
        source_path=Path(volume.source_path),
        chapter_ids=chapter_ids,
        output_path=target_dir / filename,
    )


def _render_volume(
    connection: sqlite3.Connection,
    plan: ExportVolumePlan,
    *,
    project: ProjectRecord,
    target: str,
) -> ExportArtifact:
    """Render one volume to ``target`` and report translated/fallback counts."""

    states = list_export_segment_states(connection, chapter_ids=plan.chapter_ids)
    publishable: dict[str, str] = {}
    fallback_states: list[ExportSegmentState] = []
    for state in states:
        if state.publishable_text is not None:
            publishable[state.id] = state.publishable_text
        else:
            fallback_states.append(state)

    if target == "epub":
        if plan.source_format == "epub":
            # Scope the re-read source ids to this volume so block ids match the
            # volume-scoped stored segment ids in `publishable` (Stage 11B-1.5).
            document = scope_document_to_volume(read_epub(plan.source_path), plan.volume_id)
            render_translated_epub(
                source_epub_path=plan.source_path,
                output_path=plan.output_path,
                document=document,
                translations_by_segment_id=publishable,
            )
        else:
            synthesize_epub(
                output_path=plan.output_path,
                title=plan.volume_title,
                language=project.target_lang,
                author=None,
                identifier=f"{project.name}-volume-{plan.volume_id}",
                chapters=_resolved_chapters(connection, plan, publishable=publishable),
            )
    elif target == "txt":
        render_txt(
            output_path=plan.output_path,
            title=plan.volume_title,
            chapters=_resolved_chapters(connection, plan, publishable=publishable),
        )
    elif target == "docx":
        render_docx(
            output_path=plan.output_path,
            title=plan.volume_title,
            language=project.target_lang,
            chapters=_resolved_chapters(connection, plan, publishable=publishable),
        )
    else:  # html
        render_html(
            output_path=plan.output_path,
            title=plan.volume_title,
            language=project.target_lang,
            chapters=_resolved_chapters(connection, plan, publishable=publishable),
        )

    return ExportArtifact(
        volume_id=plan.volume_id,
        volume_title=plan.volume_title,
        source_format=plan.source_format,
        output_path=plan.output_path,
        chapters_exported=len(plan.chapter_ids),
        translated_segments=len(publishable),
        fallback_segments=len(fallback_states),
        fallback_by_status=_fallback_breakdown(fallback_states),
    )


def _resolved_chapters(
    connection: sqlite3.Connection,
    plan: ExportVolumePlan,
    *,
    publishable: dict[str, str],
) -> list[RenderChapter]:
    """Build resolved render input from the DB (no source-file re-read).

    Each block is the segment's publishable translation when available, otherwise
    its source text (fallback). Shared by the EPUB-synthesis, TXT, and HTML paths.
    """

    chapters: list[RenderChapter] = []
    for chapter_id in plan.chapter_ids:
        chapter = get_chapter(connection, chapter_id)
        segments = list_chapter_segments(connection, chapter_id=chapter_id)
        blocks = tuple(
            (segment.kind, publishable.get(segment.id, segment.source_text)) for segment in segments
        )
        chapters.append(
            RenderChapter(title=chapter.title if chapter is not None else None, blocks=blocks)
        )
    return chapters


def _fallback_breakdown(fallback_states: list[ExportSegmentState]) -> FallbackByStatus:
    counts = {
        "pending": 0,
        "in_progress": 0,
        "failed": 0,
        "stale": 0,
        "skipped": 0,
        "untranslated": 0,
    }
    for state in fallback_states:
        if state.status in _PUBLISHABLE_STATUSES or state.status not in counts:
            # translated/manual without a hash-matching latest attempt, or any
            # unexpected status, is reported as untranslated.
            counts["untranslated"] += 1
        else:
            counts[state.status] += 1
    return FallbackByStatus(
        pending=counts["pending"],
        in_progress=counts["in_progress"],
        failed=counts["failed"],
        stale=counts["stale"],
        skipped=counts["skipped"],
        untranslated=counts["untranslated"],
    )


def _assert_unique_outputs(volume_plans: tuple[ExportVolumePlan, ...]) -> None:
    paths = [plan.output_path for plan in volume_plans]
    if len(set(paths)) != len(paths):
        duplicates = sorted({str(path) for path in paths if paths.count(path) > 1})
        raise ExportError(
            f"Export would write two volumes to the same file: {', '.join(duplicates)}. "
            "Likely cause: volume ids collided in output naming. "
            "Next command: report this as a bug; export was aborted to avoid overwrite."
        )


def _parse_volume_id(target_id: str) -> int:
    try:
        return int(target_id)
    except (TypeError, ValueError) as exc:
        raise VolumeNotFoundError(
            f"Volume id '{target_id}' is not a valid integer. "
            "Likely cause: the volume id in the request is malformed. "
            "Next command: open the project tree (GET /projects/<name>/tree) "
            "to list volume ids."
        ) from exc
