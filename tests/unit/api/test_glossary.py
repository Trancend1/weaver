"""Tests for the Stage 5A glossary endpoints (direct project-scoped term CRUD)."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _name(client: TestClient) -> str:
    return str(client.get("/projects").json()["projects"][0]["name"])


def test_list_glossary_empty(client_with_projects: TestClient) -> None:
    name = _name(client_with_projects)
    resp = client_with_projects.get(f"/projects/{name}/glossary")
    assert resp.status_code == 200
    assert resp.json() == {"terms": [], "count": 0}


def test_create_then_list_roundtrip(client_with_projects: TestClient) -> None:
    name = _name(client_with_projects)
    resp = client_with_projects.post(
        f"/projects/{name}/glossary",
        json={"source": "魔王", "target": "Demon King", "category": "proper_noun"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["source"] == "魔王"
    assert body["target"] == "Demon King"
    assert body["category"] == "proper_noun"
    assert body["case_sensitive"] is False

    listed = client_with_projects.get(f"/projects/{name}/glossary").json()
    assert listed["count"] == 1
    assert listed["terms"][0]["source"] == "魔王"


def test_create_same_source_upserts_not_duplicates(client_with_projects: TestClient) -> None:
    """POST the same source twice → one row, updated target (UNIQUE upsert)."""
    name = _name(client_with_projects)
    client_with_projects.post(
        f"/projects/{name}/glossary", json={"source": "勇者", "target": "Hero"}
    )
    resp = client_with_projects.post(
        f"/projects/{name}/glossary", json={"source": "勇者", "target": "Brave Hero"}
    )
    assert resp.status_code == 201

    listed = client_with_projects.get(f"/projects/{name}/glossary").json()
    sources = [t["source"] for t in listed["terms"]]
    assert sources.count("勇者") == 1
    assert listed["count"] == 1
    assert listed["terms"][0]["target"] == "Brave Hero"


def test_update_japanese_source_path(client_with_projects: TestClient) -> None:
    """PATCH with a Japanese source in the URL path (decoding safe)."""
    name = _name(client_with_projects)
    client_with_projects.post(
        f"/projects/{name}/glossary", json={"source": "日本語", "target": "Japanese"}
    )
    resp = client_with_projects.patch(
        f"/projects/{name}/glossary/日本語",
        json={"target": "the Japanese language", "notes": "language name"},
    )
    assert resp.status_code == 200
    assert resp.json()["target"] == "the Japanese language"
    assert resp.json()["notes"] == "language name"


def test_delete_japanese_source_path(client_with_projects: TestClient) -> None:
    """DELETE with a Japanese source in the URL path (decoding safe)."""
    name = _name(client_with_projects)
    client_with_projects.post(
        f"/projects/{name}/glossary", json={"source": "エリナ", "target": "Elina"}
    )
    resp = client_with_projects.delete(f"/projects/{name}/glossary/エリナ")
    assert resp.status_code == 204

    listed = client_with_projects.get(f"/projects/{name}/glossary").json()
    assert listed["count"] == 0


def test_update_missing_term_404(client_with_projects: TestClient) -> None:
    name = _name(client_with_projects)
    resp = client_with_projects.patch(f"/projects/{name}/glossary/未登録", json={"target": "x"})
    assert resp.status_code == 404


def test_delete_missing_term_404(client_with_projects: TestClient) -> None:
    name = _name(client_with_projects)
    resp = client_with_projects.delete(f"/projects/{name}/glossary/未登録")
    assert resp.status_code == 404


def test_create_empty_source_422(client_with_projects: TestClient) -> None:
    name = _name(client_with_projects)
    resp = client_with_projects.post(
        f"/projects/{name}/glossary", json={"source": "  ", "target": "x"}
    )
    assert resp.status_code == 422


def test_create_empty_target_422(client_with_projects: TestClient) -> None:
    name = _name(client_with_projects)
    resp = client_with_projects.post(
        f"/projects/{name}/glossary", json={"source": "猫", "target": ""}
    )
    assert resp.status_code == 422


def test_list_unknown_project_404(client: TestClient) -> None:
    resp = client.get("/projects/does-not-exist/glossary")
    assert resp.status_code == 404
