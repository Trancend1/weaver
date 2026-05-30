"""Shared fixtures for FastAPI cockpit tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from weaver.api.app import create_api_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_api_app())
