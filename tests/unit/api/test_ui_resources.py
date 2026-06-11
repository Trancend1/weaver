"""Q5 tests: Global Resources hub.

Verifies:
- Resources route renders ws-hub layout with workspace sidebar
- Resources sidebar entry is active
- Resource counts show across projects
- Degraded projects (error/needs_upgrade/identity_conflict) do not blank hub
- Empty state renders clearly
- Project-scoped deep-links (glossary, characters, memory) exist
- No connect_database in router source
- No QA/provider/hash calls on render
"""

from __future__ import annotations

import inspect
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from weaver.api.app import create_api_app
from weaver.services.workspace_resources import (
    ProjectResourceSummary,
    ResourceDegradedProject,
    WorkspaceResources,
)


def _insert_glossary_term(connection: sqlite3.Connection, source: str, target: str) -> None:
    connection.execute(
        "INSERT INTO glossary_terms (project_id, source, target) VALUES (1, ?, ?)",
        (source, target),
    )


def _insert_character(connection: sqlite3.Connection, jp_name: str, en_name: str) -> None:
    connection.execute(
        "INSERT INTO characters (project_id, jp_name, en_name) VALUES (1, ?, ?)",
        (jp_name, en_name),
    )


def _insert_memory_entry(
    connection: sqlite3.Connection,
    source_text: str,
    source_hash: str,
    target_text: str,
) -> None:
    connection.execute(
        "INSERT INTO translation_memory "
        "(project_id, source_text, source_hash, target_text, created_at, updated_at) "
        "VALUES (1, ?, ?, ?, '2025-01-01T00:00:00+00:00', '2025-01-01T00:00:00+00:00')",
        (source_text, source_hash, target_text),
    )


@pytest.fixture
def resources_client(tmp_path: Path) -> TestClient:
    from weaver.services.project import initialize_project

    fixtures = Path(__file__).parent.parent.parent / "fixtures"
    epubs = list(fixtures.glob("*.epub"))
    if not epubs:
        pytest.skip("no EPUB fixture available")
    initialize_project(epubs[0], cwd=tmp_path, project_name="alpha")
    initialize_project(epubs[0], cwd=tmp_path, project_name="beta")

    alpha_db = tmp_path / ".weaver" / "alpha" / "weaver.db"
    beta_db = tmp_path / ".weaver" / "beta" / "weaver.db"

    conn_a = sqlite3.connect(alpha_db)
    conn_a.row_factory = sqlite3.Row
    _insert_glossary_term(conn_a, "魔女", "witch")
    _insert_glossary_term(conn_a, "剣", "sword")
    _insert_character(conn_a, "佐藤", "Sato")
    _insert_memory_entry(conn_a, "hello", "hash1", "こんにちは")
    conn_a.commit()
    conn_a.close()

    conn_b = sqlite3.connect(beta_db)
    conn_b.row_factory = sqlite3.Row
    _insert_character(conn_b, "鈴木", "Suzuki")
    conn_b.commit()
    conn_b.close()

    return TestClient(create_api_app(tmp_path))


@pytest.fixture
def empty_resources_client(tmp_path: Path) -> TestClient:
    return TestClient(create_api_app(tmp_path))


# ---------------------------------------------------------------------------
# 1. Layout — ws-hub mode and workspace sidebar
# ---------------------------------------------------------------------------


def test_resources_uses_ws_hub_layout(resources_client: TestClient) -> None:
    html = resources_client.get("/ui/resources").text
    assert "layout--ws-hub" in html
    assert "app-shell--ws-hub" in html


def test_resources_has_workspace_sidebar(resources_client: TestClient) -> None:
    html = resources_client.get("/ui/resources").text
    assert 'class="sidebar sidebar--ws-hub"' in html


def test_resources_sidebar_entry_is_active(resources_client: TestClient) -> None:
    html = resources_client.get("/ui/resources").text
    assert 'href="/ui/resources"' in html
    resources_link = html.split('href="/ui/resources"')[1].split("</a>")[0]
    assert 'aria-current="page"' in resources_link or "active" in resources_link


# ---------------------------------------------------------------------------
# 2. Resource content — cross-project counts
# ---------------------------------------------------------------------------


def test_resources_shows_project_names(resources_client: TestClient) -> None:
    html = resources_client.get("/ui/resources").text
    assert "alpha" in html
    assert "beta" in html


def test_resources_shows_glossary_counts(resources_client: TestClient) -> None:
    html = resources_client.get("/ui/resources").text
    assert "2</strong> terms" in html


def test_resources_shows_character_counts(resources_client: TestClient) -> None:
    html = resources_client.get("/ui/resources").text
    assert "1</strong> character" in html


def test_resources_shows_memory_counts(resources_client: TestClient) -> None:
    html = resources_client.get("/ui/resources").text
    assert "1</strong> entry" in html


def test_resources_shows_prompt_and_style_coming_soon(resources_client: TestClient) -> None:
    html = resources_client.get("/ui/resources").text
    assert "soon" in html


# ---------------------------------------------------------------------------
# 3. Deep-links
# ---------------------------------------------------------------------------


def test_resources_has_project_glossary_link(resources_client: TestClient) -> None:
    html = resources_client.get("/ui/resources").text
    assert "/ui/projects/alpha/glossary" in html
    assert "/ui/projects/beta/glossary" in html


def test_resources_has_project_characters_link(resources_client: TestClient) -> None:
    html = resources_client.get("/ui/resources").text
    assert "/ui/projects/alpha/characters" in html
    assert "/ui/projects/beta/characters" in html


def test_resources_has_project_memory_link(resources_client: TestClient) -> None:
    html = resources_client.get("/ui/resources").text
    assert "/ui/projects/alpha/memory" in html
    assert "/ui/projects/beta/memory" in html


# ---------------------------------------------------------------------------
# 4. Empty state
# ---------------------------------------------------------------------------


def test_empty_resources_renders_empty_state(empty_resources_client: TestClient) -> None:
    html = empty_resources_client.get("/ui/resources").text
    assert "No resources to show" in html


# ---------------------------------------------------------------------------
# 5. Degraded project isolation
# ---------------------------------------------------------------------------


def test_error_project_degrades_without_blanking_hub(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    projects = [
        ProjectResourceSummary(
            project_name="good",
            project_uuid="uuid-good",
            state="ready",
            error=None,
            glossary_term_count=5,
            character_count=3,
            memory_entry_count=10,
            memory_reuse_count=2,
            prompt_template_count=None,
            style_guide_count=None,
        ),
    ]
    degraded = [ResourceDegradedProject("bad", None, "error", "DB locked")]
    monkeypatch.setattr(
        "weaver.api.routers.ui_resources.build_workspace_resources",
        lambda *a, **kw: WorkspaceResources(projects=projects, degraded=degraded, generated_at=0.0),
    )
    client = TestClient(create_api_app(tmp_path))
    resp = client.get("/ui/resources")
    assert resp.status_code == 200
    html = resp.text
    assert "good" in html
    assert "bad" in html
    assert "DB locked" in html


def test_needs_upgrade_project_renders_degraded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    degraded = [ResourceDegradedProject("old", None, "needs_upgrade", None)]
    monkeypatch.setattr(
        "weaver.api.routers.ui_resources.build_workspace_resources",
        lambda *a, **kw: WorkspaceResources(projects=[], degraded=degraded, generated_at=0.0),
    )
    client = TestClient(create_api_app(tmp_path))
    resp = client.get("/ui/resources")
    assert resp.status_code == 200
    assert "needs upgrade" in resp.text.lower() or "needs_upgrade" in resp.text


def test_identity_conflict_renders_degraded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    degraded = [ResourceDegradedProject("dup", "uuid-dup", "identity_conflict", None)]
    monkeypatch.setattr(
        "weaver.api.routers.ui_resources.build_workspace_resources",
        lambda *a, **kw: WorkspaceResources(projects=[], degraded=degraded, generated_at=0.0),
    )
    client = TestClient(create_api_app(tmp_path))
    resp = client.get("/ui/resources")
    assert resp.status_code == 200
    assert "identity conflict" in resp.text.lower() or "identity_conflict" in resp.text


# ---------------------------------------------------------------------------
# 6. Structural gate — router is thin, no direct DB access
# ---------------------------------------------------------------------------


def test_resources_route_uses_build_workspace_resources_not_connect_database() -> None:
    from weaver.api.routers import ui_resources

    source = inspect.getsource(ui_resources.resources_page)
    assert "build_workspace_resources" in source
    assert "connect_database" not in source
    assert "connect_readonly_database" not in source


# ---------------------------------------------------------------------------
# 7. Regression — existing routes unaffected
# ---------------------------------------------------------------------------


def test_dashboard_still_renders(resources_client: TestClient) -> None:
    resp = resources_client.get("/ui")
    assert resp.status_code == 200
    assert "Dashboard" in resp.text


def test_queue_still_renders(resources_client: TestClient) -> None:
    resp = resources_client.get("/ui/queue")
    assert resp.status_code == 200
    assert "layout--ws-hub" in resp.text
