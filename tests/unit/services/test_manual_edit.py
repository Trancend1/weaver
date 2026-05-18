"""Phase 7 manual edit service tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from weaver.errors import SegmentNotFoundError
from weaver.services.manual_edit import apply_manual_translation
from weaver.services.project import initialize_project
from weaver.services.translation import translate_project

FIXTURE_EPUB = Path(__file__).resolve().parents[2] / "fixtures" / "aozora_sample.epub"


def test_apply_manual_translation_records_text_and_marks_segment_manual(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)
    segment_id = _first_segment_id(init.database_path)

    result = apply_manual_translation(init.project_toml, segment_id, "Hand-fixed translation.")

    assert result.segment_id == segment_id
    assert result.translation == "Hand-fixed translation."
    assert result.attempt == 1
    with sqlite3.connect(init.database_path) as connection:
        status = connection.execute(
            "SELECT status FROM segments WHERE id = ?", (segment_id,)
        ).fetchone()[0]
        rows = connection.execute(
            "SELECT text, provider, model, input_tokens, output_tokens FROM translations "
            "WHERE segment_id = ?",
            (segment_id,),
        ).fetchall()
    assert status == "manual"
    assert len(rows) == 1
    assert rows[0][0] == "Hand-fixed translation."
    assert rows[0][1] == "manual"
    assert rows[0][2] == "manual"
    assert rows[0][3] is None
    assert rows[0][4] is None


def test_apply_manual_translation_overrides_previous_translation_with_new_attempt(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)
    _set_fake_provider(init.project_toml)
    translate_project(init.project_toml)
    segment_id = _first_segment_id(init.database_path)

    result = apply_manual_translation(init.project_toml, segment_id, "Manual override.")

    assert result.attempt == 2
    with sqlite3.connect(init.database_path) as connection:
        status = connection.execute(
            "SELECT status FROM segments WHERE id = ?", (segment_id,)
        ).fetchone()[0]
        attempts = connection.execute(
            "SELECT attempt, text, provider FROM translations WHERE segment_id = ? "
            "ORDER BY attempt",
            (segment_id,),
        ).fetchall()
    assert status == "manual"
    assert [(row[0], row[2]) for row in attempts] == [(1, "fake"), (2, "manual")]
    assert attempts[1][1] == "Manual override."


def test_manual_translation_survives_retry_failed(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)
    _set_fake_provider(init.project_toml)
    translate_project(init.project_toml)
    segment_id = _first_segment_id(init.database_path)
    apply_manual_translation(init.project_toml, segment_id, "Manual override.")
    with sqlite3.connect(init.database_path) as connection:
        connection.execute(
            "UPDATE segments SET status = 'failed' WHERE id != ?",
            (segment_id,),
        )
        connection.commit()

    summary = translate_project(init.project_toml, retry_failed=True)

    assert summary.translated_segments == 5
    with sqlite3.connect(init.database_path) as connection:
        manual_row = connection.execute(
            "SELECT status FROM segments WHERE id = ?", (segment_id,)
        ).fetchone()
        latest_manual = connection.execute(
            "SELECT text, provider FROM translations WHERE segment_id = ? "
            "ORDER BY attempt DESC LIMIT 1",
            (segment_id,),
        ).fetchone()
    assert manual_row[0] == "manual"
    assert latest_manual == ("Manual override.", "manual")


def test_apply_manual_translation_rejects_empty_text(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)
    segment_id = _first_segment_id(init.database_path)

    with pytest.raises(ValueError):
        apply_manual_translation(init.project_toml, segment_id, "   \n\t")


def test_apply_manual_translation_unknown_segment_id_raises(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)

    with pytest.raises(SegmentNotFoundError):
        apply_manual_translation(init.project_toml, "does-not-exist", "Anything.")


def _set_fake_provider(project_toml: Path) -> None:
    text = project_toml.read_text(encoding="utf-8")
    text = text.replace('type = "deepseek"', 'type = "fake"')
    text = text.replace('model = "deepseek-chat"', 'model = "fake-1"')
    text = text.replace('base_url = "http://localhost:11434"', 'pattern = "EN: {source}"')
    project_toml.write_text(text, encoding="utf-8")


def _first_segment_id(db_path: Path) -> str:
    with sqlite3.connect(db_path) as connection:
        return str(
            connection.execute("SELECT id FROM segments ORDER BY block_order LIMIT 1").fetchone()[0]
        )
