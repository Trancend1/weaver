"""Persistence adapter for the in-process JobRegistry (Sprint I, ADR 010).

Pure storage. Owns no threads, no queues, no run loops — those stay in the
existing :mod:`weaver.api.jobs` registry. Every public function takes a
short-lived ``sqlite3.Connection`` and runs in one transaction (or none, for
read paths). Callers open the connection per-operation so threads never share
SQLite state, in line with CLAUDE.md §4.2 ("state writes go through services").

Schema is v6 (Sprint I1): ``jobs``, ``job_progress_snapshots``, and
``job_events`` (extended with nullable ``job_id``). The single-process
invariant from ``api/jobs.py:8-10`` is preserved — this module never spawns
workers, never enqueues to an external broker, and never resumes terminated
jobs (cold start marks them ``failed`` instead).
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from weaver.errors import WeaverError
from weaver.services.project_discovery import discover_projects, find_project
from weaver.services.project_paths import resolve_database_path
from weaver.storage.db import connect_database, transaction

JOB_KIND_TRANSLATE = "translate"
JOB_KIND_BATCH = "batch"
JOB_KIND_EXPORT = "export"

VALID_STATUSES: tuple[str, ...] = (
    "queued",
    "running",
    "done",
    "failed",
    "cancelled",
    "processed",
    "finalizing",
)
TERMINAL_STATUSES: frozenset[str] = frozenset({"done", "failed", "cancelled"})


@dataclass(frozen=True)
class JobRow:
    """One persisted ``jobs`` row, denormalized for cross-project listing.

    Fields mirror the schema; ``project_name`` is the books-dir directory name
    (CLAUDE.md §4.2). ``result_json`` carries the terminal payload as a string
    so callers parse it on demand.
    """

    id: str
    kind: str
    project_name: str
    scope: str | None
    scope_id: str | None
    chapter_id: str | None
    status: str
    mode: str | None
    target: str | None
    total_units: int
    done_units: int
    failed_units: int
    skipped_units: int
    current_label: str | None
    result_json: str | None
    error_summary: str | None
    started_at: str
    finished_at: str | None


@dataclass(frozen=True)
class JobEventRow:
    """One persisted ``job_events`` row, ordered by autoincrement id."""

    id: int
    job_id: str | None
    event: str
    data: dict[str, Any]
    created_at: str


def db_path_for(base_dir: Path, project_name: str) -> Path | None:
    """Return the persistent project DB path for ``project_name``, or None."""
    discovered = find_project(base_dir, project_name)
    if discovered is None:
        return None
    try:
        return resolve_database_path(discovered.project_toml, cwd=base_dir)
    except WeaverError:
        return None


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def insert_job(
    connection: sqlite3.Connection,
    *,
    job_id: str,
    kind: str,
    project_name: str,
    scope: str | None,
    scope_id: str | None,
    chapter_id: str | None,
    mode: str | None,
    target: str | None,
    total_units: int,
    started_at: str | None = None,
) -> None:
    """Insert one fresh ``jobs`` row in status ``running``.

    The job row is created **after** the worker thread has started but
    **before** the first SSE event is enqueued, so a refresh always finds the
    job once its id has been returned to the caller.
    """
    with transaction(connection):
        connection.execute(
            """
            INSERT INTO jobs (
                id, kind, project_name, scope, scope_id, chapter_id,
                status, mode, target, total_units, done_units, failed_units,
                skipped_units, current_label, result_json, error_summary,
                started_at, finished_at
            )
            VALUES (?, ?, ?, ?, ?, ?, 'running', ?, ?, ?, 0, 0, 0, NULL, NULL,
                    NULL, ?, NULL)
            """,
            (
                job_id,
                kind,
                project_name,
                scope,
                scope_id,
                chapter_id,
                mode,
                target,
                total_units,
                started_at or now_iso(),
            ),
        )


def update_job_progress(
    connection: sqlite3.Connection,
    *,
    job_id: str,
    done_units: int,
    failed_units: int,
    skipped_units: int = 0,
    total_units: int | None = None,
    current_label: str | None = None,
) -> None:
    """Flush the latest counters onto the ``jobs`` row and snapshot them.

    Sampled by the registry at the 1-second cadence ADR 010 §write cadence
    specifies; live SSE never blocks on this.
    """
    snapshot_at = now_iso()
    with transaction(connection):
        if total_units is None:
            connection.execute(
                """
                UPDATE jobs SET done_units = ?, failed_units = ?,
                    skipped_units = ?, current_label = COALESCE(?, current_label)
                WHERE id = ?
                """,
                (done_units, failed_units, skipped_units, current_label, job_id),
            )
        else:
            connection.execute(
                """
                UPDATE jobs SET done_units = ?, failed_units = ?,
                    skipped_units = ?, total_units = ?,
                    current_label = COALESCE(?, current_label)
                WHERE id = ?
                """,
                (
                    done_units,
                    failed_units,
                    skipped_units,
                    total_units,
                    current_label,
                    job_id,
                ),
            )
        # Best-effort snapshot row; collisions inside the same second collapse.
        connection.execute(
            """
            INSERT OR REPLACE INTO job_progress_snapshots (
                job_id, snapshot_at, done_units, total_units
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                job_id,
                snapshot_at,
                done_units,
                total_units if total_units is not None else _read_total(connection, job_id),
            ),
        )


def update_job_terminal(
    connection: sqlite3.Connection,
    *,
    job_id: str,
    status: str,
    result: dict[str, Any] | None,
    error_summary: str | None,
    finished_at: str | None = None,
) -> None:
    """Move a job to a terminal status (``done``/``failed``/``cancelled``).

    Synchronous: this write commits **before** the terminal SSE event is
    emitted so a refresh after the event always sees the final row.
    """
    if status not in TERMINAL_STATUSES:
        msg = f"update_job_terminal called with non-terminal status {status!r}"
        raise ValueError(msg)
    payload = json.dumps(result, ensure_ascii=False) if result is not None else None
    with transaction(connection):
        connection.execute(
            """
            UPDATE jobs SET status = ?, result_json = ?, error_summary = ?,
                finished_at = ?
            WHERE id = ?
            """,
            (status, payload, error_summary, finished_at or now_iso(), job_id),
        )


def append_event(
    connection: sqlite3.Connection,
    *,
    project_id: int | None,
    job_id: str,
    event: str,
    data: dict[str, Any],
) -> int:
    """Append one event for SSE replay. Returns the new event id."""
    with transaction(connection):
        cursor = connection.execute(
            """
            INSERT INTO job_events (project_id, job_id, event, data_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (project_id, job_id, event, json.dumps(data, ensure_ascii=False), now_iso()),
        )
    if cursor.lastrowid is None:
        msg = "job_events insert did not return a row id"
        raise WeaverError(msg)
    return int(cursor.lastrowid)


def list_events_after(
    connection: sqlite3.Connection, *, job_id: str, after_id: int = 0
) -> list[JobEventRow]:
    """Return every event for ``job_id`` with id > ``after_id`` (ordered)."""
    rows = connection.execute(
        """
        SELECT id, job_id, event, data_json, created_at
        FROM job_events
        WHERE job_id = ? AND id > ?
        ORDER BY id ASC
        """,
        (job_id, after_id),
    ).fetchall()
    return [
        JobEventRow(
            id=int(row["id"]),
            job_id=str(row["job_id"]) if row["job_id"] else None,
            event=str(row["event"]),
            data=json.loads(row["data_json"]) if row["data_json"] else {},
            created_at=str(row["created_at"]),
        )
        for row in rows
    ]


def get_job(connection: sqlite3.Connection, *, job_id: str) -> JobRow | None:
    row = connection.execute(
        """
        SELECT id, kind, project_name, scope, scope_id, chapter_id, status,
               mode, target, total_units, done_units, failed_units,
               skipped_units, current_label, result_json, error_summary,
               started_at, finished_at
        FROM jobs WHERE id = ?
        """,
        (job_id,),
    ).fetchone()
    return _job_from_row(row) if row is not None else None


def list_jobs_for_project(connection: sqlite3.Connection) -> list[JobRow]:
    """List every job persisted in this project DB, newest first."""
    rows = connection.execute(
        """
        SELECT id, kind, project_name, scope, scope_id, chapter_id, status,
               mode, target, total_units, done_units, failed_units,
               skipped_units, current_label, result_json, error_summary,
               started_at, finished_at
        FROM jobs
        ORDER BY started_at DESC, id DESC
        """,
    ).fetchall()
    return [_job_from_row(row) for row in rows]


def recover_interrupted_jobs(
    connection: sqlite3.Connection, *, reason: str = "process restart"
) -> list[str]:
    """Mark every ``running`` job as ``failed`` (cold-start recovery, ADR 010).

    Returns the recovered job ids so callers can log them. **Never resumes
    execution** — the single-process invariant means a previous worker thread
    cannot be revived. Idempotent: a second call finds zero rows.
    """
    finished = now_iso()
    rows = connection.execute("SELECT id FROM jobs WHERE status = 'running'").fetchall()
    job_ids = [str(row["id"]) for row in rows]
    if not job_ids:
        return []
    with transaction(connection):
        connection.execute(
            """
            UPDATE jobs SET status = 'failed', error_summary = ?, finished_at = ?
            WHERE status = 'running'
            """,
            (reason, finished),
        )
        for job_id in job_ids:
            connection.execute(
                """
                INSERT INTO job_events (project_id, job_id, event, data_json, created_at)
                VALUES (NULL, ?, 'recovered', ?, ?)
                """,
                (
                    job_id,
                    json.dumps({"reason": reason}, ensure_ascii=False),
                    finished,
                ),
            )
    return job_ids


def recover_all_projects(books_dir: Path, *, reason: str = "process restart") -> dict[str, int]:
    """Run :func:`recover_interrupted_jobs` against every project under books_dir.

    Returns a ``{project_name: recovered_count}`` map for logging.
    """
    summary: dict[str, int] = {}
    for project in discover_projects(books_dir):
        if project.error:
            continue
        try:
            db_path = resolve_database_path(project.project_toml, cwd=books_dir)
        except WeaverError:
            continue
        try:
            with closing(connect_database(db_path)) as connection:
                recovered = recover_interrupted_jobs(connection, reason=reason)
        except (WeaverError, sqlite3.Error):
            # A project DB the runtime can't open should not prevent boot.
            continue
        if recovered:
            summary[project.name] = len(recovered)
    return summary


def _read_total(connection: sqlite3.Connection, job_id: str) -> int:
    row = connection.execute("SELECT total_units FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return int(row["total_units"]) if row is not None else 0


def _job_from_row(row: sqlite3.Row) -> JobRow:
    return JobRow(
        id=str(row["id"]),
        kind=str(row["kind"]),
        project_name=str(row["project_name"]),
        scope=str(row["scope"]) if row["scope"] is not None else None,
        scope_id=str(row["scope_id"]) if row["scope_id"] is not None else None,
        chapter_id=str(row["chapter_id"]) if row["chapter_id"] is not None else None,
        status=str(row["status"]),
        mode=str(row["mode"]) if row["mode"] is not None else None,
        target=str(row["target"]) if row["target"] is not None else None,
        total_units=int(row["total_units"]),
        done_units=int(row["done_units"]),
        failed_units=int(row["failed_units"]),
        skipped_units=int(row["skipped_units"]),
        current_label=str(row["current_label"]) if row["current_label"] is not None else None,
        result_json=str(row["result_json"]) if row["result_json"] is not None else None,
        error_summary=str(row["error_summary"]) if row["error_summary"] is not None else None,
        started_at=str(row["started_at"]),
        finished_at=str(row["finished_at"]) if row["finished_at"] is not None else None,
    )
