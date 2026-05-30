"""Chapter workspace read-service tests (Sprint 3A)."""

from __future__ import annotations

from pathlib import Path

import pytest

from weaver.errors import ChapterNotFoundError
from weaver.services.chapter_workspace import chapter_workspace
from weaver.services.project import initialize_project
from weaver.storage.db import connect_database, transaction
from weaver.storage.translations import record_translation

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
FIXTURE_EPUB_A = FIXTURES / "aozora_sample.epub"


def _first_chapter_and_segment(database_path: Path) -> tuple[str, str, str]:
    """Return (chapter_id, segment_id, source_hash) for the first segment."""
    with connect_database(database_path) as connection:
        row = connection.execute(
            """
            SELECT s.id AS segment_id, s.chapter_id AS chapter_id, s.source_hash AS source_hash
            FROM segments s
            JOIN chapters c ON c.id = s.chapter_id
            ORDER BY c.spine_order, s.block_order
            LIMIT 1
            """
        ).fetchone()
    return str(row["chapter_id"]), str(row["segment_id"]), str(row["source_hash"])


def test_workspace_lists_untranslated_segments(tmp_path) -> None:
    init = initialize_project(FIXTURE_EPUB_A, cwd=tmp_path, provider="fake")
    chapter_id, _, _ = _first_chapter_and_segment(init.database_path)

    workspace = chapter_workspace(init.project_toml, chapter_id, cwd=tmp_path)

    assert workspace.chapter_id == chapter_id
    assert workspace.segment_count == len(workspace.segments)
    assert workspace.segment_count > 0
    assert workspace.translated_count == 0
    assert all(segment.translated_text is None for segment in workspace.segments)
    orders = [segment.block_order for segment in workspace.segments]
    assert orders == sorted(orders)


def test_workspace_returns_latest_translation_text(tmp_path) -> None:
    init = initialize_project(FIXTURE_EPUB_A, cwd=tmp_path, provider="fake")
    chapter_id, segment_id, source_hash = _first_chapter_and_segment(init.database_path)

    with connect_database(init.database_path) as connection, transaction(connection):
        record_translation(
            connection,
            segment_id=segment_id,
            text="first attempt",
            source_hash=source_hash,
            provider="fake",
            model="fake",
        )
        record_translation(
            connection,
            segment_id=segment_id,
            text="latest attempt",
            source_hash=source_hash,
            provider="fake",
            model="fake",
        )

    workspace = chapter_workspace(init.project_toml, chapter_id, cwd=tmp_path)
    target = next(s for s in workspace.segments if s.id == segment_id)
    assert target.translated_text == "latest attempt"


def test_workspace_raises_for_unknown_chapter(tmp_path) -> None:
    init = initialize_project(FIXTURE_EPUB_A, cwd=tmp_path, provider="fake")

    with pytest.raises(ChapterNotFoundError, match="missing-chapter"):
        chapter_workspace(init.project_toml, "missing-chapter", cwd=tmp_path)
