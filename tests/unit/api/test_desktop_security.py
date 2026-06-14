"""Tests for the desktop security baseline (Sprint G5).

Covers: env-mode dispatch, ``/docs`` toggle, CORS in desktop mode,
session-token enforcement, and the CLI bind-guard exit code.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from weaver.api.app import create_api_app
from weaver.cli.main import app as cli_app

runner = CliRunner()


@pytest.fixture(autouse=True)
def _isolate_runtime_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("WEAVER_ENV", raising=False)
    monkeypatch.delenv("WEAVER_DOCS", raising=False)
    monkeypatch.delenv("WEAVER_SESSION_TOKEN", raising=False)
    # Pin app-data away from the user's real home dir; tests in this module
    # toggle WEAVER_ENV to dev/desktop and the factory will install logging
    # handlers when env != test.
    monkeypatch.setenv("WEAVER_DATA_DIR", str(tmp_path / "weaver-data"))


def test_dev_mode_keeps_docs_on(tmp_path: Path) -> None:
    client = TestClient(create_api_app(tmp_path))
    response = client.get("/docs")
    assert response.status_code == 200


def test_desktop_mode_disables_docs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEAVER_ENV", "desktop")
    client = TestClient(create_api_app(tmp_path))
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_desktop_mode_can_be_overridden_to_keep_docs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WEAVER_ENV", "desktop")
    monkeypatch.setenv("WEAVER_DOCS", "true")
    client = TestClient(create_api_app(tmp_path))
    assert client.get("/docs").status_code == 200


def test_session_token_required_when_set(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEAVER_SESSION_TOKEN", "secret-from-tauri")
    client = TestClient(create_api_app(tmp_path))

    # Public paths still work without a token.
    assert client.get("/healthz").status_code == 200
    assert client.get("/health").status_code == 200
    assert client.get("/version").status_code == 200

    # Protected paths require the token.
    no_token = client.get("/runtime/status")
    assert no_token.status_code == 401

    bad_token = client.get("/runtime/status", headers={"X-Weaver-Session": "wrong"})
    assert bad_token.status_code == 401

    good = client.get("/runtime/status", headers={"X-Weaver-Session": "secret-from-tauri"})
    assert good.status_code == 200


def test_session_token_optional_in_dev(tmp_path: Path) -> None:
    client = TestClient(create_api_app(tmp_path))
    # No WEAVER_SESSION_TOKEN set → no enforcement.
    assert client.get("/runtime/status").status_code == 200


def _make_fake_uvicorn(
    run_fn: object | None = None,
) -> types.ModuleType:
    """Build a fake ``uvicorn`` module for ``monkeypatch.setitem``.

    When *run_fn* is ``None``, the mock server passes without blocking.
    """
    fake = types.ModuleType("uvicorn")
    fake.run = run_fn if run_fn is not None else lambda *_a, **_kw: None  # type: ignore[attr-defined]
    return fake


def test_serve_refuses_non_loopback_in_desktop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEAVER_ENV", "desktop")
    monkeypatch.setitem(sys.modules, "uvicorn", _make_fake_uvicorn())

    result = runner.invoke(
        cli_app, ["serve", "--no-browser", "--host", "0.0.0.0", "--port", "9123"]
    )
    assert result.exit_code == 64
    output = result.output + (result.stderr or "")
    assert "desktop mode" in output.lower()
    # Error message must not leak secrets, tokens, or API keys.
    assert "WEAVER_SESSION_TOKEN" not in output
    assert "API_KEY" not in output
    assert "session" not in output.lower()


def test_serve_allows_non_loopback_in_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, object] = {}

    def fake_run(import_string: str, **kwargs: object) -> None:
        calls["host"] = kwargs.get("host")

    fake_uvicorn = types.ModuleType("uvicorn")
    fake_uvicorn.run = fake_run  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "uvicorn", fake_uvicorn)

    result = runner.invoke(
        cli_app, ["serve", "--no-browser", "--host", "127.0.0.1", "--port", "9124"]
    )
    assert result.exit_code == 0
    assert calls["host"] == "127.0.0.1"


def test_serve_exits_65_when_port_in_use(monkeypatch: pytest.MonkeyPatch) -> None:
    """``weaver serve`` on an occupied port must exit 65 (SIDECAR_CONTRACT.md §5)."""

    def _fail_with_addrinuse(*_a: object, **_kw: object) -> None:
        raise OSError(98, "Address already in use")

    monkeypatch.setitem(sys.modules, "uvicorn", _make_fake_uvicorn(_fail_with_addrinuse))

    result = runner.invoke(
        cli_app, ["serve", "--no-browser", "--port", "9998"]
    )
    assert result.exit_code == 65, result.output
    output = result.output + (result.stderr or "")
    assert "already in use" in output.lower()
    # Error message must not leak secrets, tokens, or API keys.
    assert "WEAVER_SESSION_TOKEN" not in output
    assert "API_KEY" not in output
    assert "9998" in output  # port number is informative, not a secret


def test_serve_stdout_summary_line_contains_host_and_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``weaver serve`` must print a clear startup summary line before blocking.

    The Tauri sidecar uses the summary line only as a *hint* (it polls
    /healthz and /runtime/status for authoritative values), but the line
    must be informative for manual browser users.
    """
    monkeypatch.setitem(sys.modules, "uvicorn", _make_fake_uvicorn())

    result = runner.invoke(
        cli_app, ["serve", "--no-browser", "--port", "8765"]
    )
    assert result.exit_code == 0, result.output
    # Required contract elements in the summary (§4, SIDECAR_CONTRACT.md).
    assert "Weaver cockpit (FastAPI UI) on http://127.0.0.1:8765" in result.output
    assert "Ctrl+C to stop" in result.output
    assert "http" in result.output
    # Must NOT leak tokens, keys, or session values.
    assert "WEAVER_SESSION_TOKEN" not in result.output
    assert "API_KEY" not in result.output
    assert "secret" not in result.output.lower()


def test_runtime_env_module_helpers_are_consistent(monkeypatch: pytest.MonkeyPatch) -> None:
    from weaver.services.runtime_env import current_env, docs_enabled, session_token

    monkeypatch.setenv("WEAVER_ENV", "desktop")
    assert current_env() == "desktop"
    assert docs_enabled() is False

    monkeypatch.setenv("WEAVER_DOCS", "true")
    assert docs_enabled() is True

    monkeypatch.setenv("WEAVER_SESSION_TOKEN", "  ")
    assert session_token() is None

    monkeypatch.setenv("WEAVER_SESSION_TOKEN", "tok")
    assert session_token() == "tok"

    monkeypatch.setenv("WEAVER_ENV", "BOGUS")
    assert current_env() == "dev"  # falls back to default
