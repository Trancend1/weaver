"""CLI integration tests for `weaver translate`."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from typer.testing import CliRunner

from weaver.cli.main import app

FIXTURE_EPUB = Path(__file__).parents[1] / "fixtures" / "aozora_sample.epub"


def test_weaver_translate_runs_fake_provider_project(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    init_result = runner.invoke(app, ["init", str(FIXTURE_EPUB)])
    assert init_result.exit_code == 0, init_result.output
    project_toml = tmp_path / ".weaver" / "aozora_sample" / "project.toml"
    _set_fake_provider(project_toml)

    translate_result = runner.invoke(app, ["translate", str(project_toml)])

    assert translate_result.exit_code == 0, translate_result.output
    assert "Translated: 6" in translate_result.output
    assert "Failed: 0" in translate_result.output
    with sqlite3.connect(tmp_path / ".weaver" / "aozora_sample" / "weaver.db") as connection:
        translated = connection.execute(
            "SELECT COUNT(*) FROM segments WHERE status = 'translated'"
        ).fetchone()[0]
    assert translated == 6


def test_translate_max_concurrent_flag_overrides_config(tmp_path, monkeypatch) -> None:
    # --max-concurrent runs the bounded window (ADR 020) for this run only,
    # without touching project.toml.
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    init_result = runner.invoke(app, ["init", str(FIXTURE_EPUB)])
    assert init_result.exit_code == 0, init_result.output
    project_toml = tmp_path / ".weaver" / "aozora_sample" / "project.toml"
    _set_fake_provider(project_toml)

    result = runner.invoke(app, ["translate", str(project_toml), "--max-concurrent", "3"])

    assert result.exit_code == 0, result.output
    assert "Translated: 6" in result.output
    assert "Failed: 0" in result.output
    assert "max_concurrent" not in project_toml.read_text(encoding="utf-8")
    with sqlite3.connect(tmp_path / ".weaver" / "aozora_sample" / "weaver.db") as connection:
        translated = connection.execute(
            "SELECT COUNT(*) FROM segments WHERE status = 'translated'"
        ).fetchone()[0]
        attempts = connection.execute("SELECT COUNT(*) FROM translations").fetchone()[0]
    assert translated == 6
    assert attempts == 6  # no duplicate attempt rows from two workers racing


def test_translate_rejects_out_of_range_max_concurrent(tmp_path, monkeypatch) -> None:
    # Out of range exits with the ConfigError code (PRD_v2.md §10 AC-9) and the
    # message points at the flag, not at project.toml.
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    init_result = runner.invoke(app, ["init", str(FIXTURE_EPUB)])
    assert init_result.exit_code == 0, init_result.output
    project_toml = tmp_path / ".weaver" / "aozora_sample" / "project.toml"
    _set_fake_provider(project_toml)

    result = runner.invoke(app, ["translate", str(project_toml), "--max-concurrent", "9"])

    assert result.exit_code == 7, result.output
    assert "max_concurrent" in result.output
    assert "--max-concurrent" in result.output

    # --dry-run must reject it too, or "validate my command first" would pass
    # and only the real run would fail.
    dry = runner.invoke(app, ["translate", str(project_toml), "--max-concurrent", "9", "--dry-run"])

    assert dry.exit_code == 7, dry.output


def _set_fake_provider(project_toml: Path) -> None:
    text = project_toml.read_text(encoding="utf-8")
    text = text.replace('type = ""', 'type = "fake"')
    text = text.replace('type = "deepseek"', 'type = "fake"')
    text = text.replace('model = ""', 'model = "fake-1"')
    text = text.replace('model = "deepseek-chat"', 'model = "fake-1"')
    if 'pattern = "EN: {source}"' not in text:
        text = text.replace('model = "fake-1"', 'model = "fake-1"\npattern = "EN: {source}"')
    project_toml.write_text(text, encoding="utf-8")
