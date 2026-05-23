"""Tests for Phase A3/A4/A5: translate --provider/--model, --dry-run, --verbose."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from typer.testing import CliRunner

from weaver.cli.main import app

FIXTURE_EPUB = Path(__file__).parents[1] / "fixtures" / "aozora_sample.epub"


def _init_with_deepseek_default(tmp_path: Path) -> Path:
    """Init a project leaving project.toml at the default [provider] = deepseek."""

    runner = CliRunner()
    init_result = runner.invoke(app, ["init", str(FIXTURE_EPUB)])
    assert init_result.exit_code == 0, init_result.output
    return tmp_path / ".weaver" / "aozora_sample" / "project.toml"


def test_translate_dry_run_reports_segment_count_and_writes_nothing(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    project_toml = _init_with_deepseek_default(tmp_path)

    result = runner.invoke(app, ["translate", str(project_toml), "--dry-run"])

    assert result.exit_code == 0, result.output
    assert "Would translate 6 segments" in result.output
    assert "Estimated input tokens" in result.output
    with sqlite3.connect(tmp_path / ".weaver" / "aozora_sample" / "weaver.db") as connection:
        translated = connection.execute(
            "SELECT COUNT(*) FROM segments WHERE status = 'translated'"
        ).fetchone()[0]
        pending = connection.execute(
            "SELECT COUNT(*) FROM segments WHERE status = 'pending'"
        ).fetchone()[0]
    assert translated == 0
    assert pending == 6


def test_translate_provider_override_runs_fake_without_editing_toml(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    project_toml = _init_with_deepseek_default(tmp_path)

    # Project.toml still says deepseek. Override per-run to fake.
    result = runner.invoke(
        app,
        [
            "translate",
            str(project_toml),
            "--provider",
            "fake",
            "--model",
            "fake-1",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Translated: 6" in result.output
    with sqlite3.connect(tmp_path / ".weaver" / "aozora_sample" / "weaver.db") as connection:
        provider = connection.execute("SELECT DISTINCT provider FROM translations").fetchall()
    assert {row[0] for row in provider} == {"fake"}


def test_translate_verbose_echoes_per_segment_token_lines(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    project_toml = _init_with_deepseek_default(tmp_path)

    result = runner.invoke(
        app,
        [
            "translate",
            str(project_toml),
            "--provider",
            "fake",
            "--model",
            "fake-1",
            "--verbose",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "<- in=" in result.output
    assert "out=" in result.output


def test_translate_dry_run_with_provider_override_still_does_not_touch_provider(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    project_toml = _init_with_deepseek_default(tmp_path)

    # --dry-run with a bogus provider/model must not error or call out.
    result = runner.invoke(
        app,
        [
            "translate",
            str(project_toml),
            "--dry-run",
            "--provider",
            "gemini",
            "--model",
            "no-such-model",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Would translate 6 segments" in result.output
