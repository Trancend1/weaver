"""Segment revision-history read-service tests (Sprint 3C)."""

from __future__ import annotations

from pathlib import Path

import pytest

from weaver.errors import ChapterNotFoundError, SegmentNotFoundError
from weaver.services.project import initialize_project
from weaver.services.segment_history import segment_translation_history
from weaver.services.workspace_edit import save_segment_translation
from weaver.storage.db import connect_readonly_database

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
FIXTURE_EPUB_A = FIXTURES / "aozora_sample.epub"


def _first_segment(database_path: Path) -> tuple[str, str]:
    with connect_readonly_database(database_path) as connection:
        row = connection.execute(
            """
            SELECT s.id AS segment_id, s.chapter_id AS chapter_id
            FROM segments s
            JOIN chapters c ON c.id = s.chapter_id
            ORDER BY c.spine_order, s.block_order
            LIMIT 1
            """
        ).fetchone()
    return str(row["chapter_id"]), str(row["segment_id"])


def test_history_empty_when_untranslated(tmp_path) -> None:
    init = initialize_project(FIXTURE_EPUB_A, cwd=tmp_path, provider="fake")
    chapter_id, segment_id = _first_segment(init.database_path)

    history = segment_translation_history(init.project_toml, chapter_id, segment_id, cwd=tmp_path)

    assert history.segment_id == segment_id
    assert history.current_translation is None
    assert history.attempts == []


def test_history_records_each_save_as_new_attempt(tmp_path) -> None:
    init = initialize_project(FIXTURE_EPUB_A, cwd=tmp_path, provider="fake")
    chapter_id, segment_id = _first_segment(init.database_path)

    for text in ("first", "second", "third"):
        save_segment_translation(init.project_toml, chapter_id, segment_id, text, cwd=tmp_path)

    history = segment_translation_history(init.project_toml, chapter_id, segment_id, cwd=tmp_path)

    assert [a.attempt for a in history.attempts] == [1, 2, 3]
    assert [a.text for a in history.attempts] == ["first", "second", "third"]
    assert history.current_translation == "third"
    assert history.status == "manual"
    assert all(a.provider == "manual" for a in history.attempts)


def test_history_rejects_unknown_chapter(tmp_path) -> None:
    init = initialize_project(FIXTURE_EPUB_A, cwd=tmp_path, provider="fake")
    _, segment_id = _first_segment(init.database_path)

    with pytest.raises(ChapterNotFoundError, match="missing-chapter"):
        segment_translation_history(init.project_toml, "missing-chapter", segment_id, cwd=tmp_path)


def test_history_rejects_segment_in_wrong_chapter(tmp_path) -> None:
    init = initialize_project(FIXTURE_EPUB_A, cwd=tmp_path, provider="fake")
    chapter_id, segment_id = _first_segment(init.database_path)

    with connect_readonly_database(init.database_path) as connection:
        other = connection.execute(
            "SELECT id FROM chapters WHERE id != ? LIMIT 1", (chapter_id,)
        ).fetchone()
    if other is None:
        pytest.skip("fixture has only one chapter")

    with pytest.raises(SegmentNotFoundError, match=segment_id):
        segment_translation_history(init.project_toml, str(other["id"]), segment_id, cwd=tmp_path)
