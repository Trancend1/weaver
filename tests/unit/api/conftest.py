"""Shared fixtures for FastAPI cockpit tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from weaver.api.app import create_api_app


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    return TestClient(create_api_app(tmp_path))


@pytest.fixture
def client_with_projects(tmp_path: Path) -> TestClient:
    """Client whose base_dir has a real initialised project."""
    from weaver.services.project import initialize_project

    fixtures = Path(__file__).parent.parent.parent / "fixtures"
    epubs = sorted(fixtures.glob("*.epub"))
    if not epubs:
        pytest.skip("no EPUB fixture available")
    initialize_project(epubs[0], cwd=tmp_path)
    return TestClient(create_api_app(tmp_path))
