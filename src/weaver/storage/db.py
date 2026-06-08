"""SQLite connection, migration, and transaction helpers."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from weaver.errors import DatabaseError
from weaver.storage.migrations import apply_migrations

SCHEMA_VERSION = 7
SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def initialize_database(path: Path) -> sqlite3.Connection:
    """Create or migrate a project database and reset interrupted segments.

    Args:
        path: Database file path.

    Returns:
        Open SQLite connection with row access by column name.

    Raises:
        DatabaseError: If schema setup fails.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    connection = _open_database(path)
    try:
        _apply_schema(connection)
        apply_migrations(connection, target_version=SCHEMA_VERSION)
        reset_interrupted_segments(connection)
        connection.commit()
    except sqlite3.Error as exc:
        connection.close()
        raise DatabaseError(
            "Failed to initialize Weaver database. "
            "Likely cause: SQLite could not apply schema or open the database file. "
            "Next command: remove the incomplete project directory and rerun "
            "`weaver init <input.epub>`."
        ) from exc
    return connection


def connect_database(path: Path) -> sqlite3.Connection:
    """Open an existing writable database and reset interrupted segments.

    Args:
        path: Database file path.

    Returns:
        Open SQLite connection with row access by column name.

    Raises:
        DatabaseError: If the database file does not exist or cannot be opened.
    """

    if not path.exists():
        raise DatabaseError(
            "Failed to open Weaver database. "
            f"Likely cause: database file '{path}' does not exist. "
            "Next command: run `weaver init <input.epub>` to create a project first."
        )
    connection = _open_database(path)
    try:
        apply_migrations(connection, target_version=SCHEMA_VERSION)
        reset_interrupted_segments(connection)
        connection.commit()
    except sqlite3.Error as exc:
        connection.close()
        raise DatabaseError(
            "Failed to open Weaver database. "
            "Likely cause: database file is locked or malformed. "
            "Next command: run `weaver inspect <project.toml>` with a valid project file."
        ) from exc
    return connection


def connect_readonly_database(path: Path) -> sqlite3.Connection:
    """Open an existing database in read-only mode.

    Args:
        path: Database file path.

    Returns:
        Read-only SQLite connection with row access by column name.

    Raises:
        DatabaseError: If the database cannot be opened read-only.
    """

    uri = path.resolve().as_uri() + "?mode=ro"
    try:
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        return connection
    except sqlite3.Error as exc:
        raise DatabaseError(
            "Failed to inspect Weaver database. "
            "Likely cause: database file is missing or unreadable. "
            "Next command: run `weaver init <input.epub>` to create a project first."
        ) from exc


@contextmanager
def transaction(connection: sqlite3.Connection) -> Iterator[None]:
    """Wrap a state mutation in one SQLite transaction.

    Args:
        connection: Open writable SQLite connection.

    Yields:
        None while the transaction is active.

    Raises:
        sqlite3.Error: If commit or rollback fails.
    """

    try:
        connection.execute("BEGIN")
        yield
    except sqlite3.Error:
        connection.rollback()
        raise
    else:
        connection.commit()


def reset_interrupted_segments(connection: sqlite3.Connection) -> int:
    """Reset interrupted `in_progress` segments back to `pending`.

    Args:
        connection: Open writable SQLite connection.

    Returns:
        Number of rows updated.
    """

    cursor = connection.execute(
        "UPDATE segments SET status = 'pending' WHERE status = 'in_progress'"
    )
    return cursor.rowcount


def _open_database(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _apply_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
