"""Tests for C6: [translation] honorifics accepts localize and hybrid."""

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


def _set_honorifics(project_toml: Path, value: str) -> None:
    text = project_toml.read_text(encoding="utf-8")
    lines = text.splitlines()
    new_lines = []
    for line in lines:
        if line.startswith("honorifics"):
            new_lines.append(f'honorifics = "{value}"')
        else:
            new_lines.append(line)
    project_toml.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def test_translate_with_localize_honorifics_succeeds(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    project_toml = _init_project(tmp_path)
    _set_honorifics(project_toml, "localize")

    result = runner.invoke(
        app,
        ["translate", str(project_toml), "--provider", "fake", "--model", "fake-1"],
    )

    assert result.exit_code == 0, result.output
    assert "Translated: 6" in result.output


def test_translate_with_hybrid_honorifics_succeeds(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    project_toml = _init_project(tmp_path)
    _set_honorifics(project_toml, "hybrid")

    result = runner.invoke(
        app,
        ["translate", str(project_toml), "--provider", "fake", "--model", "fake-1"],
    )

    assert result.exit_code == 0, result.output
    assert "Translated: 6" in result.output


def test_translate_with_invalid_honorifics_exits_with_config_error(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    project_toml = _init_project(tmp_path)
    _set_honorifics(project_toml, "rude")

    result = runner.invoke(
        app,
        ["translate", str(project_toml), "--provider", "fake", "--model", "fake-1"],
    )

    assert result.exit_code == 7, result.output
    assert "rude" in result.output
