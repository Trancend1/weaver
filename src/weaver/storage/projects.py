"""Project repository functions."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime

from weaver.storage.db import SCHEMA_VERSION


@dataclass(frozen=True)
class ProjectRecord:
    """Stored project row."""

    id: int
    name: str
    source_path: str
    source_lang: str
    target_lang: str
    schema_version: int


def create_project(
    connection: sqlite3.Connection,
    *,
    name: str,
    source_path: str,
    source_lang: str,
    target_lang: str,
) -> int:
    """Create or reuse a project row.

    Args:
        connection: Open writable SQLite connection.
        name: Project display name.
        source_path: Source EPUB path as stored in project state.
        source_lang: Source language tag.
        target_lang: Target language tag.

    Returns:
        Integer project id.
    """

    existing = connection.execute(
        """
        SELECT id FROM projects
        WHERE name = ? AND source_path = ? AND source_lang = ? AND target_lang = ?
        ORDER BY id
        LIMIT 1
        """,
        (name, source_path, source_lang, target_lang),
    ).fetchone()
    if existing is not None:
        return int(existing["id"])

    cursor = connection.execute(
        """
        INSERT INTO projects (
          name,
          source_path,
          source_lang,
          target_lang,
          created_at,
          schema_version
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            name,
            source_path,
            source_lang,
            target_lang,
            datetime.now(UTC).isoformat(),
            SCHEMA_VERSION,
        ),
    )
    if cursor.lastrowid is None:
        raise RuntimeError("Project insert did not return a row id")
    return int(cursor.lastrowid)


def get_project(connection: sqlite3.Connection, project_id: int) -> ProjectRecord:
    """Load a project row by id.

    Args:
        connection: Open SQLite connection.
        project_id: Project row id.

    Returns:
        ProjectRecord for the requested project.

    Raises:
        LookupError: If the project does not exist.
    """

    row = connection.execute(
        """
        SELECT id, name, source_path, source_lang, target_lang, schema_version
        FROM projects
        WHERE id = ?
        """,
        (project_id,),
    ).fetchone()
    if row is None:
        raise LookupError(f"Project not found: {project_id}")
    return ProjectRecord(
        id=int(row["id"]),
        name=str(row["name"]),
        source_path=str(row["source_path"]),
        source_lang=str(row["source_lang"]),
        target_lang=str(row["target_lang"]),
        schema_version=int(row["schema_version"]),
    )
