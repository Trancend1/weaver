"""Tests for POST /projects/{name}/import."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def test_import_project_not_found(client: TestClient) -> None:
    data = {"file": ("vol2.epub", BytesIO(b"fake"), "application/epub+zip")}
    response = client.post("/projects/ghost/import", files=data)
    assert response.status_code == 404
    assert "ghost" in response.json()["detail"]


def test_import_unsupported_format(client_with_projects: TestClient) -> None:
    name = client_with_projects.get("/projects").json()["projects"][0]["name"]
    data = {"file": ("novel.pdf", BytesIO(b"%PDF fake"), "application/pdf")}
    response = client_with_projects.post(f"/projects/{name}/import", files=data)
    assert response.status_code == 422


def test_import_volume_happy_path(client_with_projects: TestClient) -> None:
    name = client_with_projects.get("/projects").json()["projects"][0]["name"]
    fixtures = Path(__file__).parent.parent.parent / "fixtures"
    epubs = list(fixtures.glob("*.epub"))
    if not epubs:
        pytest.skip("no EPUB fixture available")

    epub_bytes = epubs[0].read_bytes()
    data = {"file": (epubs[0].name, BytesIO(epub_bytes), "application/epub+zip")}
    response = client_with_projects.post(f"/projects/{name}/import", files=data)
    assert response.status_code == 201
    body = response.json()
    assert body["volume_id"] >= 1
    assert isinstance(body["volume_title"], str)
    assert body["chapter_count"] >= 0
    assert body["segment_count"] >= 0
    assert "glossary_candidate_count" in body


def test_import_response_shape(client_with_projects: TestClient) -> None:
    name = client_with_projects.get("/projects").json()["projects"][0]["name"]
    fixtures = Path(__file__).parent.parent.parent / "fixtures"
    epubs = list(fixtures.glob("*.epub"))
    if not epubs:
        pytest.skip("no EPUB fixture available")

    epub_bytes = epubs[0].read_bytes()
    data = {"file": (epubs[0].name, BytesIO(epub_bytes), "application/epub+zip")}
    body = client_with_projects.post(f"/projects/{name}/import", files=data).json()
    required = {
        "volume_id",
        "volume_title",
        "chapter_count",
        "segment_count",
        "glossary_candidate_count",
    }
    assert required <= body.keys()


def test_import_increments_volume_count(client_with_projects: TestClient) -> None:
    name = client_with_projects.get("/projects").json()["projects"][0]["name"]
    fixtures = Path(__file__).parent.parent.parent / "fixtures"
    epubs = list(fixtures.glob("*.epub"))
    if not epubs:
        pytest.skip("no EPUB fixture available")

    before = client_with_projects.get("/projects").json()["projects"][0]["volume_count"]

    epub_bytes = epubs[0].read_bytes()
    data = {"file": (epubs[0].name, BytesIO(epub_bytes), "application/epub+zip")}
    r = client_with_projects.post(f"/projects/{name}/import", files=data)
    assert r.status_code == 201

    after = client_with_projects.get("/projects").json()["projects"][0]["volume_count"]
    assert after == before + 1
