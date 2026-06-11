"""Deterministic per-project + workspace analytics (Sprint Q8).

Aggregates only data that already exists in the project database: segment
status, review status, token usage per provider/model, candidate/draft funnel,
export readiness (the exporter's own publishable predicate via
``list_export_segment_states`` — no third definition), export-history summary
(Q7 ledger), and recent job activity.

Current-state only — no time-series store exists, and none is invented here.
Uses ``connect_readonly_database`` exclusively: no QA scan, no provider call,
no source hashing, no LLM, no currency estimates.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from weaver.services.project_paths import resolve_database_path
from weaver.storage.db import connect_readonly_database
from weaver.storage.export_history import ExportHistoryRow, list_export_history
from weaver.storage.translations import list_export_segment_states

_RECENT_JOBS = 5


@dataclass(frozen=True)
class TokenUsageRow:
    """Deterministic token totals for one provider/model pair."""

    provider: str
    model: str
    attempts: int
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class ExportReadiness:
    """Publishable-segment counts under the exporter's own predicate."""

    publishable: int
    total: int

    @property
    def percent(self) -> int:
        if self.total == 0:
            return 0
        return round(100 * self.publishable / self.total)


@dataclass(frozen=True)
class JobActivityRow:
    """One recent job, for the activity list."""

    job_id: str
    kind: str
    status: str
    started_at: str
    finished_at: str | None


@dataclass(frozen=True)
class ProjectAnalytics:
    """Current-state analytics for one project (deterministic reads only)."""

    project_name: str
    segment_total: int
    status_counts: dict[str, int]
    review_counts: dict[str, int]
    token_usage: list[TokenUsageRow]
    candidate_counts: dict[str, int]
    draft_counts: dict[str, int]
    export_readiness: ExportReadiness
    export_history: list[ExportHistoryRow]
    recent_jobs: list[JobActivityRow]


def build_project_analytics(project_toml: Path, *, cwd: Path | None = None) -> ProjectAnalytics:
    """Aggregate one project's analytics from its database (readonly).

    Args:
        project_toml: Path to the project's ``project.toml``.
        cwd: Working directory used to resolve project-relative paths.

    Returns:
        A :class:`ProjectAnalytics` whose numbers reconcile 1:1 with direct
        queries against the project DB — nothing is estimated or predicted.
    """

    db_path = resolve_database_path(project_toml, cwd=cwd)
    with closing(connect_readonly_database(db_path)) as connection:
        status_counts = _group_counts(connection, "segments", "status")
        review_counts = _group_counts(connection, "segments", "review_status")
        token_usage = _token_usage(connection)
        candidate_counts = _group_counts_safe(connection, "translation_candidates", "status")
        draft_counts = _group_counts_safe(connection, "character_page_drafts", "status")
        readiness = _export_readiness(connection)
        history = _export_history_safe(connection)
        recent_jobs = _recent_jobs(connection)

    return ProjectAnalytics(
        project_name=project_toml.parent.name,
        segment_total=sum(status_counts.values()),
        status_counts=status_counts,
        review_counts=review_counts,
        token_usage=token_usage,
        candidate_counts=candidate_counts,
        draft_counts=draft_counts,
        export_readiness=readiness,
        export_history=history,
        recent_jobs=recent_jobs,
    )


@dataclass(frozen=True)
class WorkspaceRollup:
    """Cross-project current-state totals, aggregated from index entries.

    Pure aggregation over already-built :class:`ProjectIndexEntry` values —
    adds zero database reads to the dashboard render (SD-6).
    """

    project_count: int
    segment_total: int
    translated_total: int
    pending_total: int
    failed_total: int
    review_totals: dict[str, int]
    job_totals: dict[str, int]
    input_tokens: int
    output_tokens: int


def build_workspace_rollup(entries: list[object]) -> WorkspaceRollup:
    """Aggregate workspace totals from workspace-index entries (no DB access)."""

    review_totals: dict[str, int] = {}
    job_totals: dict[str, int] = {}
    segment_total = translated_total = pending_total = failed_total = 0
    input_tokens = output_tokens = 0

    for entry in entries:
        segment_total += getattr(entry, "segment_count", 0)
        translated_total += getattr(entry, "translated_count", 0)
        pending_total += getattr(entry, "pending_count", 0)
        failed_total += getattr(entry, "failed_count", 0)
        input_tokens += getattr(entry, "input_tokens", 0)
        output_tokens += getattr(entry, "output_tokens", 0)
        for bucket, count in getattr(entry, "review_counts", {}).items():
            review_totals[bucket] = review_totals.get(bucket, 0) + count
        for bucket, count in getattr(entry, "job_counts", {}).items():
            job_totals[bucket] = job_totals.get(bucket, 0) + count

    return WorkspaceRollup(
        project_count=len(entries),
        segment_total=segment_total,
        translated_total=translated_total,
        pending_total=pending_total,
        failed_total=failed_total,
        review_totals=review_totals,
        job_totals=job_totals,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def _group_counts(connection: sqlite3.Connection, table: str, column: str) -> dict[str, int]:
    return {
        str(row["bucket"]): int(row["count"])
        for row in connection.execute(
            f"SELECT {column} AS bucket, COUNT(*) AS count FROM {table} GROUP BY {column}"
        ).fetchall()
    }


def _group_counts_safe(connection: sqlite3.Connection, table: str, column: str) -> dict[str, int]:
    """Group counts tolerating a missing table (older schemas)."""

    try:
        return _group_counts(connection, table, column)
    except sqlite3.Error:
        return {}


def _token_usage(connection: sqlite3.Connection) -> list[TokenUsageRow]:
    rows = connection.execute(
        """
        SELECT provider, model, COUNT(*) AS attempts,
               COALESCE(SUM(input_tokens), 0) AS input_total,
               COALESCE(SUM(output_tokens), 0) AS output_total
        FROM translations
        GROUP BY provider, model
        ORDER BY input_total + output_total DESC
        """
    ).fetchall()
    return [
        TokenUsageRow(
            provider=str(row["provider"]),
            model=str(row["model"]),
            attempts=int(row["attempts"]),
            input_tokens=int(row["input_total"]),
            output_tokens=int(row["output_total"]),
        )
        for row in rows
    ]


def _export_readiness(connection: sqlite3.Connection) -> ExportReadiness:
    """Count publishable segments under the exporter's predicate (reused, not re-derived)."""

    chapter_ids = [
        str(row["id"]) for row in connection.execute("SELECT id FROM chapters").fetchall()
    ]
    states = list_export_segment_states(connection, chapter_ids=chapter_ids)
    publishable = sum(1 for state in states if state.publishable_text is not None)
    return ExportReadiness(publishable=publishable, total=len(states))


def _export_history_safe(connection: sqlite3.Connection) -> list[ExportHistoryRow]:
    """Recent ledger rows, tolerating a pre-v11 schema without the table."""

    try:
        return list_export_history(connection, limit=10)
    except sqlite3.Error:
        return []


def _recent_jobs(connection: sqlite3.Connection) -> list[JobActivityRow]:
    rows = connection.execute(
        """
        SELECT id, kind, status, started_at, finished_at
        FROM jobs
        ORDER BY started_at DESC, id DESC
        LIMIT ?
        """,
        (_RECENT_JOBS,),
    ).fetchall()
    return [
        JobActivityRow(
            job_id=str(row["id"]),
            kind=str(row["kind"]),
            status=str(row["status"]),
            started_at=str(row["started_at"]),
            finished_at=str(row["finished_at"]) if row["finished_at"] is not None else None,
        )
        for row in rows
    ]
