"""SQLite schema migrations.

Migrations are tracked via `PRAGMA user_version`. A fresh database created
by `_apply_schema()` already matches the latest schema; in that case
`apply_migrations()` only stamps `user_version` and returns. Existing
databases at an earlier version run sequenced ALTER statements.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime

from weaver.errors import DatabaseError


def apply_migrations(connection: sqlite3.Connection, *, target_version: int) -> int:
    """Bring the connected database up to `target_version`.

    Args:
        connection: Open writable SQLite connection.
        target_version: Latest schema version known to this build.

    Returns:
        Final `user_version` after migrations are applied.

    Raises:
        DatabaseError: If the database is at a version newer than this build
            knows how to handle, or if an individual migration step fails.
    """

    current = _user_version(connection)
    if current == target_version:
        return current
    if current > target_version:
        raise DatabaseError(
            f"Weaver database is at schema version {current} but this build "
            f"only supports up to {target_version}. "
            "Likely cause: a newer Weaver wrote this project. "
            "Next command: upgrade `weaver` to the version that created this project."
        )
    if current == 0:
        connection.execute(f"PRAGMA user_version = {target_version}")
        return target_version

    for step in range(current + 1, target_version + 1):
        migrator = _MIGRATIONS.get(step)
        if migrator is None:
            raise DatabaseError(
                f"No migration registered for schema version {step}. "
                "Likely cause: build is missing a migration step. "
                "Next command: report this as a Weaver bug."
            )
        migrator(connection)
        connection.execute(f"PRAGMA user_version = {step}")
    return target_version


def _user_version(connection: sqlite3.Connection) -> int:
    row = connection.execute("PRAGMA user_version").fetchone()
    if row is None:
        return 0
    return int(row[0])


def _migrate_to_v2(connection: sqlite3.Connection) -> None:
    columns = {
        str(row["name"]) for row in connection.execute("PRAGMA table_info(translations)").fetchall()
    }
    if "input_tokens" not in columns:
        connection.execute("ALTER TABLE translations ADD COLUMN input_tokens INTEGER")
    if "output_tokens" not in columns:
        connection.execute("ALTER TABLE translations ADD COLUMN output_tokens INTEGER")


def _migrate_to_v3(connection: sqlite3.Connection) -> None:
    """Introduce the Volume tier (schema v3).

    Adds the ``volumes`` table and ``chapters.volume_id``, then wraps every
    existing project's chapters in one synthesized default volume so legacy
    (project = one EPUB) databases gain a Novel -> Volume -> Chapter shape
    without losing data.
    """

    tables = {
        str(row["name"])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    if "volumes" not in tables:
        connection.execute(
            """
            CREATE TABLE volumes (
              id INTEGER PRIMARY KEY,
              project_id INTEGER NOT NULL REFERENCES projects(id),
              title TEXT NOT NULL,
              source_path TEXT NOT NULL,
              source_format TEXT NOT NULL CHECK (source_format IN ('epub', 'txt', 'html')),
              volume_order INTEGER NOT NULL,
              created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_volumes_project ON volumes(project_id, volume_order)"
        )

    if "chapters" not in tables:
        # Partial/legacy database without the chapters table; nothing to backfill.
        return

    chapter_columns = {
        str(row["name"]) for row in connection.execute("PRAGMA table_info(chapters)").fetchall()
    }
    if "volume_id" not in chapter_columns:
        connection.execute("ALTER TABLE chapters ADD COLUMN volume_id INTEGER")
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_chapters_volume ON chapters(volume_id, spine_order)"
        )

    if "projects" not in tables:
        return

    created_at = datetime.now(UTC).isoformat()
    for project in connection.execute("SELECT id, name, source_path FROM projects").fetchall():
        project_id = int(project["id"])
        has_orphan_chapters = connection.execute(
            "SELECT 1 FROM chapters WHERE project_id = ? AND volume_id IS NULL LIMIT 1",
            (project_id,),
        ).fetchone()
        if has_orphan_chapters is None:
            continue
        cursor = connection.execute(
            """
            INSERT INTO volumes (
              project_id, title, source_path, source_format, volume_order, created_at
            )
            VALUES (?, ?, ?, 'epub', 0, ?)
            """,
            (project_id, str(project["name"]), str(project["source_path"]), created_at),
        )
        if cursor.lastrowid is None:
            raise DatabaseError(
                "Default volume insert did not return a row id during v3 migration. "
                "Likely cause: SQLite did not report lastrowid. "
                "Next command: report this as a Weaver bug."
            )
        connection.execute(
            "UPDATE chapters SET volume_id = ? WHERE project_id = ? AND volume_id IS NULL",
            (int(cursor.lastrowid), project_id),
        )


def _migrate_to_v4(connection: sqlite3.Connection) -> None:
    """Add the project-scoped ``characters`` table (schema v4).

    Character database for translation consistency. Idempotent: only creates the
    table and its index when absent, leaving existing project data untouched.
    """

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS characters (
          id INTEGER PRIMARY KEY,
          project_id INTEGER REFERENCES projects(id),
          jp_name TEXT NOT NULL,
          en_name TEXT NOT NULL,
          gender TEXT,
          role TEXT,
          notes TEXT,
          UNIQUE(project_id, jp_name)
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_characters_project ON characters(project_id, jp_name)"
    )


_MIGRATIONS: dict[int, Callable[[sqlite3.Connection], None]] = {
    2: _migrate_to_v2,
    3: _migrate_to_v3,
    4: _migrate_to_v4,
}
