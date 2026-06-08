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
    assert "epub-inspect" in result.output.lower() or "snapshot" in result.output.lower()
    assert "--reparse" in result.output
    assert "--json" in result.output


def test_epub_inspect_reports_missing_when_never_reparsed(
    initialised_project: Path,
) -> None:
    result = runner.invoke(app, ["epub-inspect", str(initialised_project), "--volume", "1"])
    assert result.exit_code == 0
    assert "No snapshot" in result.output


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
