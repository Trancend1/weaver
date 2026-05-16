"""Smoke tests for the Phase 0 skeleton."""

from __future__ import annotations

from typer.testing import CliRunner

import weaver
from weaver.cli.main import app


def test_version_string_is_set() -> None:
    assert weaver.__version__
    assert isinstance(weaver.__version__, str)


def test_cli_version_flag_exits_zero() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0, result.output
    assert weaver.__version__ in result.output
