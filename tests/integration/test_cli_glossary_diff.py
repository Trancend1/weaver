"""Integration tests for weaver glossary diff command."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from weaver.cli.main import app

FIXTURE_EPUB = Path(__file__).parents[1] / "fixtures" / "aozora_sample.epub"


def _init_project(tmp_path: Path) -> Path:
    runner = CliRunner()
    result = runner.invoke(app, ["init", str(FIXTURE_EPUB)])
    assert result.exit_code == 0, result.output
    return tmp_path / ".weaver" / "aozora_sample" / "project.toml"


def test_glossary_diff_exits_zero_with_empty_glossary(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    project_toml = _init_project(tmp_path)

    result = runner.invoke(app, ["glossary", "diff", str(project_toml), "1", "2"])

    assert result.exit_code == 0, result.output
    assert "No approved glossary terms found in either chapter." in result.output


def test_glossary_diff_out_of_range_chapter_exits_nonzero(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    project_toml = _init_project(tmp_path)

    result = runner.invoke(app, ["glossary", "diff", str(project_toml), "99", "1"])

    assert result.exit_code != 0
    assert "out of range" in result.output
