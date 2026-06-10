"""Tests for the project overview service (Sprint P5, WV-005)."""

from __future__ import annotations

from pathlib import Path

from weaver.services.project import initialize_project
from weaver.services.project_overview import project_overview
from weaver.services.segment_review import set_segment_review_status
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


def _first_chapter_id_and_volume_id(db_path: Path) -> tuple[str, int]:
    with connect_database(db_path) as conn:
        row = conn.execute("SELECT id, volume_id FROM chapters ORDER BY spine_order").fetchone()
        return str(row["id"]), int(row["volume_id"])


def _segments(db_path: Path) -> list[tuple[str, str]]:
    with connect_database(db_path) as conn:
        chapter_id, _ = _first_chapter_id_and_volume_id(db_path)
        rows = conn.execute(
            "SELECT id, source_hash FROM segments WHERE chapter_id = ? ORDER BY block_order",
            (chapter_id,),
        ).fetchall()
        return [(str(r["id"]), str(r["source_hash"])) for r in rows]


def test_overview_counts_match_project(tmp_path: Path) -> None:
    project_toml, db_path = _init_project(tmp_path)
    overview = project_overview(project_toml, cwd=tmp_path)
    assert overview.project_name is not None
    assert overview.volume_count == 1
    assert overview.chapter_count == 1
    assert overview.segment_count == 3


def test_overview_translation_progress(tmp_path: Path) -> None:
    project_toml, db_path = _init_project(tmp_path)
    chapter_id, volume_id = _first_chapter_id_and_volume_id(db_path)
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
        update_segment_status(conn, segment_id=segs[1][0], status="manual")
        record_translation(
            conn,
            segment_id=segs[1][0],
            text="Manual B",
            source_hash=segs[1][1],
            provider="fake",
            model="fake",
        )
        update_segment_status(conn, segment_id=segs[2][0], status="failed")

    overview = project_overview(project_toml, cwd=tmp_path)
    assert overview.done_count == 2
    assert overview.pending_count == 0
    assert overview.failed_stale_count == 1
    assert overview.volume_count == 1
    vol = overview.volumes[0]
    assert vol.done_count == 2
    assert vol.failed_stale_count == 1


def test_overview_review_counts(tmp_path: Path) -> None:
    project_toml, db_path = _init_project(tmp_path)
    chapter_id, volume_id = _first_chapter_id_and_volume_id(db_path)
    segs = _segments(db_path)

    set_segment_review_status(project_toml, segs[0][0], "approved", cwd=tmp_path)
    set_segment_review_status(project_toml, segs[1][0], "needs_review", cwd=tmp_path)
    set_segment_review_status(project_toml, segs[2][0], "needs_revision", cwd=tmp_path)

    overview = project_overview(project_toml, cwd=tmp_path)
    assert overview.review_counts.approved == 1
    assert overview.review_counts.needs_review == 1
    assert overview.review_counts.needs_revision == 1
    assert overview.review_counts.not_reviewed == 0


def test_overview_volumes_have_snapshot_status(tmp_path: Path) -> None:
    project_toml, db_path = _init_project(tmp_path)
    overview = project_overview(project_toml, cwd=tmp_path)
    assert len(overview.volumes) == 1
    assert overview.volumes[0].snapshot_status in {"missing", "fresh", "stale"}


def test_empty_project_overview(tmp_path: Path) -> None:
    from weaver.services.project import initialize_project

    init = initialize_project(cwd=tmp_path, provider="fake", project_name="empty_proj")
    overview = project_overview(init.project_toml, cwd=tmp_path)
    assert overview.volume_count == 0
    assert overview.segment_count == 0
    assert overview.volumes == []
