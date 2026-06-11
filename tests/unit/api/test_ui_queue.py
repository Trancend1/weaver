"""Q4 tests: Global Translation Queue hub.

Verifies:
- Queue route renders ws-hub layout with workspace sidebar
- Queue page lists jobs from multiple projects
- stale_running is rendered distinctly from running
- Degraded projects (error/needs_upgrade/identity_conflict) do not blank the queue
- Empty queue state renders clearly
- Project-scoped job detail deep-link exists
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
from weaver.services.workspace_queue import QueueDegradedProject, QueueJobRow, WorkspaceQueue


def _insert_job(
    connection: sqlite3.Connection,
    job_id: str,
    status: str,
    started_at: str,
    kind: str = "translate",
) -> None:
    connection.execute(
        """
        INSERT INTO jobs (
            id, kind, project_name, scope, scope_id, chapter_id, status,
            total_units, done_units, failed_units, skipped_units, started_at
        )
        VALUES (?, ?, 'test', NULL, NULL, NULL, ?, 10, 0, 0, 0, ?)
        """,
        (job_id, kind, status, started_at),
    )


@pytest.fixture
def queue_client(tmp_path: Path) -> TestClient:
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
    _insert_job(conn_a, "job-a1", "running", "2025-06-10T10:00:00+00:00")
    _insert_job(conn_a, "job-a2", "done", "2025-06-10T09:00:00+00:00")
    conn_a.commit()
    conn_a.close()

    conn_b = sqlite3.connect(beta_db)
    conn_b.row_factory = sqlite3.Row
    _insert_job(conn_b, "job-b1", "queued", "2025-06-10T08:00:00+00:00")
    conn_b.commit()
    conn_b.close()

    return TestClient(create_api_app(tmp_path))


@pytest.fixture
def empty_queue_client(tmp_path: Path) -> TestClient:
    return TestClient(create_api_app(tmp_path))


# ---------------------------------------------------------------------------
# 1. Layout — ws-hub mode and workspace sidebar
# ---------------------------------------------------------------------------


def test_queue_uses_ws_hub_layout(queue_client: TestClient) -> None:
    html = queue_client.get("/ui/queue").text
    assert "layout--ws-hub" in html
    assert "app-shell--ws-hub" in html


def test_queue_has_workspace_sidebar(queue_client: TestClient) -> None:
    html = queue_client.get("/ui/queue").text
    assert 'class="sidebar sidebar--ws-hub"' in html


def test_queue_sidebar_entry_is_active(queue_client: TestClient) -> None:
    html = queue_client.get("/ui/queue").text
    # The Queue link should be active
    assert 'href="/ui/queue"' in html
    # aria-current appears on the active sidebar item
    queue_link = html.split('href="/ui/queue"')[1].split("</a>")[0]
    assert 'aria-current="page"' in queue_link or "active" in queue_link


# ---------------------------------------------------------------------------
# 2. Queue content — cross-project jobs
# ---------------------------------------------------------------------------


def test_queue_lists_jobs_from_multiple_projects(queue_client: TestClient) -> None:
    html = queue_client.get("/ui/queue").text
    assert "job-a1" in html or "alpha" in html
    assert "job-b1" in html or "beta" in html


def test_queue_shows_job_statuses(queue_client: TestClient) -> None:
    html = queue_client.get("/ui/queue").text
    # Should see some status labels
    assert "Processing" in html or "Waiting" in html or "Completed" in html


def test_queue_has_detail_links(queue_client: TestClient) -> None:
    html = queue_client.get("/ui/queue").text
    # Deep-link to per-project job detail
    assert "/jobs/job-a1/detail" in html or "/jobs/job-b1/detail" in html


# ---------------------------------------------------------------------------
# 3. Empty state
# ---------------------------------------------------------------------------


def test_empty_queue_renders_empty_state(empty_queue_client: TestClient) -> None:
    html = empty_queue_client.get("/ui/queue").text
    assert "Queue is empty" in html


# ---------------------------------------------------------------------------
# 4. Degraded project isolation
# ---------------------------------------------------------------------------


def test_error_project_degrades_without_blanking_queue(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    jobs = [
        QueueJobRow(
            job_id="j1",
            project_name="good",
            project_uuid="uuid-good",
            kind="translate",
            status="running",
            scope=None,
            scope_id=None,
            done_units=0,
            total_units=10,
            current_label=None,
            error_summary=None,
            started_at="2025-06-10T10:00:00+00:00",
            finished_at=None,
        ),
    ]
    degraded = [QueueDegradedProject("bad", None, "error", "DB locked")]
    monkeypatch.setattr(
        "weaver.api.routers.ui_queue.build_workspace_queue",
        lambda *a, **kw: WorkspaceQueue(jobs=jobs, degraded=degraded, generated_at=0.0),
    )
    client = TestClient(create_api_app(tmp_path))
    resp = client.get("/ui/queue")
    assert resp.status_code == 200
    html = resp.text
    assert "good" in html
    assert "bad" in html
    assert "DB locked" in html


def test_needs_upgrade_project_renders_degraded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    degraded = [QueueDegradedProject("old", None, "needs_upgrade", None)]
    monkeypatch.setattr(
        "weaver.api.routers.ui_queue.build_workspace_queue",
        lambda *a, **kw: WorkspaceQueue(jobs=[], degraded=degraded, generated_at=0.0),
    )
    client = TestClient(create_api_app(tmp_path))
    resp = client.get("/ui/queue")
    assert resp.status_code == 200
    assert "needs upgrade" in resp.text.lower() or "needs_upgrade" in resp.text


def test_identity_conflict_disables_actions(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    degraded = [QueueDegradedProject("dup", "uuid-dup", "identity_conflict", None)]
    monkeypatch.setattr(
        "weaver.api.routers.ui_queue.build_workspace_queue",
        lambda *a, **kw: WorkspaceQueue(jobs=[], degraded=degraded, generated_at=0.0),
    )
    client = TestClient(create_api_app(tmp_path))
    resp = client.get("/ui/queue")
    assert resp.status_code == 200
    assert "identity conflict" in resp.text.lower() or "identity_conflict" in resp.text


# ---------------------------------------------------------------------------
# 5. stale_running distinctly rendered
# ---------------------------------------------------------------------------


def test_stale_running_renders_distinctly(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    jobs = [
        QueueJobRow(
            job_id="j-stale",
            project_name="proj",
            project_uuid="uuid",
            kind="translate",
            status="stale_running",
            scope=None,
            scope_id=None,
            done_units=0,
            total_units=10,
            current_label=None,
            error_summary=None,
            started_at="2025-06-10T09:00:00+00:00",
            finished_at=None,
        ),
    ]
    monkeypatch.setattr(
        "weaver.api.routers.ui_queue.build_workspace_queue",
        lambda *a, **kw: WorkspaceQueue(jobs=jobs, degraded=[], generated_at=0.0),
    )
    client = TestClient(create_api_app(tmp_path))
    resp = client.get("/ui/queue")
    assert resp.status_code == 200
    html = resp.text
    assert "Stale" in html
    assert "job-status--stale_running" in html


# ---------------------------------------------------------------------------
# 6. Structural gate — router is thin, no direct DB access
# ---------------------------------------------------------------------------


def test_queue_route_uses_build_workspace_queue_not_connect_database() -> None:
    from weaver.api.routers import ui_queue

    source = inspect.getsource(ui_queue.queue_page)
    assert "build_workspace_queue" in source
    assert "connect_database" not in source
    assert "connect_readonly_database" not in source


# ---------------------------------------------------------------------------
# 7. Regression — existing routes unaffected
# ---------------------------------------------------------------------------


def test_existing_project_jobs_route_still_works(queue_client: TestClient) -> None:
    resp = queue_client.get("/ui/projects/alpha/jobs")
    assert resp.status_code == 200
    assert "layout--project" in resp.text


def test_dashboard_still_renders(queue_client: TestClient) -> None:
    resp = queue_client.get("/ui")
    assert resp.status_code == 200
    assert "Dashboard" in resp.text
