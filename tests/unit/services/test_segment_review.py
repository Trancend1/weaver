"""Tests for the segment review service (Sprint P3, WV-003)."""

from __future__ import annotations

from pathlib import Path

import pytest

from weaver.errors import SegmentNotFoundError, WeaverError
from weaver.services.project import initialize_project
from weaver.services.segment_review import (
    get_segment_review_status,
    list_review_queue,
    review_counts_for_volume,
    set_segment_review_status,
)
from weaver.storage.db import connect_database, connect_readonly_database, transaction
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


def _first_chapter_and_volume_id(db_path: Path) -> tuple[str, int]:
    with connect_database(db_path) as conn:
        row = conn.execute("SELECT id, volume_id FROM chapters ORDER BY spine_order").fetchone()
        return str(row["id"]), int(row["volume_id"])


def _segments(db_path: Path) -> list[tuple[str, str]]:
    with connect_database(db_path) as conn:
        chapter_id, _ = _first_chapter_and_volume_id(db_path)
        rows = conn.execute(
            "SELECT id, source_hash FROM segments WHERE chapter_id = ? ORDER BY block_order",
            (chapter_id,),
        ).fetchall()
        return [(str(r["id"]), str(r["source_hash"])) for r in rows]


def test_set_and_get_review_status(tmp_path: Path) -> None:
    project_toml, db_path = _init_project(tmp_path)
    segs = _segments(db_path)

    set_segment_review_status(project_toml, segs[0][0], "approved", cwd=tmp_path)

    with connect_readonly_database(db_path) as conn:
        assert get_segment_review_status(conn, segment_id=segs[0][0]) == "approved"
        assert get_segment_review_status(conn, segment_id=segs[1][0]) == "not_reviewed"


def test_set_review_status_invalid_raises_weaver_error(tmp_path: Path) -> None:
    project_toml, db_path = _init_project(tmp_path)
    seg_id = _segments(db_path)[0][0]
    with pytest.raises(WeaverError):
        set_segment_review_status(project_toml, seg_id, "bogus_status", cwd=tmp_path)


def test_set_review_status_missing_segment_raises_not_found(tmp_path: Path) -> None:
    project_toml, db_path = _init_project(tmp_path)
    with pytest.raises(SegmentNotFoundError):
        set_segment_review_status(project_toml, "no-such-seg", "approved", cwd=tmp_path)


def test_review_queue_returns_items(tmp_path: Path) -> None:
    project_toml, db_path = _init_project(tmp_path)
    _, volume_id = _first_chapter_and_volume_id(db_path)
    segs = _segments(db_path)

    with connect_database(db_path) as conn, transaction(conn):
        update_segment_status(conn, segment_id=segs[0][0], status="translated")
        record_translation(
            conn,
            segment_id=segs[0][0],
            text="Translated A",
            source_hash=segs[0][1],
            provider="fake",
            model="fake",
        )

    set_segment_review_status(project_toml, segs[0][0], "needs_review", cwd=tmp_path)
    set_segment_review_status(project_toml, segs[1][0], "approved", cwd=tmp_path)

    queue = list_review_queue(project_toml, volume_id, cwd=tmp_path)
    assert len(queue) == 3
    item0 = next(q for q in queue if q.segment_id == segs[0][0])
    assert item0.review_status == "needs_review"
    assert item0.translation == "Translated A"

    filtered = list_review_queue(project_toml, volume_id, status_filter="approved", cwd=tmp_path)
    assert len(filtered) == 1
    assert filtered[0].segment_id == segs[1][0]


def test_review_queue_invalid_filter_ignored(tmp_path: Path) -> None:
    project_toml, db_path = _init_project(tmp_path)
    _, volume_id = _first_chapter_and_volume_id(db_path)
    queue = list_review_queue(project_toml, volume_id, status_filter="invalid", cwd=tmp_path)
    assert len(queue) == 3


def test_review_counts_for_volume(tmp_path: Path) -> None:
    project_toml, db_path = _init_project(tmp_path)
    _, volume_id = _first_chapter_and_volume_id(db_path)
    segs = _segments(db_path)

    set_segment_review_status(project_toml, segs[0][0], "needs_review", cwd=tmp_path)
    set_segment_review_status(project_toml, segs[1][0], "approved", cwd=tmp_path)

    with connect_readonly_database(db_path) as conn:
        counts = review_counts_for_volume(conn, volume_id=volume_id)
    assert counts.not_reviewed == 1
    assert counts.needs_review == 1
    assert counts.approved == 1
    assert counts.needs_revision == 0
    assert counts.rejected == 0


def test_review_status_does_not_alter_translation_status(tmp_path: Path) -> None:
    project_toml, db_path = _init_project(tmp_path)
    seg_id = _segments(db_path)[0][0]

    set_segment_review_status(project_toml, seg_id, "approved", cwd=tmp_path)

    with connect_readonly_database(db_path) as conn:
        row = conn.execute(
            "SELECT status, review_status FROM segments WHERE id = ?", (seg_id,)
        ).fetchone()
    assert str(row["status"]) == "pending"
    assert str(row["review_status"]) == "approved"
