"""Tests for the FastAPI cockpit application factory."""

from __future__ import annotations

from fastapi import FastAPI

from weaver import __version__
from weaver.api.app import create_api_app


def test_create_api_app_returns_fastapi_app() -> None:
    app = create_api_app()
    assert isinstance(app, FastAPI)
    assert app.version == __version__


def test_create_api_app_registers_system_routes() -> None:
    app = create_api_app()
    paths = {route.path for route in app.routes}  # type: ignore[attr-defined]
    assert "/health" in paths
    assert "/version" in paths
