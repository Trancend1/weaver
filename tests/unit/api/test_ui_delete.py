"""Tests for the web delete-project route (HTMX HX-Redirect to dashboard)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from weaver.api.app import create_api_app


@pytest.fixture
def ui_client(tmp_path: Path) -> TestClient:
    from weaver.services.project import initialize_project

    fixtures = Path(__file__).parent.parent.parent / "fixtures"
    epubs = list(fixtures.glob("*.epub"))
    if not epubs:
        pytest.skip("no EPUB fixture available")
    initialize_project(epubs[0], cwd=tmp_path)
    return TestClient(create_api_app(tmp_path))


def _name(client: TestClient) -> str:
    return client.get("/projects").json()["projects"][0]["name"]


def test_delete_redirects_and_removes_project(ui_client: TestClient) -> None:
    name = _name(ui_client)
    assert ui_client.get(f"/ui/projects/{name}").status_code == 200

    resp = ui_client.post(f"/ui/projects/{name}/delete")
    assert resp.status_code == 200
    assert resp.headers.get("HX-Redirect") == "/ui"

    # The project is gone from both the UI and the JSON API.
    assert ui_client.get(f"/ui/projects/{name}").status_code == 404
    assert ui_client.get("/projects").json()["projects"] == []


def test_delete_unknown_project_is_404(ui_client: TestClient) -> None:
    assert ui_client.post("/ui/projects/ghost/delete").status_code == 404


def test_project_page_renders_delete_control(ui_client: TestClient) -> None:
    name = _name(ui_client)
    page = ui_client.get(f"/ui/projects/{name}").text
    assert f'hx-post="/ui/projects/{name}/delete"' in page
    assert "Delete project" in page
    assert "hx-confirm" in page
