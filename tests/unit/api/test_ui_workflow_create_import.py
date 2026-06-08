"""Tests for the FastAPI UI create/import + browser (Stage 11B-1)."""

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


def _with_project(tmp_path: Path) -> tuple[TestClient, str]:
    from weaver.services.project import initialize_project

    epub = _fixture_epub()
    initialize_project(epub, cwd=tmp_path)
    return TestClient(create_api_app(tmp_path)), epub.stem


# --- new-project page + browser ---------------------------------------------


def test_new_page_renders(tmp_path: Path) -> None:
    client = TestClient(create_api_app(tmp_path))
    r = client.get("/ui/new")
    assert r.status_code == 200
    assert "Create a project" in r.text
    assert 'name="project_name"' in r.text
    assert 'hx-get="/ui/browse' not in r.text


def test_browse_fragment_lists_sources(tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()
    (tmp_path / "book.txt").write_text("hi", encoding="utf-8")
    client = TestClient(create_api_app(tmp_path))
    r = client.get("/ui/browse", params={"dir": ""})
    assert r.status_code == 200
    assert "book.txt" in r.text
    assert "📁 sub/" in r.text or "sub/" in r.text
    # a "use" button wires the hidden source_path field
    assert "source_path" in r.text


def test_browse_fragment_traversal_shows_error(tmp_path: Path) -> None:
    client = TestClient(create_api_app(tmp_path))
    r = client.get("/ui/browse", params={"dir": "../.."})
    assert r.status_code == 200
    assert "escapes" in r.text.lower() or "error" in r.text.lower()


# --- create (POST /ui/new) --------------------------------------------------


def test_create_via_upload_redirects(tmp_path: Path) -> None:
    epub = _fixture_epub()
    client = TestClient(create_api_app(tmp_path))
    data = {"file": (epub.name, BytesIO(epub.read_bytes()), "application/epub+zip")}
    r = client.post("/ui/new", files=data, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == f"/ui/projects/{epub.stem}"
    # project now visible on the dashboard
    assert epub.stem in client.get("/ui").text


def test_create_via_browsed_path_redirects(tmp_path: Path) -> None:
    epub = _fixture_epub()
    (tmp_path / epub.name).write_bytes(epub.read_bytes())
    client = TestClient(create_api_app(tmp_path))
    r = client.post("/ui/new", data={"source_path": epub.name}, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == f"/ui/projects/{epub.stem}"


def test_create_no_name_rerenders_with_error(tmp_path: Path) -> None:
    client = TestClient(create_api_app(tmp_path))
    r = client.post("/ui/new", data={})
    assert r.status_code == 400
    assert "Create a project" in r.text
    assert "Project name is required" in r.text


def test_create_empty_project_redirects_to_empty_state(tmp_path: Path) -> None:
    client = TestClient(create_api_app(tmp_path))
    r = client.post("/ui/new", data={"project_name": "demo"}, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/ui/projects/demo"
    page = client.get("/ui/projects/demo")
    assert page.status_code == 200
    assert "No volumes yet" in page.text
    assert "Import first volume" in page.text


def test_create_duplicate_rerenders_with_error(tmp_path: Path) -> None:
    client, name = _with_project(tmp_path)
    r = client.post("/ui/new", data={"project_name": name})
    assert r.status_code == 400
    assert "already exists" in r.text


# --- import (POST /ui/projects/{name}/import) -------------------------------


def test_import_returns_refreshed_tree(tmp_path: Path) -> None:
    client, name = _with_project(tmp_path)
    before = client.get("/projects").json()["projects"][0]["volume_count"]

    epub = _fixture_epub()
    data = {"file": (epub.name, BytesIO(epub.read_bytes()), "application/epub+zip")}
    r = client.post(f"/ui/projects/{name}/import", files=data)
    assert r.status_code == 200
    assert 'id="tree"' in r.text  # the refreshed tree fragment

    after = client.get("/projects").json()["projects"][0]["volume_count"]
    assert after == before + 1


def test_import_unknown_project_error_fragment(tmp_path: Path) -> None:
    client = TestClient(create_api_app(tmp_path))
    epub = _fixture_epub()
    data = {"file": (epub.name, BytesIO(epub.read_bytes()), "application/epub+zip")}
    r = client.post("/ui/projects/ghost/import", files=data)
    assert r.status_code == 200  # HTMX-swappable fragment
    assert r.headers.get("HX-Retarget") == "#import_error"
    assert "ghost" in r.text


def test_import_no_source_error_fragment(tmp_path: Path) -> None:
    client, name = _with_project(tmp_path)
    r = client.post(f"/ui/projects/{name}/import", data={})
    assert r.status_code == 200
    assert r.headers.get("HX-Retarget") == "#import_error"
    assert "Import failed" in r.text


# --- JSON create unchanged after the service extraction ---------------------


def test_json_create_still_works(tmp_path: Path) -> None:
    epub = _fixture_epub()
    client = TestClient(create_api_app(tmp_path))
    data = {"file": (epub.name, BytesIO(epub.read_bytes()), "application/epub+zip")}
    r = client.post("/projects/create", files=data)
    assert r.status_code == 201
    assert r.json()["project_name"] == epub.stem
