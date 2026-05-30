"""Tests for the workspace save endpoint (Stage 3B).

PATCH /projects/{name}/chapters/{chapter_id}/segments/{segment_id}/translation
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _first_segment(client: TestClient) -> tuple[str, str, str]:
    """Return (project_name, chapter_id, segment_id) for the first segment."""
    name = client.get("/projects").json()["projects"][0]["name"]
    tree = client.get(f"/projects/{name}/tree").json()
    for volume in tree["volumes"]:
        for chapter in volume["chapters"]:
            workspace = client.get(f"/projects/{name}/chapters/{chapter['id']}/workspace").json()
            if workspace["segments"]:
                return name, chapter["id"], workspace["segments"][0]["id"]
    raise AssertionError("fixture project has no segments")


def _patch(client: TestClient, name: str, chapter_id: str, segment_id: str, text: str):
    return client.patch(
        f"/projects/{name}/chapters/{chapter_id}/segments/{segment_id}/translation",
        json={"translated_text": text},
    )


def test_save_returns_manual_payload(client_with_projects: TestClient) -> None:
    name, chapter_id, segment_id = _first_segment(client_with_projects)
    response = _patch(client_with_projects, name, chapter_id, segment_id, "Hello world.")
    assert response.status_code == 200
    data = response.json()
    assert data["segment_id"] == segment_id
    assert data["status"] == "manual"
    assert data["translated_text"] == "Hello world."
    assert data["saved_at"]


def test_save_round_trips_into_workspace(client_with_projects: TestClient) -> None:
    name, chapter_id, segment_id = _first_segment(client_with_projects)
    _patch(client_with_projects, name, chapter_id, segment_id, "Persisted line.")

    workspace = client_with_projects.get(f"/projects/{name}/chapters/{chapter_id}/workspace").json()
    saved = next(s for s in workspace["segments"] if s["id"] == segment_id)
    assert saved["translated_text"] == "Persisted line."
    assert saved["status"] == "manual"
    # Source text is preserved across the edit.
    assert saved["source_text"]


def test_save_preserves_source_text(client_with_projects: TestClient) -> None:
    name, chapter_id, segment_id = _first_segment(client_with_projects)
    before = client_with_projects.get(f"/projects/{name}/chapters/{chapter_id}/workspace").json()
    source_before = next(s for s in before["segments"] if s["id"] == segment_id)["source_text"]

    _patch(client_with_projects, name, chapter_id, segment_id, "Edited.")

    after = client_with_projects.get(f"/projects/{name}/chapters/{chapter_id}/workspace").json()
    source_after = next(s for s in after["segments"] if s["id"] == segment_id)["source_text"]
    assert source_after == source_before


def test_save_rejects_empty_text(client_with_projects: TestClient) -> None:
    name, chapter_id, segment_id = _first_segment(client_with_projects)
    response = _patch(client_with_projects, name, chapter_id, segment_id, "   ")
    assert response.status_code == 422
    assert "empty" in response.json()["detail"].lower()


def test_save_unknown_project(client: TestClient) -> None:
    response = _patch(client, "nonexistent", "c1", "s1", "x")
    assert response.status_code == 404
    assert "nonexistent" in response.json()["detail"]


def test_save_unknown_chapter(client_with_projects: TestClient) -> None:
    name = client_with_projects.get("/projects").json()["projects"][0]["name"]
    response = _patch(client_with_projects, name, "no-such-chapter", "s1", "x")
    assert response.status_code == 404
    assert "no-such-chapter" in response.json()["detail"]


def test_save_segment_not_in_chapter(client_with_projects: TestClient) -> None:
    name, chapter_id, _ = _first_segment(client_with_projects)
    response = _patch(client_with_projects, name, chapter_id, "bogus-segment", "x")
    assert response.status_code == 404
    assert "bogus-segment" in response.json()["detail"]
