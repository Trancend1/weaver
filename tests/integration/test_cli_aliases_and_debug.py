"""Tests for Phase A1/A11/A13: aliases (tx/gl/ins) and --debug global flag."""

from __future__ import annotations

from typer.testing import CliRunner

from weaver.cli.main import app


def test_tx_alias_appears_when_listed_via_help_no_args_runs() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["tx", "--help"])

    assert result.exit_code == 0, result.output
    assert "Translate project segments" in result.output


def test_ins_alias_runs_inspect_help() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["ins", "--help"])

    assert result.exit_code == 0, result.output
    assert "Show project status" in result.output


def test_gl_alias_routes_to_glossary_subapp_help() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["gl", "--help"])

    assert result.exit_code == 0, result.output
    assert "Review and edit glossary candidates" in result.output


def test_aliases_are_hidden_from_top_level_help() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0, result.output
    # primary names visible
    assert "translate" in result.output
    assert "inspect" in result.output
    assert "glossary" in result.output
    # aliases hidden — none of the hidden tokens appear as command list entries.
    # Match the command-listing region only; broad substring search would catch
    # references inside descriptions.
    for hidden in ("│ tx ", "│ ins ", "│ gl "):
        assert hidden not in result.output


def test_debug_flag_prints_traceback_on_error(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    # Use init against a missing path: triggers EpubReadError via service.
    result = runner.invoke(app, ["--debug", "init", str(tmp_path / "missing.epub")])

    assert result.exit_code != 0
    # Traceback format leaves "Traceback (most recent call last)" in output.
    assert "Traceback" in result.output


def test_no_debug_flag_prints_three_line_user_error(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    result = runner.invoke(app, ["init", str(tmp_path / "missing.epub")])

    assert result.exit_code != 0
    # Without --debug, no Python traceback header should appear.
    assert "Traceback" not in result.output
