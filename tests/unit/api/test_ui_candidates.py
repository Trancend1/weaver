"""UI (HTMX) candidate-generation flow tests — Sprint P / WV-001.

Proves the review loop is closed *through the UI routes* (not just the JSON
API): generate → pending card → approve → apply writes a translation, with the
live translation untouched until apply. Uses ``FakeProvider`` (never a live LLM).
"""

from __future__ import annotations

import re
from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from weaver.api.app import create_api_app
from weaver.services.project import initialize_project
from weaver.services.project_paths import resolve_database_path
from weaver.services.project_tree import project_tree
from weaver.storage.db import connect_database
from weaver.storage.segments import list_chapter_segments
from weaver.storage.translations import get_latest_translation_text

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
FIXTURE_EPUB = FIXTURES / "aozora_sample.epub"


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
    with closing(connect_database(db_path)) as conn:
        segment_id = list_chapter_segments(conn, chapter_id=chapter_id)[0].id
    client = TestClient(create_api_app(tmp_path))
    return client, _project_name(tmp_path), chapter_id, segment_id, db_path


def _gen_url(name: str, chapter_id: str, segment_id: str) -> str:
    return f"/ui/projects/{name}/chapters/{chapter_id}/segments/{segment_id}/candidates/generate"


def _segment(db_path: Path, chapter_id: str, segment_id: str):
    with closing(connect_database(db_path)) as conn:
        for seg in list_chapter_segments(conn, chapter_id=chapter_id):
            if seg.id == segment_id:
                return seg
    raise AssertionError("segment vanished")


def _translation_text(db_path: Path, segment_id: str) -> str | None:
    with closing(connect_database(db_path)) as conn:
        return get_latest_translation_text(conn, segment_id=segment_id)


def test_generate_renders_pending_card_with_provenance(project):
    client, name, chapter_id, segment_id, _ = project
    resp = client.post(_gen_url(name, chapter_id, segment_id))
    assert resp.status_code == 200
    body = resp.text
    assert "candidate-card" in body
    assert "pending" in body
    # Provenance (provider/model + the provenance details block) is visible.
    assert "AI suggestion" in body
    assert "Provenance" in body


def test_generate_does_not_mutate_live_translation(project):
    client, name, chapter_id, segment_id, db_path = project
    before = _segment(db_path, chapter_id, segment_id)
    assert before.status == "pending"

    client.post(_gen_url(name, chapter_id, segment_id))

    # Generation must not touch the segment's status or live translation.
    assert _segment(db_path, chapter_id, segment_id).status == "pending"
    assert _translation_text(db_path, segment_id) is None


def test_generate_approve_apply_loop_writes_translation(project):
    client, name, chapter_id, segment_id, db_path = project

    gen = client.post(_gen_url(name, chapter_id, segment_id))
    assert gen.status_code == 200
    match = re.search(r'id="candidate-([^"]+)"', gen.text)
    assert match, "no candidate id in the rendered card"
    cid = match.group(1)

    approved = client.post(f"/ui/projects/{name}/candidates/{cid}/approve")
    assert approved.status_code == 200
    assert "approved" in approved.text

    applied = client.post(f"/ui/projects/{name}/candidates/{cid}/apply")
    assert applied.status_code == 200
    assert "applied" in applied.text

    # Apply promotes the candidate into the live translation (normal history).
    assert _segment(db_path, chapter_id, segment_id).status in ("translated", "manual")
    assert (_translation_text(db_path, segment_id) or "").strip()


def test_generate_missing_segment_renders_safe_error(project):
    client, name, chapter_id, _, _ = project
    resp = client.post(_gen_url(name, chapter_id, "does-not-exist"))
    # Safe inline fragment, not a 500.
    assert resp.status_code == 200
    assert "error" in resp.text
    assert "Could not generate" in resp.text
