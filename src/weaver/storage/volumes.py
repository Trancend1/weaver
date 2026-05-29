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
