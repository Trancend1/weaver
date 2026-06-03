"""Tests for the FastAPI workspace UI: read, save, history (Stage 11B-2)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from weaver.api.app import create_api_app


@pytest.fixture
def ws_client(tmp_path: Path) -> TestClient:
    from weaver.services.project import initialize_project

    fixtures = Path(__file__).parent.parent.parent / "fixtures"
    epubs = list(fixtures.glob("*.epub"))
    if not epubs:
        pytest.skip("no EPUB fixture available")
    initialize_project(epubs[0], cwd=tmp_path)
    return TestClient(create_api_app(tmp_path))


def _name(client: TestClient) -> str:
    return client.get("/projects").json()["projects"][0]["name"]


def _first_chapter_id(client: TestClient, name: str) -> str:
    tree = client.get(f"/projects/{name}/tree").json()
    return tree["volumes"][0]["chapters"][0]["id"]


def _first_segment_id(client: TestClient, name: str, chapter_id: str) -> str:
    ws = client.get(f"/projects/{name}/chapters/{chapter_id}/workspace").json()
    return ws["segments"][0]["id"]


# --- read -------------------------------------------------------------------


def test_tree_links_to_workspace(ws_client: TestClient) -> None:
    name = _name(ws_client)
    chapter_id = _first_chapter_id(ws_client, name)
    page = ws_client.get(f"/ui/projects/{name}").text
    assert f"/ui/projects/{name}/chapters/{chapter_id}" in page


def test_workspace_renders_segments(ws_client: TestClient) -> None:
    name = _name(ws_client)
    chapter_id = _first_chapter_id(ws_client, name)
    r = ws_client.get(f"/ui/projects/{name}/chapters/{chapter_id}")
    assert r.status_code == 200
    assert "Source (JP)" in r.text and "Translation (EN)" in r.text
    # one editable translation field per segment
    seg_id = _first_segment_id(ws_client, name, chapter_id)
    assert f'id="seg-{seg_id}"' in r.text
    assert 'name="translated_text"' in r.text


def test_workspace_unknown_chapter_404(ws_client: TestClient) -> None:
    name = _name(ws_client)
    r = ws_client.get(f"/ui/projects/{name}/chapters/nope")
    assert r.status_code == 404
    assert "Not found" in r.text


# --- save -------------------------------------------------------------------


def test_save_updates_translation_and_shows_state(ws_client: TestClient) -> None:
    name = _name(ws_client)
    chapter_id = _first_chapter_id(ws_client, name)
    seg_id = _first_segment_id(ws_client, name, chapter_id)

    r = ws_client.post(
        f"/ui/projects/{name}/chapters/{chapter_id}/segments/{seg_id}",
        data={"translated_text": "MY MANUAL EN"},
    )
    assert r.status_code == 200
    assert "MY MANUAL EN" in r.text
    assert "Saved" in r.text
    assert "manual" in r.text

    # persisted in the JSON workspace
    ws = ws_client.get(f"/projects/{name}/chapters/{chapter_id}/workspace").json()
    seg = next(s for s in ws["segments"] if s["id"] == seg_id)
    assert seg["translated_text"] == "MY MANUAL EN"
    assert seg["status"] == "manual"


def test_manual_edit_survives_refresh(ws_client: TestClient) -> None:
    name = _name(ws_client)
    chapter_id = _first_chapter_id(ws_client, name)
    seg_id = _first_segment_id(ws_client, name, chapter_id)
    ws_client.post(
        f"/ui/projects/{name}/chapters/{chapter_id}/segments/{seg_id}",
        data={"translated_text": "PERSIST ME"},
    )
    # reload the whole workspace page
    page = ws_client.get(f"/ui/projects/{name}/chapters/{chapter_id}").text
    assert "PERSIST ME" in page


def test_save_empty_text_shows_error(ws_client: TestClient) -> None:
    name = _name(ws_client)
    chapter_id = _first_chapter_id(ws_client, name)
    seg_id = _first_segment_id(ws_client, name, chapter_id)
    r = ws_client.post(
        f"/ui/projects/{name}/chapters/{chapter_id}/segments/{seg_id}",
        data={"translated_text": "   "},
    )
    # service rejects empty/whitespace; the row re-renders with an error, not a 500
    assert r.status_code == 200
    assert f'id="seg-{seg_id}"' in r.text


# --- history ----------------------------------------------------------------


def test_history_shows_attempts_after_save(ws_client: TestClient) -> None:
    name = _name(ws_client)
    chapter_id = _first_chapter_id(ws_client, name)
    seg_id = _first_segment_id(ws_client, name, chapter_id)
    ws_client.post(
        f"/ui/projects/{name}/chapters/{chapter_id}/segments/{seg_id}",
        data={"translated_text": "ATTEMPT ONE"},
    )
    r = ws_client.get(f"/ui/projects/{name}/chapters/{chapter_id}/segments/{seg_id}/history")
    assert r.status_code == 200
    assert "ATTEMPT ONE" in r.text
    assert "attempt" in r.text.lower()


def test_history_unknown_segment_404(ws_client: TestClient) -> None:
    name = _name(ws_client)
    chapter_id = _first_chapter_id(ws_client, name)
    r = ws_client.get(f"/ui/projects/{name}/chapters/{chapter_id}/segments/ghost/history")
    assert r.status_code == 404


# --- volume-scoped chapter ids work through the UI (11B-1.5 guard) ----------


def test_workspace_works_for_second_duplicate_volume(ws_client: TestClient) -> None:
    name = _name(ws_client)
    fixtures = Path(__file__).parent.parent.parent / "fixtures"
    epub = next(fixtures.glob("*.epub"))
    from io import BytesIO

    data = {"file": (epub.name, BytesIO(epub.read_bytes()), "application/epub+zip")}
    assert ws_client.post(f"/projects/{name}/import", files=data).status_code == 201

    tree = ws_client.get(f"/projects/{name}/tree").json()
    assert len(tree["volumes"]) == 2
    # both volumes' chapters are independently openable (distinct scoped ids)
    for volume in tree["volumes"]:
        chapter_id = volume["chapters"][0]["id"]
        r = ws_client.get(f"/ui/projects/{name}/chapters/{chapter_id}")
        assert r.status_code == 200
        assert "Source (JP)" in r.text
