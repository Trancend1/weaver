"""Tests for the FastAPI UI shell (Sprint 11A): dashboard, project view, states."""

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


# --- shell + redirect -------------------------------------------------------


def test_root_redirects_to_ui(ui_client: TestClient) -> None:
    r = ui_client.get("/", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert r.headers["location"] == "/ui"


def test_dashboard_renders_html(ui_client: TestClient) -> None:
    r = ui_client.get("/ui")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "Dashboard" in r.text
    # the initialised project appears with a link to its view
    name = _name(ui_client)
    assert name in r.text
    assert f"/ui/projects/{name}" in r.text


def test_dashboard_empty_state(tmp_path: Path) -> None:
    client = TestClient(create_api_app(tmp_path))
    r = client.get("/ui")
    assert r.status_code == 200
    assert "No projects found" in r.text


# --- project view -----------------------------------------------------------


def test_project_view_renders_tree(ui_client: TestClient) -> None:
    name = _name(ui_client)
    r = ui_client.get(f"/ui/projects/{name}")
    assert r.status_code == 200
    assert name in r.text
    # tree shows at least the crumb back to the dashboard
    assert "Dashboard" in r.text


def test_project_view_unknown_is_404_html(ui_client: TestClient) -> None:
    r = ui_client.get("/ui/projects/ghost")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("text/html")
    assert "Not found" in r.text
    assert "ghost" in r.text


# --- static assets ----------------------------------------------------------


def test_htmx_vendored_served(ui_client: TestClient) -> None:
    r = ui_client.get("/static/htmx.min.js")
    assert r.status_code == 200
    assert "javascript" in r.headers["content-type"]
    assert "1.9.12" in r.text  # pinned stable 1.x


def test_css_served(ui_client: TestClient) -> None:
    r = ui_client.get("/static/app.css")
    assert r.status_code == 200
    assert "text/css" in r.headers["content-type"]


# --- JSON API not shadowed by the UI mount ----------------------------------


def test_json_api_still_works(ui_client: TestClient) -> None:
    assert ui_client.get("/projects").status_code == 200
    assert (
        ui_client.get("/health").json() == {"status": "ok"}
        or ui_client.get("/health").status_code == 200
    )
    # UI routes are excluded from the OpenAPI schema
    paths = ui_client.get("/openapi.json").json()["paths"]
    assert "/ui" not in paths
    assert "/projects" in paths
