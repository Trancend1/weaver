"""Tests for the Stage 8B export endpoints (novel/volume/chapter EPUB export).

Uses `client_with_projects` (a single EPUB-volume project with no translations):
export still succeeds via source fallback, which is enough to exercise
start/status/SSE/cancel/errors. Content correctness is covered by the 8A service
tests (`tests/unit/services/test_export_book.py`).
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient


def _name(client: TestClient) -> str:
    return str(client.get("/projects").json()["projects"][0]["name"])


def _volume_id(client: TestClient, name: str) -> str:
    tree = client.get(f"/projects/{name}/tree").json()
    return str(tree["volumes"][0]["id"])


def _first_chapter(client: TestClient, name: str) -> str:
    tree = client.get(f"/projects/{name}/tree").json()
    return str(tree["volumes"][0]["chapters"][0]["id"])


def _wait_export(client: TestClient, job_id: str) -> None:
    job = client.app.state.jobs.get_export(job_id)  # type: ignore[attr-defined]
    assert job is not None
    job.wait(timeout=10)


# --------------------------------------------------------------------------- #
# start each scope
# --------------------------------------------------------------------------- #


def test_export_novel_starts_and_completes(client_with_projects: TestClient) -> None:
    name = _name(client_with_projects)
    resp = client_with_projects.post(f"/projects/{name}/export/novel")
    assert resp.status_code == 202
    data = resp.json()
    assert data["scope"] == "novel"
    assert data["scope_id"] is None
    assert data["target"] == "epub"
    job_id = data["job_id"]

    _wait_export(client_with_projects, job_id)
    status = client_with_projects.get(f"/projects/{name}/export/jobs/{job_id}").json()
    assert status["status"] == "done"
    assert status["error"] is None
    result = status["result"]
    assert result["target"] == "epub"
    assert result["volumes_total"] >= 1
    assert result["volumes_exported"] == result["volumes_total"]
    assert len(result["artifacts"]) == result["volumes_exported"]
    assert result["cancelled"] is False
    assert result["generated_at"]
    # the artifact was actually written to disk
    artifact = result["artifacts"][0]
    assert artifact["source_format"] == "epub"
    assert Path(artifact["output_path"]).exists()
    assert "fallback_by_status" in artifact


def test_export_volume_starts_and_completes(client_with_projects: TestClient) -> None:
    name = _name(client_with_projects)
    volume_id = _volume_id(client_with_projects, name)
    resp = client_with_projects.post(f"/projects/{name}/export/volumes/{volume_id}")
    assert resp.status_code == 202
    data = resp.json()
    assert data["scope"] == "volume"
    assert data["scope_id"] == volume_id

    _wait_export(client_with_projects, data["job_id"])
    result = client_with_projects.get(f"/projects/{name}/export/jobs/{data['job_id']}").json()[
        "result"
    ]
    assert result["volumes_total"] == 1
    assert result["volumes_exported"] == 1


def test_export_chapter_starts_and_completes(client_with_projects: TestClient) -> None:
    name = _name(client_with_projects)
    chapter_id = _first_chapter(client_with_projects, name)
    resp = client_with_projects.post(f"/projects/{name}/export/chapters/{chapter_id}")
    assert resp.status_code == 202
    data = resp.json()
    assert data["scope"] == "chapter"
    assert data["scope_id"] == chapter_id

    _wait_export(client_with_projects, data["job_id"])
    result = client_with_projects.get(f"/projects/{name}/export/jobs/{data['job_id']}").json()[
        "result"
    ]
    assert result["chapters_exported"] == 1
    assert result["volumes_exported"] == 1


# --------------------------------------------------------------------------- #
# progress + SSE + cancel
# --------------------------------------------------------------------------- #


def test_export_status_progress_carries_target_scope(client_with_projects: TestClient) -> None:
    name = _name(client_with_projects)
    job_id = client_with_projects.post(f"/projects/{name}/export/novel").json()["job_id"]
    _wait_export(client_with_projects, job_id)

    progress = client_with_projects.get(f"/projects/{name}/export/jobs/{job_id}").json()["progress"]
    assert progress["target"] == "epub"
    assert progress["scope"] == "novel"
    assert progress["volumes_done"] == progress["volumes_total"]


def test_export_events_stream_emits_progress_then_terminal(
    client_with_projects: TestClient,
) -> None:
    name = _name(client_with_projects)
    job_id = client_with_projects.post(f"/projects/{name}/export/novel").json()["job_id"]
    body = client_with_projects.get(f"/projects/{name}/export/jobs/{job_id}/events").text
    assert "event: progress" in body
    assert "event: done" in body


def test_export_cancel_endpoint_returns_status(client_with_projects: TestClient) -> None:
    name = _name(client_with_projects)
    job_id = client_with_projects.post(f"/projects/{name}/export/novel").json()["job_id"]
    resp = client_with_projects.post(f"/projects/{name}/export/jobs/{job_id}/cancel")
    assert resp.status_code == 200
    assert resp.json()["status"] in {"running", "done", "cancelled"}


# --------------------------------------------------------------------------- #
# errors + namespace isolation
# --------------------------------------------------------------------------- #


def test_export_unknown_project_returns_404(client_with_projects: TestClient) -> None:
    resp = client_with_projects.post("/projects/nope/export/novel")
    assert resp.status_code == 404


def test_export_unknown_volume_returns_404(client_with_projects: TestClient) -> None:
    name = _name(client_with_projects)
    resp = client_with_projects.post(f"/projects/{name}/export/volumes/9999")
    assert resp.status_code == 404


def test_export_unknown_chapter_returns_404(client_with_projects: TestClient) -> None:
    name = _name(client_with_projects)
    resp = client_with_projects.post(f"/projects/{name}/export/chapters/missing")
    assert resp.status_code == 404


def test_export_unsupported_target_returns_422(client_with_projects: TestClient) -> None:
    name = _name(client_with_projects)
    resp = client_with_projects.post(f"/projects/{name}/export/novel", json={"target": "pdf"})
    assert resp.status_code == 422


def test_export_unknown_job_returns_404(client_with_projects: TestClient) -> None:
    name = _name(client_with_projects)
    resp = client_with_projects.get(f"/projects/{name}/export/jobs/deadbeef")
    assert resp.status_code == 404


def test_export_job_id_not_resolvable_via_batch_jobs_route(
    client_with_projects: TestClient,
) -> None:
    name = _name(client_with_projects)
    job_id = client_with_projects.post(f"/projects/{name}/export/novel").json()["job_id"]
    _wait_export(client_with_projects, job_id)
    # The batch-job namespace must not resolve an export job id.
    resp = client_with_projects.get(f"/projects/{name}/batch/jobs/{job_id}")
    assert resp.status_code == 404


# --------------------------------------------------------------------------- #
# TXT / HTML targets (Sprint 8C)
# --------------------------------------------------------------------------- #


def test_export_txt_target_via_endpoint(client_with_projects: TestClient) -> None:
    name = _name(client_with_projects)
    resp = client_with_projects.post(f"/projects/{name}/export/novel", json={"target": "txt"})
    assert resp.status_code == 202
    assert resp.json()["target"] == "txt"
    job_id = resp.json()["job_id"]

    _wait_export(client_with_projects, job_id)
    result = client_with_projects.get(f"/projects/{name}/export/jobs/{job_id}").json()["result"]
    assert result["target"] == "txt"
    artifact = result["artifacts"][0]
    assert artifact["output_path"].endswith(".txt")
    assert Path(artifact["output_path"]).exists()


def test_export_html_target_via_endpoint(client_with_projects: TestClient) -> None:
    name = _name(client_with_projects)
    resp = client_with_projects.post(f"/projects/{name}/export/novel", json={"target": "html"})
    assert resp.status_code == 202
    assert resp.json()["target"] == "html"
    job_id = resp.json()["job_id"]

    _wait_export(client_with_projects, job_id)
    result = client_with_projects.get(f"/projects/{name}/export/jobs/{job_id}").json()["result"]
    assert result["target"] == "html"
    assert result["artifacts"][0]["output_path"].endswith(".html")


# --------------------------------------------------------------------------- #
# DOCX target (Phase D)
# --------------------------------------------------------------------------- #


def test_export_docx_target_via_endpoint(client_with_projects: TestClient) -> None:
    name = _name(client_with_projects)
    resp = client_with_projects.post(f"/projects/{name}/export/novel", json={"target": "docx"})
    assert resp.status_code == 202
    assert resp.json()["target"] == "docx"
    job_id = resp.json()["job_id"]

    _wait_export(client_with_projects, job_id)
    status = client_with_projects.get(f"/projects/{name}/export/jobs/{job_id}").json()
    assert status["status"] == "done"
    assert status["error"] is None
    result = status["result"]
    assert result["target"] == "docx"
    artifact = result["artifacts"][0]
    assert artifact["output_path"].endswith(".docx")
    assert Path(artifact["output_path"]).exists()


# --------------------------------------------------------------------------- #
# Combined ZIP bundle (Phase D)
# --------------------------------------------------------------------------- #


def test_export_bundle_via_endpoint(client_with_projects: TestClient) -> None:
    name = _name(client_with_projects)
    resp = client_with_projects.post(
        f"/projects/{name}/export/novel", json={"target": "txt", "bundle": True}
    )
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    _wait_export(client_with_projects, job_id)
    result = client_with_projects.get(f"/projects/{name}/export/jobs/{job_id}").json()["result"]
    assert result["bundle_path"] is not None
    assert result["bundle_path"].endswith("bundle-txt.zip")
    assert Path(result["bundle_path"]).exists()


def test_export_default_has_null_bundle_path(client_with_projects: TestClient) -> None:
    name = _name(client_with_projects)
    resp = client_with_projects.post(f"/projects/{name}/export/novel", json={"target": "txt"})
    job_id = resp.json()["job_id"]
    _wait_export(client_with_projects, job_id)
    result = client_with_projects.get(f"/projects/{name}/export/jobs/{job_id}").json()["result"]
    assert result["bundle_path"] is None
