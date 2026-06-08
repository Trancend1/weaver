"""Volume repository functions.

A Volume is one imported source file (EPUB/TXT/HTML) inside a Novel (project).
Chapters belong to a volume; a novel may hold several volumes in reading order.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

VolumeFormat = Literal["epub", "txt", "html"]


@dataclass(frozen=True)
class VolumeRecord:
    """Stored volume row."""

    id: int
    project_id: int
    title: str
    source_path: str
    source_format: str
    volume_order: int


def create_volume(
    connection: sqlite3.Connection,
    *,
    project_id: int,
    title: str,
    source_path: str,
    source_format: VolumeFormat,
    volume_order: int | None = None,
) -> int:
    """Insert one volume into a novel.

    Args:
        connection: Open writable SQLite connection.
        project_id: Owning project (novel) id.
        title: Volume display title.
        source_path: Path to the imported source file.
        source_format: Source format (``epub`` | ``txt`` | ``html``).
        volume_order: Reading-order index; appended after existing volumes when None.

    Returns:
        Integer volume id.
    """

    order = volume_order if volume_order is not None else _next_volume_order(connection, project_id)
    cursor = connection.execute(
        """
        INSERT INTO volumes (
          project_id, title, source_path, source_format, volume_order, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            project_id,
            title,
            source_path,
            source_format,
            order,
            datetime.now(UTC).isoformat(),
        ),
    )
    if cursor.lastrowid is None:
        raise RuntimeError("Volume insert did not return a row id")
    return int(cursor.lastrowid)


def list_volumes(connection: sqlite3.Connection, project_id: int) -> list[VolumeRecord]:
    """List a novel's volumes in reading order.

    Args:
        connection: Open SQLite connection.
        project_id: Owning project (novel) id.

    Returns:
        Volume records ordered by ``volume_order``.
    """

    rows = connection.execute(
        """
        SELECT id, project_id, title, source_path, source_format, volume_order
        FROM volumes
        WHERE project_id = ?
        ORDER BY volume_order, id
        """,
        (project_id,),
    ).fetchall()
    return [_volume_from_row(row) for row in rows]


def get_volume(connection: sqlite3.Connection, volume_id: int) -> VolumeRecord:
    """Load one volume by id.

    Args:
        connection: Open SQLite connection.
        volume_id: Volume row id.

    Returns:
        VolumeRecord for the requested volume.

    Raises:
        LookupError: If the volume does not exist.
    """

    row = connection.execute(
        """
        SELECT id, project_id, title, source_path, source_format, volume_order
        FROM volumes
        WHERE id = ?
        """,
        (volume_id,),
    ).fetchone()
    if row is None:
        raise LookupError(f"Volume not found: {volume_id}")
    return _volume_from_row(row)


def delete_volume(connection: sqlite3.Connection, volume_id: int) -> None:
    """Delete one volume and every row that depends on it (Sprint H3).

    Removes, in dependency order: ``qa_warnings`` → ``translations`` →
    ``segments`` → ``chapters`` → the ``volume`` row. Project-scoped data
    (glossary, characters, translation memory) is **not** touched — those live
    at the project level and survive a single-volume delete.

    The caller is responsible for opening a transaction; this function assumes
    it runs inside one.

    Args:
        connection: Open writable SQLite connection.
        volume_id: Volume row id. A volume that does not exist is a no-op.
    """
    chapter_rows = connection.execute(
        "SELECT id FROM chapters WHERE volume_id = ?", (volume_id,)
    ).fetchall()
    chapter_ids = [str(row["id"]) for row in chapter_rows]
    if chapter_ids:
        placeholders = ",".join("?" for _ in chapter_ids)
        # qa_warnings ← translations ← segments are referenced via segment_id.
        # Resolve the segment ids once so each delete uses a small IN list.
        segment_rows = connection.execute(
            f"SELECT id FROM segments WHERE chapter_id IN ({placeholders})",
            tuple(chapter_ids),
        ).fetchall()
        segment_ids = [str(row["id"]) for row in segment_rows]
        if segment_ids:
            seg_placeholders = ",".join("?" for _ in segment_ids)
            connection.execute(
                f"DELETE FROM qa_warnings WHERE segment_id IN ({seg_placeholders})",
                tuple(segment_ids),
            )
            connection.execute(
                f"DELETE FROM translations WHERE segment_id IN ({seg_placeholders})",
                tuple(segment_ids),
            )
            connection.execute(
                f"DELETE FROM segments WHERE id IN ({seg_placeholders})",
                tuple(segment_ids),
            )
        connection.execute(
            f"DELETE FROM chapters WHERE id IN ({placeholders})",
            tuple(chapter_ids),
        )
    # Sprint J2 — preservation snapshot rows (Phase F ParsedEpub mirror) belong
    # to the volume, never to project-scoped data, so they go with the volume.
    for snapshot_table in (
        "epub_snapshot_validation",
        "epub_snapshot_images",
        "epub_snapshot_navigation",
        "epub_snapshot_spine",
        "epub_snapshot_manifest",
        "epub_snapshots",
    ):
        connection.execute(f"DELETE FROM {snapshot_table} WHERE volume_id = ?", (volume_id,))
    connection.execute("DELETE FROM volumes WHERE id = ?", (volume_id,))


def _next_volume_order(connection: sqlite3.Connection, project_id: int) -> int:
    row = connection.execute(
        "SELECT COALESCE(MAX(volume_order) + 1, 0) AS next FROM volumes WHERE project_id = ?",
        (project_id,),
    ).fetchone()
    return int(row["next"])


def _volume_from_row(row: sqlite3.Row) -> VolumeRecord:
    return VolumeRecord(
        id=int(row["id"]),
        project_id=int(row["project_id"]),
        title=str(row["title"]),
        source_path=str(row["source_path"]),
        source_format=str(row["source_format"]),
        volume_order=int(row["volume_order"]),
    )
