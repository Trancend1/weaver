"""Integration tests for `weaver serve` command routing (Sprint 12B flip).

After the Sprint 12B default-serve flip:
- `weaver serve`       -> FastAPI cockpit (UI), default.
- `weaver serve-api`   -> FastAPI cockpit, headless (no browser).
- `weaver serve-flask` -> legacy Flask cockpit (fallback).

The serve commands launch long-running servers, so the launch primitives
(``uvicorn.run`` / ``weaver.web.app.run_server``) are patched; the body returns
immediately and we assert which primitive was invoked.
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
    assert "serve-flask" in result.output


def test_serve_flask_command_is_registered() -> None:
    result = runner.invoke(app, ["serve-flask", "--help"])
    assert result.exit_code == 0
    assert "Flask" in result.output
    assert "127.0.0.1" in result.output


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

    # Flask launcher must NOT be touched.
    def fail_run_server(**kwargs: object) -> None:  # pragma: no cover - guard
        raise AssertionError("serve must not start the Flask server")

    import weaver.web.app as flask_app

    monkeypatch.setattr(flask_app, "run_server", fail_run_server)

    result = runner.invoke(app, ["serve", "--no-browser", "--port", "9123"])
    assert result.exit_code == 0
    assert calls["import_string"] == "weaver.api.app:create_api_app"
    kwargs = calls["kwargs"]
    assert isinstance(kwargs, dict)
    assert kwargs["host"] == "127.0.0.1"
    assert kwargs["port"] == 9123
    assert kwargs["factory"] is True


def test_serve_flask_routes_to_flask(monkeypatch: pytest.MonkeyPatch) -> None:
    """`weaver serve-flask` must launch the legacy Flask server."""

    calls: dict[str, object] = {}

    def fake_run_server(**kwargs: object) -> None:
        calls.update(kwargs)

    import weaver.web.app as flask_app

    monkeypatch.setattr(flask_app, "run_server", fake_run_server)

    result = runner.invoke(app, ["serve-flask", "--no-browser", "--port", "9124"])
    assert result.exit_code == 0
    assert calls["port"] == 9124
    assert calls["open_browser"] is False
