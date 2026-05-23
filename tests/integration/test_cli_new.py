"""Integration tests for weaver new command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from weaver.cli.main import app
from weaver.errors import ConfigError
from weaver.services.wizard import WizardAnswers

FIXTURE_EPUB = Path(__file__).parents[1] / "fixtures" / "aozora_sample.epub"


def test_new_with_yes_and_mocked_wizard_creates_project(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    answers = WizardAnswers(
        epub_path=FIXTURE_EPUB,
        provider="fake",
        template=None,
        working_dir=tmp_path,
    )
    with patch("weaver.services.wizard.run_new_wizard", return_value=answers):
        result = runner.invoke(app, ["new", "--yes"])

    assert result.exit_code == 0, result.output
    assert "Created:" in result.output
    assert (tmp_path / ".weaver" / "aozora_sample" / "project.toml").exists()


def test_new_wizard_config_error_surfaced(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    with patch(
        "weaver.services.wizard.run_new_wizard",
        side_effect=ConfigError(
            "weaver new requires questionary. "
            "Likely cause: optional dependency not installed. "
            "Next command: pip install 'weaver[wizard]'"
        ),
    ):
        result = runner.invoke(app, ["new", "--yes"])

    assert result.exit_code == 7
    assert "weaver[wizard]" in result.output


def test_new_invalid_epub_raises_error(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    missing_epub = tmp_path / "nonexistent.epub"

    answers = WizardAnswers(
        epub_path=missing_epub,
        provider="fake",
        template=None,
        working_dir=tmp_path,
    )
    with patch("weaver.services.wizard.run_new_wizard", return_value=answers):
        result = runner.invoke(app, ["new", "--yes"])

    assert result.exit_code != 0
