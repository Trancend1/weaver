"""Schema migration tests."""

from __future__ import annotations

import sqlite3

from weaver.storage.db import SCHEMA_VERSION, initialize_database
from weaver.storage.migrations import apply_migrations


def test_fresh_database_lands_at_target_version(tmp_path) -> None:
    db_path = tmp_path / "fresh.db"

    with initialize_database(db_path) as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(translations)").fetchall()
        }

    assert version == SCHEMA_VERSION
    assert "input_tokens" in columns
    assert "output_tokens" in columns


def test_apply_migrations_upgrades_v1_to_v2(tmp_path) -> None:
    db_path = tmp_path / "legacy.db"
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        CREATE TABLE translations (
          segment_id TEXT,
          attempt INTEGER NOT NULL,
          text TEXT NOT NULL,
          source_hash TEXT NOT NULL,
          provider TEXT NOT NULL,
          model TEXT NOT NULL,
          created_at TEXT NOT NULL,
          raw_response TEXT,
          PRIMARY KEY (segment_id, attempt)
        );
        """
    )
    connection.execute("PRAGMA user_version = 1")
    connection.commit()

    apply_migrations(connection, target_version=SCHEMA_VERSION)

    columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(translations)").fetchall()
    }
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    connection.close()

    assert "input_tokens" in columns
    assert "output_tokens" in columns
    assert version == SCHEMA_VERSION


def test_apply_migrations_is_idempotent(tmp_path) -> None:
    db_path = tmp_path / "fresh.db"
    with initialize_database(db_path) as connection:
        apply_migrations(connection, target_version=SCHEMA_VERSION)
        apply_migrations(connection, target_version=SCHEMA_VERSION)
        version = connection.execute("PRAGMA user_version").fetchone()[0]

    assert version == SCHEMA_VERSION
