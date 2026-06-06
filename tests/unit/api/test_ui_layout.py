"""Tests for the Phase E layout shell: mode dispatch, sidebar presence, active nav."""

from __future__ import annotations

import re
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


# --- global mode ------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "nav_label"),
    [("/ui", "Dashboard"), ("/ui/new", "New novel"), ("/ui/config", "Config")],
)
def test_global_mode_has_no_sidebar(ui_client: TestClient, path: str, nav_label: str) -> None:
    html = ui_client.get(path).text
    assert "layout--global" in html
    assert "app-shell--global" in html
    # global mode renders no sidebar aside
    assert '<aside class="sidebar' not in html
    # the matching nav link is marked active for assistive tech
    link = re.search(rf'<a href="[^"]*"([^>]*)>{re.escape(nav_label)}</a>', html)
    assert link is not None
    assert 'aria-current="page"' in link.group(1)


# --- project mode -----------------------------------------------------------


def test_project_mode_renders_expanded_sidebar(ui_client: TestClient) -> None:
    name = _name(ui_client)
    html = ui_client.get(f"/ui/projects/{name}").text
    assert "layout--project" in html
    assert "app-shell--project" in html
    assert 'class="sidebar sidebar--project"' in html
    # the active project section is flagged in the sidebar nav
    assert 'class="sidebar-item active"' in html


def test_admin_page_is_project_mode_with_active_nav(ui_client: TestClient) -> None:
    name = _name(ui_client)
    html = ui_client.get(f"/ui/projects/{name}/glossary").text
    assert "layout--project" in html
    assert 'class="sidebar sidebar--project"' in html
    # glossary item carries aria-current in the sidebar
    item = re.search(r'<a class="sidebar-item active"[^>]*>', html)
    assert item is not None
    assert 'aria-current="page"' in item.group(0)


# --- workspace mode ---------------------------------------------------------


def test_workspace_mode_collapses_sidebar(ui_client: TestClient) -> None:
    name = _name(ui_client)
    project_html = ui_client.get(f"/ui/projects/{name}").text
    m = re.search(rf"/ui/projects/{re.escape(name)}/chapters/([^\"']+)", project_html)
    if m is None:
        pytest.skip("fixture project has no chapter to open")
    html = ui_client.get(f"/ui/projects/{name}/chapters/{m.group(1)}").text
    assert "layout--workspace" in html
    assert "app-shell--workspace" in html
    assert 'class="sidebar sidebar--workspace"' in html
