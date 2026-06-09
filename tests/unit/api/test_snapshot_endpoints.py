"""Tests for the Sprint J4 snapshot JSON + UI endpoints."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from weaver.api.app import create_api_app


@pytest.fixture
def client_with_projects(tmp_path: Path) -> TestClient:
    from weaver.services.project import initialize_project

    fixtures = Path(__file__).parent.parent.parent / "fixtures"
    epubs = list(fixtures.glob("*.epub"))
    if not epubs:
        pytest.skip("no EPUB fixture available")
    initialize_project(epubs[0], cwd=tmp_path)
    return TestClient(create_api_app(tmp_path))


def _project(client: TestClient) -> str:
    return client.get("/projects").json()["projects"][0]["name"]


def _volume(client: TestClient, name: str) -> int:
    return int(client.get(f"/projects/{name}/tree").json()["volumes"][0]["id"])


def _wait_terminal(client: TestClient, name: str, job_id: str, *, tries: int = 200) -> str:
    for _ in range(tries):
        body = client.get(f"/projects/{name}/jobs/{job_id}/detail").json()
        if body["job"]["status"] in {"done", "failed", "cancelled"}:
            return body["job"]["status"]
        time.sleep(0.05)
    msg = "parse job did not finish in time"
    raise AssertionError(msg)


def test_snapshot_status_is_fresh_after_first_import(
    client_with_projects: TestClient,
) -> None:
    name = _project(client_with_projects)
    volume_id = _volume(client_with_projects, name)

    body = client_with_projects.get(f"/projects/{name}/volumes/{volume_id}/snapshot").json()
    assert body["volume_id"] == volume_id
    assert body["state"] == "fresh"
    assert body["source_hash"]


def test_reparse_endpoint_submits_persistent_parse_job(
    client_with_projects: TestClient,
) -> None:
    name = _project(client_with_projects)
    volume_id = _volume(client_with_projects, name)

    submission = client_with_projects.post(f"/projects/{name}/volumes/{volume_id}/reparse")
    assert submission.status_code == 202
    body = submission.json()
    assert body["volume_id"] == volume_id
    job_id = body["job_id"]

    status = _wait_terminal(client_with_projects, name, job_id)
    assert status == "done"

    # Snapshot is now fresh.
    snap = client_with_projects.get(f"/projects/{name}/volumes/{volume_id}/snapshot").json()
    assert snap["state"] == "fresh"
    assert snap["parser_version"] is not None
    assert snap["source_hash"]


def test_snapshot_status_404_for_unknown_project(client_with_projects: TestClient) -> None:
    response = client_with_projects.get("/projects/nope/volumes/1/snapshot")
    assert response.status_code == 404


def test_snapshot_status_404_for_unknown_volume(client_with_projects: TestClient) -> None:
    name = _project(client_with_projects)
    response = client_with_projects.get(f"/projects/{name}/volumes/999999/snapshot")
    assert response.status_code == 404


def test_ui_tree_renders_snapshot_controls(client_with_projects: TestClient) -> None:
    name = _project(client_with_projects)
    page = client_with_projects.get(f"/ui/projects/{name}").text
    assert "Preview EPUB" in page
    assert "Inspect status" in page
    assert "Full structure page" in page
    assert "snapshot-vol-" in page
    assert "Reparse EPUB" not in page


def test_ui_snapshot_partial_swap(client_with_projects: TestClient) -> None:
    name = _project(client_with_projects)
    volume_id = _volume(client_with_projects, name)
    page = client_with_projects.get(f"/ui/projects/{name}/volumes/{volume_id}/snapshot").text
    assert "snapshot-card" in page
    assert "fresh" in page


def test_ui_reparse_returns_running_card_with_job_link(
    client_with_projects: TestClient,
) -> None:
    name = _project(client_with_projects)
    volume_id = _volume(client_with_projects, name)
    page = client_with_projects.post(f"/ui/projects/{name}/volumes/{volume_id}/reparse").text
    assert "snapshot-state--reparsing" in page
    assert "/jobs/" in page  # link to the persistent Job Detail page


def test_ui_structure_page_falls_back_when_snapshot_missing(
    client_with_projects: TestClient,
) -> None:
    name = _project(client_with_projects)
    volume_id = _volume(client_with_projects, name)
    page = client_with_projects.get(f"/ui/projects/{name}/volumes/{volume_id}/structure").text
    assert "Snapshot missing" in page or "Reparse" in page


def test_ui_snapshot_partial_hides_reparse_for_fresh_snapshot(
    client_with_projects: TestClient,
) -> None:
    name = _project(client_with_projects)
    volume_id = _volume(client_with_projects, name)

    page = client_with_projects.get(f"/ui/projects/{name}/volumes/{volume_id}/snapshot").text

    assert "snapshot-state--fresh" in page
    assert "Reparse EPUB" not in page


def test_ui_structure_page_renders_after_reparse(
    client_with_projects: TestClient,
) -> None:
    name = _project(client_with_projects)
    volume_id = _volume(client_with_projects, name)
    job_id = client_with_projects.post(f"/projects/{name}/volumes/{volume_id}/reparse").json()[
        "job_id"
    ]
    _wait_terminal(client_with_projects, name, job_id)

    page = client_with_projects.get(f"/ui/projects/{name}/volumes/{volume_id}/structure").text
    # Phase F's preview template re-used; the persisted snapshot fed it.
    assert "epub-preview" in page or "metadata" in page.lower()
