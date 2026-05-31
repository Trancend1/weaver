"""Tests for the Stage 6B translation-memory endpoints (read overview + delete)."""

from __future__ import annotations

from fastapi.testclient import TestClient

FAKE_BODY = {"provider": "fake", "model": "fake-1"}


def _name(client: TestClient) -> str:
    return str(client.get("/projects").json()["projects"][0]["name"])


def _first_chapter(client: TestClient, name: str) -> str:
    tree = client.get(f"/projects/{name}/tree").json()
    return str(tree["volumes"][0]["chapters"][0]["id"])


def _translate_first_chapter(client: TestClient, name: str) -> str:
    chapter_id = _first_chapter(client, name)
    resp = client.post(f"/projects/{name}/chapters/{chapter_id}/translate", json=FAKE_BODY)
    job_id = resp.json()["job_id"]
    job = client.app.state.jobs.get(job_id)  # type: ignore[attr-defined]
    assert job is not None
    job.wait(timeout=5)
    return chapter_id


def test_get_memory_empty(client_with_projects: TestClient) -> None:
    name = _name(client_with_projects)
    resp = client_with_projects.get(f"/projects/{name}/memory")
    assert resp.status_code == 200
    assert resp.json() == {
        "total_entries": 0,
        "exact_hits": 0,
        "reused_from_memory": 0,
        "entries": [],
    }


def test_get_memory_after_translate_lists_entries(client_with_projects: TestClient) -> None:
    name = _name(client_with_projects)
    _translate_first_chapter(client_with_projects, name)

    body = client_with_projects.get(f"/projects/{name}/memory").json()

    assert body["total_entries"] > 0
    assert body["reused_from_memory"] == 0  # first pass: nothing reused yet
    assert body["exact_hits"] == 0
    assert len(body["entries"]) == body["total_entries"]
    entry = body["entries"][0]
    assert entry["target_text"]
    assert entry["source_hash"]
    assert entry["provider"] == "fake"


def test_delete_memory_entry_removes_only_tm_row(client_with_projects: TestClient) -> None:
    name = _name(client_with_projects)
    chapter_id = _translate_first_chapter(client_with_projects, name)
    before = client_with_projects.get(f"/projects/{name}/memory").json()
    target_hash = before["entries"][0]["source_hash"]

    resp = client_with_projects.delete(f"/projects/{name}/memory/{target_hash}")
    assert resp.status_code == 204

    after = client_with_projects.get(f"/projects/{name}/memory").json()
    assert after["total_entries"] == before["total_entries"] - 1
    assert all(e["source_hash"] != target_hash for e in after["entries"])

    # Translation history is preserved — the workspace still shows translations.
    workspace = client_with_projects.get(f"/projects/{name}/chapters/{chapter_id}/workspace").json()
    assert any(seg["translated_text"] for seg in workspace["segments"])


def test_delete_unknown_memory_entry_returns_404(client_with_projects: TestClient) -> None:
    name = _name(client_with_projects)
    resp = client_with_projects.delete(f"/projects/{name}/memory/deadbeef")
    assert resp.status_code == 404


def test_get_memory_unknown_project_returns_404(client_with_projects: TestClient) -> None:
    resp = client_with_projects.get("/projects/nope/memory")
    assert resp.status_code == 404
