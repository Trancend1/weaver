"""CLI integration tests for `weaver preview`."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from weaver.cli.main import app

FIXTURE_EPUB = Path(__file__).parents[1] / "fixtures" / "aozora_sample.epub"


def _init_project(tmp_path: Path, runner: CliRunner) -> Path:
    result = runner.invoke(app, ["init", str(FIXTURE_EPUB)])
    assert result.exit_code == 0, result.output
    return tmp_path / ".weaver" / "aozora_sample" / "project.toml"


def test_preview_shows_segments(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    project_toml = _init_project(tmp_path, runner)

    result = runner.invoke(app, ["preview", str(project_toml)])
    assert result.exit_code == 0, result.output
    assert "Source:" in result.output
    assert "Chapter" in result.output


def test_preview_chapter_filter(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    project_toml = _init_project(tmp_path, runner)

    result = runner.invoke(app, ["preview", str(project_toml), "--chapter", "1"])
    assert result.exit_code == 0, result.output
    assert "Chapter 1:" in result.output


def test_preview_invalid_chapter(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    project_toml = _init_project(tmp_path, runner)

    result = runner.invoke(app, ["preview", str(project_toml), "--chapter", "999"])
    assert result.exit_code != 0


def test_preview_invalid_segment(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    project_toml = _init_project(tmp_path, runner)

    result = runner.invoke(app, ["preview", str(project_toml), "--segment", "nonexistent"])
    assert result.exit_code != 0
