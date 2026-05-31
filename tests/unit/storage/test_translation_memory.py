"""Translation memory repository tests (schema v5)."""

from __future__ import annotations

import sqlite3

from weaver.storage.db import initialize_database, transaction
from weaver.storage.translation_memory import (
    list_translation_memory,
    lookup_translation_memory,
    save_translation_memory,
)


def _make_project(connection: sqlite3.Connection, *, name: str) -> int:
    cursor = connection.execute(
        """
        INSERT INTO projects (
          name, source_path, source_lang, target_lang, created_at, schema_version
        )
        VALUES (?, ?, 'ja', 'en', '2026-05-31T00:00:00+00:00', 5)
        """,
        (name, f"{name}.epub"),
    )
    assert cursor.lastrowid is not None
    return int(cursor.lastrowid)


def test_save_then_lookup_returns_exact_match(tmp_path) -> None:
    db_path = tmp_path / "tm.db"
    with initialize_database(db_path) as connection:
        with transaction(connection):
            project_id = _make_project(connection, name="novel")
            save_translation_memory(
                connection,
                project_id=project_id,
                source_text="おはよう",
                source_hash="hash-1",
                target_text="Good morning.",
                provider="fake",
                model="fake-1",
            )
        hit = lookup_translation_memory(connection, project_id=project_id, source_hash="hash-1")

    assert hit is not None
    assert hit.target_text == "Good morning."
    assert hit.source_text == "おはよう"
    assert hit.provider == "fake"
    assert hit.model == "fake-1"


def test_lookup_miss_returns_none(tmp_path) -> None:
    db_path = tmp_path / "tm.db"
    with initialize_database(db_path) as connection:
        with transaction(connection):
            project_id = _make_project(connection, name="novel")
        miss = lookup_translation_memory(connection, project_id=project_id, source_hash="absent")

    assert miss is None


def test_save_is_upsert_without_duplicate_row(tmp_path) -> None:
    db_path = tmp_path / "tm.db"
    with initialize_database(db_path) as connection:
        with transaction(connection):
            project_id = _make_project(connection, name="novel")
            save_translation_memory(
                connection,
                project_id=project_id,
                source_text="同じ",
                source_hash="hash-dup",
                target_text="first",
                provider="fake",
                model="fake-1",
            )
            save_translation_memory(
                connection,
                project_id=project_id,
                source_text="同じ",
                source_hash="hash-dup",
                target_text="second",
                provider="fake",
                model="fake-1",
            )
        rows = list_translation_memory(connection, project_id=project_id)
        hit = lookup_translation_memory(connection, project_id=project_id, source_hash="hash-dup")

    assert len(rows) == 1
    assert hit is not None
    assert hit.target_text == "second"


def test_memory_is_project_scoped(tmp_path) -> None:
    db_path = tmp_path / "tm.db"
    with initialize_database(db_path) as connection:
        with transaction(connection):
            project_a = _make_project(connection, name="alpha")
            project_b = _make_project(connection, name="beta")
            save_translation_memory(
                connection,
                project_id=project_b,
                source_text="共有",
                source_hash="shared-hash",
                target_text="only in B",
                provider="fake",
                model="fake-1",
            )
        from_a = lookup_translation_memory(
            connection, project_id=project_a, source_hash="shared-hash"
        )
        from_b = lookup_translation_memory(
            connection, project_id=project_b, source_hash="shared-hash"
        )

    assert from_a is None
    assert from_b is not None
    assert from_b.target_text == "only in B"


def test_provider_save_does_not_overwrite_manual_entry(tmp_path) -> None:
    db_path = tmp_path / "tm.db"
    with initialize_database(db_path) as connection:
        with transaction(connection):
            project_id = _make_project(connection, name="novel")
            save_translation_memory(
                connection,
                project_id=project_id,
                source_text="本文",
                source_hash="hash-m",
                target_text="hand edit",
                provider="manual",
                model="manual",
            )
            save_translation_memory(
                connection,
                project_id=project_id,
                source_text="本文",
                source_hash="hash-m",
                target_text="provider output",
                provider="fake",
                model="fake-1",
                protect_manual=True,
            )
        hit = lookup_translation_memory(connection, project_id=project_id, source_hash="hash-m")

    assert hit is not None
    assert hit.provider == "manual"
    assert hit.target_text == "hand edit"


def test_manual_save_overwrites_existing_provider_entry(tmp_path) -> None:
    db_path = tmp_path / "tm.db"
    with initialize_database(db_path) as connection:
        with transaction(connection):
            project_id = _make_project(connection, name="novel")
            save_translation_memory(
                connection,
                project_id=project_id,
                source_text="本文",
                source_hash="hash-p",
                target_text="provider output",
                provider="fake",
                model="fake-1",
                protect_manual=True,
            )
            save_translation_memory(
                connection,
                project_id=project_id,
                source_text="本文",
                source_hash="hash-p",
                target_text="hand edit",
                provider="manual",
                model="manual",
            )
        hit = lookup_translation_memory(connection, project_id=project_id, source_hash="hash-p")

    assert hit is not None
    assert hit.provider == "manual"
    assert hit.target_text == "hand edit"
