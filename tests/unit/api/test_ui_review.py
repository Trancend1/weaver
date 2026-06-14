"""Tests for the review status UI routes (Sprint P3, WV-003)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from weaver.api.app import create_api_app
from weaver.services.project import initialize_project
from weaver.storage.db import connect_database, connect_readonly_database, transaction
from weaver.storage.segments import update_segment_status
from weaver.storage.translations import record_translation

SOURCE = """第一章 テスト

最初の段落の説明文。

二番目の段落の説明文。
"""


def _chapter_and_segments(db_path: Path) -> tuple[str, list[tuple[str, str]]]:
    with connect_readonly_database(db_path) as connection:
        chapter_id = str(
            connection.execute("SELECT id FROM chapters ORDER BY spine_order").fetchone()["id"]
        )
        segments = [
            (str(row["id"]), str(row["source_hash"]))
            for row in connection.execute(
                "SELECT id, source_hash FROM segments WHERE chapter_id = ? ORDER BY block_order",
                (chapter_id,),
            ).fetchall()
        ]
    return chapter_id, segments


def _volume_id(db_path: Path) -> int:
    with connect_readonly_database(db_path) as connection:
        return int(connection.execute("SELECT id FROM volumes ORDER BY id").fetchone()["id"])


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


def test_workspace_review_pills_use_optimistic_scheme(review_client: TestClient) -> None:
    """Workspace pills update the badge in JS + POST with hx-swap='none' (no fragment swap).

    Regression: the old ``hx-target="#seg-statusline" hx-swap="outerHTML"`` swap failed to
    paint live in the browser (badge vanished until reload). The new scheme paints
    optimistically from data-* attrs and posts in the background.
    """
    name = _name(review_client)
    chapter_id = _first_chapter_id(review_client, name)
    page = review_client.get(f"/ui/projects/{name}/chapters/{chapter_id}").text
    assert 'data-review-status="approved"' in page
    assert 'data-review-label="Reviewed"' in page
    assert 'hx-swap="none"' in page
    # pills must no longer drive a fragile statusline outerHTML swap
    assert 'hx-target="#seg-statusline-' not in page
    assert "function applyReview" in page


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


def test_review_queue_inline_actions_target_cell_not_row(review_client: TestClient) -> None:
    """Queue Approve/Needs-revision must swap a review-badge cell, never the whole <tr>.

    Regression: the endpoint returns a ``<div class="seg-statusline">`` fragment; an
    ``hx-target="closest tr"`` outerHTML swap would replace the row's ``<tr>`` with a
    ``<div>`` and visually destroy the row. The fix targets a ``#qrev-<id>`` cell and
    uses ``hx-select=".seg-review-status"`` to graft only the review badge.
    """
    name = _name(review_client)
    volume_id = _first_volume_id(review_client, name)
    page = review_client.get(f"/ui/projects/{name}/volumes/{volume_id}/review").text
    assert 'hx-target="closest tr"' not in page  # the row-destroying pattern is gone
    assert 'id="qrev-' in page
    assert 'hx-select=".seg-review-status"' in page
    # the badge carries a human label (the raw enum only survives inside the CSS class)
    assert "Not reviewed" in page


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


def test_empty_state_nothing_ready_when_nothing_translated(tmp_path: Path) -> None:
    # No translations exist yet; filtering to an empty result must explain that
    # nothing is reviewable, not that a filter merely hid matches.
    src = tmp_path / "book.txt"
    src.write_text(SOURCE, encoding="utf-8")
    result = initialize_project(src, cwd=tmp_path, provider="fake")
    volume_id = _volume_id(result.database_path)
    client = TestClient(create_api_app(tmp_path))
    name = _name(client)

    page = client.get(
        f"/ui/projects/{name}/volumes/{volume_id}/review?status_filter=approved"
    ).text
    assert "Nothing ready for review yet" in page


def test_empty_state_all_handled_when_reviewable_all_resolved(tmp_path: Path) -> None:
    src = tmp_path / "book.txt"
    src.write_text(SOURCE, encoding="utf-8")
    result = initialize_project(src, cwd=tmp_path, provider="fake")
    _, segments = _chapter_and_segments(result.database_path)
    volume_id = _volume_id(result.database_path)
    with connect_database(result.database_path) as connection, transaction(connection):
        for seg_id, source_hash in segments:
            record_translation(
                connection,
                segment_id=seg_id,
                text="A reviewed English sentence.",
                source_hash=source_hash,
                provider="fake",
                model="fake",
            )
            update_segment_status(connection, segment_id=seg_id, status="translated")
    client = TestClient(create_api_app(tmp_path))
    name = _name(client)
    for seg_id, _ in segments:
        client.post(f"/ui/projects/{name}/segments/{seg_id}/review?review_status=approved")

    # Every reviewable segment is approved, so the "needs revision" filter is empty
    # for the right reason.
    page = client.get(
        f"/ui/projects/{name}/volumes/{volume_id}/review?status_filter=needs_revision"
    ).text
    assert "All reviewable segments are handled" in page


def test_empty_state_filter_no_match_when_reviewable_unhandled(tmp_path: Path) -> None:
    src = tmp_path / "book.txt"
    src.write_text(SOURCE, encoding="utf-8")
    result = initialize_project(src, cwd=tmp_path, provider="fake")
    _, segments = _chapter_and_segments(result.database_path)
    volume_id = _volume_id(result.database_path)
    with connect_database(result.database_path) as connection, transaction(connection):
        seg_id, source_hash = segments[0]
        record_translation(
            connection,
            segment_id=seg_id,
            text="A pending-review English sentence.",
            source_hash=source_hash,
            provider="fake",
            model="fake",
        )
        update_segment_status(connection, segment_id=seg_id, status="translated")
    client = TestClient(create_api_app(tmp_path))
    name = _name(client)

    # There is reviewable, still-unhandled content; the approved filter is simply
    # not matched yet.
    page = client.get(
        f"/ui/projects/{name}/volumes/{volume_id}/review?status_filter=approved"
    ).text
    assert "No segments match this review filter" in page


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
