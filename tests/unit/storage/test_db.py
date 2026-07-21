"""SQLite connection, migration, and recovery tests."""

from __future__ import annotations

import sqlite3
import threading
import time
from contextlib import closing

from weaver.storage.db import connect_database, initialize_database, transaction


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
        "job_events",
    }.issubset(tables)
    # qa_warnings was dropped in schema v12 (WV-011): a fresh DB never has it.
    assert "qa_warnings" not in tables
    assert journal_mode == "wal"
    assert foreign_keys == 1


def test_writable_connection_sets_busy_timeout(tmp_path) -> None:
    """Writable connections wait on a contended lock instead of failing fast,
    so a transient overlap (e.g. a running translation) doesn't 500 an import."""
    db_path = tmp_path / "weaver.db"
    with initialize_database(db_path):
        pass
    with connect_database(db_path) as connection:
        busy_timeout = connection.execute("PRAGMA busy_timeout").fetchone()[0]
    assert busy_timeout == 10000


def test_connect_database_does_not_reset_in_progress_segments(tmp_path) -> None:
    """connect_database must NOT reset in_progress segments (R-02 / Q2b)."""
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

    assert status == "in_progress", (
        "connect_database must NOT reset in_progress segments (R-02). "
        "Reset belongs at explicit recovery points only."
    )


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


def test_transaction_survives_concurrent_read_then_write(tmp_path) -> None:
    """`transaction()` must open IMMEDIATE, not DEFERRED (ADR 020 M4).

    Under DEFERRED, two connections can each take a SHARED read lock and then
    race to upgrade to a write lock; SQLite reports that upgrade race as an
    instant `SQLITE_BUSY` ("database is locked") *without* consulting the
    10 s `busy_timeout`. Every hot-path transaction has this shape --
    `record_translation()` opens with `SELECT MAX(attempt)` and then writes --
    so `max_concurrent > 1` would surface it as a run-killing exception.
    """
    db_path = tmp_path / "weaver.db"
    with initialize_database(db_path) as connection:
        connection.execute(
            """
            INSERT INTO projects (
              id, name, source_path, source_lang, target_lang, created_at, schema_version
            )
            VALUES (1, 'fixture', 'fixture.epub', 'ja', 'en', '2026-07-21T00:00:00Z', 1)
            """
        )
        connection.commit()

    worker_count = 4
    iterations = 15
    errors: list[BaseException] = []
    errors_lock = threading.Lock()
    ready = threading.Barrier(worker_count, timeout=30)

    def run_worker() -> None:
        try:
            with closing(connect_database(db_path)) as connection:
                ready.wait()
                for _ in range(iterations):
                    with transaction(connection):
                        # Read first, then write on the same connection: the
                        # lock-upgrade shape DEFERRED cannot serialize.
                        current = connection.execute(
                            "SELECT schema_version FROM projects WHERE id = 1"
                        ).fetchone()[0]
                        time.sleep(0.001)  # widen the upgrade window
                        connection.execute(
                            "UPDATE projects SET schema_version = ? WHERE id = 1",
                            (int(current) + 1,),
                        )
        except BaseException as exc:  # noqa: BLE001 - reported via `errors`
            with errors_lock:
                errors.append(exc)

    threads = [threading.Thread(target=run_worker) for _ in range(worker_count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == [], f"concurrent transactions raised: {errors!r}"
    with closing(connect_database(db_path)) as connection:
        final = connection.execute("SELECT schema_version FROM projects WHERE id = 1").fetchone()[0]
    # Serialized writers means no lost update: every increment landed.
    assert final == 1 + worker_count * iterations
