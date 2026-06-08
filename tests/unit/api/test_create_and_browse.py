"""Tests for GET /projects/browse and POST /projects/create (Sprint 10B)."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from weaver.api.app import create_api_app


def _fixture_epub() -> Path:
    fixtures = Path(__file__).parent.parent.parent / "fixtures"
    epubs = list(fixtures.glob("*.epub"))
    if not epubs:
        pytest.skip("no EPUB fixture available")
    return epubs[0]


# --- browse -----------------------------------------------------------------


def test_browse_root_lists_sources(tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()
    (tmp_path / "novel.txt").write_text("hi", encoding="utf-8")
    (tmp_path / "skip.md").write_text("x", encoding="utf-8")
    client = TestClient(create_api_app(tmp_path))

    body = client.get("/projects/browse").json()
    assert body["rel_dir"] == ""
    assert body["parent"] is None
    names = {e["name"] for e in body["entries"]}
    assert names == {"sub", "novel.txt"}


def test_browse_nested_dir(tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "vol1.txt").write_text("hi", encoding="utf-8")
    client = TestClient(create_api_app(tmp_path))

    body = client.get("/projects/browse", params={"dir": "sub"}).json()
    assert body["rel_dir"] == "sub"
    assert body["parent"] == ""
    assert [e["name"] for e in body["entries"]] == ["vol1.txt"]


def test_browse_traversal_rejected(tmp_path: Path) -> None:
    client = TestClient(create_api_app(tmp_path))
    assert client.get("/projects/browse", params={"dir": "../.."}).status_code == 422


def test_browse_missing_dir_rejected(tmp_path: Path) -> None:
    client = TestClient(create_api_app(tmp_path))
    assert client.get("/projects/browse", params={"dir": "ghost"}).status_code == 422


# --- create -----------------------------------------------------------------


def test_create_from_upload(tmp_path: Path) -> None:
    epub = _fixture_epub()
    client = TestClient(create_api_app(tmp_path))

    data = {"file": (epub.name, BytesIO(epub.read_bytes()), "application/epub+zip")}
    r = client.post("/projects/create", files=data)
    assert r.status_code == 201
    body = r.json()
    assert body["project_name"] == epub.stem
    assert body["chapter_count"] >= 0
    assert body["segment_count"] >= 0
    assert "glossary_candidate_count" in body

    # project is now discoverable
    listed = {p["name"] for p in client.get("/projects").json()["projects"]}
    assert epub.stem in listed


def test_create_from_browsed_path(tmp_path: Path) -> None:
    epub = _fixture_epub()
    (tmp_path / epub.name).write_bytes(epub.read_bytes())
    client = TestClient(create_api_app(tmp_path))

    r = client.post("/projects/create", data={"source_path": epub.name})
    assert r.status_code == 201
    assert r.json()["project_name"] == epub.stem


def test_create_empty_project(tmp_path: Path) -> None:
    client = TestClient(create_api_app(tmp_path))
    r = client.post("/projects/create", data={"project_name": "demo"})
    assert r.status_code == 201
    body = r.json()
    assert body["project_name"] == "demo"
    assert body["chapter_count"] == 0
    assert body["segment_count"] == 0
    tree = client.get("/projects/demo/tree").json()
    assert tree["project_name"] == "demo"
    assert tree["volumes"] == []


def test_import_first_volume_into_empty_project(tmp_path: Path) -> None:
    epub = _fixture_epub()
    client = TestClient(create_api_app(tmp_path))
    assert client.post("/projects/create", data={"project_name": "demo"}).status_code == 201

    data = {"file": (epub.name, BytesIO(epub.read_bytes()), "application/epub+zip")}
    r = client.post("/projects/demo/import", files=data)
    assert r.status_code == 201
    assert r.json()["volume_title"]
    tree = client.get("/projects/demo/tree").json()
    assert len(tree["volumes"]) == 1


def test_create_no_name_or_source_is_422(tmp_path: Path) -> None:
    client = TestClient(create_api_app(tmp_path))
    assert client.post("/projects/create").status_code == 422


def test_create_unsupported_upload_is_422(tmp_path: Path) -> None:
    client = TestClient(create_api_app(tmp_path))
    data = {"file": ("book.pdf", BytesIO(b"%PDF"), "application/pdf")}
    assert client.post("/projects/create", files=data).status_code == 422


def test_create_browsed_traversal_is_422(tmp_path: Path) -> None:
    client = TestClient(create_api_app(tmp_path))
    r = client.post("/projects/create", data={"source_path": "../../evil.epub"})
    assert r.status_code == 422


def test_create_duplicate_is_409(tmp_path: Path) -> None:
    epub = _fixture_epub()
    client = TestClient(create_api_app(tmp_path))
    data = {"file": (epub.name, BytesIO(epub.read_bytes()), "application/epub+zip")}
    assert client.post("/projects/create", files=data).status_code == 201
    again = {"file": (epub.name, BytesIO(epub.read_bytes()), "application/epub+zip")}
    assert client.post("/projects/create", files=again).status_code == 409


def test_create_invalid_provider_is_422(tmp_path: Path) -> None:
    epub = _fixture_epub()
    client = TestClient(create_api_app(tmp_path))
    data = {"file": (epub.name, BytesIO(epub.read_bytes()), "application/epub+zip")}
    r = client.post("/projects/create", files=data, data={"provider": "not-a-provider"})
    assert r.status_code == 422
