"""Workspace save-service tests (Sprint 3B)."""

from __future__ import annotations

from pathlib import Path

import pytest

from weaver.errors import ChapterNotFoundError, SegmentNotFoundError
from weaver.services.project import initialize_project
from weaver.services.workspace_edit import save_segment_translation
from weaver.storage.db import connect_readonly_database
from weaver.storage.segments import get_segment

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
FIXTURE_EPUB_A = FIXTURES / "aozora_sample.epub"


def _first_segment(database_path: Path) -> tuple[str, str]:
    """Return (chapter_id, segment_id) for the first segment."""
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


def test_save_persists_manual_translation(tmp_path) -> None:
    init = initialize_project(FIXTURE_EPUB_A, cwd=tmp_path, provider="fake")
    chapter_id, segment_id = _first_segment(init.database_path)

    result = save_segment_translation(
        init.project_toml, chapter_id, segment_id, "  Translated.  ", cwd=tmp_path
    )

    assert result.segment_id == segment_id
    assert result.status == "manual"
    assert result.translated_text == "Translated."  # stripped
    assert result.saved_at

    with connect_readonly_database(init.database_path) as connection:
        segment = get_segment(connection, segment_id)
        assert segment is not None
        assert segment.status == "manual"
        latest = connection.execute(
            "SELECT text, provider FROM translations WHERE segment_id = ? "
            "ORDER BY attempt DESC LIMIT 1",
            (segment_id,),
        ).fetchone()
    assert latest["text"] == "Translated."
    assert latest["provider"] == "manual"


def test_save_preserves_source_text_and_hash(tmp_path) -> None:
    init = initialize_project(FIXTURE_EPUB_A, cwd=tmp_path, provider="fake")
    chapter_id, segment_id = _first_segment(init.database_path)

    with connect_readonly_database(init.database_path) as connection:
        before = get_segment(connection, segment_id)
    assert before is not None

    save_segment_translation(init.project_toml, chapter_id, segment_id, "Edit.", cwd=tmp_path)

    with connect_readonly_database(init.database_path) as connection:
        after = get_segment(connection, segment_id)
    assert after is not None
    assert after.source_text == before.source_text
    assert after.source_hash == before.source_hash


def test_save_rejects_empty(tmp_path) -> None:
    init = initialize_project(FIXTURE_EPUB_A, cwd=tmp_path, provider="fake")
    chapter_id, segment_id = _first_segment(init.database_path)

    with pytest.raises(ValueError, match="empty"):
        save_segment_translation(init.project_toml, chapter_id, segment_id, "   ", cwd=tmp_path)


def test_save_rejects_unknown_chapter(tmp_path) -> None:
    init = initialize_project(FIXTURE_EPUB_A, cwd=tmp_path, provider="fake")
    _, segment_id = _first_segment(init.database_path)

    with pytest.raises(ChapterNotFoundError, match="missing-chapter"):
        save_segment_translation(
            init.project_toml, "missing-chapter", segment_id, "x", cwd=tmp_path
        )


def test_save_rejects_segment_in_wrong_chapter(tmp_path) -> None:
    init = initialize_project(FIXTURE_EPUB_A, cwd=tmp_path, provider="fake")
    chapter_id, segment_id = _first_segment(init.database_path)

    # A real chapter that does not own this segment: find a different chapter id.
    with connect_readonly_database(init.database_path) as connection:
        other = connection.execute(
            "SELECT id FROM chapters WHERE id != ? LIMIT 1", (chapter_id,)
        ).fetchone()
    if other is None:
        pytest.skip("fixture has only one chapter")

    with pytest.raises(SegmentNotFoundError, match=segment_id):
        save_segment_translation(init.project_toml, str(other["id"]), segment_id, "x", cwd=tmp_path)
