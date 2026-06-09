"""Integration tests for the `weaver epub-inspect` CLI (Sprint J6)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from weaver.cli.main import app

runner = CliRunner()


@pytest.fixture
def initialised_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    fixtures = Path(__file__).parent.parent / "fixtures"
    epubs = list(fixtures.glob("*.epub"))
    if not epubs:
        pytest.skip("no EPUB fixture available")
    monkeypatch.chdir(tmp_path)
    from weaver.services.project import initialize_project

    init = initialize_project(epubs[0], cwd=tmp_path)
    return init.project_toml


def test_epub_inspect_help() -> None:
    result = runner.invoke(app, ["epub-inspect", "--help"])
    assert result.exit_code == 0
    # Typer/Rich wraps the help table at terminal width, so the literal
    # ``--reparse`` / ``--json`` tokens can land split across lines on a
    # narrow CI tty. Match the dash-less option names so the assertion is
    # immune to wrapping.
    output = result.output.lower()
    assert "epub-inspect" in output or "snapshot" in output
    assert "reparse" in output
    assert "json" in output


def test_epub_inspect_reports_fresh_after_initial_import(
    initialised_project: Path,
) -> None:
    result = runner.invoke(app, ["epub-inspect", str(initialised_project), "--volume", "1"])
    assert result.exit_code == 0
    assert "EPUB snapshot" in result.output
    assert "fresh" in result.output


def test_epub_inspect_reparses_then_summarises(initialised_project: Path) -> None:
    result = runner.invoke(
        app,
        ["epub-inspect", str(initialised_project), "--volume", "1", "--reparse"],
    )
    assert result.exit_code == 0
    out = result.output
    assert "EPUB snapshot" in out
    assert "Manifest items" in out
    assert "Parser version" in out


def test_epub_inspect_json_output_includes_snapshot_status(
    initialised_project: Path,
) -> None:
    result = runner.invoke(
        app,
        [
            "epub-inspect",
            str(initialised_project),
            "--volume",
            "1",
            "--reparse",
            "--json",
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert "snapshot_status" in payload
    assert payload["snapshot_status"]["state"] == "fresh"
    assert payload["snapshot_status"]["parser_version"] is not None
