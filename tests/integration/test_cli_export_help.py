"""CLI help-text tests."""

from __future__ import annotations

from typer.testing import CliRunner

from weaver.cli.main import app


def test_export_help_mentions_epub_mode() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["export", "--help"])
    assert result.exit_code == 0, result.output
    assert "epub" in result.output.lower()
    assert "markdown" in result.output.lower()
