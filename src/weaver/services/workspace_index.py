"""Read-only cross-project workspace index.

Builds a cached, error-isolated summary of every project under a books
directory.  Uses ``connect_readonly_database`` exclusively — never migrates,
never resets ``in_progress``, never hashes source files, and never calls a
provider.
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from weaver.errors import WeaverError
from weaver.services.project_discovery import DiscoveredProject, discover_projects
from weaver.storage.db import connect_readonly_database


@dataclass(frozen=True)
class ProjectIndexEntry:
    """Read-only summary of one project for cross-project surfaces."""

    uuid: str | None
    name: str
    schema_version: int
    state: str  # ready | needs_upgrade | locked | error | identity_conflict
    error: str | None
    volume_count: int
    chapter_count: int
    segment_count: int
    pending_count: int
    translated_count: int
    failed_count: int
    stale_count: int
    review_counts: dict[str, int]
    job_counts: dict[str, int]
    last_activity: str | None
    # Q8: deterministic token totals (COALESCE sums; cached with the entry).
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True)
class WorkspaceIndex:
    """Result of a workspace index build."""

    entries: list[ProjectIndexEntry]
    generated_at: float


@dataclass(frozen=True)
class _CacheKey:
    """Filesystem invalidation key for one project."""

    toml_mtime: int
    db_mtime: int
    wal_mtime: int


def build_workspace_index(
    books_dir: Path,
    *,
    registry_live_check: Callable[[str, str], bool] | None = None,
    cache: dict[str, Any] | None = None,
    ttl_seconds: float = 5.0,
) -> WorkspaceIndex:
    """Build a read-only cross-project index.

    Args:
        books_dir: Root directory containing ``.weaver/<name>/`` projects.
        registry_live_check: Optional ``(project_name, job_id) -> bool`` that
            returns True when a job is currently live in the in-process
            ``JobRegistry``.  Used to classify stale ``running`` rows.
        cache: Optional mutable cache dict for read-through caching.  Keys are
            ``str(project_toml)``; values are ``(_CacheKey, entry, timestamp)``.
            The caller (e.g. FastAPI ``app.state``) owns the dict lifetime.
        ttl_seconds: Maximum cache age before a project is re-read.

    Returns:
        A :class:`WorkspaceIndex` with one entry per discovered project.
        Broken projects are represented by ``state='error'`` entries — one
        bad project never blanks the index.
    """

    discovered = discover_projects(books_dir)
    now = time.monotonic()
    entries: list[ProjectIndexEntry] = []
    working_cache: dict[str, Any] = cache if cache is not None else {}

    for project in discovered:
        entry = _entry_for_project(
            project,
            registry_live_check=registry_live_check,
            cache=working_cache,
            now=now,
            ttl_seconds=ttl_seconds,
        )
        entries.append(entry)

    return WorkspaceIndex(entries=entries, generated_at=time.time())


def _entry_for_project(
    discovered: DiscoveredProject,
    *,
    registry_live_check: Callable[[str, str], bool] | None,
    cache: dict[str, Any],
    now: float,
    ttl_seconds: float,
) -> ProjectIndexEntry:
    """Resolve a single discovered project to an index entry (cached or fresh)."""

    name = discovered.name
    project_toml = discovered.project_toml
    db_path = project_toml.parent / "weaver.db"

    # Discovery-level errors
    if discovered.error is not None:
        return ProjectIndexEntry(
            uuid=None,
            name=name,
            schema_version=0,
            state="error",
            error=discovered.error,
            volume_count=0,
            chapter_count=0,
            segment_count=0,
            pending_count=0,
            translated_count=0,
            failed_count=0,
            stale_count=0,
            review_counts={},
            job_counts={},
            last_activity=None,
        )

    summary = discovered.summary
    assert summary is not None
    schema_version = summary.schema_version

    # Schema too old to trust column access
    if schema_version < 10:
        return ProjectIndexEntry(
            uuid=summary.uuid,
            name=name,
            schema_version=schema_version,
            state="needs_upgrade",
            error=None,
            volume_count=_or_zero(summary.volume_count),
            chapter_count=_or_zero(summary.chapter_count),
            segment_count=_or_zero(summary.segment_count),
            pending_count=_or_zero(summary.pending_count),
            translated_count=_or_zero(summary.translated_count),
            failed_count=_or_zero(summary.failed_count),
            stale_count=_or_zero(summary.stale_count),
            review_counts={},
            job_counts={},
            last_activity=None,
        )

    # Identity conflict flagged by discovery (directory copy)
    base_state = "identity_conflict" if discovered.identity_conflict else "ready"

    # Cache lookup — first by path + TTL, then validate key match
    cache_key = _cache_key_for(project_toml, db_path)
    cached = cache.get(str(project_toml))
    if cached is not None:
        cached_key, cached_entry, cached_at = cached
        within_ttl = (now - cached_at) < ttl_seconds
        key_match = cache_key is None or cache_key == cached_key
        if within_ttl and key_match:
            # Cache hit — but still respect identity_conflict updates from discovery
            if discovered.identity_conflict and cached_entry.state != "identity_conflict":
                return ProjectIndexEntry(
                    uuid=cached_entry.uuid,
                    name=cached_entry.name,
                    schema_version=cached_entry.schema_version,
                    state="identity_conflict",
                    error=cached_entry.error,
                    volume_count=cached_entry.volume_count,
                    chapter_count=cached_entry.chapter_count,
                    segment_count=cached_entry.segment_count,
                    pending_count=cached_entry.pending_count,
                    translated_count=cached_entry.translated_count,
                    failed_count=cached_entry.failed_count,
                    stale_count=cached_entry.stale_count,
                    review_counts=cached_entry.review_counts,
                    job_counts=cached_entry.job_counts,
                    last_activity=cached_entry.last_activity,
                    input_tokens=cached_entry.input_tokens,
                    output_tokens=cached_entry.output_tokens,
                )
            return cached_entry

    # Fresh readonly read
    try:
        with closing(connect_readonly_database(db_path)) as connection:
            counts = _read_counts(connection)
            review_counts = _read_review_counts(connection)
            job_counts, last_activity = _read_job_summary(connection, name, registry_live_check)
    except (WeaverError, sqlite3.Error) as exc:
        return ProjectIndexEntry(
            uuid=summary.uuid,
            name=name,
            schema_version=schema_version,
            state="error",
            error=str(exc),
            volume_count=summary.volume_count,
            chapter_count=summary.chapter_count,
            segment_count=summary.segment_count,
            pending_count=summary.pending_count,
            translated_count=summary.translated_count,
            failed_count=summary.failed_count,
            stale_count=summary.stale_count,
            review_counts={},
            job_counts={},
            last_activity=None,
        )

    entry = ProjectIndexEntry(
        uuid=summary.uuid,
        name=name,
        schema_version=schema_version,
        state=base_state,
        error=None,
        volume_count=counts["volumes"],
        chapter_count=counts["chapters"],
        segment_count=counts["segments"],
        pending_count=counts["pending"],
        translated_count=counts["translated"],
        failed_count=counts["failed"],
        stale_count=counts["stale"],
        review_counts=review_counts,
        job_counts=job_counts,
        last_activity=last_activity,
        input_tokens=counts["input_tokens"],
        output_tokens=counts["output_tokens"],
    )

    if cache_key is not None:
        cache[str(project_toml)] = (cache_key, entry, now)

    return entry


def _cache_key_for(project_toml: Path, db_path: Path) -> _CacheKey | None:
    """Build an invalidation key from filesystem mtimes."""

    try:
        toml_mtime = project_toml.stat().st_mtime_ns
        db_mtime = db_path.stat().st_mtime_ns
        wal_mtime = db_path.with_suffix(".db-wal")
        wal_mtime_val = wal_mtime.stat().st_mtime_ns if wal_mtime.exists() else 0
        return _CacheKey(toml_mtime=toml_mtime, db_mtime=db_mtime, wal_mtime=wal_mtime_val)
    except OSError:
        return None


def _read_counts(connection: sqlite3.Connection) -> dict[str, int]:
    """Return basic project counts from a readonly connection."""

    status_counts = {
        str(row["status"]): int(row["count"])
        for row in connection.execute(
            "SELECT status, COUNT(*) AS count FROM segments GROUP BY status"
        ).fetchall()
    }
    token_row = connection.execute(
        "SELECT COALESCE(SUM(input_tokens), 0) AS input_total, "
        "COALESCE(SUM(output_tokens), 0) AS output_total FROM translations"
    ).fetchone()
    return {
        "volumes": _count(connection, "volumes"),
        "chapters": _count(connection, "chapters"),
        "segments": _count(connection, "segments"),
        "pending": status_counts.get("pending", 0),
        "translated": status_counts.get("translated", 0),
        "failed": status_counts.get("failed", 0),
        "stale": status_counts.get("stale", 0),
        "input_tokens": int(token_row["input_total"]) if token_row is not None else 0,
        "output_tokens": int(token_row["output_total"]) if token_row is not None else 0,
    }


def _read_review_counts(connection: sqlite3.Connection) -> dict[str, int]:
    """Return segment review-status bucket counts."""

    return {
        str(row["review_status"]): int(row["count"])
        for row in connection.execute(
            "SELECT review_status, COUNT(*) AS count FROM segments GROUP BY review_status"
        ).fetchall()
    }


def _read_job_summary(
    connection: sqlite3.Connection,
    project_name: str,
    registry_live_check: Callable[[str, str], bool] | None,
) -> tuple[dict[str, int], str | None]:
    """Return job status counts + last activity timestamp.

    A DB ``running`` row not confirmed by ``registry_live_check`` is counted
    as ``stale_running`` instead of ``running``.
    """

    counts: dict[str, int] = {}
    last_activity: str | None = None

    for row in connection.execute(
        "SELECT status, COUNT(*) AS count FROM jobs GROUP BY status"
    ).fetchall():
        status = str(row["status"])
        count = int(row["count"])
        if status == "running" and registry_live_check is not None:
            confirmed = 0
            stale = 0
            for job_row in connection.execute(
                "SELECT id FROM jobs WHERE status = 'running'"
            ).fetchall():
                job_id = str(job_row["id"])
                if registry_live_check(project_name, job_id):
                    confirmed += 1
                else:
                    stale += 1
            counts["running"] = confirmed
            counts["stale_running"] = stale
        else:
            counts[status] = count

    # Last activity = latest started_at or finished_at across all jobs
    activity_row = connection.execute(
        """
        SELECT MAX(started_at) AS started, MAX(finished_at) AS finished
        FROM jobs
        """,
    ).fetchone()
    if activity_row is not None:
        started = activity_row["started"]
        finished = activity_row["finished"]
        candidates = [str(v) for v in (started, finished) if v is not None]
        if candidates:
            last_activity = max(candidates)

    return counts, last_activity


def _count(connection: sqlite3.Connection, table_name: str) -> int:
    row = connection.execute(f"SELECT COUNT(*) AS count FROM {table_name}").fetchone()
    return int(row["count"])


def _or_zero(value: int | None) -> int:
    return value if value is not None else 0
