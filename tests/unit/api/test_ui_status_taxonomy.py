"""Tests for status taxonomy consistency across UI surfaces (Sprint P6, WV-006)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from weaver.api.app import create_api_app
from weaver.api.status_labels import (
    REVIEW_LABELS,
    TRANSLATION_LABELS,
    badge_class_for_review,
    badge_class_for_translation,
    job_status_label,
    review_status_label,
    translation_status_label,
)
from weaver.services.project import initialize_project


@pytest.fixture
def tax_client(tmp_path: Path) -> TestClient:
    fixtures = Path(__file__).parent.parent.parent / "fixtures"
    epubs = list(fixtures.glob("*.epub"))
    if not epubs:
        pytest.skip("no EPUB fixture available")
    initialize_project(epubs[0], cwd=tmp_path)
    return TestClient(create_api_app(tmp_path))


def _name(client: TestClient) -> str:
    return client.get("/projects").json()["projects"][0]["name"]


def _first_chapter_id(client: TestClient, name: str) -> str:
    return client.get(f"/projects/{name}/tree").json()["volumes"][0]["chapters"][0]["id"]


# ---- translation status labels ---------------------------------------------


def test_translation_status_label_maps_all_db_values() -> None:
    assert translation_status_label("pending") == "Untranslated"
    assert translation_status_label("in_progress") == "Translating"
    assert translation_status_label("translated") == "Translated"
    assert translation_status_label("manual") == "Manual"
    assert translation_status_label("failed") == "Failed"
    assert translation_status_label("stale") == "Stale"
    assert translation_status_label("skipped") == "Skipped"
    assert translation_status_label("unknown") == "unknown"


def test_badge_class_for_translation() -> None:
    assert badge_class_for_translation("translated") == "ok"
    assert badge_class_for_translation("manual") == "ok"
    assert badge_class_for_translation("failed") == "bad"
    assert badge_class_for_translation("stale") == "bad"
    assert badge_class_for_translation("in_progress") == "warn"
    assert badge_class_for_translation("pending") == ""


def test_workspace_shows_canonical_translation_labels(tax_client: TestClient) -> None:
    name = _name(tax_client)
    chapter_id = _first_chapter_id(tax_client, name)
    page = tax_client.get(f"/ui/projects/{name}/chapters/{chapter_id}").text

    # default fixture segments are pending → should display "Untranslated", not raw "pending"
    assert "Untranslated" in page
    assert "Needs translation" in page

    # raw DB strings that should NOT appear as user-facing badges
    assert '<span class="badge c-badge seg-status seg-status--pending ">pending</span>' not in page
    # the old dead branch strings must be gone
    assert "Translation memory reuse" not in page


def test_reading_preview_shows_canonical_labels(tax_client: TestClient) -> None:
    name = _name(tax_client)
    chapter_id = _first_chapter_id(tax_client, name)
    page = tax_client.get(f"/ui/projects/{name}/chapters/{chapter_id}/preview?mode=compare").text
    assert "Untranslated" in page
    assert "pending</span>" not in page


# ---- job status labels -----------------------------------------------------


def test_job_status_label_maps_all_db_values() -> None:
    assert job_status_label("queued") == "Waiting"
    assert job_status_label("running") == "Processing"
    assert job_status_label("done") == "Completed"
    assert job_status_label("cancelled") == "Cancelled"
    assert job_status_label("failed") == "Failed"
    assert job_status_label("unknown") == "unknown"


def test_ui_job_panel_uses_canonical_labels(tax_client: TestClient) -> None:
    """After translating, the job detail/badge should show canonical labels."""
    name = _name(tax_client)
    chapter_id = _first_chapter_id(tax_client, name)
    tax_client.post(f"/ui/projects/{name}/chapters/{chapter_id}/translate")
    page = tax_client.get(f"/ui/projects/{name}/chapters/{chapter_id}").text
    # job panel should not show raw 'done' label; likely shows 'Completed' or 'Processing'
    assert '<span class="badge c-badge ">done</span>' not in page


# ---- review status labels (WV-003 axis) ------------------------------------


def test_review_status_label_maps_all_db_values() -> None:
    assert review_status_label("not_reviewed") == "Not reviewed"
    assert review_status_label("needs_review") == "Needs review"
    assert review_status_label("needs_revision") == "Needs revision"
    assert review_status_label("approved") == "Reviewed"
    assert review_status_label("rejected") == "Rejected"
    assert review_status_label("unknown") == "unknown"


def test_badge_class_for_review() -> None:
    assert badge_class_for_review("approved") == "ok"
    assert badge_class_for_review("needs_revision") == "bad"
    assert badge_class_for_review("rejected") == "bad"
    assert badge_class_for_review("needs_review") == "warn"
    assert badge_class_for_review("not_reviewed") == ""


def test_review_status_badge_is_human_labelled_not_raw(tax_client: TestClient) -> None:
    """The review badge shows a human label + color class, never the raw enum."""
    name = _name(tax_client)
    chapter_id = _first_chapter_id(tax_client, name)
    page = tax_client.get(f"/ui/projects/{name}/chapters/{chapter_id}").text
    # default review status is not_reviewed → "Not reviewed", never bare ">not_reviewed<"
    assert "Not reviewed" in page
    assert ">not_reviewed<" not in page
    # the three review pills carry an aria-pressed state for active reflection
    assert "aria-pressed=" in page


# ---- dead branches ---------------------------------------------------------


def test_no_dead_status_branches_in_templates() -> None:
    """No template references segment statuses the DB cannot produce (reused/tm/memory)."""
    templates_dir = Path(__file__).parent.parent.parent.parent / "src/weaver/api/templates"
    assert templates_dir.exists()
    # pattern: a comparison involving status and the dead words
    dead = re.compile(r"status\s*(==|in)\s*.*\b(reused|tm|memory)\b")
    bad_files: list[str] = []
    for path in templates_dir.rglob("*.html"):
        text = path.read_text(encoding="utf-8")
        # strip Jinja comments (simple)
        stripped = "\n".join(
            line for line in text.splitlines() if not line.strip().startswith("{#")
        )
        if dead.search(stripped):
            bad_files.append(str(path.relative_to(templates_dir.parent.parent)))
    assert not bad_files, f"Dead status branches found in: {bad_files}"


# ---- taxonomy keys never drift ---------------------------------------------


def test_translation_labels_cover_db_check_constraint() -> None:
    """Every status in schema.sql CHECK must have a presentation label."""
    db_statuses = {"pending", "in_progress", "translated", "failed", "stale", "skipped", "manual"}
    assert db_statuses <= set(TRANSLATION_LABELS.keys())


def test_review_labels_cover_canonical_review_statuses() -> None:
    """Every canonical review status has a presentation label."""
    from weaver.services.segment_review import _REVIEW_STATUSES

    assert set(_REVIEW_STATUSES) <= set(REVIEW_LABELS.keys())
