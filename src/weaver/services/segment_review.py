"""Review-status service for per-segment human review (Sprint P3, WV-003).

The review axis is independent of the translation status (a segment can be
``translated`` but still ``not_reviewed``). All state writes go through
:func:`set_segment_review_status` inside a single transaction.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from weaver.errors import SegmentNotFoundError, WeaverError
from weaver.services.project_paths import resolve_database_path
from weaver.storage.db import connect_database, transaction

ReviewStatus = Literal[
    "not_reviewed",
    "needs_review",
    "needs_revision",
    "approved",
    "rejected",
]

_REVIEW_STATUSES = frozenset(
    {"not_reviewed", "needs_review", "needs_revision", "approved", "rejected"}
)


@dataclass(frozen=True)
class ReviewQueueItem:
    """One segment in the review queue."""

    segment_id: str
    chapter_id: str
    chapter_title: str | None
    block_order: int
    kind: str
    source_text: str
    translation: str | None
    translation_status: str
    review_status: str


@dataclass(frozen=True)
class ReviewCounts:
    """Per-chapter review count summary."""

    not_reviewed: int = 0
    needs_review: int = 0
    needs_revision: int = 0
    approved: int = 0
    rejected: int = 0


def set_segment_review_status(
    project_toml: Path,
    segment_id: str,
    review_status: str,
    *,
    cwd: Path | None = None,
) -> None:
    """Persist a review status for one segment.

    Args:
        project_toml: Path to the project's ``project.toml``.
        segment_id: Segment id to update.
        review_status: New review status (must be a canonical value).
        cwd: Working directory used to resolve project-relative paths.

    Raises:
        SegmentNotFoundError: If the segment does not exist.
        WeaverError: If ``review_status`` is not a canonical value.
    """

    if review_status not in _REVIEW_STATUSES:
        raise WeaverError(
            f"Invalid review status `{review_status}`. "
            f"Likely cause: the UI sent an unexpected status value. "
            f"Next command: use one of {sorted(_REVIEW_STATUSES)}."
        )

    db_path = resolve_database_path(project_toml, cwd=cwd)
    with closing(connect_database(db_path)) as connection:
        row = connection.execute("SELECT 1 FROM segments WHERE id = ?", (segment_id,)).fetchone()
        if row is None:
            raise SegmentNotFoundError(
                f"Segment '{segment_id}' was not found in this project. "
                "Likely cause: the segment id is wrong or the chapter was removed. "
                "Next command: open the chapter workspace to list segment ids."
            )
        with transaction(connection):
            connection.execute(
                "UPDATE segments SET review_status = ? WHERE id = ?",
                (review_status, segment_id),
            )


def get_segment_review_status(connection: sqlite3.Connection, *, segment_id: str) -> str:
    """Return the review status for one segment, or ``not_reviewed`` as default.

    Args:
        connection: Open SQLite connection.
        segment_id: Segment id to look up.

    Returns:
        Review status string (``not_reviewed`` if the column is missing).
    """

    try:
        row = connection.execute(
            "SELECT review_status FROM segments WHERE id = ?", (segment_id,)
        ).fetchone()
    except sqlite3.OperationalError:
        return "not_reviewed"
    if row is None:
        return "not_reviewed"
    return str(row["review_status"])


def list_review_queue(
    project_toml: Path,
    volume_id: int,
    *,
    status_filter: str | None = None,
    cwd: Path | None = None,
) -> list[ReviewQueueItem]:
    """List segments in a volume's review queue.

    Args:
        project_toml: Path to the project's ``project.toml``.
        volume_id: Volume whose segments are listed.
        status_filter: Optional review status to filter by.
        cwd: Working directory used to resolve project-relative paths.

    Returns:
        Review queue items ordered by chapter spine order then block order.
    """

    db_path = resolve_database_path(project_toml, cwd=cwd)
    with closing(connect_database(db_path)) as connection:
        clauses = "c.volume_id = ?"
        params: list[object] = [volume_id]
        if status_filter and status_filter in _REVIEW_STATUSES:
            clauses += " AND s.review_status = ?"
            params.append(status_filter)

        rows = connection.execute(
            f"""
            SELECT
              s.id AS segment_id,
              s.chapter_id,
              c.title AS chapter_title,
              s.block_order,
              s.kind,
              s.source_text,
              s.status AS translation_status,
              COALESCE(s.review_status, 'not_reviewed') AS review_status,
              (
                SELECT t.text
                FROM translations t
                WHERE t.segment_id = s.id
                ORDER BY t.attempt DESC
                LIMIT 1
              ) AS latest_translation
            FROM segments s
            JOIN chapters c ON c.id = s.chapter_id
            WHERE {clauses}
            ORDER BY c.spine_order, s.block_order
            """,
            params,
        ).fetchall()

        return [
            ReviewQueueItem(
                segment_id=str(row["segment_id"]),
                chapter_id=str(row["chapter_id"]),
                chapter_title=row["chapter_title"],
                block_order=int(row["block_order"]),
                kind=str(row["kind"]),
                source_text=str(row["source_text"]),
                translation=None
                if row["latest_translation"] is None
                else str(row["latest_translation"]),
                translation_status=str(row["translation_status"]),
                review_status=str(row["review_status"]),
            )
            for row in rows
        ]


def review_counts_for_volume(connection: sqlite3.Connection, *, volume_id: int) -> ReviewCounts:
    """Return review-status tallies for every segment in a volume.

    Args:
        connection: Open SQLite connection.
        volume_id: Volume whose counts are returned.

    Returns:
        ReviewCounts with per-status totals.
    """

    try:
        rows = connection.execute(
            """
            SELECT COALESCE(s.review_status, 'not_reviewed') AS review_status,
                   COUNT(*) AS cnt
            FROM segments s
            JOIN chapters c ON c.id = s.chapter_id
            WHERE c.volume_id = ?
            GROUP BY s.review_status
            """,
            (volume_id,),
        ).fetchall()
    except sqlite3.OperationalError:
        return ReviewCounts()

    counts: dict[str, int] = {}
    for row in rows:
        counts[str(row["review_status"])] = int(row["cnt"])
    return ReviewCounts(
        not_reviewed=counts.get("not_reviewed", 0),
        needs_review=counts.get("needs_review", 0),
        needs_revision=counts.get("needs_revision", 0),
        approved=counts.get("approved", 0),
        rejected=counts.get("rejected", 0),
    )
