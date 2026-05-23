"""CLI integration tests for destructive-action confirmation prompts."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from weaver.cli.main import app

FIXTURE_EPUB = Path(__file__).parents[1] / "fixtures" / "aozora_sample.epub"


def test_init_overwrite_prompt_aborts_on_no(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    # First init succeeds
    result = runner.invoke(app, ["init", str(FIXTURE_EPUB)])
    assert result.exit_code == 0, result.output

    # Second init without --yes prompts and 'n' aborts
    result = runner.invoke(app, ["init", str(FIXTURE_EPUB)], input="n\n")
    assert result.exit_code != 0


def test_init_overwrite_with_yes_succeeds(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    # First init
    result = runner.invoke(app, ["init", str(FIXTURE_EPUB)])
    assert result.exit_code == 0, result.output

    # Second init with --yes skips prompt
    result = runner.invoke(app, ["init", str(FIXTURE_EPUB), "--yes"])
    assert result.exit_code == 0, result.output
    assert "Created:" in result.output


def test_init_first_time_no_prompt(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    # Fresh init should not prompt
    result = runner.invoke(app, ["init", str(FIXTURE_EPUB)])
    assert result.exit_code == 0, result.output
    assert "Overwrite?" not in result.output
