"""Tests for the Content Explorer segment-listing read service (Sprint Q9)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from weaver.errors import VolumeNotFoundError
from weaver.services.project import initialize_project
from weaver.services.segment_listing import list_volume_segments

FIXTURE_EPUB = Path(__file__).parents[2] / "fixtures" / "aozora_sample.epub"


def _project(tmp_path: Path) -> tuple[Path, Path, int]:
    result = initialize_project(FIXTURE_EPUB, cwd=tmp_path, project_name="alpha")
    db_path = tmp_path / ".weaver" / "alpha" / "weaver.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    volume_id = int(conn.execute("SELECT id FROM volumes LIMIT 1").fetchone()["id"])
    conn.close()
    return result.project_toml, db_path, volume_id


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def test_lists_chapters_with_counts(tmp_path: Path) -> None:
    project_toml, _, volume_id = _project(tmp_path)

    listing = list_volume_segments(project_toml, volume_id, cwd=tmp_path)

    assert listing.volume_id == volume_id
    assert listing.chapters, "fixture volume should have chapters"
    first = listing.chapters[0]
    assert first.segment_count > 0
    assert first.status_counts.get("pending", 0) == first.segment_count
    assert first.review_counts.get("not_reviewed", 0) == first.segment_count
    # Default selection = first chapter, with rows.
    assert listing.page is not None
    assert listing.page.chapter_id == first.chapter_id
    assert listing.page.total == first.segment_count


def test_status_filter_and_reconciliation(tmp_path: Path) -> None:
    project_toml, db_path, volume_id = _project(tmp_path)
    conn = _connect(db_path)
    row = conn.execute("SELECT id, chapter_id FROM segments LIMIT 1").fetchone()
    seg_id, chapter_id = str(row["id"]), str(row["chapter_id"])
    conn.execute("UPDATE segments SET status = 'translated' WHERE id = ?", (seg_id,))
    conn.commit()
    conn.close()

    listing = list_volume_segments(
        project_toml, volume_id, chapter_id=chapter_id, status="translated", cwd=tmp_path
    )
    assert listing.page is not None
    assert listing.page.total == 1
    assert listing.page.rows[0].id == seg_id
    assert listing.page.rows[0].status == "translated"


def test_review_filter(tmp_path: Path) -> None:
    project_toml, db_path, volume_id = _project(tmp_path)
    conn = _connect(db_path)
    row = conn.execute("SELECT id, chapter_id FROM segments LIMIT 1").fetchone()
    seg_id, chapter_id = str(row["id"]), str(row["chapter_id"])
    conn.execute("UPDATE segments SET review_status = 'needs_revision' WHERE id = ?", (seg_id,))
    conn.commit()
    conn.close()

    listing = list_volume_segments(
        project_toml, volume_id, chapter_id=chapter_id, review_status="needs_revision", cwd=tmp_path
    )
    assert listing.page is not None
    assert [r.id for r in listing.page.rows] == [seg_id]


def test_unknown_filter_values_are_ignored(tmp_path: Path) -> None:
    project_toml, _, volume_id = _project(tmp_path)

    listing = list_volume_segments(
        project_toml, volume_id, status="bogus", review_status="nope", cwd=tmp_path
    )
    assert listing.status_filter == ""
    assert listing.review_filter == ""
    assert listing.page is not None and listing.page.total > 0


def test_pagination_clamps_and_pages(tmp_path: Path) -> None:
    project_toml, db_path, volume_id = _project(tmp_path)
    conn = _connect(db_path)
    chapter_id = str(conn.execute("SELECT id FROM chapters LIMIT 1").fetchone()["id"])
    conn.close()

    listing = list_volume_segments(
        project_toml, volume_id, chapter_id=chapter_id, page=1, page_size=2, cwd=tmp_path
    )
    assert listing.page is not None
    p1 = listing.page
    assert len(p1.rows) <= 2
    assert p1.page == 1
    if p1.total > 2:
        assert p1.has_next
        p2 = list_volume_segments(
            project_toml, volume_id, chapter_id=chapter_id, page=2, page_size=2, cwd=tmp_path
        ).page
        assert p2 is not None
        assert p2.page == 2
        assert [r.id for r in p2.rows] != [r.id for r in p1.rows]

    # Out-of-range page clamps to the last page instead of erroring.
    clamped = list_volume_segments(
        project_toml, volume_id, chapter_id=chapter_id, page=9999, page_size=2, cwd=tmp_path
    ).page
    assert clamped is not None
    assert clamped.page == clamped.page_count


def test_rows_ordered_by_block_order(tmp_path: Path) -> None:
    project_toml, _, volume_id = _project(tmp_path)
    listing = list_volume_segments(project_toml, volume_id, cwd=tmp_path)
    assert listing.page is not None
    orders = [r.block_order for r in listing.page.rows]
    assert orders == sorted(orders)


def test_unknown_chapter_falls_back_to_first(tmp_path: Path) -> None:
    project_toml, _, volume_id = _project(tmp_path)
    listing = list_volume_segments(project_toml, volume_id, chapter_id="nope", cwd=tmp_path)
    assert listing.page is not None
    assert listing.page.chapter_id == listing.chapters[0].chapter_id


def test_missing_volume_raises(tmp_path: Path) -> None:
    project_toml, _, _ = _project(tmp_path)
    with pytest.raises(VolumeNotFoundError):
        list_volume_segments(project_toml, 9999, cwd=tmp_path)


def test_listing_does_not_modify_database(tmp_path: Path) -> None:
    project_toml, db_path, volume_id = _project(tmp_path)
    mtime_before = db_path.stat().st_mtime_ns

    list_volume_segments(project_toml, volume_id, cwd=tmp_path)

    assert db_path.stat().st_mtime_ns == mtime_before
