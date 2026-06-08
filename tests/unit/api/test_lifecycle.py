"""Tests for project + volume lifecycle endpoints (Sprint H3)."""

from __future__ import annotations

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


def _project_name(client: TestClient) -> str:
    body = client.get("/projects").json()
    assert body["projects"], body
    return body["projects"][0]["name"]


def test_tree_includes_volume_lifecycle_status(client_with_projects: TestClient) -> None:
    name = _project_name(client_with_projects)
    body = client_with_projects.get(f"/projects/{name}/tree").json()
    assert body["volumes"]
    for volume in body["volumes"]:
        assert "status" in volume
        assert volume["status"] in {
            "empty",
            "imported",
            "in_progress",
            "translated",
            "translating",
        }
        assert volume["status_label"]


def test_delete_volume_returns_204_and_removes_it(client_with_projects: TestClient) -> None:
    name = _project_name(client_with_projects)
    tree = client_with_projects.get(f"/projects/{name}/tree").json()
    assert tree["volumes"], tree
    volume_id = tree["volumes"][0]["id"]

    deleted = client_with_projects.delete(f"/projects/{name}/volumes/{volume_id}")
    assert deleted.status_code == 204

    after = client_with_projects.get(f"/projects/{name}/tree").json()
    remaining_ids = [v["id"] for v in after["volumes"]]
    assert volume_id not in remaining_ids


def test_delete_volume_unknown_id_returns_404(client_with_projects: TestClient) -> None:
    name = _project_name(client_with_projects)
    response = client_with_projects.delete(f"/projects/{name}/volumes/9999999")
    assert response.status_code == 404


def test_delete_volume_unknown_project_returns_404(client_with_projects: TestClient) -> None:
    response = client_with_projects.delete("/projects/no-such-project/volumes/1")
    assert response.status_code == 404


def test_delete_project_returns_204_and_removes_it(client_with_projects: TestClient) -> None:
    name = _project_name(client_with_projects)
    response = client_with_projects.delete(f"/projects/{name}")
    assert response.status_code == 204
    after = client_with_projects.get("/projects").json()
    remaining = [p["name"] for p in after["projects"]]
    assert name not in remaining


def test_delete_project_unknown_returns_404(client_with_projects: TestClient) -> None:
    response = client_with_projects.delete("/projects/never-existed")
    assert response.status_code == 404


def test_ui_volume_delete_re_renders_tree(client_with_projects: TestClient) -> None:
    name = _project_name(client_with_projects)
    tree = client_with_projects.get(f"/projects/{name}/tree").json()
    volume_id = tree["volumes"][0]["id"]

    response = client_with_projects.post(f"/ui/projects/{name}/volumes/{volume_id}/delete")
    assert response.status_code == 200
    # Returned the rendered tree partial, not an error fragment.
    assert 'id="tree"' in response.text


def test_ui_volume_delete_unknown_id_returns_error_fragment(
    client_with_projects: TestClient,
) -> None:
    name = _project_name(client_with_projects)
    response = client_with_projects.post(f"/ui/projects/{name}/volumes/9999999/delete")
    # The shared _import_error helper retargets the error away from the tree.
    assert response.status_code in (200, 422)
    assert "tree" not in response.text or "error" in response.text.lower()
