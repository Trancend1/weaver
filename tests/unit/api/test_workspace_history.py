"""Tests for the segment revision-history endpoint (Stage 3C).

GET /projects/{name}/chapters/{chapter_id}/segments/{segment_id}/translations
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


def _save(client: TestClient, name: str, chapter_id: str, segment_id: str, text: str):
    return client.patch(
        f"/projects/{name}/chapters/{chapter_id}/segments/{segment_id}/translation",
        json={"translated_text": text},
    )


def _history(client: TestClient, name: str, chapter_id: str, segment_id: str):
    return client.get(f"/projects/{name}/chapters/{chapter_id}/segments/{segment_id}/translations")


def test_history_empty_before_any_save(client_with_projects: TestClient) -> None:
    name, chapter_id, segment_id = _first_segment(client_with_projects)
    data = _history(client_with_projects, name, chapter_id, segment_id).json()
    assert data["segment_id"] == segment_id
    assert data["chapter_id"] == chapter_id
    assert data["current_translation"] is None
    assert data["attempts"] == []


def test_history_returns_all_attempts_in_order(client_with_projects: TestClient) -> None:
    name, chapter_id, segment_id = _first_segment(client_with_projects)
    _save(client_with_projects, name, chapter_id, segment_id, "v1")
    _save(client_with_projects, name, chapter_id, segment_id, "v2")
    _save(client_with_projects, name, chapter_id, segment_id, "v3")

    data = _history(client_with_projects, name, chapter_id, segment_id).json()
    assert [a["attempt"] for a in data["attempts"]] == [1, 2, 3]
    assert [a["translated_text"] for a in data["attempts"]] == ["v1", "v2", "v3"]
    assert data["current_translation"] == "v3"
    assert data["status"] == "manual"


def test_history_attempt_shape(client_with_projects: TestClient) -> None:
    name, chapter_id, segment_id = _first_segment(client_with_projects)
    _save(client_with_projects, name, chapter_id, segment_id, "v1")
    attempt = _history(client_with_projects, name, chapter_id, segment_id).json()["attempts"][0]
    assert {
        "attempt",
        "translated_text",
        "provider",
        "model",
        "created_at",
    } <= attempt.keys()
    assert attempt["provider"] == "manual"


def test_workspace_still_returns_latest_only(client_with_projects: TestClient) -> None:
    name, chapter_id, segment_id = _first_segment(client_with_projects)
    _save(client_with_projects, name, chapter_id, segment_id, "old")
    _save(client_with_projects, name, chapter_id, segment_id, "new")

    workspace = client_with_projects.get(f"/projects/{name}/chapters/{chapter_id}/workspace").json()
    seg = next(s for s in workspace["segments"] if s["id"] == segment_id)
    # Workspace exposes only the latest translation, not the attempt list.
    assert seg["translated_text"] == "new"
    assert "attempts" not in seg


def test_history_unknown_project(client: TestClient) -> None:
    response = _history(client, "nonexistent", "c1", "s1")
    assert response.status_code == 404
    assert "nonexistent" in response.json()["detail"]


def test_history_unknown_chapter(client_with_projects: TestClient) -> None:
    name = client_with_projects.get("/projects").json()["projects"][0]["name"]
    response = _history(client_with_projects, name, "no-such-chapter", "s1")
    assert response.status_code == 404
    assert "no-such-chapter" in response.json()["detail"]


def test_history_segment_not_in_chapter(client_with_projects: TestClient) -> None:
    name, chapter_id, _ = _first_segment(client_with_projects)
    response = _history(client_with_projects, name, chapter_id, "bogus-segment")
    assert response.status_code == 404
    assert "bogus-segment" in response.json()["detail"]
