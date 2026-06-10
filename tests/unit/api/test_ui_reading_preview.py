"""Tests for the reading preview UI routes (Sprint P2 — WV-002)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from weaver.api.app import create_api_app
from weaver.services.project import initialize_project

SOURCE = """第一章 テスト

最初の段落の説明文。

二番目の段落の説明文。
"""


@pytest.fixture
def preview_client(tmp_path: Path) -> TestClient:
    src = tmp_path / "book.txt"
    src.write_text(SOURCE, encoding="utf-8")
    initialize_project(src, cwd=tmp_path, provider="fake")
    return TestClient(create_api_app(tmp_path))


def _name(client: TestClient) -> str:
    return client.get("/projects").json()["projects"][0]["name"]


def _first_chapter_id(client: TestClient, name: str) -> str:
    tree = client.get(f"/projects/{name}/tree").json()
    return tree["volumes"][0]["chapters"][0]["id"]


def _first_volume_id(client: TestClient, name: str) -> int:
    tree = client.get(f"/projects/{name}/tree").json()
    return tree["volumes"][0]["id"]


def _translate_first_segment(client: TestClient, name: str, chapter_id: str) -> None:
    seg_id = client.get(f"/projects/{name}/chapters/{chapter_id}/workspace").json()["segments"][0][
        "id"
    ]
    client.post(
        f"/ui/projects/{name}/chapters/{chapter_id}/segments/{seg_id}",
        data={"translated_text": "English paragraph one."},
    )


def test_chapter_reading_preview_renders(preview_client: TestClient) -> None:
    name = _name(preview_client)
    chapter_id = _first_chapter_id(preview_client, name)
    r = preview_client.get(f"/ui/projects/{name}/chapters/{chapter_id}/preview")
    assert r.status_code == 200
    assert "Reading preview" in r.text


def test_volume_reading_preview_renders(preview_client: TestClient) -> None:
    name = _name(preview_client)
    volume_id = _first_volume_id(preview_client, name)
    r = preview_client.get(f"/ui/projects/{name}/volumes/{volume_id}/preview")
    assert r.status_code == 200
    assert "Reading preview" in r.text


def test_compare_mode_shows_source_and_translation(preview_client: TestClient) -> None:
    name = _name(preview_client)
    chapter_id = _first_chapter_id(preview_client, name)
    _translate_first_segment(preview_client, name, chapter_id)
    r = preview_client.get(f"/ui/projects/{name}/chapters/{chapter_id}/preview?mode=compare")
    assert r.status_code == 200
    assert "Source (JP)" in r.text
    assert "Translation (EN)" in r.text
    assert "English paragraph one." in r.text


def test_structure_mode_link_for_volume(preview_client: TestClient) -> None:
    name = _name(preview_client)
    volume_id = _first_volume_id(preview_client, name)
    r = preview_client.get(f"/ui/projects/{name}/volumes/{volume_id}/preview")
    assert r.status_code == 200
    assert f"/ui/projects/{name}/volumes/{volume_id}/structure" in r.text


def test_no_files_written_during_preview(preview_client: TestClient, tmp_path: Path) -> None:
    name = _name(preview_client)
    chapter_id = _first_chapter_id(preview_client, name)
    output_dir = tmp_path / "book" / "output"
    before = set(output_dir.iterdir()) if output_dir.exists() else set()
    preview_client.get(f"/ui/projects/{name}/chapters/{chapter_id}/preview")
    after = set(output_dir.iterdir()) if output_dir.exists() else set()
    assert before == after


def test_navigation_links_project_scoped(preview_client: TestClient) -> None:
    name = _name(preview_client)
    chapter_id = _first_chapter_id(preview_client, name)
    r = preview_client.get(f"/ui/projects/{name}/chapters/{chapter_id}/preview")
    assert r.status_code == 200
    assert f'href="/ui/projects/{name}"' in r.text
    assert f'href="/ui/projects/{name}/chapters/{chapter_id}"' in r.text
    assert f'href="/ui/projects/{name}/qa"' in r.text
    assert f'href="/ui/projects/{name}/export/preflight"' in r.text


def test_unknown_chapter_404(preview_client: TestClient) -> None:
    name = _name(preview_client)
    r = preview_client.get(f"/ui/projects/{name}/chapters/nope/preview")
    assert r.status_code == 404


def test_unknown_volume_404(preview_client: TestClient) -> None:
    name = _name(preview_client)
    r = preview_client.get(f"/ui/projects/{name}/volumes/9999/preview")
    assert r.status_code == 404
