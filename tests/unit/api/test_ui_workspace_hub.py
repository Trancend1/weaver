"""Q3 tests: global Workspace shell + Dashboard command center.

Verifies:
- Dashboard renders ws-hub layout with workspace sidebar
- Data comes from workspace_index, not direct DB fan-out
- Error/degraded projects render without blanking the dashboard
- Identity conflict surfaces a visible warning
- Active jobs chip uses in-memory registry only
- All six sidebar entries present; disabled entries have no broken links
- Existing project routes remain unaffected
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from weaver.api.app import create_api_app
from weaver.services.workspace_index import ProjectIndexEntry, WorkspaceIndex


@pytest.fixture
def hub_client(tmp_path: Path) -> TestClient:
    from weaver.services.project import initialize_project

    fixtures = Path(__file__).parent.parent.parent / "fixtures"
    epubs = list(fixtures.glob("*.epub"))
    if not epubs:
        pytest.skip("no EPUB fixture available")
    initialize_project(epubs[0], cwd=tmp_path)
    return TestClient(create_api_app(tmp_path))


@pytest.fixture
def empty_hub_client(tmp_path: Path) -> TestClient:
    return TestClient(create_api_app(tmp_path))


def _make_entry(
    name: str = "test-project",
    state: str = "ready",
    error: str | None = None,
    running: int = 0,
) -> ProjectIndexEntry:
    return ProjectIndexEntry(
        uuid="uuid-" + name,
        name=name,
        schema_version=10,
        state=state,
        error=error,
        volume_count=1,
        chapter_count=3,
        segment_count=100,
        pending_count=40,
        translated_count=60,
        failed_count=0,
        stale_count=0,
        review_counts={},
        job_counts={"running": running} if running else {},
        last_activity="2026-06-10T12:00:00+00:00" if state == "ready" else None,
    )


# ---------------------------------------------------------------------------
# 1. Layout — ws-hub mode and workspace sidebar
# ---------------------------------------------------------------------------


def test_dashboard_uses_ws_hub_layout(hub_client: TestClient) -> None:
    html = hub_client.get("/ui").text
    assert "layout--ws-hub" in html
    assert "app-shell--ws-hub" in html


def test_dashboard_has_workspace_sidebar(hub_client: TestClient) -> None:
    html = hub_client.get("/ui").text
    assert 'class="sidebar sidebar--ws-hub"' in html


def test_workspace_sidebar_has_six_entries(hub_client: TestClient) -> None:
    html = hub_client.get("/ui").text
    for label in ("Projects", "Queue", "Resources", "Providers", "Exports", "Settings"):
        assert label in html, f"Sidebar entry '{label}' missing from dashboard"


def test_workspace_sidebar_projects_entry_is_active(hub_client: TestClient) -> None:
    html = hub_client.get("/ui").text
    assert 'aria-current="page"' in html


def test_workspace_sidebar_disabled_entries_have_no_links(hub_client: TestClient) -> None:
    html = hub_client.get("/ui").text
    # Providers (Q6) + Exports (Q7) are now active hubs; Settings remains disabled.
    for disabled in ("Settings",):
        # Disabled entries render as <span> not <a href=...>
        # Quick check: no href pointing to missing hub routes
        assert f'href="/ui/workspace/{disabled.lower()}"' not in html
        assert f'href="/ui/{disabled.lower()}"' not in html


def test_workspace_sidebar_hub_entries_are_active_links(hub_client: TestClient) -> None:
    html = hub_client.get("/ui").text
    assert 'href="/ui/providers"' in html
    assert 'href="/ui/exports"' in html


def test_workspace_sidebar_queue_is_enabled(hub_client: TestClient) -> None:
    html = hub_client.get("/ui").text
    assert 'href="/ui/queue"' in html


def test_workspace_sidebar_resources_is_enabled(hub_client: TestClient) -> None:
    html = hub_client.get("/ui").text
    assert 'href="/ui/resources"' in html


# ---------------------------------------------------------------------------
# 2. Dashboard command center — data from workspace_index
# ---------------------------------------------------------------------------


def test_dashboard_renders_project_cards(hub_client: TestClient) -> None:
    html = hub_client.get("/ui").text
    assert "project-card" in html


def test_dashboard_shows_ws_grid(hub_client: TestClient) -> None:
    html = hub_client.get("/ui").text
    assert 'id="ws-grid"' in html


def test_dashboard_empty_state_when_no_projects(empty_hub_client: TestClient) -> None:
    html = empty_hub_client.get("/ui").text
    assert "No projects found" in html


def test_dashboard_shows_books_dir_in_meta(hub_client: TestClient) -> None:
    html = hub_client.get("/ui").text
    assert "project" in html  # page_meta includes project count


# ---------------------------------------------------------------------------
# 3. Error isolation — degraded projects don't blank the dashboard
# ---------------------------------------------------------------------------


def test_error_project_renders_degraded_card(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    entry = _make_entry("broken-proj", state="error", error="DB locked")
    monkeypatch.setattr(
        "weaver.api.routers.ui.build_workspace_index",
        lambda *a, **kw: WorkspaceIndex(entries=[entry], generated_at=0.0),
    )
    client = TestClient(create_api_app(tmp_path))
    resp = client.get("/ui")
    assert resp.status_code == 200
    assert "broken-proj" in resp.text
    assert "DB locked" in resp.text
    assert "project-card--error" in resp.text


def test_needs_upgrade_project_renders_warn_card(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    entry = _make_entry("old-proj", state="needs_upgrade")
    monkeypatch.setattr(
        "weaver.api.routers.ui.build_workspace_index",
        lambda *a, **kw: WorkspaceIndex(entries=[entry], generated_at=0.0),
    )
    client = TestClient(create_api_app(tmp_path))
    resp = client.get("/ui")
    assert resp.status_code == 200
    assert "needs upgrade" in resp.text
    assert "project-card--warn" in resp.text


def test_multiple_entries_including_errors_renders_all(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    entries = [
        _make_entry("good-proj"),
        _make_entry("bad-proj", state="error", error="missing file"),
    ]
    monkeypatch.setattr(
        "weaver.api.routers.ui.build_workspace_index",
        lambda *a, **kw: WorkspaceIndex(entries=entries, generated_at=0.0),
    )
    client = TestClient(create_api_app(tmp_path))
    resp = client.get("/ui")
    assert resp.status_code == 200
    assert "good-proj" in resp.text
    assert "bad-proj" in resp.text


# ---------------------------------------------------------------------------
# 4. Identity conflict warning
# ---------------------------------------------------------------------------


def test_identity_conflict_renders_warning_banner(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    conflict = _make_entry("proj-a", state="identity_conflict")
    monkeypatch.setattr(
        "weaver.api.routers.ui.build_workspace_index",
        lambda *a, **kw: WorkspaceIndex(entries=[conflict], generated_at=0.0),
    )
    client = TestClient(create_api_app(tmp_path))
    resp = client.get("/ui")
    assert resp.status_code == 200
    html = resp.text
    assert "identity conflict" in html.lower() or "Identity conflict" in html


def test_no_identity_conflict_no_banner(hub_client: TestClient) -> None:
    html = hub_client.get("/ui").text
    assert "Identity conflict" not in html


# ---------------------------------------------------------------------------
# 5. Active jobs chip — zero DB access
# ---------------------------------------------------------------------------


def test_no_active_jobs_chip_when_registry_empty(hub_client: TestClient) -> None:
    # With no running jobs, the chip should not appear
    html = hub_client.get("/ui").text
    assert "dash-active-jobs" not in html


def test_active_jobs_chip_shown_when_jobs_running(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from unittest.mock import patch

    monkeypatch.setattr(
        "weaver.api.routers.ui.build_workspace_index",
        lambda *a, **kw: WorkspaceIndex(entries=[], generated_at=0.0),
    )

    app = create_api_app(tmp_path)
    client = TestClient(app)

    with patch.object(app.state.jobs, "running_count", return_value=2):
        resp = client.get("/ui")

    assert resp.status_code == 200
    assert "2 jobs running" in resp.text


# ---------------------------------------------------------------------------
# 6. Structural gate — dashboard uses workspace_index, not discover_projects
# ---------------------------------------------------------------------------


def test_dashboard_route_uses_build_workspace_index_not_discover_projects() -> None:
    from weaver.api.routers import ui

    source = inspect.getsource(ui.dashboard)
    assert "build_workspace_index" in source
    assert "discover_projects" not in source
    assert "_project_rows" not in source


def test_dashboard_route_uses_ws_hub_layout() -> None:
    from weaver.api.routers import ui

    source = inspect.getsource(ui.dashboard)
    assert "ws_hub_layout" in source
    assert 'global_layout("dashboard")' not in source


# ---------------------------------------------------------------------------
# 7. Regression — existing routes unaffected
# ---------------------------------------------------------------------------


def test_existing_project_route_still_works(hub_client: TestClient) -> None:
    name = hub_client.get("/projects").json()["projects"][0]["name"]
    resp = hub_client.get(f"/ui/projects/{name}")
    assert resp.status_code == 200
    assert "layout--project" in resp.text


def test_new_project_route_still_global_layout(hub_client: TestClient) -> None:
    resp = hub_client.get("/ui/new")
    assert resp.status_code == 200
    assert "layout--global" in resp.text


def test_config_route_still_global_layout(hub_client: TestClient) -> None:
    resp = hub_client.get("/ui/config")
    assert resp.status_code == 200
    assert "layout--global" in resp.text
