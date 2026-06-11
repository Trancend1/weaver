"""Read-only segment listing for the Content Explorer (Sprint Q9).

Lists a volume's chapters with per-chapter status/review counts, and one
chapter's segments as a filtered, paginated page. Pure project-DB reads via
``connect_readonly_database`` — no snapshot access, no source-file access, no
QA scan, no provider call, no writes.

The exporter/QA "publishable" semantics are NOT re-derived here: this surface
reports raw ``status`` / ``review_status`` values only (presentation maps them
to badges).
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from weaver.errors import VolumeNotFoundError
from weaver.services.project_paths import resolve_database_path
from weaver.storage.db import connect_readonly_database

DEFAULT_PAGE_SIZE = 50
_MAX_PAGE_SIZE = 200

# Valid filter values mirror the schema CHECK constraints (never renamed).
SEGMENT_STATUSES = (
    "pending",
    "in_progress",
    "translated",
    "failed",
    "stale",
    "skipped",
    "manual",
)
REVIEW_STATUSES = (
    "not_reviewed",
    "needs_review",
    "needs_revision",
    "approved",
    "rejected",
)


@dataclass(frozen=True)
class ChapterSegmentSummary:
    """One chapter with its segment status/review counts (for the chapter rail)."""

    chapter_id: str
    title: str | None
    spine_order: int
    segment_count: int
    status_counts: dict[str, int]
    review_counts: dict[str, int]


@dataclass(frozen=True)
class SegmentListRow:
    """One segment row in the explorer's Segments tab."""

    id: str
    chapter_id: str
    block_order: int
    kind: str
    status: str
    review_status: str


@dataclass(frozen=True)
class SegmentPage:
    """One filtered, paginated page of a chapter's segments."""

    chapter_id: str
    rows: list[SegmentListRow]
    total: int
    page: int
    page_size: int

    @property
    def page_count(self) -> int:
        if self.total == 0:
            return 1
        return -(-self.total // self.page_size)

    @property
    def has_prev(self) -> bool:
        return self.page > 1

    @property
    def has_next(self) -> bool:
        return self.page < self.page_count


@dataclass(frozen=True)
class VolumeSegmentListing:
    """Chapters of one volume + the selected chapter's segment page."""

    volume_id: int
    chapters: list[ChapterSegmentSummary]
    page: SegmentPage | None  # None when the volume has no chapters
    status_filter: str
    review_filter: str
    kind_filter: str
    kinds: list[str]  # distinct kinds present in the selected chapter


def list_volume_segments(
    project_toml: Path,
    volume_id: int,
    *,
    chapter_id: str | None = None,
    status: str = "",
    review_status: str = "",
    kind: str = "",
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    cwd: Path | None = None,
) -> VolumeSegmentListing:
    """Build the Segments-tab read model for one volume.

    Args:
        project_toml: Path to the project's ``project.toml``.
        volume_id: Volume whose chapters/segments are listed.
        chapter_id: Selected chapter; defaults to the volume's first chapter
            in spine order. An unknown id falls back to the first chapter.
        status: Optional segment-status filter (ignored when not a known value).
        review_status: Optional review-status filter (same rule).
        kind: Optional segment-kind filter (free-form; matched exactly).
        page: 1-based page number (clamped to valid range).
        page_size: Rows per page (clamped to 1..200).
        cwd: Working directory used to resolve project-relative paths.

    Returns:
        A :class:`VolumeSegmentListing`. Raises :class:`VolumeNotFoundError`
        when the volume does not exist.
    """

    safe_status = status if status in SEGMENT_STATUSES else ""
    safe_review = review_status if review_status in REVIEW_STATUSES else ""
    safe_kind = kind.strip()
    safe_page_size = max(1, min(int(page_size), _MAX_PAGE_SIZE))

    db_path = resolve_database_path(project_toml, cwd=cwd)
    with closing(connect_readonly_database(db_path)) as connection:
        _assert_volume_exists(connection, volume_id)
        chapters = _chapter_summaries(connection, volume_id)

        selected = None
        if chapter_id is not None:
            selected = next((c for c in chapters if c.chapter_id == chapter_id), None)
        if selected is None and chapters:
            selected = chapters[0]

        if selected is None:
            return VolumeSegmentListing(
                volume_id=volume_id,
                chapters=[],
                page=None,
                status_filter=safe_status,
                review_filter=safe_review,
                kind_filter=safe_kind,
                kinds=[],
            )

        kinds = _chapter_kinds(connection, selected.chapter_id)
        segment_page = _segment_page(
            connection,
            selected.chapter_id,
            status=safe_status,
            review_status=safe_review,
            kind=safe_kind,
            page=page,
            page_size=safe_page_size,
        )

    return VolumeSegmentListing(
        volume_id=volume_id,
        chapters=chapters,
        page=segment_page,
        status_filter=safe_status,
        review_filter=safe_review,
        kind_filter=safe_kind,
        kinds=kinds,
    )


def _assert_volume_exists(connection: sqlite3.Connection, volume_id: int) -> None:
    row = connection.execute("SELECT id FROM volumes WHERE id = ?", (volume_id,)).fetchone()
    if row is None:
        raise VolumeNotFoundError(
            f"No volume with id {volume_id}. "
            "Likely cause: the volume was deleted or the link is stale. "
            "Next command: open the project page to list volumes."
        )


def _chapter_summaries(
    connection: sqlite3.Connection, volume_id: int
) -> list[ChapterSegmentSummary]:
    chapter_rows = connection.execute(
        """
        SELECT id, title, spine_order FROM chapters
        WHERE volume_id = ? ORDER BY spine_order, id
        """,
        (volume_id,),
    ).fetchall()

    status_rows = connection.execute(
        """
        SELECT s.chapter_id AS chapter_id, s.status AS bucket, COUNT(*) AS count
        FROM segments s JOIN chapters c ON c.id = s.chapter_id
        WHERE c.volume_id = ?
        GROUP BY s.chapter_id, s.status
        """,
        (volume_id,),
    ).fetchall()
    review_rows = connection.execute(
        """
        SELECT s.chapter_id AS chapter_id, s.review_status AS bucket, COUNT(*) AS count
        FROM segments s JOIN chapters c ON c.id = s.chapter_id
        WHERE c.volume_id = ?
        GROUP BY s.chapter_id, s.review_status
        """,
        (volume_id,),
    ).fetchall()

    status_by_chapter: dict[str, dict[str, int]] = {}
    for row in status_rows:
        status_by_chapter.setdefault(str(row["chapter_id"]), {})[str(row["bucket"])] = int(
            row["count"]
        )
    review_by_chapter: dict[str, dict[str, int]] = {}
    for row in review_rows:
        review_by_chapter.setdefault(str(row["chapter_id"]), {})[str(row["bucket"])] = int(
            row["count"]
        )

    summaries: list[ChapterSegmentSummary] = []
    for row in chapter_rows:
        cid = str(row["id"])
        status_counts = status_by_chapter.get(cid, {})
        summaries.append(
            ChapterSegmentSummary(
                chapter_id=cid,
                title=str(row["title"]) if row["title"] is not None else None,
                spine_order=int(row["spine_order"]),
                segment_count=sum(status_counts.values()),
                status_counts=status_counts,
                review_counts=review_by_chapter.get(cid, {}),
            )
        )
    return summaries


def _chapter_kinds(connection: sqlite3.Connection, chapter_id: str) -> list[str]:
    return [
        str(row["kind"])
        for row in connection.execute(
            "SELECT DISTINCT kind FROM segments WHERE chapter_id = ? ORDER BY kind",
            (chapter_id,),
        ).fetchall()
    ]


def _segment_page(
    connection: sqlite3.Connection,
    chapter_id: str,
    *,
    status: str,
    review_status: str,
    kind: str,
    page: int,
    page_size: int,
) -> SegmentPage:
    where = ["chapter_id = ?"]
    params: list[object] = [chapter_id]
    if status:
        where.append("status = ?")
        params.append(status)
    if review_status:
        where.append("review_status = ?")
        params.append(review_status)
    if kind:
        where.append("kind = ?")
        params.append(kind)
    where_sql = " AND ".join(where)

    total_row = connection.execute(
        f"SELECT COUNT(*) AS count FROM segments WHERE {where_sql}", params
    ).fetchone()
    total = int(total_row["count"]) if total_row is not None else 0

    page_count = max(1, -(-total // page_size))
    safe_page = max(1, min(int(page), page_count))
    offset = (safe_page - 1) * page_size

    rows = connection.execute(
        f"""
        SELECT id, chapter_id, block_order, kind, status, review_status
        FROM segments WHERE {where_sql}
        ORDER BY block_order, id
        LIMIT ? OFFSET ?
        """,
        [*params, page_size, offset],
    ).fetchall()

    return SegmentPage(
        chapter_id=chapter_id,
        rows=[
            SegmentListRow(
                id=str(row["id"]),
                chapter_id=str(row["chapter_id"]),
                block_order=int(row["block_order"]),
                kind=str(row["kind"]),
                status=str(row["status"]),
                review_status=str(row["review_status"]),
            )
            for row in rows
        ],
        total=total,
        page=safe_page,
        page_size=page_size,
    )
