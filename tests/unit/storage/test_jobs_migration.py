"""Tests for the v5 → v6 job-persistence migration (Sprint I1, ADR 010)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from weaver.storage.db import SCHEMA_VERSION, initialize_database
from weaver.storage.migrations import apply_migrations


def _legacy_v5_database(path: Path) -> None:
    """Build a hand-rolled v5 database (job_events without job_id, no jobs table)."""
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
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
              source_format TEXT NOT NULL CHECK (source_format IN ('epub','txt','html')),
              volume_order INTEGER NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE chapters (
              id TEXT PRIMARY KEY, project_id INTEGER REFERENCES projects(id),
              volume_id INTEGER REFERENCES volumes(id), title TEXT, href TEXT,
              spine_order INTEGER NOT NULL
            );
            CREATE TABLE segments (
              id TEXT PRIMARY KEY, chapter_id TEXT REFERENCES chapters(id),
              block_order INTEGER NOT NULL, kind TEXT NOT NULL,
              source_text TEXT NOT NULL, source_hash TEXT NOT NULL,
              status TEXT NOT NULL
            );
            CREATE TABLE translations (
              segment_id TEXT REFERENCES segments(id), attempt INTEGER NOT NULL,
              text TEXT NOT NULL, source_hash TEXT NOT NULL,
              provider TEXT NOT NULL, model TEXT NOT NULL, created_at TEXT NOT NULL,
              raw_response TEXT, input_tokens INTEGER, output_tokens INTEGER,
              PRIMARY KEY (segment_id, attempt)
            );
            CREATE TABLE glossary_candidates (
              id INTEGER PRIMARY KEY, project_id INTEGER REFERENCES projects(id),
              source TEXT NOT NULL, target TEXT, category TEXT, notes TEXT,
              status TEXT NOT NULL, frequency INTEGER NOT NULL
            );
            CREATE TABLE glossary_terms (
              id INTEGER PRIMARY KEY, project_id INTEGER REFERENCES projects(id),
              source TEXT NOT NULL, target TEXT NOT NULL, category TEXT, notes TEXT,
              case_sensitive INTEGER NOT NULL DEFAULT 0,
              UNIQUE(project_id, source)
            );
            CREATE TABLE characters (
              id INTEGER PRIMARY KEY, project_id INTEGER REFERENCES projects(id),
              jp_name TEXT NOT NULL, en_name TEXT NOT NULL, gender TEXT,
              role TEXT, notes TEXT, UNIQUE(project_id, jp_name)
            );
            CREATE TABLE translation_memory (
              id INTEGER PRIMARY KEY, project_id INTEGER REFERENCES projects(id),
              source_text TEXT NOT NULL, source_hash TEXT NOT NULL,
              target_text TEXT NOT NULL, provider TEXT, model TEXT,
              created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
              UNIQUE(project_id, source_hash)
            );
            CREATE TABLE qa_warnings (
              id INTEGER PRIMARY KEY, segment_id TEXT REFERENCES segments(id),
              check_name TEXT NOT NULL, severity TEXT NOT NULL,
              message TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE job_events (
              id INTEGER PRIMARY KEY, project_id INTEGER REFERENCES projects(id),
              event TEXT NOT NULL, data_json TEXT, created_at TEXT NOT NULL
            );
            INSERT INTO projects VALUES
              (1, 'legacy', 'a.epub', 'ja', 'en', '2026-06-01T00:00:00Z', 1);
            INSERT INTO job_events (project_id, event, data_json, created_at)
              VALUES (1, 'legacy.event', '{}', '2026-06-01T00:00:00Z');
            PRAGMA user_version = 5;
            """
        )
        connection.commit()
    finally:
        connection.close()


def test_v6_migration_adds_jobs_and_snapshots_and_extends_job_events(tmp_path: Path) -> None:
    db_path = tmp_path / "weaver.db"
    _legacy_v5_database(db_path)

    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        apply_migrations(connection, target_version=SCHEMA_VERSION)
        connection.commit()

        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "jobs" in tables
        assert "job_progress_snapshots" in tables

        job_event_cols = {
            row["name"] for row in connection.execute("PRAGMA table_info(job_events)").fetchall()
        }
        assert "job_id" in job_event_cols

        # Pre-existing rows backfill to NULL.
        legacy = connection.execute(
            "SELECT job_id FROM job_events WHERE event = 'legacy.event'"
        ).fetchone()
        assert legacy["job_id"] is None

        version = connection.execute("PRAGMA user_version").fetchone()[0]
        assert version == SCHEMA_VERSION
    finally:
        connection.close()


def test_v6_migration_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "weaver.db"
    _legacy_v5_database(db_path)

    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        apply_migrations(connection, target_version=SCHEMA_VERSION)
        # Running again must be a no-op (no IntegrityError, no duplicate work).
        apply_migrations(connection, target_version=SCHEMA_VERSION)
        connection.commit()
    finally:
        connection.close()


def test_fresh_database_lands_at_v6(tmp_path: Path) -> None:
    with initialize_database(tmp_path / "weaver.db") as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert version == SCHEMA_VERSION
    assert {"jobs", "job_progress_snapshots", "job_events"}.issubset(tables)
