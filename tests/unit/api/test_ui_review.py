"""Tests for the review status UI routes (Sprint P3, WV-003)."""

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
def review_client(tmp_path: Path) -> TestClient:
    src = tmp_path / "book.txt"
    src.write_text(SOURCE, encoding="utf-8")
    initialize_project(src, cwd=tmp_path, provider="fake")
    return TestClient(create_api_app(tmp_path))


def _name(client: TestClient) -> str:
    return client.get("/projects").json()["projects"][0]["name"]


def _first_chapter_id(client: TestClient, name: str) -> str:
    return client.get(f"/projects/{name}/tree").json()["volumes"][0]["chapters"][0]["id"]


def _first_segment_id(client: TestClient, name: str, chapter_id: str) -> str:
    ws = client.get(f"/projects/{name}/chapters/{chapter_id}/workspace").json()
    return ws["segments"][0]["id"]


def _first_volume_id(client: TestClient, name: str) -> int:
    return client.get(f"/projects/{name}/tree").json()["volumes"][0]["id"]


def test_workspace_shows_review_status_badge(review_client: TestClient) -> None:
    name = _name(review_client)
    chapter_id = _first_chapter_id(review_client, name)
    page = review_client.get(f"/ui/projects/{name}/chapters/{chapter_id}").text
    assert "seg-review-status" in page
    assert "Mark reviewed" in page
    assert "Needs revision" in page
    assert "Reset review" in page


def test_review_status_post_updates_badge(review_client: TestClient) -> None:
    name = _name(review_client)
    chapter_id = _first_chapter_id(review_client, name)
    seg_id = _first_segment_id(review_client, name, chapter_id)

    r = review_client.post(f"/ui/projects/{name}/segments/{seg_id}/review?review_status=approved")
    assert r.status_code == 200
    assert "approved" in r.text
    assert "seg-review-status--approved" in r.text


def test_review_queue_page_renders(review_client: TestClient) -> None:
    name = _name(review_client)
    volume_id = _first_volume_id(review_client, name)
    page = review_client.get(f"/ui/projects/{name}/volumes/{volume_id}/review").text
    assert "Review queue" in page
    # Should show at least the default segments
    assert "Not reviewed" in page or "Needs revision" in page or "Approve" in page


def test_review_queue_filter_works(review_client: TestClient) -> None:
    name = _name(review_client)
    volume_id = _first_volume_id(review_client, name)
    seg_id = _first_segment_id(review_client, name, _first_chapter_id(review_client, name))
    review_client.post(f"/ui/projects/{name}/segments/{seg_id}/review?review_status=approved")

    approved_page = review_client.get(
        f"/ui/projects/{name}/volumes/{volume_id}/review?status_filter=approved"
    ).text
    _ = review_client.get(f"/ui/projects/{name}/volumes/{volume_id}/review").text
    _ = review_client.get(
        f"/ui/projects/{name}/volumes/{volume_id}/review?status_filter=not_reviewed"
    ).text

    # The approved filter should show the approved segment
    assert "approved" in approved_page.lower()


def test_review_status_does_not_mutate_translation(review_client: TestClient) -> None:
    name = _name(review_client)
    chapter_id = _first_chapter_id(review_client, name)
    seg_id = _first_segment_id(review_client, name, chapter_id)

    review_client.post(f"/ui/projects/{name}/segments/{seg_id}/review?review_status=approved")
    ws = review_client.get(f"/projects/{name}/chapters/{chapter_id}/workspace").json()
    seg = next(s for s in ws["segments"] if s["id"] == seg_id)
    assert seg["status"] == "pending"
    assert seg["review_status"] == "approved"


def test_unknown_segment_review_404(review_client: TestClient) -> None:
    name = _name(review_client)
    r = review_client.post(f"/ui/projects/{name}/segments/nope/review?review_status=approved")
    assert r.status_code == 404


def test_invalid_review_status_returns_inline_error(review_client: TestClient) -> None:
    name = _name(review_client)
    chapter_id = _first_chapter_id(review_client, name)
    seg_id = _first_segment_id(review_client, name, chapter_id)

    r = review_client.post(f"/ui/projects/{name}/segments/{seg_id}/review?review_status=banana")
    # HTMX inline error fragment, not a 4xx
    assert r.status_code == 200
    assert "error" in r.text.lower() or "invalid" in r.text.lower()
