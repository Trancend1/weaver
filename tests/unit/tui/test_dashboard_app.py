"""Regression tests for the Textual dashboard app construction.

The CLI-level dashboard tests mock ``run_dashboard`` wholesale, so the real
``WeaverDashboardApp.__init__`` path is never exercised there. This test drives
that path (with the UI event loop patched out) to guard against the latent
``TypeError`` from passing ``no_color`` into Textual's ``App.__init__`` (which
does not accept it). Skipped when the optional ``tui`` extra (textual) is absent.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from weaver.cli.main import app

textual_missing = importlib.util.find_spec("textual") is None
pytestmark = pytest.mark.skipif(textual_missing, reason="textual (tui extra) not installed")

FIXTURE_EPUB = Path(__file__).parents[2] / "fixtures" / "aozora_sample.epub"


def _init_project(tmp_path: Path) -> Path:
    runner = CliRunner()
    result = runner.invoke(app, ["init", str(FIXTURE_EPUB)])
    assert result.exit_code == 0, result.output
    return tmp_path / ".weaver" / "aozora_sample" / "project.toml"


def test_run_dashboard_constructs_app_without_no_color_typeerror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    project_toml = _init_project(tmp_path)

    # Patch the blocking UI loop so run_dashboard returns after construction.
    from textual.app import App

    monkeypatch.setattr(App, "run", lambda self: None)
    monkeypatch.delenv("NO_COLOR", raising=False)

    from weaver.tui.dashboard_app import run_dashboard

    # Must not raise: the app must build with the project path and honor
    # --no-color via the NO_COLOR env var (App.__init__ takes no color arg).
    run_dashboard(project_toml, no_color=True)
    assert os.environ.get("NO_COLOR") == "1"


def test_run_dashboard_without_no_color_does_not_force_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    project_toml = _init_project(tmp_path)

    from textual.app import App

    monkeypatch.setattr(App, "run", lambda self: None)
    monkeypatch.delenv("NO_COLOR", raising=False)

    from weaver.tui.dashboard_app import run_dashboard

    run_dashboard(project_toml, no_color=False)
    assert "NO_COLOR" not in os.environ
