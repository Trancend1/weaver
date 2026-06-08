"""Tests for runtime endpoints (Sprint G3)."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient


def test_healthz_returns_ok_with_timestamp(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert isinstance(body["ts"], str)
    assert "T" in body["ts"]  # ISO-8601


def test_healthz_does_not_replace_health(client: TestClient) -> None:
    # ``/health`` must keep its existing payload (soak script + tests rely on it).
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_runtime_status_reports_app_data_and_books_dir(
    client: TestClient, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("WEAVER_ENV", raising=False)
    monkeypatch.setenv("WEAVER_DATA_DIR", str(tmp_path / "weaver-data"))
    response = client.get("/runtime/status")
    assert response.status_code == 200
    body = response.json()
    # WEAVER_ENV unset → default ("dev"). The factory cached env_mode at
    # construction (under conftest's "test" env), so the runtime endpoint
    # reports the live env, which is now unset → dev.
    assert body["env"] == "dev"
    assert body["app_data_dir"]
    assert body["logs_dir"].endswith("logs")
    assert body["books_dir"] == str(tmp_path.resolve())


def test_runtime_status_reports_env_mode_when_set(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WEAVER_ENV", "desktop")
    monkeypatch.setenv("WEAVER_HOST", "127.0.0.1")
    monkeypatch.setenv("WEAVER_PORT", "8765")
    response = client.get("/runtime/status")
    assert response.status_code == 200
    body = response.json()
    assert body["env"] == "desktop"
    assert body["host"] == "127.0.0.1"
    assert body["port"] == 8765


def test_runtime_status_handles_invalid_port_env(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WEAVER_PORT", "not-a-number")
    response = client.get("/runtime/status")
    assert response.status_code == 200
    body = response.json()
    assert body["port"] is None


def test_healthz_cold_response_under_50ms(client: TestClient) -> None:
    # Smoke check on the sidecar boot-poll budget. TestClient skips network so
    # this only asserts that handler work is minimal.
    start = time.perf_counter()
    response = client.get("/healthz")
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    assert response.status_code == 200
    assert elapsed_ms < 50.0, f"/healthz took {elapsed_ms:.1f} ms; budget is 50"


def test_runtime_endpoints_never_leak_secrets(client: TestClient) -> None:
    # Sanity: no payload field is named like a secret.
    for path in ("/healthz", "/runtime/status"):
        body = client.get(path).json()
        for key in body:
            assert "key" not in key.lower()
            assert "secret" not in key.lower()
            assert "token" not in key.lower()
