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


def test_apply_migrations_upgrades_v2_to_v3_wraps_chapters_in_default_volume(tmp_path) -> None:
    db_path = tmp_path / "legacy_v2.db"
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        CREATE TABLE projects (
          id INTEGER PRIMARY KEY,
          name TEXT NOT NULL,
          source_path TEXT NOT NULL,
          source_lang TEXT NOT NULL,
          target_lang TEXT NOT NULL,
          created_at TEXT NOT NULL,
          schema_version INTEGER NOT NULL
        );
        CREATE TABLE chapters (
          id TEXT PRIMARY KEY,
          project_id INTEGER REFERENCES projects(id),
          title TEXT,
          href TEXT,
          spine_order INTEGER NOT NULL
        );
        INSERT INTO projects (
          id, name, source_path, source_lang, target_lang, created_at, schema_version
        )
        VALUES (1, 'legacy-novel', 'legacy.epub', 'ja', 'en', '2025-01-01T00:00:00+00:00', 2);
        INSERT INTO chapters (id, project_id, title, href, spine_order)
        VALUES ('c1', 1, 'One', 'text/c1.xhtml', 0), ('c2', 1, 'Two', 'text/c2.xhtml', 1);
        """
    )
    connection.execute("PRAGMA user_version = 2")
    connection.commit()

    apply_migrations(connection, target_version=SCHEMA_VERSION)

    volumes = connection.execute(
        "SELECT id, project_id, title, source_path, source_format, volume_order FROM volumes"
    ).fetchall()
    chapter_volume_ids = {
        row["id"]: row["volume_id"]
        for row in connection.execute("SELECT id, volume_id FROM chapters").fetchall()
    }
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    connection.close()

    assert len(volumes) == 1
    assert volumes[0]["project_id"] == 1
    assert volumes[0]["title"] == "legacy-novel"
    assert volumes[0]["source_path"] == "legacy.epub"
    assert volumes[0]["source_format"] == "epub"
    assert volumes[0]["volume_order"] == 0
    assert set(chapter_volume_ids.values()) == {volumes[0]["id"]}
    assert version == SCHEMA_VERSION


def test_apply_migrations_upgrades_v3_to_v4_adds_characters_table(tmp_path) -> None:
    db_path = tmp_path / "legacy_v3.db"
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        CREATE TABLE projects (
          id INTEGER PRIMARY KEY,
          name TEXT NOT NULL,
          source_path TEXT NOT NULL,
          source_lang TEXT NOT NULL,
          target_lang TEXT NOT NULL,
          created_at TEXT NOT NULL,
          schema_version INTEGER NOT NULL
        );
        INSERT INTO projects (
          id, name, source_path, source_lang, target_lang, created_at, schema_version
        )
        VALUES (1, 'novel', 'n.epub', 'ja', 'en', '2025-01-01T00:00:00+00:00', 3);
        """
    )
    connection.execute("PRAGMA user_version = 3")
    connection.commit()

    apply_migrations(connection, target_version=SCHEMA_VERSION)

    tables = {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    char_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(characters)").fetchall()
    }
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    connection.close()

    assert "characters" in tables
    assert {"jp_name", "en_name", "gender", "role", "notes"} <= char_columns
    assert version == SCHEMA_VERSION


def test_apply_migrations_upgrades_v4_to_v5_adds_translation_memory_table(tmp_path) -> None:
    db_path = tmp_path / "legacy_v4.db"
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        CREATE TABLE projects (
          id INTEGER PRIMARY KEY,
          name TEXT NOT NULL,
          source_path TEXT NOT NULL,
          source_lang TEXT NOT NULL,
          target_lang TEXT NOT NULL,
          created_at TEXT NOT NULL,
          schema_version INTEGER NOT NULL
        );
        INSERT INTO projects (
          id, name, source_path, source_lang, target_lang, created_at, schema_version
        )
        VALUES (1, 'novel', 'n.epub', 'ja', 'en', '2025-01-01T00:00:00+00:00', 4);
        """
    )
    connection.execute("PRAGMA user_version = 4")
    connection.commit()

    apply_migrations(connection, target_version=SCHEMA_VERSION)

    tables = {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    tm_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(translation_memory)").fetchall()
    }
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    connection.close()

    assert "translation_memory" in tables
    assert {"project_id", "source_text", "source_hash", "target_text"} <= tm_columns
    assert version == SCHEMA_VERSION


def test_apply_migrations_is_idempotent(tmp_path) -> None:
    db_path = tmp_path / "fresh.db"
    with initialize_database(db_path) as connection:
        apply_migrations(connection, target_version=SCHEMA_VERSION)
        apply_migrations(connection, target_version=SCHEMA_VERSION)
        version = connection.execute("PRAGMA user_version").fetchone()[0]

    assert version == SCHEMA_VERSION
