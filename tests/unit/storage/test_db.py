"""SQLite connection, migration, and recovery tests."""

from __future__ import annotations

import sqlite3

from weaver.storage.db import connect_database, initialize_database


def test_initialize_database_creates_schema_and_enables_wal(tmp_path) -> None:
    db_path = tmp_path / "weaver.db"

    with initialize_database(db_path) as connection:
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
        foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()[0]

    assert {
        "projects",
        "chapters",
        "segments",
        "translations",
        "glossary_candidates",
        "glossary_terms",
        "translation_memory",
        "qa_warnings",
        "job_events",
    }.issubset(tables)
    assert journal_mode == "wal"
    assert foreign_keys == 1


def test_connect_database_resets_in_progress_segments(tmp_path) -> None:
    db_path = tmp_path / "weaver.db"
    with initialize_database(db_path) as connection:
        connection.execute(
            """
            INSERT INTO projects (
              id,
              name,
              source_path,
              source_lang,
              target_lang,
              created_at,
              schema_version
            )
            VALUES (1, 'fixture', 'fixture.epub', 'ja', 'en', '2026-05-17T00:00:00Z', 1)
            """
        )
        connection.execute(
            """
            INSERT INTO chapters (id, project_id, title, href, spine_order)
            VALUES ('chapter', 1, 'Chapter', 'text/chapter.xhtml', 0)
            """
        )
        connection.execute(
            """
            INSERT INTO segments (
              id,
              chapter_id,
              block_order,
              kind,
              source_text,
              source_hash,
              status
            )
            VALUES ('seg-1', 'chapter', 0, 'paragraph', 'source', 'hash', 'in_progress')
            """
        )
        connection.commit()

    with connect_database(db_path) as connection:
        status = connection.execute("SELECT status FROM segments WHERE id = 'seg-1'").fetchone()[0]

    assert status == "pending"


def test_foreign_keys_are_enforced(tmp_path) -> None:
    db_path = tmp_path / "weaver.db"

    with initialize_database(db_path) as connection:
        try:
            connection.execute(
                """
                INSERT INTO segments (
                  id,
                  chapter_id,
                  block_order,
                  kind,
                  source_text,
                  source_hash,
                  status
                )
                VALUES ('seg-1', 'missing', 0, 'paragraph', 'source', 'hash', 'pending')
                """
            )
        except sqlite3.IntegrityError:
            enforced = True
        else:
            enforced = False

    assert enforced
