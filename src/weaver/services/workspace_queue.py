"""Read-only cross-project translation queue.

Aggregates recent jobs from every project under a books directory.  Uses
``connect_readonly_database`` exclusively and isolates per-project failures
so one bad project never blanks the queue.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from weaver.errors import WeaverError
from weaver.services.project_discovery import discover_projects
from weaver.storage.db import connect_readonly_database

_RECENT_JOBS_PER_PROJECT = 20


@dataclass(frozen=True)
class QueueJobRow:
    """One job row for the cross-project queue, with stale-running distinction."""

    job_id: str
    project_name: str
    project_uuid: str | None
    kind: str
    status: str
    scope: str | None
    scope_id: str | None
    done_units: int
    total_units: int
    current_label: str | None
    error_summary: str | None
    started_at: str
    finished_at: str | None


@dataclass(frozen=True)
class QueueDegradedProject:
    """A project that could not be read fully — rendered as a degraded row."""

    name: str
    uuid: str | None
    state: str  # locked | missing | needs_upgrade | identity_conflict | error
    error: str | None


@dataclass(frozen=True)
class WorkspaceQueue:
    """Result of a cross-project queue build."""

    jobs: list[QueueJobRow]
    degraded: list[QueueDegradedProject]
    generated_at: float


@dataclass(frozen=True)
class _ProjectQueueState:
    """Internal accumulator for one project."""

    jobs: list[QueueJobRow]
    degraded: QueueDegradedProject | None


def build_workspace_queue(
    books_dir: Path,
    *,
    registry_live_check: Callable[[str, str], bool] | None = None,
) -> WorkspaceQueue:
    """Build a read-only cross-project job queue.

    Args:
        books_dir: Root directory containing ``.weaver/<name>/`` projects.
        registry_live_check: Optional ``(project_name, job_id) -> bool`` that
            returns True when a job is currently live in the in-process
            ``JobRegistry``.  Used to classify stale ``running`` rows.

    Returns:
        A :class:`WorkspaceQueue` with recent jobs and degraded-project rows.
        One broken project never blanks the queue.
    """

    import time as _time

    discovered = discover_projects(books_dir)
    all_jobs: list[QueueJobRow] = []
    degraded: list[QueueDegradedProject] = []

    for project in discovered:
        result = _queue_for_project(
            project,
            registry_live_check=registry_live_check,
        )
        if result.degraded is not None:
            degraded.append(result.degraded)
        all_jobs.extend(result.jobs)

    # Stable sort: running first, then queued, then stale, then failed, then done
    def _sort_key(job: QueueJobRow) -> tuple[int, str]:
        order = {
            "running": 0,
            "queued": 1,
            "stale_running": 2,
            "failed": 3,
            "done": 4,
            "cancelled": 5,
        }
        return (order.get(job.status, 6), job.started_at)

    all_jobs.sort(key=_sort_key)

    return WorkspaceQueue(
        jobs=all_jobs,
        degraded=degraded,
        generated_at=_time.time(),
    )


def _queue_for_project(
    project: Any,
    *,
    registry_live_check: Callable[[str, str], bool] | None,
) -> _ProjectQueueState:
    """Resolve recent jobs for a single discovered project."""

    name = project.name
    uuid: str | None = None
    if hasattr(project, "summary") and project.summary is not None:
        uuid = getattr(project.summary, "uuid", None)

    # Discovery-level errors
    if getattr(project, "error", None) is not None:
        return _ProjectQueueState(
            jobs=[],
            degraded=QueueDegradedProject(
                name=name,
                uuid=uuid,
                state="error",
                error=project.error,
            ),
        )

    summary = project.summary
    if summary is None:
        return _ProjectQueueState(
            jobs=[],
            degraded=QueueDegradedProject(
                name=name,
                uuid=uuid,
                state="error",
                error="Missing project summary.",
            ),
        )

    schema_version = summary.schema_version

    # Schema too old to trust column access
    if schema_version < 10:
        return _ProjectQueueState(
            jobs=[],
            degraded=QueueDegradedProject(
                name=name,
                uuid=getattr(summary, "uuid", None),
                state="needs_upgrade",
                error=None,
            ),
        )

    base_state = "identity_conflict" if getattr(project, "identity_conflict", False) else "ready"

    db_path = project.project_toml.parent / "weaver.db"
    jobs: list[QueueJobRow] = []

    try:
        with closing(connect_readonly_database(db_path)) as connection:
            rows = connection.execute(
                """
                SELECT id, kind, project_name, scope, scope_id, chapter_id, status,
                       mode, target, total_units, done_units, failed_units,
                       skipped_units, current_label, result_json, error_summary,
                       started_at, finished_at
                FROM jobs
                ORDER BY started_at DESC, id DESC
                LIMIT ?
                """,
                (_RECENT_JOBS_PER_PROJECT,),
            ).fetchall()

            for row in rows:
                job_id = str(row["id"])
                db_status = str(row["status"])
                status = db_status
                is_not_live = (
                    db_status == "running"
                    and registry_live_check is not None
                    and not registry_live_check(name, job_id)
                )
                if is_not_live:
                    status = "stale_running"

                _cur = row["current_label"]
                _err = row["error_summary"]
                _fin = row["finished_at"]
                jobs.append(
                    QueueJobRow(
                        job_id=job_id,
                        project_name=name,
                        project_uuid=getattr(summary, "uuid", None),
                        kind=str(row["kind"]),
                        status=status,
                        scope=str(row["scope"]) if row["scope"] is not None else None,
                        scope_id=str(row["scope_id"]) if row["scope_id"] is not None else None,
                        done_units=int(row["done_units"]),
                        total_units=int(row["total_units"]),
                        current_label=str(_cur) if _cur is not None else None,
                        error_summary=str(_err) if _err is not None else None,
                        started_at=str(row["started_at"]),
                        finished_at=str(_fin) if _fin is not None else None,
                    )
                )
    except (WeaverError, sqlite3.Error) as exc:
        return _ProjectQueueState(
            jobs=[],
            degraded=QueueDegradedProject(
                name=name,
                uuid=getattr(summary, "uuid", None),
                state="error",
                error=str(exc),
            ),
        )

    if base_state == "identity_conflict":
        return _ProjectQueueState(
            jobs=jobs,
            degraded=QueueDegradedProject(
                name=name,
                uuid=getattr(summary, "uuid", None),
                state="identity_conflict",
                error=None,
            ),
        )

    return _ProjectQueueState(jobs=jobs, degraded=None)
