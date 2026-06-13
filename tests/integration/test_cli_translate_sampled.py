"""CLI integration tests for `weaver translate --first-N`."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from typer.testing import CliRunner

from weaver.cli.main import app

FIXTURE_EPUB = Path(__file__).parents[1] / "fixtures" / "aozora_sample.epub"


def _init_fake_project(tmp_path: Path, runner: CliRunner) -> Path:
    result = runner.invoke(app, ["init", str(FIXTURE_EPUB)])
    assert result.exit_code == 0, result.output
    project_toml = tmp_path / ".weaver" / "aozora_sample" / "project.toml"
    _set_fake_provider(project_toml)
    return project_toml


def test_first_n_translates_only_n_segments(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    project_toml = _init_fake_project(tmp_path, runner)

    result = runner.invoke(app, ["translate", str(project_toml), "--first-N", "2"])
    assert result.exit_code == 0, result.output
    assert "Selected: 2" in result.output
    assert "Translated: 2" in result.output

    with sqlite3.connect(tmp_path / ".weaver" / "aozora_sample" / "weaver.db") as conn:
        translated = conn.execute(
            "SELECT COUNT(*) FROM segments WHERE status = 'translated'"
        ).fetchone()[0]
    assert translated == 2


def test_first_n_zero_translates_nothing(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    project_toml = _init_fake_project(tmp_path, runner)

    result = runner.invoke(app, ["translate", str(project_toml), "--first-N", "0"])
    assert result.exit_code == 0, result.output
    assert "Selected: 0" in result.output
    assert "Translated: 0" in result.output


def test_first_n_with_dry_run(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    project_toml = _init_fake_project(tmp_path, runner)

    result = runner.invoke(app, ["translate", str(project_toml), "--first-N", "3", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "Would translate 3 segments" in result.output


def _set_fake_provider(project_toml: Path) -> None:
    text = project_toml.read_text(encoding="utf-8")
    text = text.replace('type = ""', 'type = "fake"')
    text = text.replace('type = "deepseek"', 'type = "fake"')
    text = text.replace('model = ""', 'model = "fake-1"')
    text = text.replace('model = "deepseek-chat"', 'model = "fake-1"')
    if 'pattern = "EN: {source}"' not in text:
        text = text.replace('model = "fake-1"', 'model = "fake-1"\npattern = "EN: {source}"')
    project_toml.write_text(text, encoding="utf-8")
