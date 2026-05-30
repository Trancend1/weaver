"""Integration tests for the `weaver serve-api` command wiring.

Verifies registration and help text only; the command launches a long-running
Uvicorn server, so it is never invoked without ``--help`` in CI.
"""

from __future__ import annotations

from typer.testing import CliRunner

from weaver.cli.main import app

runner = CliRunner()


def test_serve_api_command_is_registered() -> None:
    result = runner.invoke(app, ["serve-api", "--help"])
    assert result.exit_code == 0
    assert "FastAPI cockpit" in result.output
