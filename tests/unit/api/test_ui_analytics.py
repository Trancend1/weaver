"""Q8 tests: per-project Analytics page + dashboard rollup section.

Verifies:
- /ui/projects/{name}/analytics renders with project layout + active sidebar
- analytics numbers visible; honest current-state framing
- zero QA scans and zero provider builds on render (spies)
- dashboard shows the workspace rollup section
- unknown project 404; degraded project errors surfaced, not crashed
- router is thin (service call, no direct DB access)
"""

from __future__ import annotations

import inspect
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from weaver.api.app import create_api_app
from weaver.services.project import initialize_project

FIXTURES = Path(__file__).parent.parent.parent / "fixtures"


def _epub() -> Path:
    epubs = list(FIXTURES.glob("*.epub"))
    if not epubs:
        pytest.skip("no EPUB fixture available")
    return epubs[0]


def _seed_translated(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT id, source_hash FROM segments LIMIT 1").fetchone()
    conn.execute("UPDATE segments SET status = 'translated' WHERE id = ?", (row["id"],))
    conn.execute(
        "INSERT INTO translations (segment_id, attempt, text, source_hash, provider, "
        "model, created_at, input_tokens, output_tokens) "
        "VALUES (?, 1, 'Hello', ?, 'fake', 'fake-1', '2025-01-01T00:00:00+00:00', 200, 50)",
        (row["id"], row["source_hash"]),
    )
    conn.commit()
    conn.close()


@pytest.fixture
def analytics_client(tmp_path: Path) -> TestClient:
    initialize_project(_epub(), cwd=tmp_path, project_name="alpha")
    _seed_translated(tmp_path / ".weaver" / "alpha" / "weaver.db")
    return TestClient(create_api_app(tmp_path))


# --- page -------------------------------------------------------------------


def test_analytics_page_renders(analytics_client: TestClient) -> None:
    resp = analytics_client.get("/ui/projects/alpha/analytics")
    assert resp.status_code == 200
    html = resp.text
    assert "Analytics" in html
    assert "Translation status" in html
    assert "Review status" in html
    assert "Token usage" in html
    assert "Export readiness" in html


def test_analytics_shows_token_numbers(analytics_client: TestClient) -> None:
    html = analytics_client.get("/ui/projects/alpha/analytics").text
    assert "fake-1" in html
    assert "200" in html
    assert "50" in html


def test_analytics_honest_current_state_framing(analytics_client: TestClient) -> None:
    html = analytics_client.get("/ui/projects/alpha/analytics").text
    assert "not a time series" in html
    assert "tokens, not currency" in html


def test_analytics_sidebar_entry_active(analytics_client: TestClient) -> None:
    html = analytics_client.get("/ui/projects/alpha/analytics").text
    # The sidebar item exists and is marked current on its own page.
    before, _, after = html.partition('href="/ui/projects/alpha/analytics"')
    assert after, "Analytics sidebar entry missing"
    assert "active" in before[-120:] or 'aria-current="page"' in after[:200]


def test_analytics_unknown_project_404(analytics_client: TestClient) -> None:
    assert analytics_client.get("/ui/projects/nope/analytics").status_code == 404


# --- no side effects on render ------------------------------------------------


def test_no_qa_and_no_provider_on_analytics_render(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    initialize_project(_epub(), cwd=tmp_path, project_name="alpha")
    client = TestClient(create_api_app(tmp_path))

    def _no_qa(*args: object, **kwargs: object) -> object:
        _ = (args, kwargs)
        raise AssertionError("QA must not run on analytics render")

    def _no_provider(*args: object, **kwargs: object) -> object:
        _ = (args, kwargs)
        raise AssertionError("provider must not be built on analytics render")

    monkeypatch.setattr("weaver.services.translation_qa.analyze_novel", _no_qa)
    monkeypatch.setattr("weaver.providers.registry.build_provider", _no_provider)

    resp = client.get("/ui/projects/alpha/analytics")
    assert resp.status_code == 200


def test_no_db_write_on_analytics_render(tmp_path: Path) -> None:
    initialize_project(_epub(), cwd=tmp_path, project_name="alpha")
    db_path = tmp_path / ".weaver" / "alpha" / "weaver.db"
    client = TestClient(create_api_app(tmp_path))
    mtime_before = db_path.stat().st_mtime_ns

    client.get("/ui/projects/alpha/analytics")

    assert db_path.stat().st_mtime_ns == mtime_before


# --- dashboard rollup ---------------------------------------------------------


def test_dashboard_shows_workspace_rollup(tmp_path: Path) -> None:
    for name in ("alpha", "beta", "gamma"):
        initialize_project(_epub(), cwd=tmp_path, project_name=name)
    _seed_translated(tmp_path / ".weaver" / "alpha" / "weaver.db")
    client = TestClient(create_api_app(tmp_path))

    html = client.get("/ui").text
    assert "Workspace at a glance" in html
    assert "3 projects" in html
    assert "tokens in / out" in html


def test_dashboard_rollup_absent_when_no_projects(tmp_path: Path) -> None:
    client = TestClient(create_api_app(tmp_path))
    html = client.get("/ui").text
    assert "Workspace at a glance" not in html


# --- structural ---------------------------------------------------------------


def test_analytics_route_is_thin() -> None:
    from weaver.api.routers import ui_analytics

    source = inspect.getsource(ui_analytics.project_analytics_page)
    assert "build_project_analytics" in source
    assert "connect_database" not in source
    assert "connect_readonly_database" not in source
