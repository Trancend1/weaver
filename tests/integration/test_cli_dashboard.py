"""Integration tests for weaver dashboard command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from weaver.cli.main import app
from weaver.errors import ConfigError

FIXTURE_EPUB = Path(__file__).parents[1] / "fixtures" / "aozora_sample.epub"


def _init_project(tmp_path: Path) -> Path:
    runner = CliRunner()
    result = runner.invoke(app, ["init", str(FIXTURE_EPUB)])
    assert result.exit_code == 0, result.output
    return tmp_path / ".weaver" / "aozora_sample" / "project.toml"


def test_dashboard_exits_zero_with_run_dashboard_mocked(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    project_toml = _init_project(tmp_path)

    with patch("weaver.tui.dashboard_app.run_dashboard"):
        result = runner.invoke(app, ["dashboard", str(project_toml)])

    assert result.exit_code == 0


def test_dashboard_missing_textual_shows_install_hint(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    project_toml = _init_project(tmp_path)

    with patch(
        "weaver.tui.dashboard_app.run_dashboard",
        side_effect=ConfigError(
            "weaver dashboard requires textual. "
            "Likely cause: optional dependency not installed. "
            "Next command: pip install 'weaver[tui]'"
        ),
    ):
        result = runner.invoke(app, ["dashboard", str(project_toml)])

    assert result.exit_code == 7
    assert "weaver[tui]" in result.output
