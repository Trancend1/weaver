"""Character repository functions (schema v4).

Project-scoped character database keyed by Japanese name
(``UNIQUE(project_id, jp_name)``). Powers translation name consistency; the
prompt-injection wiring lands in Stage 5C.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class CharacterRecord:
    """Stored character row (project-scoped, keyed by jp_name)."""

    jp_name: str
    en_name: str
    gender: str | None
    role: str | None
    notes: str | None


def list_characters(connection: sqlite3.Connection, *, project_id: int) -> list[CharacterRecord]:
    """Load all characters for a project in stable insertion (id) order."""

    rows = connection.execute(
        """
        SELECT jp_name, en_name, gender, role, notes
        FROM characters
        WHERE project_id = ?
        ORDER BY id
        """,
        (project_id,),
    ).fetchall()
    return [_from_row(row) for row in rows]


def get_character(
    connection: sqlite3.Connection, *, project_id: int, jp_name: str
) -> CharacterRecord | None:
    """Load one character by Japanese name, or None if absent."""

    row = connection.execute(
        """
        SELECT jp_name, en_name, gender, role, notes
        FROM characters
        WHERE project_id = ? AND jp_name = ?
        """,
        (project_id, jp_name),
    ).fetchone()
    if row is None:
        return None
    return _from_row(row)


def upsert_character(
    connection: sqlite3.Connection,
    *,
    project_id: int,
    jp_name: str,
    en_name: str,
    gender: str | None = None,
    role: str | None = None,
    notes: str | None = None,
) -> CharacterRecord:
    """Insert or update one character (UNIQUE(project_id, jp_name) → upsert)."""

    connection.execute(
        """
        INSERT INTO characters (project_id, jp_name, en_name, gender, role, notes)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(project_id, jp_name) DO UPDATE SET
          en_name = excluded.en_name,
          gender = excluded.gender,
          role = excluded.role,
          notes = excluded.notes
        """,
        (project_id, jp_name, en_name, gender, role, notes),
    )
    stored = get_character(connection, project_id=project_id, jp_name=jp_name)
    if stored is None:  # pragma: no cover - upsert always yields a row
        raise RuntimeError("Character upsert did not persist a row")
    return stored


def delete_character(connection: sqlite3.Connection, *, project_id: int, jp_name: str) -> bool:
    """Delete one character by Japanese name; return whether a row was removed."""

    cursor = connection.execute(
        "DELETE FROM characters WHERE project_id = ? AND jp_name = ?",
        (project_id, jp_name),
    )
    return cursor.rowcount > 0


def _from_row(row: sqlite3.Row) -> CharacterRecord:
    return CharacterRecord(
        jp_name=str(row["jp_name"]),
        en_name=str(row["en_name"]),
        gender=_optional_str(row["gender"]),
        role=_optional_str(row["role"]),
        notes=_optional_str(row["notes"]),
    )


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)
