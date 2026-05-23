"""Tests for Phase A6 CLI: weaver edit selector flag validation."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from weaver.cli.main import app

FIXTURE_EPUB = Path(__file__).parents[1] / "fixtures" / "aozora_sample.epub"


def _init(tmp_path: Path) -> Path:
    runner = CliRunner()
    init = runner.invoke(app, ["init", str(FIXTURE_EPUB)])
    assert init.exit_code == 0, init.output
    return tmp_path / ".weaver" / "aozora_sample" / "project.toml"


def test_edit_without_id_or_selector_exits_with_clear_error(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    project_toml = _init(tmp_path)
    runner = CliRunner()

    result = runner.invoke(app, ["edit", str(project_toml)])

    assert result.exit_code == 1, result.output
    assert "segment id or one of" in result.output


def test_edit_with_id_and_selector_exits(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    project_toml = _init(tmp_path)
    runner = CliRunner()

    result = runner.invoke(app, ["edit", str(project_toml), "deadbeef", "--first-failed"])

    assert result.exit_code == 1, result.output
    assert "either a positional segment id or a selector" in result.output


def test_edit_with_multiple_selectors_exits(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    project_toml = _init(tmp_path)
    runner = CliRunner()

    result = runner.invoke(app, ["edit", str(project_toml), "--first-failed", "--next-stale"])

    assert result.exit_code == 1, result.output
    assert "only one selector flag" in result.output


def test_edit_first_failed_with_no_failed_segments_surfaces_segment_not_found(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    project_toml = _init(tmp_path)
    runner = CliRunner()

    result = runner.invoke(app, ["edit", str(project_toml), "--first-failed"])

    # Exit code 5 = SegmentNotFoundError per AC-9.
    assert result.exit_code == 5, result.output
    assert "No segment matches" in result.output
