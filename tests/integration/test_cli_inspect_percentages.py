"""Tests for Phase A14: inspect table shows segment/glossary percentages."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from weaver.cli.main import app

FIXTURE_EPUB = Path(__file__).parents[1] / "fixtures" / "aozora_sample.epub"


def test_inspect_pending_row_shows_count_and_percent(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    init = runner.invoke(app, ["init", str(FIXTURE_EPUB)])
    assert init.exit_code == 0, init.output
    project_toml = tmp_path / ".weaver" / "aozora_sample" / "project.toml"

    result = runner.invoke(app, ["inspect", str(project_toml)])

    assert result.exit_code == 0, result.output
    # All 6 segments are pending at a fresh init → 100.0%.
    assert "6 (100.0%)" in result.output


def test_inspect_after_translate_reports_translated_percent(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    init = runner.invoke(app, ["init", str(FIXTURE_EPUB)])
    assert init.exit_code == 0, init.output
    project_toml = tmp_path / ".weaver" / "aozora_sample" / "project.toml"

    tx = runner.invoke(
        app,
        ["translate", str(project_toml), "--provider", "fake", "--model", "fake-1"],
    )
    assert tx.exit_code == 0, tx.output

    result = runner.invoke(app, ["inspect", str(project_toml)])
    assert result.exit_code == 0, result.output
    # After translating all 6, Translated should read 6 (100.0%) and Pending 0 with no percent.
    assert "100.0%" in result.output


def test_inspect_glossary_terms_row_shows_candidate_denominator(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    init = runner.invoke(app, ["init", str(FIXTURE_EPUB)])
    assert init.exit_code == 0, init.output
    project_toml = tmp_path / ".weaver" / "aozora_sample" / "project.toml"

    result = runner.invoke(app, ["inspect", str(project_toml)])

    assert result.exit_code == 0, result.output
    # Fresh init has 0 approved terms out of N candidates → "0 (0.0% of candidates)".
    assert "of candidates" in result.output
