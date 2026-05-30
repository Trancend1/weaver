"""Tests for the project read endpoints (GET /projects, GET /projects/{name}/tree)."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_list_projects_empty_base_dir(client: TestClient) -> None:
    response = client.get("/projects")
    assert response.status_code == 200
    assert response.json() == {"projects": []}


def test_list_projects_returns_project(client_with_projects: TestClient) -> None:
    response = client_with_projects.get("/projects")
    assert response.status_code == 200
    data = response.json()
    assert len(data["projects"]) == 1
    proj = data["projects"][0]
    assert "name" in proj
    assert "segment_count" in proj
    assert proj["error"] is None


def test_list_projects_response_shape(client_with_projects: TestClient) -> None:
    response = client_with_projects.get("/projects")
    proj = response.json()["projects"][0]
    required = {
        "name",
        "project_toml",
        "source_file",
        "provider",
        "model",
        "volume_count",
        "chapter_count",
        "segment_count",
        "pending_count",
        "translated_count",
        "failed_count",
        "stale_count",
        "glossary_candidate_count",
        "glossary_term_count",
        "output_dir",
        "error",
    }
    assert required <= proj.keys()


def test_get_project_tree_not_found(client: TestClient) -> None:
    response = client.get("/projects/nonexistent/tree")
    assert response.status_code == 404
    assert "nonexistent" in response.json()["detail"]


def test_get_project_tree_returns_tree(client_with_projects: TestClient) -> None:
    # First discover the project name
    projects = client_with_projects.get("/projects").json()["projects"]
    name = projects[0]["name"]

    response = client_with_projects.get(f"/projects/{name}/tree")
    assert response.status_code == 200
    data = response.json()
    assert "project_name" in data
    assert "volumes" in data
    assert isinstance(data["volumes"], list)
    assert len(data["volumes"]) >= 1


def test_get_project_tree_volume_shape(client_with_projects: TestClient) -> None:
    name = client_with_projects.get("/projects").json()["projects"][0]["name"]
    data = client_with_projects.get(f"/projects/{name}/tree").json()
    vol = data["volumes"][0]
    assert {
        "id",
        "title",
        "source_format",
        "volume_order",
        "chapter_count",
        "segment_count",
        "chapters",
    } <= vol.keys()
    if vol["chapters"]:
        ch = vol["chapters"][0]
        assert {"id", "title", "segment_count", "translated_count"} <= ch.keys()
