"""Tests for Phase A2: every command's --help includes an Examples section."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from weaver.cli.main import app

COMMANDS_WITH_EPILOG = [
    ["init", "--help"],
    ["inspect", "--help"],
    ["translate", "--help"],
    ["edit", "--help"],
    ["export", "--help"],
    ["doctor", "--help"],
    ["validate", "--help"],
    ["glossary", "review", "--help"],
    ["glossary", "edit", "--help"],
    ["glossary", "conflicts", "--help"],
]


@pytest.mark.parametrize("argv", COMMANDS_WITH_EPILOG)
def test_help_includes_examples_section(argv: list[str]) -> None:
    runner = CliRunner()

    result = runner.invoke(app, argv)

    assert result.exit_code == 0, result.output
    assert "Examples:" in result.output, f"missing Examples in `weaver {' '.join(argv[:-1])}`"
    assert "weaver " in result.output
