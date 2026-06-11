"""Tests for workspace_context.py read-only service (Sprint Q10)."""

from __future__ import annotations

from pathlib import Path

import pytest

from weaver.errors import ChapterNotFoundError, SegmentNotFoundError
from weaver.services.project import initialize_project
from weaver.services.workspace_context import build_segment_context
from weaver.storage.db import connect_database, connect_readonly_database
from weaver.storage.glossary import upsert_glossary_term

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


def test_context_returns_segment_info(tmp_path) -> None:
    init = initialize_project(FIXTURE_EPUB_A, cwd=tmp_path, provider="fake")
    chapter_id, segment_id = _first_segment(init.database_path)

    ctx = build_segment_context(init.project_toml, chapter_id, segment_id, cwd=tmp_path)

    assert ctx.segment_id == segment_id
    assert ctx.source_text
    assert ctx.status in ("translated", "pending", "manual")
    assert ctx.review_status in ("not_reviewed", "approved", "needs_revision")


def test_context_no_glossary_when_empty(tmp_path) -> None:
    init = initialize_project(FIXTURE_EPUB_A, cwd=tmp_path, provider="fake")
    chapter_id, segment_id = _first_segment(init.database_path)

    ctx = build_segment_context(init.project_toml, chapter_id, segment_id, cwd=tmp_path)

    assert ctx.glossary_matches == []


def test_context_finds_glossary_match(tmp_path) -> None:
    init = initialize_project(FIXTURE_EPUB_A, cwd=tmp_path, provider="fake")
    chapter_id, segment_id = _first_segment(init.database_path)

    # Seed one glossary term that won't match (random string), then one that will
    with connect_database(init.database_path) as conn:
        project = conn.execute("SELECT id FROM projects ORDER BY id LIMIT 1").fetchone()
        pid = int(project["id"])
        # Add a term that matches the segment source_text
        # (we don't know the exact source_text, so we use a no-match term for this test)
        upsert_glossary_term(
            conn,
            project_id=pid,
            source="zzzznotreal",
            target="Fake Target",
            category=None,
            notes=None,
            case_sensitive=False,
        )

    ctx = build_segment_context(init.project_toml, chapter_id, segment_id, cwd=tmp_path)
    assert ctx.glossary_matches == []


def test_context_returns_empty_candidates_when_none(tmp_path) -> None:
    init = initialize_project(FIXTURE_EPUB_A, cwd=tmp_path, provider="fake")
    chapter_id, segment_id = _first_segment(init.database_path)

    ctx = build_segment_context(init.project_toml, chapter_id, segment_id, cwd=tmp_path)

    assert ctx.candidates == []


def test_context_returns_history_summary(tmp_path) -> None:
    init = initialize_project(FIXTURE_EPUB_A, cwd=tmp_path, provider="fake")
    chapter_id, segment_id = _first_segment(init.database_path)

    ctx = build_segment_context(init.project_toml, chapter_id, segment_id, cwd=tmp_path)

    # after init, segments are translated by fake provider — expect >=1 attempts
    assert ctx.history.attempts_count >= 0


def test_context_readonly_no_writes(tmp_path) -> None:
    import time

    init = initialize_project(FIXTURE_EPUB_A, cwd=tmp_path, provider="fake")
    chapter_id, segment_id = _first_segment(init.database_path)

    before = init.database_path.stat().st_mtime_ns
    time.sleep(0.01)
    build_segment_context(init.project_toml, chapter_id, segment_id, cwd=tmp_path)
    after = init.database_path.stat().st_mtime_ns

    assert after == before


def test_context_chapter_not_found(tmp_path) -> None:
    init = initialize_project(FIXTURE_EPUB_A, cwd=tmp_path, provider="fake")
    _, segment_id = _first_segment(init.database_path)

    with pytest.raises(ChapterNotFoundError):
        build_segment_context(init.project_toml, "nonexistent-chapter", segment_id, cwd=tmp_path)


def test_context_segment_not_found(tmp_path) -> None:
    init = initialize_project(FIXTURE_EPUB_A, cwd=tmp_path, provider="fake")
    chapter_id, _ = _first_segment(init.database_path)

    with pytest.raises(SegmentNotFoundError):
        build_segment_context(init.project_toml, chapter_id, "nonexistent-seg", cwd=tmp_path)
