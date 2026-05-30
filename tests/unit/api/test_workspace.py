"""Tests for the chapter workspace read endpoint (Stage 3A).

GET /projects/{name}/chapters/{chapter_id}/workspace
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _first_chapter(client: TestClient) -> tuple[str, str]:
    """Return (project_name, chapter_id) for the first chapter in the fixture."""
    name = client.get("/projects").json()["projects"][0]["name"]
    tree = client.get(f"/projects/{name}/tree").json()
    for volume in tree["volumes"]:
        if volume["chapters"]:
            return name, volume["chapters"][0]["id"]
    raise AssertionError("fixture project has no chapters")


def test_workspace_project_not_found(client: TestClient) -> None:
    response = client.get("/projects/nonexistent/chapters/c1/workspace")
    assert response.status_code == 404
    assert "nonexistent" in response.json()["detail"]


def test_workspace_chapter_not_found(client_with_projects: TestClient) -> None:
    name = client_with_projects.get("/projects").json()["projects"][0]["name"]
    response = client_with_projects.get(f"/projects/{name}/chapters/no-such-chapter/workspace")
    assert response.status_code == 404
    assert "no-such-chapter" in response.json()["detail"]


def test_workspace_returns_payload(client_with_projects: TestClient) -> None:
    name, chapter_id = _first_chapter(client_with_projects)
    response = client_with_projects.get(f"/projects/{name}/chapters/{chapter_id}/workspace")
    assert response.status_code == 200
    data = response.json()
    assert data["chapter_id"] == chapter_id
    assert data["project_name"]
    assert data["volume_id"] >= 1
    assert isinstance(data["segments"], list)


def test_workspace_payload_shape(client_with_projects: TestClient) -> None:
    name, chapter_id = _first_chapter(client_with_projects)
    data = client_with_projects.get(f"/projects/{name}/chapters/{chapter_id}/workspace").json()
    assert {
        "project_name",
        "volume_id",
        "volume_title",
        "chapter_id",
        "chapter_title",
        "segment_count",
        "translated_count",
        "segments",
    } <= data.keys()
    assert data["segment_count"] == len(data["segments"])


def test_workspace_segment_shape(client_with_projects: TestClient) -> None:
    name, chapter_id = _first_chapter(client_with_projects)
    data = client_with_projects.get(f"/projects/{name}/chapters/{chapter_id}/workspace").json()
    if not data["segments"]:
        return
    segment = data["segments"][0]
    assert {
        "id",
        "block_order",
        "kind",
        "source_text",
        "status",
        "translated_text",
    } <= segment.keys()
    # Untranslated fixture project: translation text starts null.
    assert segment["translated_text"] is None


def test_workspace_segments_ordered_by_block_order(client_with_projects: TestClient) -> None:
    name, chapter_id = _first_chapter(client_with_projects)
    segments = client_with_projects.get(f"/projects/{name}/chapters/{chapter_id}/workspace").json()[
        "segments"
    ]
    orders = [s["block_order"] for s in segments]
    assert orders == sorted(orders)
