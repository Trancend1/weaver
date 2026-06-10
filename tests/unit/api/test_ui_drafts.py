"""UI (HTMX) character-draft generation tests — Sprint P / WV-001 (P1b).

Covers the new in-cockpit "Generate character draft" action: the chapter
picker renders, a chapter with character-page text produces an inline draft
card, and a chapter without it yields a safe "no content" notice. The draft
service is deterministic XHTML text extraction (no provider, no OCR), so a
character page is seeded as a segment rather than mocked.
"""

from __future__ import annotations

from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from weaver.api.app import create_api_app
from weaver.services.project import initialize_project
from weaver.services.project_paths import resolve_database_path
from weaver.services.project_tree import project_tree
from weaver.storage.db import connect_database, transaction
from weaver.storage.segments import insert_segment

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
FIXTURE_EPUB = FIXTURES / "aozora_sample.epub"

# Shape the character-page extractor recognizes (see test_character_draft.py).
CHARACTER_PAGE_TEXT = "名前: エリナ\n年齢: 18\n性別: 女性\nA young elven mage from the village."


def _project_name(tmp_path: Path) -> str:
    weaver_dir = tmp_path / ".weaver"
    for p in weaver_dir.iterdir():
        if p.is_dir() and (p / "project.toml").exists():
            return p.name
    return "unknown"


@pytest.fixture
def project(tmp_path: Path):
    init = initialize_project(FIXTURE_EPUB, cwd=tmp_path, provider="fake")
    tree = project_tree(init.project_toml, cwd=tmp_path)
    chapter_id = tree.volumes[0].chapters[0].id
    db_path = resolve_database_path(init.project_toml, cwd=tmp_path)
    client = TestClient(create_api_app(tmp_path))
    return client, _project_name(tmp_path), chapter_id, db_path


def _seed_character_segment(db_path: Path, chapter_id: str) -> None:
    with closing(connect_database(db_path)) as conn, transaction(conn):
        insert_segment(
            conn,
            segment_id="seg-char-test",
            chapter_id=chapter_id,
            block_order=9999,
            kind="paragraph",
            source_text=CHARACTER_PAGE_TEXT,
            source_hash="charpagehash",
        )


def test_drafts_page_renders_chapter_picker(project):
    client, name, _, _ = project
    resp = client.get(f"/ui/projects/{name}/character-drafts")
    assert resp.status_code == 200
    body = resp.text
    assert 'name="chapter_id"' in body
    assert "Generate character draft" in body
    assert "<option" in body


def test_generate_renders_draft_card_with_provenance(project):
    client, name, chapter_id, db_path = project
    _seed_character_segment(db_path, chapter_id)

    resp = client.post(f"/ui/projects/{name}/drafts/generate", data={"chapter_id": chapter_id})
    assert resp.status_code == 200
    body = resp.text
    assert "draft-card" in body
    assert "Provenance" in body


def test_generate_no_content_renders_safe_notice(project):
    client, name, _, _ = project
    # A chapter with no extractable character text (here: no such chapter, so no
    # segments) yields the calm notice rather than a draft or a 500.
    resp = client.post(
        f"/ui/projects/{name}/drafts/generate", data={"chapter_id": "no-such-chapter"}
    )
    assert resp.status_code == 200
    assert "No character page content detected" in resp.text


def test_generate_missing_chapter_id_is_unprocessable(project):
    client, name, _, _ = project
    resp = client.post(f"/ui/projects/{name}/drafts/generate", data={})
    # Required form field missing -> 422 from validation, not a 500.
    assert resp.status_code == 422
