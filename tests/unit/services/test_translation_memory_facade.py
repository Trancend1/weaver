"""Tests for the Stage 6B translation-memory read/management facade."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from weaver.errors import TranslationMemoryNotFoundError
from weaver.providers.fake import FakeProvider
from weaver.services.characters import add_character, list_all
from weaver.services.glossary_terms import add_term, list_terms
from weaver.services.manual_edit import apply_manual_translation
from weaver.services.project import initialize_project
from weaver.services.translation import translate_project
from weaver.services.translation_memory import delete_entry, get_memory_overview
from weaver.storage.db import connect_database, transaction

FIXTURE_EPUB = Path(__file__).resolve().parents[2] / "fixtures" / "aozora_sample.epub"


def _reset_all_to_pending(db_path: Path) -> None:
    with connect_database(db_path) as connection, transaction(connection):
        connection.execute("UPDATE segments SET status = 'pending'")


def _count_translations(db_path: Path) -> int:
    with sqlite3.connect(db_path) as connection:
        return int(connection.execute("SELECT COUNT(*) FROM translations").fetchone()[0])


def _status(db_path: Path, segment_id: str) -> str:
    with sqlite3.connect(db_path) as connection:
        return str(
            connection.execute(
                "SELECT status FROM segments WHERE id = ?", (segment_id,)
            ).fetchone()[0]
        )


def _first_segment(db_path: Path) -> tuple[str, str]:
    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT s.id, s.source_hash
            FROM segments s
            JOIN chapters c ON c.id = s.chapter_id
            ORDER BY c.spine_order, s.block_order
            LIMIT 1
            """
        ).fetchone()
    return str(row[0]), str(row[1])


def test_overview_counts_entries_and_reuses(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)

    translate_project(init.project_toml, provider=FakeProvider())
    _reset_all_to_pending(init.database_path)
    translate_project(init.project_toml, provider=FakeProvider())  # full reuse pass

    overview = get_memory_overview(init.project_toml)

    assert overview.total_entries == 6
    assert overview.reused_from_memory == 6
    assert overview.exact_hits == 6
    assert len(overview.entries) == 6


def test_delete_unknown_entry_raises(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)

    with pytest.raises(TranslationMemoryNotFoundError):
        delete_entry(init.project_toml, source_hash="does-not-exist")


def test_delete_entry_preserves_history_and_other_data(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)
    translate_project(init.project_toml, provider=FakeProvider())
    segment_id, source_hash = _first_segment(init.database_path)
    apply_manual_translation(init.project_toml, segment_id, "MANUAL TRUTH")
    add_term(init.project_toml, source="魔王", target="Demon King")
    add_character(init.project_toml, jp_name="エリナ", en_name="Elina")

    translations_before = _count_translations(init.database_path)

    delete_entry(init.project_toml, source_hash=source_hash)

    overview = get_memory_overview(init.project_toml)
    # Only the TM row is gone — everything else is untouched.
    assert all(entry.source_hash != source_hash for entry in overview.entries)
    assert _count_translations(init.database_path) == translations_before
    assert _status(init.database_path, segment_id) == "manual"
    assert len(list_terms(init.project_toml)) == 1
    assert len(list_all(init.project_toml)) == 1
