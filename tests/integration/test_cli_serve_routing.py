"""Integration tests for `weaver serve` command routing.

After the Sprint 13 Flask decommission:
- `weaver serve`     -> FastAPI cockpit (UI), default.
- `weaver serve-api` -> FastAPI cockpit, headless (no browser).

(The legacy `weaver serve-flask` command was removed in Sprint 13B.)

The serve commands launch a long-running server, so the launch primitive
(``uvicorn.run``) is patched; the body returns immediately and we assert which
factory was invoked.
"""

from __future__ import annotations

import sys
import types

import pytest
from typer.testing import CliRunner

from weaver.cli.main import app

runner = CliRunner()


def test_serve_help_describes_fastapi_default() -> None:
    result = runner.invoke(app, ["serve", "--help"])
    assert result.exit_code == 0
    assert "FastAPI" in result.output
    assert "127.0.0.1" in result.output


def test_serve_flask_command_is_gone() -> None:
    result = runner.invoke(app, ["serve-flask", "--help"])
    assert result.exit_code != 0


def test_serve_api_command_is_registered() -> None:
    result = runner.invoke(app, ["serve-api", "--help"])
    assert result.exit_code == 0
    assert "FastAPI cockpit" in result.output


def test_serve_routes_to_fastapi(monkeypatch: pytest.MonkeyPatch) -> None:
    """`weaver serve` must launch Uvicorn against the FastAPI factory."""

    calls: dict[str, object] = {}

    def fake_run(import_string: str, **kwargs: object) -> None:
        calls["import_string"] = import_string
        calls["kwargs"] = kwargs

    fake_uvicorn = types.ModuleType("uvicorn")
    fake_uvicorn.run = fake_run  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "uvicorn", fake_uvicorn)

    result = runner.invoke(app, ["serve", "--no-browser", "--port", "9123"])
    assert result.exit_code == 0
    assert calls["import_string"] == "weaver.api.app:create_api_app"
    kwargs = calls["kwargs"]
    assert isinstance(kwargs, dict)
    assert kwargs["host"] == "127.0.0.1"
    assert kwargs["port"] == 9123
    assert kwargs["factory"] is True


def test_serve_api_routes_to_fastapi(monkeypatch: pytest.MonkeyPatch) -> None:
    """`weaver serve-api` uses the same FastAPI factory, headless."""

    calls: dict[str, object] = {}

    def fake_run(import_string: str, **kwargs: object) -> None:
        calls["import_string"] = import_string
        calls["kwargs"] = kwargs

    fake_uvicorn = types.ModuleType("uvicorn")
    fake_uvicorn.run = fake_run  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "uvicorn", fake_uvicorn)

    result = runner.invoke(app, ["serve-api", "--port", "9124"])
    assert result.exit_code == 0
    assert calls["import_string"] == "weaver.api.app:create_api_app"
    kwargs = calls["kwargs"]
    assert isinstance(kwargs, dict)
    assert kwargs["port"] == 9124
