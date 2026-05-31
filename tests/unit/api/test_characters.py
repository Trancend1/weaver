"""Tests for the Stage 5B character endpoints (project-scoped CRUD by jp_name)."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _name(client: TestClient) -> str:
    return str(client.get("/projects").json()["projects"][0]["name"])


def test_list_characters_empty(client_with_projects: TestClient) -> None:
    name = _name(client_with_projects)
    resp = client_with_projects.get(f"/projects/{name}/characters")
    assert resp.status_code == 200
    assert resp.json() == {"characters": [], "count": 0}


def test_create_then_list_roundtrip(client_with_projects: TestClient) -> None:
    name = _name(client_with_projects)
    resp = client_with_projects.post(
        f"/projects/{name}/characters",
        json={
            "jp_name": "エリナ",
            "en_name": "Elina",
            "gender": "Female",
            "role": "Main Heroine",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["jp_name"] == "エリナ"
    assert body["en_name"] == "Elina"
    assert body["gender"] == "Female"
    assert body["role"] == "Main Heroine"
    assert body["notes"] is None

    listed = client_with_projects.get(f"/projects/{name}/characters").json()
    assert listed["count"] == 1
    assert listed["characters"][0]["jp_name"] == "エリナ"


def test_create_same_jp_name_upserts_not_duplicates(client_with_projects: TestClient) -> None:
    name = _name(client_with_projects)
    client_with_projects.post(
        f"/projects/{name}/characters", json={"jp_name": "魔王", "en_name": "Demon King"}
    )
    resp = client_with_projects.post(
        f"/projects/{name}/characters", json={"jp_name": "魔王", "en_name": "Demon Lord"}
    )
    assert resp.status_code == 201

    listed = client_with_projects.get(f"/projects/{name}/characters").json()
    jp_names = [c["jp_name"] for c in listed["characters"]]
    assert jp_names.count("魔王") == 1
    assert listed["count"] == 1
    assert listed["characters"][0]["en_name"] == "Demon Lord"


def test_update_japanese_name_path(client_with_projects: TestClient) -> None:
    """PATCH with a Japanese jp_name in the URL path (decoding safe)."""
    name = _name(client_with_projects)
    client_with_projects.post(
        f"/projects/{name}/characters", json={"jp_name": "エリナ", "en_name": "Elina"}
    )
    resp = client_with_projects.patch(
        f"/projects/{name}/characters/エリナ",
        json={"en_name": "Erina", "role": "Heroine"},
    )
    assert resp.status_code == 200
    assert resp.json()["en_name"] == "Erina"
    assert resp.json()["role"] == "Heroine"


def test_delete_japanese_name_path(client_with_projects: TestClient) -> None:
    """DELETE with a Japanese jp_name in the URL path (decoding safe)."""
    name = _name(client_with_projects)
    client_with_projects.post(
        f"/projects/{name}/characters", json={"jp_name": "魔王", "en_name": "Demon King"}
    )
    resp = client_with_projects.delete(f"/projects/{name}/characters/魔王")
    assert resp.status_code == 204

    listed = client_with_projects.get(f"/projects/{name}/characters").json()
    assert listed["count"] == 0


def test_update_missing_character_404(client_with_projects: TestClient) -> None:
    name = _name(client_with_projects)
    resp = client_with_projects.patch(f"/projects/{name}/characters/未登録", json={"en_name": "x"})
    assert resp.status_code == 404


def test_delete_missing_character_404(client_with_projects: TestClient) -> None:
    name = _name(client_with_projects)
    resp = client_with_projects.delete(f"/projects/{name}/characters/未登録")
    assert resp.status_code == 404


def test_create_empty_jp_name_422(client_with_projects: TestClient) -> None:
    name = _name(client_with_projects)
    resp = client_with_projects.post(
        f"/projects/{name}/characters", json={"jp_name": "  ", "en_name": "x"}
    )
    assert resp.status_code == 422


def test_create_empty_en_name_422(client_with_projects: TestClient) -> None:
    name = _name(client_with_projects)
    resp = client_with_projects.post(
        f"/projects/{name}/characters", json={"jp_name": "猫", "en_name": ""}
    )
    assert resp.status_code == 422


def test_list_unknown_project_404(client: TestClient) -> None:
    resp = client.get("/projects/does-not-exist/characters")
    assert resp.status_code == 404
