"""Tests for the system endpoints (health, version)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from weaver import __version__


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_version_returns_name_and_version(client: TestClient) -> None:
    response = client.get("/version")
    assert response.status_code == 200
    assert response.json() == {"name": "weaver", "version": __version__}
