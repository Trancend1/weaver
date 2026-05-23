"""CLI integration tests for `weaver init --from-template`."""

from __future__ import annotations

import tomllib
from pathlib import Path

from typer.testing import CliRunner

from weaver.cli.main import app

FIXTURE_EPUB = Path(__file__).parents[1] / "fixtures" / "aozora_sample.epub"


def test_init_with_light_novel_template(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ["init", str(FIXTURE_EPUB), "--from-template", "light-novel"])
    assert result.exit_code == 0, result.output
    assert "Template: light-novel" in result.output

    project_toml = tmp_path / ".weaver" / "aozora_sample" / "project.toml"
    data = tomllib.loads(project_toml.read_text(encoding="utf-8"))
    assert data["glossary"]["max_terms_per_segment"] == 30
    assert data["glossary"]["require_review"] is True
    assert data["qa"]["minimum_length_ratio"] == 0.25


def test_init_with_web_novel_template(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ["init", str(FIXTURE_EPUB), "--from-template", "web-novel"])
    assert result.exit_code == 0, result.output

    project_toml = tmp_path / ".weaver" / "aozora_sample" / "project.toml"
    data = tomllib.loads(project_toml.read_text(encoding="utf-8"))
    assert data["glossary"]["max_terms_per_segment"] == 15
    assert data["glossary"]["require_review"] is False
    assert data["qa"]["minimum_length_ratio"] == 0.2


def test_init_with_unknown_template_fails(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ["init", str(FIXTURE_EPUB), "--from-template", "nonexistent"])
    assert result.exit_code != 0
    assert "Unknown template" in result.output
