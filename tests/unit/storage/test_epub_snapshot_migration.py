"""Tests for the v6 → v7 EPUB snapshot migration (Sprint J1)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from weaver.storage.db import SCHEMA_VERSION, initialize_database
from weaver.storage.migrations import apply_migrations

_V7_TABLES = {
    "epub_snapshots",
    "epub_snapshot_manifest",
    "epub_snapshot_spine",
    "epub_snapshot_navigation",
    "epub_snapshot_images",
    "epub_snapshot_validation",
}


def test_fresh_database_includes_v7_snapshot_tables(tmp_path: Path) -> None:
    with initialize_database(tmp_path / "weaver.db") as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert version == SCHEMA_VERSION
    assert _V7_TABLES.issubset(tables)


def test_legacy_v6_database_migrates_to_v7(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy_v6.db"
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    # Seed the bare minimum a v6 database needs: projects + volumes (so the
    # epub_snapshots FK constraint is satisfiable in any later test) and bump
    # user_version to 6.
    connection.executescript(
        """
        CREATE TABLE projects (
          id INTEGER PRIMARY KEY, name TEXT NOT NULL, source_path TEXT NOT NULL,
          source_lang TEXT NOT NULL, target_lang TEXT NOT NULL,
          created_at TEXT NOT NULL, schema_version INTEGER NOT NULL
        );
        CREATE TABLE volumes (
          id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES projects(id),
          title TEXT NOT NULL, source_path TEXT NOT NULL,
          source_format TEXT NOT NULL, volume_order INTEGER NOT NULL,
          created_at TEXT NOT NULL
        );
        PRAGMA user_version = 6;
        """
    )
    connection.commit()

    apply_migrations(connection, target_version=SCHEMA_VERSION)
    connection.commit()

    tables = {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    connection.close()

    assert version == SCHEMA_VERSION
    assert _V7_TABLES.issubset(tables)


def test_v7_migration_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "fresh.db"
    with initialize_database(db_path) as connection:
        apply_migrations(connection, target_version=SCHEMA_VERSION)
        apply_migrations(connection, target_version=SCHEMA_VERSION)
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert _V7_TABLES.issubset(tables)


def test_epub_snapshots_columns_have_expected_shape(tmp_path: Path) -> None:
    with initialize_database(tmp_path / "weaver.db") as connection:
        cols = {
            row["name"]: row["type"]
            for row in connection.execute("PRAGMA table_info(epub_snapshots)").fetchall()
        }
    assert cols["volume_id"] == "INTEGER"
    assert cols["source_hash"] == "TEXT"
    assert cols["parser_version"] == "INTEGER"
    assert cols["package_path"] == "TEXT"
    assert cols["metadata_json"] == "TEXT"
    assert cols["preservation_context_json"] == "TEXT"
    assert cols["created_at"] == "TEXT"
    assert cols["updated_at"] == "TEXT"
