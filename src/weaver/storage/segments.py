"""Segment and chapter repository functions."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Literal

from weaver.core.ir import DocumentIR
from weaver.core.segment import compute_source_hash

SegmentStatus = Literal[
    "pending",
    "in_progress",
    "translated",
    "failed",
    "stale",
    "skipped",
    "manual",
]


@dataclass(frozen=True)
class SegmentRecord:
    """Stored segment row."""

    id: str
    chapter_id: str
    block_order: int
    kind: str
    source_text: str
    source_hash: str
    status: str


def sync_document_segments(
    connection: sqlite3.Connection, *, project_id: int, volume_id: int, document: DocumentIR
) -> None:
    """Persist chapters and segments from DocumentIR.

    Args:
        connection: Open writable SQLite connection.
        project_id: Project (novel) row id.
        volume_id: Owning volume row id; chapters are attached to this volume.
        document: Source document IR emitted by a reader.

    Returns:
        None.
    """

    for chapter in document.chapters:
        connection.execute(
            """
            INSERT INTO chapters (id, project_id, volume_id, title, href, spine_order)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              project_id = excluded.project_id,
              volume_id = excluded.volume_id,
              title = excluded.title,
              href = excluded.href,
              spine_order = excluded.spine_order
            """,
            (chapter.id, project_id, volume_id, chapter.title, chapter.href, chapter.order),
        )
        for block in chapter.blocks:
            insert_segment(
                connection,
                segment_id=block.id,
                chapter_id=chapter.id,
                block_order=block.order,
                kind=block.kind,
                source_text=block.source_text,
                source_hash=compute_source_hash(block.normalized_source_text),
            )


def insert_segment(
    connection: sqlite3.Connection,
    *,
    segment_id: str,
    chapter_id: str,
    block_order: int,
    kind: str,
    source_text: str,
    source_hash: str,
    status: SegmentStatus = "pending",
) -> None:
    """Insert or refresh one segment.

    Args:
        connection: Open writable SQLite connection.
        segment_id: Stable segment id.
        chapter_id: Parent chapter id.
        block_order: 0-indexed block order.
        kind: Block kind.
        source_text: Original source text.
        source_hash: SHA-256 source hash.
        status: Initial status for a new segment.

    Returns:
        None.
    """

    existing = connection.execute(
        "SELECT source_hash FROM segments WHERE id = ?", (segment_id,)
    ).fetchone()
    if existing is None:
        connection.execute(
            """
            INSERT INTO segments (
              id,
              chapter_id,
              block_order,
              kind,
              source_text,
              source_hash,
              status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (segment_id, chapter_id, block_order, kind, source_text, source_hash, status),
        )
        return

    next_status = "stale" if str(existing["source_hash"]) != source_hash else status
    connection.execute(
        """
        UPDATE segments
        SET chapter_id = ?,
            block_order = ?,
            kind = ?,
            source_text = ?,
            source_hash = ?,
            status = CASE WHEN ? = 'stale' THEN 'stale' ELSE status END
        WHERE id = ?
        """,
        (chapter_id, block_order, kind, source_text, source_hash, next_status, segment_id),
    )


def update_segment_status(
    connection: sqlite3.Connection, *, segment_id: str, status: SegmentStatus
) -> None:
    """Update one segment status.

    Args:
        connection: Open writable SQLite connection.
        segment_id: Segment id to update.
        status: New segment status.

    Returns:
        None.
    """

    connection.execute("UPDATE segments SET status = ? WHERE id = ?", (status, segment_id))


def list_pending_segments(
    connection: sqlite3.Connection, *, project_id: int
) -> list[SegmentRecord]:
    """List pending segments in spine order.

    Args:
        connection: Open SQLite connection.
        project_id: Project row id.

    Returns:
        Pending segments ordered by chapter spine order and block order.
    """

    rows = connection.execute(
        """
        SELECT s.id, s.chapter_id, s.block_order, s.kind, s.source_text, s.source_hash, s.status
        FROM segments s
        JOIN chapters c ON c.id = s.chapter_id
        WHERE c.project_id = ? AND s.status = 'pending'
        ORDER BY c.spine_order, s.block_order
        """,
        (project_id,),
    ).fetchall()
    return [_segment_from_row(row) for row in rows]


def list_segments_for_translation(
    connection: sqlite3.Connection, *, project_id: int, retry_failed: bool = False
) -> list[SegmentRecord]:
    """List segments selected by `weaver translate`.

    Args:
        connection: Open SQLite connection.
        project_id: Project row id.
        retry_failed: When true, select failed segments instead of pending ones.

    Returns:
        Translation targets ordered by chapter spine order and block order.
    """

    status = "failed" if retry_failed else "pending"
    rows = connection.execute(
        """
        SELECT s.id, s.chapter_id, s.block_order, s.kind, s.source_text, s.source_hash, s.status
        FROM segments s
        JOIN chapters c ON c.id = s.chapter_id
        WHERE c.project_id = ? AND s.status = ?
        ORDER BY c.spine_order, s.block_order
        """,
        (project_id, status),
    ).fetchall()
    return [_segment_from_row(row) for row in rows]


def list_chapter_segments(
    connection: sqlite3.Connection, *, chapter_id: str
) -> list[SegmentRecord]:
    """List all of one chapter's segments in block order.

    Translation target selection (which statuses are eligible) is applied by the
    caller per requested mode; this returns the full chapter so the caller can
    also count what was skipped.

    Args:
        connection: Open SQLite connection.
        chapter_id: Chapter id whose segments are listed.

    Returns:
        All chapter segments ordered by block order.
    """

    rows = connection.execute(
        """
        SELECT id, chapter_id, block_order, kind, source_text, source_hash, status
        FROM segments
        WHERE chapter_id = ?
        ORDER BY block_order
        """,
        (chapter_id,),
    ).fetchall()
    return [_segment_from_row(row) for row in rows]


def chapter_exists(connection: sqlite3.Connection, chapter_id: str) -> bool:
    """Return whether a chapter row exists.

    Args:
        connection: Open SQLite connection.
        chapter_id: Chapter id to check.

    Returns:
        True if the chapter exists, otherwise False.
    """

    row = connection.execute("SELECT 1 FROM chapters WHERE id = ?", (chapter_id,)).fetchone()
    return row is not None


def list_chapter_ids_for_volume(connection: sqlite3.Connection, volume_id: int) -> list[str]:
    """List a volume's chapter ids in reading order.

    Args:
        connection: Open SQLite connection.
        volume_id: Owning volume row id.

    Returns:
        Chapter ids ordered by ``spine_order``.
    """

    rows = connection.execute(
        "SELECT id FROM chapters WHERE volume_id = ? ORDER BY spine_order, id",
        (volume_id,),
    ).fetchall()
    return [str(row["id"]) for row in rows]


def list_chapter_ids_for_project(connection: sqlite3.Connection, project_id: int) -> list[str]:
    """List a novel's chapter ids across all volumes in reading order.

    Args:
        connection: Open SQLite connection.
        project_id: Owning project (novel) row id.

    Returns:
        Chapter ids ordered by volume reading order then ``spine_order``.
    """

    rows = connection.execute(
        """
        SELECT c.id AS id
        FROM chapters c
        JOIN volumes v ON v.id = c.volume_id
        WHERE c.project_id = ?
        ORDER BY v.volume_order, v.id, c.spine_order, c.id
        """,
        (project_id,),
    ).fetchall()
    return [str(row["id"]) for row in rows]


def get_segment(connection: sqlite3.Connection, segment_id: str) -> SegmentRecord | None:
    """Return one segment row by id, or None if it does not exist.

    Args:
        connection: Open SQLite connection.
        segment_id: Segment id to look up.

    Returns:
        SegmentRecord if the segment exists, otherwise None.
    """

    row = connection.execute(
        """
        SELECT id, chapter_id, block_order, kind, source_text, source_hash, status
        FROM segments
        WHERE id = ?
        """,
        (segment_id,),
    ).fetchone()
    if row is None:
        return None
    return _segment_from_row(row)


def reset_in_progress_segments(connection: sqlite3.Connection) -> int:
    """Reset interrupted segments to pending.

    Args:
        connection: Open writable SQLite connection.

    Returns:
        Number of segments reset.
    """

    cursor = connection.execute(
        "UPDATE segments SET status = 'pending' WHERE status = 'in_progress'"
    )
    return cursor.rowcount


def _segment_from_row(row: sqlite3.Row) -> SegmentRecord:
    return SegmentRecord(
        id=str(row["id"]),
        chapter_id=str(row["chapter_id"]),
        block_order=int(row["block_order"]),
        kind=str(row["kind"]),
        source_text=str(row["source_text"]),
        source_hash=str(row["source_hash"]),
        status=str(row["status"]),
    )
