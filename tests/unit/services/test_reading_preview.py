"""Tests for the read-only reading preview service."""

from __future__ import annotations

from pathlib import Path

import pytest

from weaver.errors import ChapterNotFoundError, VolumeNotFoundError
from weaver.services.project import initialize_project
from weaver.services.reading_preview import (
    reading_preview_for_chapter,
    reading_preview_for_volume,
)
from weaver.storage.db import connect_database, transaction
from weaver.storage.segments import update_segment_status
from weaver.storage.translations import record_translation

SOURCE = """第一章 テスト

最初の段落の説明文。

二番目の段落の説明文。
"""


def _init_project(tmp_path: Path) -> tuple[Path, Path]:
    src = tmp_path / "book.txt"
    src.write_text(SOURCE, encoding="utf-8")
    init = initialize_project(src, cwd=tmp_path, provider="fake")
    return init.project_toml, init.database_path


def _first_chapter_id(db_path: Path) -> str:
    with connect_database(db_path) as conn:
        row = conn.execute("SELECT id FROM chapters ORDER BY spine_order").fetchone()
        return str(row["id"])


def _segments(db_path: Path) -> list[tuple[str, str]]:
    with connect_database(db_path) as conn:
        chapter_id = _first_chapter_id(db_path)
        rows = conn.execute(
            "SELECT id, source_hash FROM segments WHERE chapter_id = ? ORDER BY block_order",
            (chapter_id,),
        ).fetchall()
        return [(str(r["id"]), str(r["source_hash"])) for r in rows]


def test_reading_preview_shows_translated_text(tmp_path: Path) -> None:
    project_toml, db_path = _init_project(tmp_path)
    segs = _segments(db_path)
    with connect_database(db_path) as conn, transaction(conn):
        record_translation(
            conn,
            segment_id=segs[0][0],
            text="Translated A",
            source_hash=segs[0][1],
            provider="fake",
            model="fake",
        )
        update_segment_status(conn, segment_id=segs[0][0], status="translated")

    chapter = reading_preview_for_chapter(project_toml, _first_chapter_id(db_path), cwd=tmp_path)
    assert len(chapter.blocks) == 3
    assert chapter.blocks[0].resolved_text == "Translated A"
    assert not chapter.blocks[0].is_fallback
    assert chapter.blocks[1].is_fallback
    assert chapter.blocks[1].resolved_text == chapter.blocks[1].source_text


def test_reading_preview_shows_manual_text(tmp_path: Path) -> None:
    project_toml, db_path = _init_project(tmp_path)
    segs = _segments(db_path)
    with connect_database(db_path) as conn, transaction(conn):
        record_translation(
            conn,
            segment_id=segs[1][0],
            text="Manual B",
            source_hash=segs[1][1],
            provider="fake",
            model="fake",
        )
        update_segment_status(conn, segment_id=segs[1][0], status="manual")

    chapter = reading_preview_for_chapter(project_toml, _first_chapter_id(db_path), cwd=tmp_path)
    assert chapter.blocks[1].resolved_text == "Manual B"
    assert not chapter.blocks[1].is_fallback


def test_reading_preview_fallback_on_hash_mismatch(tmp_path: Path) -> None:
    project_toml, db_path = _init_project(tmp_path)
    segs = _segments(db_path)
    with connect_database(db_path) as conn, transaction(conn):
        record_translation(
            conn,
            segment_id=segs[0][0],
            text="Stale translation",
            source_hash="wrong-hash",
            provider="fake",
            model="fake",
        )
        update_segment_status(conn, segment_id=segs[0][0], status="translated")

    chapter = reading_preview_for_chapter(project_toml, _first_chapter_id(db_path), cwd=tmp_path)
    assert chapter.blocks[0].is_fallback
    assert chapter.blocks[0].resolved_text == chapter.blocks[0].source_text


def test_reading_preview_unknown_chapter(tmp_path: Path) -> None:
    project_toml, db_path = _init_project(tmp_path)
    with pytest.raises(ChapterNotFoundError):
        reading_preview_for_chapter(project_toml, "no-such-chapter", cwd=tmp_path)


def test_reading_preview_unknown_volume(tmp_path: Path) -> None:
    project_toml, db_path = _init_project(tmp_path)
    with pytest.raises(VolumeNotFoundError):
        reading_preview_for_volume(project_toml, 9999, cwd=tmp_path)


def test_reading_preview_volume_order_matches_chapter_order(tmp_path: Path) -> None:
    project_toml, db_path = _init_project(tmp_path)
    chapter_id = _first_chapter_id(db_path)
    with connect_database(db_path) as conn:
        row = conn.execute("SELECT volume_id FROM chapters WHERE id = ?", (chapter_id,)).fetchone()
        volume_id = int(row["volume_id"])

    chapters = reading_preview_for_volume(project_toml, volume_id, cwd=tmp_path)
    assert len(chapters) == 1
    assert chapters[0].chapter_id == chapter_id
    assert len(chapters[0].blocks) == 3


def test_reading_preview_block_html_is_safe_escaped(tmp_path: Path) -> None:
    project_toml, db_path = _init_project(tmp_path)
    segs = _segments(db_path)
    with connect_database(db_path) as conn, transaction(conn):
        record_translation(
            conn,
            segment_id=segs[0][0],
            text="<script>alert(1)</script>",
            source_hash=segs[0][1],
            provider="fake",
            model="fake",
        )
        update_segment_status(conn, segment_id=segs[0][0], status="translated")

    chapter = reading_preview_for_chapter(project_toml, _first_chapter_id(db_path), cwd=tmp_path)
    html = chapter.blocks[0].html
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
