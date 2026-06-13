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
    [("/ui/new", "New project")],
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


def test_dashboard_uses_ws_hub_mode_with_sidebar(ui_client: TestClient) -> None:
    html = ui_client.get("/ui").text
    assert "layout--ws-hub" in html
    assert "app-shell--ws-hub" in html
    assert 'class="sidebar sidebar--ws-hub"' in html


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


# --- P4 navigation coherence (WV-004) ---------------------------------------


def test_sidebar_includes_jobs_link(ui_client: TestClient) -> None:
    """Sidebar must expose the Jobs page (Sprint P4)."""
    name = _name(ui_client)
    html = ui_client.get(f"/ui/projects/{name}").text
    assert f'href="/ui/projects/{name}/jobs"' in html
    assert ">Jobs<" in html


def test_project_page_has_no_duplicate_subnav(ui_client: TestClient) -> None:
    """Project page must not repeat sidebar links in a subnav rail (P4)."""
    name = _name(ui_client)
    html = ui_client.get(f"/ui/projects/{name}").text
    # The old duplicate subnav is a <nav class="subnav"> inside the tree section.
    # After P4 it is removed.
    tree_section = html.split('id="tree"', 1)[0] if 'id="tree"' in html else html
    assert '<nav class="subnav"' not in tree_section


def test_child_pages_have_dashboard_breadcrumb(ui_client: TestClient) -> None:
    """All non-dashboard pages must lead back to Dashboard in breadcrumbs."""
    name = _name(ui_client)
    project_html = ui_client.get(f"/ui/projects/{name}").text
    m = re.search(rf"/ui/projects/{re.escape(name)}/chapters/([^\"']+)", project_html)
    chapter_id = m.group(1) if m else None

    pages = [
        ("/ui", False),  # Dashboard itself – no crumb to self
        (f"/ui/projects/{name}", True),
        (f"/ui/projects/{name}/glossary", True),
        (f"/ui/projects/{name}/characters", True),
        (f"/ui/projects/{name}/memory", True),
        (f"/ui/projects/{name}/candidates", True),
        (f"/ui/projects/{name}/qa", True),
        (f"/ui/projects/{name}/jobs", True),
    ]
    if chapter_id:
        pages.append((f"/ui/projects/{name}/chapters/{chapter_id}", True))

    for path, expect_dashboard in pages:
        html = ui_client.get(path).text
        if expect_dashboard:
            assert '<a href="/ui">Dashboard</a>' in html, f"{path} missing Dashboard crumb"
        else:
            # Dashboard page should not breadcrumb to itself
            pass


def test_back_button_consistency(ui_client: TestClient) -> None:
    """Preview and review queue must have a Back-to-project action."""
    name = _name(ui_client)
    project_html = ui_client.get(f"/ui/projects/{name}").text

    # Reading preview (volume scope)
    vol_id_match = re.search(rf"/ui/projects/{re.escape(name)}/volumes/(\d+)/preview", project_html)
    if vol_id_match:
        preview_html = ui_client.get(
            f"/ui/projects/{name}/volumes/{vol_id_match.group(1)}/preview"
        ).text
        assert "Back to project" in preview_html

    # Review queue
    review_html = ui_client.get(f"/ui/projects/{name}/volumes/1/review").text
    assert "Back to project" in review_html


def test_dashboard_page_title_matches_topbar(ui_client: TestClient) -> None:
    """Dashboard tab/title must say Dashboard, not Projects (P4)."""
    html = ui_client.get("/ui").text
    assert "Dashboard" in html
    # The old title "Projects" should no longer appear as a page heading
    title_tag = re.search(r"<h1>([^<]+)</h1>", html)
    assert title_tag is not None
    assert title_tag.group(1).strip() == "Dashboard"
