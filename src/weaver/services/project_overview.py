"""Cheap read-only project overview for the cockpit hub page (Sprint P5, WV-005).

All data comes from existing tables; no QA scan, no provider call, no file
access beyond a DB read. Snapshot status per volume is read-only.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from weaver.api.jobs import JobRegistry
from weaver.errors import WeaverError
from weaver.services.epub_reparse import status_for_volume
from weaver.services.job_store import list_jobs_for_project
from weaver.services.project_paths import resolve_database_path
from weaver.services.project_tree import NovelTree, project_tree
from weaver.services.segment_review import ReviewCounts, review_counts_for_volume
from weaver.storage.db import connect_readonly_database


@dataclass(frozen=True)
class VolumeOverview:
    """Cheap counts for one volume on the project overview."""

    id: int
    title: str
    chapter_count: int
    segment_count: int
    done_count: int
    pending_count: int
    failed_stale_count: int
    review_counts: ReviewCounts
    snapshot_status: str
    source_format: str


@dataclass(frozen=True)
class ProjectOverview:
    """Cheap overview data for the project hub page."""

    project_name: str
    volume_count: int
    chapter_count: int
    segment_count: int
    done_count: int
    pending_count: int
    failed_stale_count: int
    review_counts: ReviewCounts
    volumes: list[VolumeOverview]
    recent_job: dict[str, Any] | None
    candidate_count: int
    draft_count: int


def project_overview(
    project_toml: Path,
    *,
    cwd: Path | None = None,
    jobs: JobRegistry | None = None,
) -> ProjectOverview:
    """Build a cheap, read-only overview for one project.

    Args:
        project_toml: Path to the project's ``project.toml``.
        cwd: Working directory used to resolve project-relative paths.
        jobs: Optional JobRegistry (passed to ``project_tree`` for translating
            overlay).

    Returns:
        ProjectOverview with counts, review state, snapshot hints, and
        recent activity.
    """
    tree = project_tree(project_toml, cwd=cwd, jobs=jobs)

    with closing(
        connect_readonly_database(resolve_database_path(project_toml, cwd=cwd))
    ) as connection:
        volumes_overview = _volume_overviews(connection, tree, project_toml, cwd=cwd)
        recent_job = _recent_job(connection)
        candidate_count = _count_or_zero(connection, "translation_candidates")
        draft_count = _count_or_zero(connection, "character_page_drafts")

    total_chapters = sum(v.chapter_count for v in volumes_overview)
    total_segments = sum(v.segment_count for v in volumes_overview)
    total_done = sum(v.done_count for v in volumes_overview)
    total_pending = sum(v.pending_count for v in volumes_overview)
    total_failed_stale = sum(v.failed_stale_count for v in volumes_overview)
    total_review = _sum_review_counts(v.review_counts for v in volumes_overview)

    return ProjectOverview(
        project_name=tree.project_name,
        volume_count=len(tree.volumes),
        chapter_count=total_chapters,
        segment_count=total_segments,
        done_count=total_done,
        pending_count=total_pending,
        failed_stale_count=total_failed_stale,
        review_counts=total_review,
        volumes=volumes_overview,
        recent_job=recent_job,
        candidate_count=candidate_count,
        draft_count=draft_count,
    )


def _volume_overviews(
    connection: sqlite3.Connection,
    tree: NovelTree,
    project_toml: Path,
    *,
    cwd: Path | None = None,
) -> list[VolumeOverview]:
    result: list[VolumeOverview] = []
    for v in tree.volumes:
        done_count = sum(c.done_count for c in v.chapters)
        total_seg = sum(c.segment_count for c in v.chapters)
        status_counts = _volume_segment_status_counts(connection, v.id)
        review_counts = review_counts_for_volume(connection, volume_id=v.id)

        snapshot = _snapshot_status_safe(project_toml, v.id, cwd=cwd)
        result.append(
            VolumeOverview(
                id=v.id,
                title=v.title,
                chapter_count=v.chapter_count,
                segment_count=total_seg,
                done_count=done_count,
                pending_count=status_counts.get("pending", 0),
                failed_stale_count=status_counts.get("failed", 0) + status_counts.get("stale", 0),
                review_counts=review_counts,
                snapshot_status=snapshot,
                source_format=v.source_format,
            )
        )
    return result


def _volume_segment_status_counts(connection: sqlite3.Connection, volume_id: int) -> dict[str, int]:
    rows = connection.execute(
        """
        SELECT s.status, COUNT(*) AS cnt
        FROM segments s
        JOIN chapters c ON c.id = s.chapter_id
        WHERE c.volume_id = ?
        GROUP BY s.status
        """,
        (volume_id,),
    ).fetchall()
    return {str(row["status"]): int(row["cnt"]) for row in rows}


def _snapshot_status_safe(project_toml: Path, volume_id: int, *, cwd: Path | None = None) -> str:
    try:
        status = status_for_volume(project_toml, volume_id, cwd=cwd)
        return status.state
    except WeaverError:
        return "missing"


def _recent_job(connection: sqlite3.Connection) -> dict[str, Any] | None:
    rows = list_jobs_for_project(connection)
    if not rows:
        return None
    job = rows[0]
    return {
        "id": job.id,
        "kind": job.kind,
        "status": job.status,
        "scope": job.scope,
        "scope_id": job.scope_id,
        "started_at": job.started_at,
    }


def _count_or_zero(connection: sqlite3.Connection, table_name: str) -> int:
    safe_tables = frozenset({"translation_candidates", "character_page_drafts"})
    if table_name not in safe_tables:
        return 0
    try:
        row = connection.execute(f"SELECT COUNT(*) AS cnt FROM {table_name}").fetchone()
        return int(row["cnt"])
    except sqlite3.OperationalError:
        return 0


def _sum_review_counts(
    counts_iter: Iterator[ReviewCounts],
) -> ReviewCounts:
    not_reviewed = 0
    needs_review = 0
    needs_revision = 0
    approved = 0
    rejected = 0
    for rc in counts_iter:
        not_reviewed += rc.not_reviewed
        needs_review += rc.needs_review
        needs_revision += rc.needs_revision
        approved += rc.approved
        rejected += rc.rejected
    return ReviewCounts(
        not_reviewed=not_reviewed,
        needs_review=needs_review,
        needs_revision=needs_revision,
        approved=approved,
        rejected=rejected,
    )
