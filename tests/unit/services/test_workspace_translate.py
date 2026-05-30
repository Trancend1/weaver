"""Tests for chapter-/selection-scoped AI translation (Sprint 4A)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from weaver.errors import ChapterNotFoundError, SegmentNotFoundError
from weaver.services.project import initialize_project
from weaver.services.workspace_edit import save_segment_translation
from weaver.services.workspace_translate import (
    prepare_chapter_translation,
    run_translation,
)
from weaver.storage.db import connect_database, transaction
from weaver.storage.segments import update_segment_status

FIXTURE_EPUB = Path(__file__).resolve().parents[2] / "fixtures" / "aozora_sample.epub"


def _set_fake_provider(project_toml: Path) -> None:
    text = project_toml.read_text(encoding="utf-8")
    text = text.replace('type = "deepseek"', 'type = "fake"')
    text = text.replace('model = "deepseek-chat"', 'model = "fake-1"\npattern = "EN: {source}"')
    project_toml.write_text(text, encoding="utf-8")


def _first_chapter_id(db_path: Path) -> str:
    with sqlite3.connect(db_path) as connection:
        return str(
            connection.execute(
                "SELECT chapter_id FROM segments ORDER BY block_order LIMIT 1"
            ).fetchone()[0]
        )


def _chapter_segment_ids(db_path: Path, chapter_id: str) -> list[str]:
    with sqlite3.connect(db_path) as connection:
        return [
            str(row[0])
            for row in connection.execute(
                "SELECT id FROM segments WHERE chapter_id = ? ORDER BY block_order",
                (chapter_id,),
            ).fetchall()
        ]


def _status(db_path: Path, segment_id: str) -> str:
    with sqlite3.connect(db_path) as connection:
        return str(
            connection.execute(
                "SELECT status FROM segments WHERE id = ?", (segment_id,)
            ).fetchone()[0]
        )


def _count_translations(db_path: Path) -> int:
    with sqlite3.connect(db_path) as connection:
        return int(connection.execute("SELECT COUNT(*) FROM translations").fetchone()[0])


def _attempt_texts(db_path: Path, segment_id: str) -> list[str]:
    with sqlite3.connect(db_path) as connection:
        return [
            str(row[0])
            for row in connection.execute(
                "SELECT text FROM translations WHERE segment_id = ? ORDER BY attempt",
                (segment_id,),
            ).fetchall()
        ]


def test_chapter_translate_translates_all_pending(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)
    _set_fake_provider(init.project_toml)
    chapter_id = _first_chapter_id(init.database_path)
    segment_ids = _chapter_segment_ids(init.database_path, chapter_id)

    plan = prepare_chapter_translation(init.project_toml, chapter_id)
    result = run_translation(plan)

    assert plan.mode == "chapter"
    assert result.selected == len(segment_ids)
    assert result.translated == len(segment_ids)
    assert result.failed == 0
    assert result.skipped == 0
    assert _count_translations(init.database_path) == len(segment_ids)
    for segment_id in segment_ids:
        assert _status(init.database_path, segment_id) == "translated"


def test_selection_translate_only_given_segments(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)
    _set_fake_provider(init.project_toml)
    chapter_id = _first_chapter_id(init.database_path)
    segment_ids = _chapter_segment_ids(init.database_path, chapter_id)
    chosen = segment_ids[:2]

    plan = prepare_chapter_translation(init.project_toml, chapter_id, segment_ids=chosen)
    result = run_translation(plan)

    assert plan.mode == "selection"
    assert result.selected == 2
    assert result.translated == 2
    for segment_id in chosen:
        assert _status(init.database_path, segment_id) == "translated"
    for segment_id in segment_ids[2:]:
        assert _status(init.database_path, segment_id) == "pending"


def test_chapter_translate_skips_already_translated(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)
    _set_fake_provider(init.project_toml)
    chapter_id = _first_chapter_id(init.database_path)
    segment_ids = _chapter_segment_ids(init.database_path, chapter_id)
    with connect_database(init.database_path) as connection, transaction(connection):
        update_segment_status(connection, segment_id=segment_ids[0], status="translated")

    plan = prepare_chapter_translation(init.project_toml, chapter_id)
    result = run_translation(plan)

    assert result.selected == len(segment_ids) - 1
    assert result.skipped == 1
    assert result.translated == len(segment_ids) - 1
    assert segment_ids[0] not in plan.target_segment_ids


def test_prepare_rejects_unknown_chapter(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)
    _set_fake_provider(init.project_toml)

    with pytest.raises(ChapterNotFoundError):
        prepare_chapter_translation(init.project_toml, "does-not-exist")


def test_prepare_rejects_segment_from_other_chapter(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)
    _set_fake_provider(init.project_toml)
    chapter_id = _first_chapter_id(init.database_path)

    with pytest.raises(SegmentNotFoundError):
        prepare_chapter_translation(init.project_toml, chapter_id, segment_ids=["nope"])


def test_prepare_rejects_empty_selection(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)
    _set_fake_provider(init.project_toml)
    chapter_id = _first_chapter_id(init.database_path)

    with pytest.raises(ValueError):
        prepare_chapter_translation(init.project_toml, chapter_id, segment_ids=[])


def test_provider_override_runs_fake_without_editing_config(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)  # default provider left unchanged
    chapter_id = _first_chapter_id(init.database_path)

    plan = prepare_chapter_translation(
        init.project_toml,
        chapter_id,
        provider_override={"type": "fake", "model": "fake-1"},
    )
    result = run_translation(plan)

    assert plan.provider.name == "fake"
    assert plan.provider_model == "fake-1"
    assert result.translated == result.selected
    assert result.translated > 0


def test_prepare_rejects_unknown_mode(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)
    _set_fake_provider(init.project_toml)
    chapter_id = _first_chapter_id(init.database_path)

    with pytest.raises(ValueError):
        prepare_chapter_translation(init.project_toml, chapter_id, mode="bogus")


def test_skip_existing_skips_everything_once_translated(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)
    _set_fake_provider(init.project_toml)
    chapter_id = _first_chapter_id(init.database_path)
    segment_ids = _chapter_segment_ids(init.database_path, chapter_id)
    run_translation(prepare_chapter_translation(init.project_toml, chapter_id))

    plan = prepare_chapter_translation(init.project_toml, chapter_id)  # skip_existing default
    result = run_translation(plan)

    assert plan.target_segment_ids == ()
    assert result.selected == 0
    assert result.skipped == len(segment_ids)


def test_retranslate_non_manual_retranslates_translated_protects_manual(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)
    _set_fake_provider(init.project_toml)
    chapter_id = _first_chapter_id(init.database_path)
    segment_ids = _chapter_segment_ids(init.database_path, chapter_id)
    run_translation(prepare_chapter_translation(init.project_toml, chapter_id))  # all translated
    save_segment_translation(init.project_toml, chapter_id, segment_ids[0], "hand edit")  # manual

    plan = prepare_chapter_translation(
        init.project_toml, chapter_id, mode="retranslate_non_manual"
    )
    run_translation(plan)

    assert segment_ids[0] not in plan.target_segment_ids  # manual protected
    assert set(segment_ids[1:]) <= set(plan.target_segment_ids)  # translated retranslated
    assert _status(init.database_path, segment_ids[0]) == "manual"


def test_force_selected_overwrites_manual_and_appends_attempt(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)
    _set_fake_provider(init.project_toml)
    chapter_id = _first_chapter_id(init.database_path)
    segment_ids = _chapter_segment_ids(init.database_path, chapter_id)
    save_segment_translation(init.project_toml, chapter_id, segment_ids[0], "hand edit")
    before = _attempt_texts(init.database_path, segment_ids[0])

    plan = prepare_chapter_translation(
        init.project_toml, chapter_id, segment_ids=[segment_ids[0]], mode="force_selected"
    )
    result = run_translation(plan)

    assert plan.target_segment_ids == (segment_ids[0],)
    assert result.translated == 1
    after = _attempt_texts(init.database_path, segment_ids[0])
    assert len(after) == len(before) + 1  # append-only
    assert "hand edit" in after  # prior manual attempt preserved as history
    assert _status(init.database_path, segment_ids[0]) == "translated"
