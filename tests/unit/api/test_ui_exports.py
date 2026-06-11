"""Q7 tests: Exports hub, per-project export history, and the Draft/Final gate.

Verifies:
- /ui/exports renders ws-hub layout with active sidebar entry
- cross-project rows show basename + missing state; no absolute path leak
- per-project page lists history with full path
- Draft export always starts; Final+require_clean is refused (blocked fragment)
- a full export through the route records a ledger row (wired end to end)
- degraded isolation; thin router; existing routes still render
"""

from __future__ import annotations

import inspect
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from weaver.api.app import create_api_app
from weaver.services.project import initialize_project
from weaver.services.workspace_exports import (
    ExportDegradedProject,
    ExportHubRow,
    WorkspaceExports,
)

FIXTURES = Path(__file__).parent.parent.parent / "fixtures"


def _epub() -> Path:
    epubs = list(FIXTURES.glob("*.epub"))
    if not epubs:
        pytest.skip("no EPUB fixture available")
    return epubs[0]


def _volume_id(db_path: Path) -> int:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT id FROM volumes ORDER BY id LIMIT 1").fetchone()
    conn.close()
    return int(row["id"]) if row is not None else 1


def _seed_export(db_path: Path, *, id: str, artifact_path: str | None) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(
        "INSERT INTO export_history (id, volume_id, format, kind, status, qa_badge, "
        "artifact_path, byte_size, job_id, version_label, created_at) "
        "VALUES (?, ?, 'epub', 'draft', 'succeeded', 'clean', ?, 10, NULL, NULL, "
        "'2025-01-01T00:00:00+00:00')",
        (id, _volume_id(db_path), artifact_path),
    )
    conn.commit()
    conn.close()


@pytest.fixture
def exports_client(tmp_path: Path) -> TestClient:
    initialize_project(_epub(), cwd=tmp_path, project_name="alpha")
    db = tmp_path / ".weaver" / "alpha" / "weaver.db"
    artifact = tmp_path / "out" / "volume-01.epub"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"epub")
    _seed_export(db, id="e1", artifact_path=str(artifact))
    _seed_export(db, id="gone", artifact_path=str(tmp_path / "missing.epub"))
    return TestClient(create_api_app(tmp_path))


@pytest.fixture
def empty_exports_client(tmp_path: Path) -> TestClient:
    return TestClient(create_api_app(tmp_path))


# --- layout -----------------------------------------------------------------


def test_exports_uses_ws_hub_layout(exports_client: TestClient) -> None:
    html = exports_client.get("/ui/exports").text
    assert "layout--ws-hub" in html
    assert "app-shell--ws-hub" in html


def test_exports_sidebar_entry_is_active(exports_client: TestClient) -> None:
    html = exports_client.get("/ui/exports").text
    assert 'href="/ui/exports"' in html
    link = html.split('href="/ui/exports"')[1].split("</a>")[0]
    assert 'aria-current="page"' in link or "active" in link


# --- content ----------------------------------------------------------------


def test_exports_shows_basename_and_missing(exports_client: TestClient) -> None:
    html = exports_client.get("/ui/exports").text
    assert "volume-01.epub" in html
    assert "missing" in html  # the second seeded row's artifact is gone


def test_exports_does_not_leak_absolute_path(exports_client: TestClient, tmp_path: Path) -> None:
    html = exports_client.get("/ui/exports").text
    # The cross-project hub must not render the absolute output directory path.
    assert str(tmp_path / "out") not in html


def test_empty_exports_renders_empty_state(empty_exports_client: TestClient) -> None:
    assert "No exports yet" in empty_exports_client.get("/ui/exports").text


# --- per-project ------------------------------------------------------------


def test_project_exports_page_shows_full_path(exports_client: TestClient, tmp_path: Path) -> None:
    html = exports_client.get("/ui/projects/alpha/exports").text
    assert "Export history" in html
    assert str(tmp_path / "out" / "volume-01.epub") in html


def test_project_exports_unknown_project_404(exports_client: TestClient) -> None:
    assert exports_client.get("/ui/projects/nope/exports").status_code == 404


# --- Draft/Final gate via the route -----------------------------------------


def test_draft_export_always_starts(exports_client: TestClient) -> None:
    resp = exports_client.post(
        "/ui/projects/alpha/export", data={"target": "epub", "kind": "draft"}
    )
    assert resp.status_code == 200
    assert "blocked" not in resp.text.lower()


def test_final_export_blocked_with_criticals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    initialize_project(_epub(), cwd=tmp_path, project_name="alpha")

    from weaver.services.export_gate import ExportGateDecision

    def _blocked(*args: object, **kwargs: object) -> ExportGateDecision:
        _ = (args, kwargs)
        return ExportGateDecision(
            allowed=False,
            kind="final",
            require_clean=True,
            qa_badge="errors",
            critical_count=2,
            reason="Final export is blocked: 2 unresolved critical quality issue(s).",
        )

    monkeypatch.setattr("weaver.api.routers.export.evaluate_export_gate", _blocked)
    client = TestClient(create_api_app(tmp_path))
    resp = client.post(
        "/ui/projects/alpha/export",
        data={"target": "epub", "kind": "final", "require_clean": "true"},
    )
    assert resp.status_code == 200
    assert "Final export blocked" in resp.text
    assert "Export as Draft instead" in resp.text


def test_route_export_records_ledger_row(tmp_path: Path) -> None:
    initialize_project(_epub(), cwd=tmp_path, project_name="alpha")
    client = TestClient(create_api_app(tmp_path))
    resp = client.post("/projects/alpha/export/novel", json={"target": "epub", "kind": "draft"})
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]
    job = client.app.state.jobs.get_export(job_id)  # type: ignore[attr-defined]
    assert job is not None
    job.wait(timeout=15)

    history = client.get("/ui/projects/alpha/exports").text
    assert "succeeded" in history


# --- degraded + structural --------------------------------------------------


def test_degraded_project_does_not_blank_hub(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    rows = [
        ExportHubRow(
            project_name="good",
            project_uuid="u",
            format="epub",
            kind="draft",
            status="succeeded",
            qa_badge="clean",
            artifact_basename="v.epub",
            byte_size=5,
            exists=True,
            created_at="2025-01-01T00:00:00+00:00",
        )
    ]
    degraded = [ExportDegradedProject("bad", None, "error", "DB locked")]
    monkeypatch.setattr(
        "weaver.api.routers.ui_exports.build_workspace_exports",
        lambda *a, **kw: WorkspaceExports(rows=rows, degraded=degraded, generated_at=0.0),
    )
    client = TestClient(create_api_app(tmp_path))
    resp = client.get("/ui/exports")
    assert resp.status_code == 200
    assert "good" in resp.text
    assert "bad" in resp.text
    assert "DB locked" in resp.text


def test_exports_get_route_is_thin() -> None:
    from weaver.api.routers import ui_exports

    source = inspect.getsource(ui_exports.exports_page)
    assert "build_workspace_exports" in source
    assert "connect_database" not in source
    assert "connect_readonly_database" not in source


def test_providers_still_renders(exports_client: TestClient) -> None:
    resp = exports_client.get("/ui/providers")
    assert resp.status_code == 200
    assert "layout--ws-hub" in resp.text
