"""Read-only translation QA service (ADR 008).

Scope-aware QA over the Novel/Volume/Chapter model: ``analyze_chapter`` /
``analyze_volume`` / ``analyze_novel`` open a **read-only** connection, run the
shared deterministic checks (:mod:`weaver.qa.checks` plus the Phase B rule
modules), and aggregate a :class:`~weaver.qa.report.QAReport`.

No mutation, no provider/LLM calls, no semantic/vector analysis. Per-segment
rule logic is reused from ``weaver.qa.checks`` — there is no parallel QA system.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from weaver.core.config import load_project_config
from weaver.core.segment import normalize_japanese_text
from weaver.errors import ChapterNotFoundError, ConfigError, VolumeNotFoundError
from weaver.providers.types import GlossaryTerm
from weaver.qa.checks import QAWarning, SegmentInput, run_all_checks
from weaver.qa.consistency_checks import (
    CharacterName,
    check_character_name_missing,
    check_untranslated_segment,
)
from weaver.qa.report import (
    QA_REPORT_SCHEMA_VERSION,
    QACategory,
    QAIssue,
    QAReport,
    QAScope,
    QAScopeSummary,
    badge_for,
    category_for,
)
from weaver.qa.scope_checks import (
    ScopeWarning,
    check_fallback_heavy,
    check_mixed_status,
    check_repeated_identical_translation,
)
from weaver.qa.thresholds import QAThresholds, load_qa_thresholds
from weaver.services.project_paths import resolve_database_path
from weaver.storage.characters import list_characters
from weaver.storage.db import connect_readonly_database
from weaver.storage.glossary import list_glossary_terms
from weaver.storage.segments import (
    chapter_exists,
    get_chapter,
    list_chapter_ids_for_project,
    list_chapter_ids_for_volume,
)
from weaver.storage.translations import list_export_segment_states
from weaver.storage.volumes import list_volumes


@dataclass(frozen=True)
class _ChapterResult:
    """Per-chapter analysis, aggregated into the wider report."""

    chapter_id: str
    volume_id: int
    title: str | None
    segment_count: int
    issues: tuple[QAIssue, ...]


def analyze_chapter(project_toml: Path, chapter_id: str, *, cwd: Path | None = None) -> QAReport:
    """Build a QA report for one chapter."""

    config = load_project_config(project_toml)
    project_name = str(config["project"]["name"])
    thresholds = load_qa_thresholds(config)
    db_path = resolve_database_path(project_toml, cwd=cwd)
    with closing(connect_readonly_database(db_path)) as connection:
        project_id = _single_project_id(connection)
        if not chapter_exists(connection, chapter_id):
            raise ChapterNotFoundError(
                f"Chapter {chapter_id!r} does not exist in project {project_name!r}. "
                "Likely cause: wrong chapter id or the volume was not imported. "
                "Next command: open the project tree (`weaver serve`) to find the chapter id."
            )
        glossary = list_glossary_terms(connection, project_id=project_id)
        characters = _character_names(connection, project_id)
        result = _chapter_result(
            connection, chapter_id, glossary=glossary, characters=characters, thresholds=thresholds
        )
    return _build_report(
        project_name=project_name,
        scope="chapter",
        scope_id=chapter_id,
        results=[result],
        include_chapter_summary=False,
        include_volume_summary=False,
        volume_titles={},
    )


def analyze_volume(project_toml: Path, volume_id: int, *, cwd: Path | None = None) -> QAReport:
    """Build a QA report for one volume (per-chapter roll-up included)."""

    config = load_project_config(project_toml)
    project_name = str(config["project"]["name"])
    thresholds = load_qa_thresholds(config)
    db_path = resolve_database_path(project_toml, cwd=cwd)
    with closing(connect_readonly_database(db_path)) as connection:
        project_id = _single_project_id(connection)
        volume = next((v for v in list_volumes(connection, project_id) if v.id == volume_id), None)
        if volume is None:
            raise VolumeNotFoundError(
                f"Volume {volume_id} does not exist in project {project_name!r}. "
                "Likely cause: wrong volume id or nothing imported yet. "
                "Next command: import a source with `weaver import <file>`."
            )
        glossary = list_glossary_terms(connection, project_id=project_id)
        characters = _character_names(connection, project_id)
        results = [
            _chapter_result(
                connection,
                chapter_id,
                glossary=glossary,
                characters=characters,
                thresholds=thresholds,
            )
            for chapter_id in list_chapter_ids_for_volume(connection, volume_id)
        ]
    return _build_report(
        project_name=project_name,
        scope="volume",
        scope_id=str(volume_id),
        results=results,
        include_chapter_summary=True,
        include_volume_summary=False,
        volume_titles={volume.id: volume.title},
    )


def analyze_novel(project_toml: Path, *, cwd: Path | None = None) -> QAReport:
    """Build a QA report for the whole novel (per-chapter and per-volume roll-ups)."""

    config = load_project_config(project_toml)
    project_name = str(config["project"]["name"])
    thresholds = load_qa_thresholds(config)
    db_path = resolve_database_path(project_toml, cwd=cwd)
    with closing(connect_readonly_database(db_path)) as connection:
        project_id = _single_project_id(connection)
        glossary = list_glossary_terms(connection, project_id=project_id)
        characters = _character_names(connection, project_id)
        volume_titles = {volume.id: volume.title for volume in list_volumes(connection, project_id)}
        results = [
            _chapter_result(
                connection,
                chapter_id,
                glossary=glossary,
                characters=characters,
                thresholds=thresholds,
            )
            for chapter_id in list_chapter_ids_for_project(connection, project_id)
        ]
    return _build_report(
        project_name=project_name,
        scope="novel",
        scope_id=project_name,
        results=results,
        include_chapter_summary=True,
        include_volume_summary=True,
        volume_titles=volume_titles,
    )


def _chapter_result(
    connection: sqlite3.Connection,
    chapter_id: str,
    *,
    glossary: Sequence[GlossaryTerm],
    characters: Sequence[CharacterName],
    thresholds: QAThresholds,
) -> _ChapterResult:
    chapter = get_chapter(connection, chapter_id)
    segments = _load_chapter_segment_inputs(connection, chapter_id)
    issues: list[QAIssue] = []
    for seg in segments:
        for warning in run_all_checks(seg, glossary):
            issues.append(_issue_from_segment(warning, chapter_id=chapter_id))
        untranslated = check_untranslated_segment(seg)
        if untranslated is not None:
            issues.append(_issue_from_segment(untranslated, chapter_id=chapter_id))
        for warning in check_character_name_missing(seg, characters):
            issues.append(_issue_from_segment(warning, chapter_id=chapter_id))

    for warning in check_repeated_identical_translation(
        segments, min_chars=thresholds.repeated_min_chars
    ):
        issues.append(_issue_from_segment(warning, chapter_id=chapter_id))
    mixed = check_mixed_status(segments)
    if mixed is not None:
        issues.append(_issue_from_scope(mixed, chapter_id=chapter_id))
    states = list_export_segment_states(connection, chapter_ids=[chapter_id])
    fallback_segments = sum(1 for state in states if state.publishable_text is None)
    fallback = check_fallback_heavy(
        total_segments=len(states),
        fallback_segments=fallback_segments,
        heavy_ratio=thresholds.fallback_heavy_ratio,
        min_segments=thresholds.fallback_heavy_min_segments,
    )
    if fallback is not None:
        issues.append(_issue_from_scope(fallback, chapter_id=chapter_id))

    return _ChapterResult(
        chapter_id=chapter_id,
        volume_id=chapter.volume_id if chapter is not None else 0,
        title=chapter.title if chapter is not None else None,
        segment_count=len(segments),
        issues=tuple(issues),
    )


def _build_report(
    *,
    project_name: str,
    scope: QAScope,
    scope_id: str,
    results: Sequence[_ChapterResult],
    include_chapter_summary: bool,
    include_volume_summary: bool,
    volume_titles: dict[int, str],
) -> QAReport:
    all_issues: list[QAIssue] = []
    for result in results:
        all_issues.extend(result.issues)
    info_count, warning_count, critical_count = _counts(all_issues)

    summary_by_category: dict[QACategory, int] = {}
    for issue in all_issues:
        summary_by_category[issue.category] = summary_by_category.get(issue.category, 0) + 1

    chapter_summaries: tuple[QAScopeSummary, ...] = ()
    if include_chapter_summary:
        chapter_summaries = tuple(
            _scope_summary("chapter", result.chapter_id, result.title, result.issues)
            for result in results
        )
    volume_summaries: tuple[QAScopeSummary, ...] = ()
    if include_volume_summary:
        volume_summaries = tuple(_volume_summaries(results, volume_titles))

    return QAReport(
        schema_version=QA_REPORT_SCHEMA_VERSION,
        project=project_name,
        scope=scope,
        scope_id=scope_id,
        total_segments=sum(result.segment_count for result in results),
        total_issues=len(all_issues),
        info_count=info_count,
        warning_count=warning_count,
        critical_count=critical_count,
        badge=badge_for(warning_count=warning_count, critical_count=critical_count),
        issues=tuple(all_issues),
        summary_by_category=summary_by_category,
        summary_by_chapter=chapter_summaries,
        summary_by_volume=volume_summaries,
    )


def _volume_summaries(
    results: Sequence[_ChapterResult], volume_titles: dict[int, str]
) -> list[QAScopeSummary]:
    order: list[int] = []
    grouped: dict[int, list[QAIssue]] = {}
    for result in results:
        if result.volume_id not in grouped:
            grouped[result.volume_id] = []
            order.append(result.volume_id)
        grouped[result.volume_id].extend(result.issues)
    return [
        _scope_summary("volume", str(volume_id), volume_titles.get(volume_id), grouped[volume_id])
        for volume_id in order
    ]


def _scope_summary(
    scope: str, scope_id: str, title: str | None, issues: Sequence[QAIssue]
) -> QAScopeSummary:
    info_count, warning_count, critical_count = _counts(issues)
    return QAScopeSummary(
        scope="volume" if scope == "volume" else "chapter",
        id=scope_id,
        title=title,
        total_issues=len(issues),
        info_count=info_count,
        warning_count=warning_count,
        critical_count=critical_count,
        badge=badge_for(warning_count=warning_count, critical_count=critical_count),
    )


def _counts(issues: Sequence[QAIssue]) -> tuple[int, int, int]:
    info = warning = critical = 0
    for issue in issues:
        if issue.severity == "info":
            info += 1
        elif issue.severity == "warning":
            warning += 1
        else:
            critical += 1
    return info, warning, critical


def _issue_from_segment(warning: QAWarning, *, chapter_id: str) -> QAIssue:
    return QAIssue(
        rule=warning.check_name,
        category=category_for(warning.check_name),
        severity=warning.severity,
        message=warning.message,
        segment_id=warning.segment_id,
        chapter_id=chapter_id,
    )


def _issue_from_scope(warning: ScopeWarning, *, chapter_id: str) -> QAIssue:
    return QAIssue(
        rule=warning.check_name,
        category=category_for(warning.check_name),
        severity=warning.severity,
        message=warning.message,
        segment_id=None,
        chapter_id=chapter_id,
    )


def _load_chapter_segment_inputs(
    connection: sqlite3.Connection, chapter_id: str
) -> list[SegmentInput]:
    rows = connection.execute(
        """
        WITH latest AS (
          SELECT segment_id, MAX(attempt) AS attempt
          FROM translations
          GROUP BY segment_id
        )
        SELECT
          s.id,
          s.source_text,
          s.status,
          t.text AS translation_text
        FROM segments s
        LEFT JOIN latest l ON l.segment_id = s.id
        LEFT JOIN translations t
          ON t.segment_id = l.segment_id
         AND t.attempt = l.attempt
         AND t.source_hash = s.source_hash
        WHERE s.chapter_id = ?
        ORDER BY s.block_order
        """,
        (chapter_id,),
    ).fetchall()
    inputs: list[SegmentInput] = []
    for row in rows:
        source_text = str(row["source_text"])
        translation_text = None if row["translation_text"] is None else str(row["translation_text"])
        inputs.append(
            SegmentInput(
                segment_id=str(row["id"]),
                source_text=source_text,
                normalized_source_text=normalize_japanese_text(source_text),
                status=str(row["status"]),
                translation_text=translation_text,
            )
        )
    return inputs


def _character_names(connection: sqlite3.Connection, project_id: int) -> list[CharacterName]:
    return [
        CharacterName(jp_name=character.jp_name, en_name=character.en_name)
        for character in list_characters(connection, project_id=project_id)
    ]


def _single_project_id(connection: sqlite3.Connection) -> int:
    row = connection.execute("SELECT id FROM projects ORDER BY id LIMIT 1").fetchone()
    if row is None:
        raise ConfigError(
            "Project database has no project row. "
            "Likely cause: database was not initialized by `weaver init`. "
            "Next command: run `weaver init <input.epub>`."
        )
    return int(row["id"])
