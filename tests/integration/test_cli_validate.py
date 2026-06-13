"""CLI tests for Phase 9 `weaver validate`."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from typer.testing import CliRunner

from weaver.cli.main import app
from weaver.storage.db import connect_database, transaction
from weaver.storage.segments import update_segment_status

FIXTURE_EPUB = Path(__file__).parents[1] / "fixtures" / "aozora_sample.epub"


def test_weaver_validate_reports_clean_run_when_no_issues_exit_zero(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    project_toml = _init_with_fake_pattern(runner, tmp_path, pattern="EN translation.")
    _translate(runner, project_toml)

    result = runner.invoke(app, ["validate", str(project_toml)])

    assert result.exit_code == 0, result.output
    assert "No QA warnings." in result.output


def test_weaver_validate_detects_untranslated_japanese_exit_one(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    project_toml = _init_with_fake_pattern(runner, tmp_path, pattern="EN: {source}")
    _translate(runner, project_toml)

    result = runner.invoke(app, ["validate", str(project_toml)])

    assert result.exit_code == 1, result.output
    assert "untranslated_japanese" in result.output
    assert "critical" in result.output


def test_weaver_validate_flags_failed_segment_exit_one(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    project_toml = _init_with_fake_pattern(runner, tmp_path, pattern="EN translation.")
    _translate(runner, project_toml)

    db_path = tmp_path / ".weaver" / "aozora_sample" / "weaver.db"
    segment_ids = _segment_ids(db_path)
    with connect_database(db_path) as connection, transaction(connection):
        update_segment_status(connection, segment_id=segment_ids[0], status="failed")

    result = runner.invoke(app, ["validate", str(project_toml)])

    assert result.exit_code == 1, result.output
    assert "failed_segment" in result.output
    assert segment_ids[0] in result.output


def test_weaver_validate_warning_only_exits_zero(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    project_toml = _init_with_fake_pattern(runner, tmp_path, pattern="EN translation.")
    _translate(runner, project_toml)

    db_path = tmp_path / ".weaver" / "aozora_sample" / "weaver.db"
    segment_ids = _segment_ids(db_path)
    with connect_database(db_path) as connection, transaction(connection):
        update_segment_status(connection, segment_id=segment_ids[0], status="stale")

    result = runner.invoke(app, ["validate", str(project_toml)])

    assert result.exit_code == 0, result.output
    assert "stale_segment" in result.output


def test_weaver_validate_json_output_shape(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    project_toml = _init_with_fake_pattern(runner, tmp_path, pattern="EN: {source}")
    _translate(runner, project_toml)

    result = runner.invoke(app, ["validate", str(project_toml), "--json"])

    assert result.exit_code == 1, result.output
    payload = json.loads(result.output)
    assert payload["project"] == "aozora_sample"
    assert isinstance(payload["total_segments"], int)
    assert payload["total_segments"] > 0
    assert set(payload["summary"].keys()) == {"info", "warning", "critical"}
    assert payload["summary"]["critical"] >= 1
    assert any(finding["check"] == "untranslated_japanese" for finding in payload["findings"])


def _init_with_fake_pattern(runner: CliRunner, tmp_path: Path, *, pattern: str) -> Path:
    init = runner.invoke(app, ["init", str(FIXTURE_EPUB)])
    assert init.exit_code == 0, init.output
    project_toml = tmp_path / ".weaver" / "aozora_sample" / "project.toml"
    text = project_toml.read_text(encoding="utf-8")
    text = text.replace('type = ""', 'type = "fake"')
    text = text.replace('type = "deepseek"', 'type = "fake"')
    text = text.replace('model = ""', 'model = "fake-1"')
    text = text.replace('model = "deepseek-chat"', 'model = "fake-1"')
    text = text.replace(
        'model = "fake-1"',
        f'model = "fake-1"\npattern = "{pattern}"',
    )
    project_toml.write_text(text, encoding="utf-8")
    return project_toml


def _translate(runner: CliRunner, project_toml: Path) -> None:
    translate = runner.invoke(app, ["translate", str(project_toml)])
    assert translate.exit_code == 0, translate.output


def _segment_ids(db_path: Path) -> list[str]:
    with sqlite3.connect(db_path) as connection:
        return [
            str(row[0])
            for row in connection.execute(
                """
                SELECT s.id
                FROM segments s
                JOIN chapters c ON c.id = s.chapter_id
                ORDER BY c.spine_order, s.block_order
                """
            ).fetchall()
        ]
