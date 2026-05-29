"""Tests for Phase A6 helper: manual_edit.resolve_segment_id."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from weaver.errors import SegmentNotFoundError
from weaver.services.manual_edit import resolve_segment_id
from weaver.services.project import initialize_project
from weaver.services.translation import translate_project

FIXTURE_EPUB = Path(__file__).resolve().parents[2] / "fixtures" / "aozora_sample.epub"


def _set_fake_provider(project_toml: Path) -> None:
    text = project_toml.read_text(encoding="utf-8")
    text = text.replace('type = "deepseek"', 'type = "fake"')
    text = text.replace('model = "deepseek-chat"', 'model = "fake-1"')
    text = text.replace('model = "fake-1"', 'model = "fake-1"\npattern = "EN: {source}"')
    project_toml.write_text(text, encoding="utf-8")


def test_resolve_first_failed_returns_earliest_failed_segment_in_epub_order(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)

    with sqlite3.connect(init.database_path) as connection:
        connection.execute(
            "UPDATE segments SET status = 'failed' WHERE id IN "
            "(SELECT s.id FROM segments s JOIN chapters c ON c.id = s.chapter_id "
            "ORDER BY c.spine_order, s.block_order LIMIT 2)"
        )
        connection.commit()
        ordered_failed = [
            row[0]
            for row in connection.execute(
                "SELECT s.id FROM segments s JOIN chapters c ON c.id = s.chapter_id "
                "WHERE s.status = 'failed' "
                "ORDER BY c.spine_order, s.block_order"
            )
        ]

    resolved = resolve_segment_id(init.project_toml, selector="first-failed")
    assert resolved == ordered_failed[0]


def test_resolve_next_stale_returns_first_stale_segment(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)

    with sqlite3.connect(init.database_path) as connection:
        connection.execute(
            "UPDATE segments SET status = 'stale' WHERE id = "
            "(SELECT id FROM segments LIMIT 1 OFFSET 1)"
        )
        connection.commit()
        stale_id = connection.execute(
            "SELECT id FROM segments WHERE status = 'stale' LIMIT 1"
        ).fetchone()[0]

    resolved = resolve_segment_id(init.project_toml, selector="next-stale")
    assert resolved == stale_id


def test_resolve_recent_returns_segment_with_latest_translation(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)
    _set_fake_provider(init.project_toml)
    translate_project(init.project_toml)

    # The most recently translated segment is the last one in iteration order.
    with sqlite3.connect(init.database_path) as connection:
        most_recent = connection.execute(
            "SELECT segment_id FROM translations ORDER BY created_at DESC, attempt DESC LIMIT 1"
        ).fetchone()[0]

    resolved = resolve_segment_id(init.project_toml, selector="recent")
    assert resolved == most_recent


def test_resolve_first_failed_raises_when_no_failed_segments(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)

    with pytest.raises(SegmentNotFoundError):
        resolve_segment_id(init.project_toml, selector="first-failed")


def test_resolve_recent_raises_when_no_translations(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)

    with pytest.raises(SegmentNotFoundError):
        resolve_segment_id(init.project_toml, selector="recent")
