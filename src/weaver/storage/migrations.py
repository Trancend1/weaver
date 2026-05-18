"""SQLite schema migrations.

Migrations are tracked via `PRAGMA user_version`. A fresh database created
by `_apply_schema()` already matches the latest schema; in that case
`apply_migrations()` only stamps `user_version` and returns. Existing
databases at an earlier version run sequenced ALTER statements.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable

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


_MIGRATIONS: dict[int, Callable[[sqlite3.Connection], None]] = {
    2: _migrate_to_v2,
}
