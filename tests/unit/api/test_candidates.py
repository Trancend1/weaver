"""Candidate-review JSON API endpoint tests (Sprint L3)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from weaver.api.app import create_api_app
from weaver.services.project import initialize_project

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
FIXTURE_EPUB = FIXTURES / "aozora_sample.epub"


@pytest.fixture
def client_with_project(tmp_path: Path) -> TestClient:
    initialize_project(FIXTURE_EPUB, cwd=tmp_path, provider="fake")
    return TestClient(create_api_app(tmp_path))


def _get_project_name(tmp_path: Path) -> str:
    weaver_dir = tmp_path / ".weaver"
    if not weaver_dir.is_dir():
        return "unknown"
    for p in weaver_dir.iterdir():
        if p.is_dir() and (p / "project.toml").exists():
            return p.name
    return "unknown"


def _first_segment(tmp_path: Path) -> tuple[str, str, str, int]:
    from contextlib import closing

    from weaver.services.project_paths import resolve_database_path
    from weaver.services.project_tree import project_tree
    from weaver.storage.db import connect_database
    from weaver.storage.segments import list_chapter_segments

    init = initialize_project(FIXTURE_EPUB, cwd=tmp_path, provider="fake")
    tree = project_tree(init.project_toml, cwd=tmp_path)
    chapter_id = tree.volumes[0].chapters[0].id
    db_path = resolve_database_path(init.project_toml, cwd=tmp_path)
    with closing(connect_database(db_path)) as conn:
        segments = list_chapter_segments(conn, chapter_id=chapter_id)
    return _get_project_name(tmp_path), chapter_id, segments[0].id, segments[0].block_order


def _insert_candidate_for_test(tmp_path: Path) -> tuple[str, str]:
    from contextlib import closing

    from weaver.services.project_paths import resolve_database_path
    from weaver.services.project_tree import project_tree
    from weaver.storage.candidates import insert_candidate
    from weaver.storage.db import connect_database, transaction
    from weaver.storage.segments import list_chapter_segments

    init = initialize_project(FIXTURE_EPUB, cwd=tmp_path, provider="fake")
    tree = project_tree(init.project_toml, cwd=tmp_path)
    chapter_id = tree.volumes[0].chapters[0].id
    db_path = resolve_database_path(init.project_toml, cwd=tmp_path)
    with closing(connect_database(db_path)) as conn, transaction(conn):
        proj = conn.execute("SELECT id FROM projects ORDER BY id LIMIT 1").fetchone()
        pid = int(proj["id"])
        segs = list_chapter_segments(conn, chapter_id=chapter_id)
        record = insert_candidate(
            conn,
            project_id=pid,
            volume_id=1,
            chapter_id=chapter_id,
            segment_id=segs[0].id,
            source_text=segs[0].source_text,
            candidate_text="Test candidate text",
            provider="fake",
            model="fake-1",
            provenance_json='{"prompt_version": "v1", "source": "test"}',
        )
    return record.id, chapter_id


def _insert_draft_for_test(tmp_path: Path) -> tuple[str, str]:
    from contextlib import closing

    from weaver.services.project_paths import resolve_database_path
    from weaver.services.project_tree import project_tree
    from weaver.storage.character_drafts import insert_draft
    from weaver.storage.db import connect_database, transaction

    init = initialize_project(FIXTURE_EPUB, cwd=tmp_path, provider="fake")
    tree = project_tree(init.project_toml, cwd=tmp_path)
    chapter_id = tree.volumes[0].chapters[0].id
    db_path = resolve_database_path(init.project_toml, cwd=tmp_path)
    with closing(connect_database(db_path)) as conn, transaction(conn):
        proj = conn.execute("SELECT id FROM projects ORDER BY id LIMIT 1").fetchone()
        pid = int(proj["id"])
        record = insert_draft(
            conn,
            project_id=pid,
            volume_id=1,
            chapter_id=chapter_id,
            segment_id=None,
            source_text="Source character page text",
            draft_text="# Draft character description",
            heading="Character Page",
            page_identifier="ch01.xhtml",
            provenance_json='{"source": "xhtml_text", "no_ocr": true}',
        )
    return record.id, chapter_id


class TestCandidatesEndpoints:
    def test_list_candidates_empty(self, client_with_project, tmp_path):
        name = _get_project_name(tmp_path)
        resp = client_with_project.get(f"/projects/{name}/candidates")
        assert resp.status_code == 200
        data = resp.json()
        assert "candidates" in data
        assert isinstance(data["candidates"], list)

    def test_generate_candidate(self, client_with_project, tmp_path):
        name, chapter_id, segment_id, _ = _first_segment(tmp_path)
        resp = client_with_project.post(
            f"/projects/{name}/candidates/generate",
            params={"chapter_id": chapter_id, "segment_id": segment_id},
            json={"provider": "fake"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["candidate"]["status"] == "pending"
        assert data["candidate"]["segment_id"] == segment_id

    def test_generate_candidate_missing_segment(self, client_with_project, tmp_path):
        name, chapter_id, _, _ = _first_segment(tmp_path)
        resp = client_with_project.post(
            f"/projects/{name}/candidates/generate",
            params={"chapter_id": chapter_id, "segment_id": "nonexistent"},
            json={"provider": "fake"},
        )
        assert resp.status_code == 422

    def test_approve_candidate(self, client_with_project, tmp_path):
        name = _get_project_name(tmp_path)
        cid, _ = _insert_candidate_for_test(tmp_path)
        resp = client_with_project.post(f"/projects/{name}/candidates/{cid}/approve")
        assert resp.status_code == 200
        assert resp.json()["candidate"]["status"] == "approved"

    def test_reject_candidate(self, client_with_project, tmp_path):
        name = _get_project_name(tmp_path)
        cid, _ = _insert_candidate_for_test(tmp_path)
        resp = client_with_project.post(f"/projects/{name}/candidates/{cid}/reject")
        assert resp.status_code == 200
        assert resp.json()["candidate"]["status"] == "rejected"

    def test_apply_candidate(self, client_with_project, tmp_path):
        name = _get_project_name(tmp_path)
        cid, _ = _insert_candidate_for_test(tmp_path)
        resp = client_with_project.post(
            f"/projects/{name}/candidates/{cid}/apply",
            json={"edited_text": "Edited after apply"},
        )
        assert resp.status_code == 200
        assert resp.json()["candidate"]["status"] == "applied"

    def test_apply_candidate_no_edit(self, client_with_project, tmp_path):
        name = _get_project_name(tmp_path)
        cid, _ = _insert_candidate_for_test(tmp_path)
        resp = client_with_project.post(f"/projects/{name}/candidates/{cid}/apply")
        assert resp.status_code == 200
        assert resp.json()["candidate"]["status"] == "applied"

    def test_candidate_not_found(self, client_with_project, tmp_path):
        name = _get_project_name(tmp_path)
        resp = client_with_project.post(f"/projects/{name}/candidates/nonexistent/approve")
        assert resp.status_code == 404

    def test_generate_candidate_full_flow(self, client_with_project, tmp_path):
        name, chapter_id, segment_id, _ = _first_segment(tmp_path)
        resp = client_with_project.post(
            f"/projects/{name}/candidates/generate",
            params={"chapter_id": chapter_id, "segment_id": segment_id},
            json={"provider": "fake"},
        )
        assert resp.status_code == 200
        cid = resp.json()["candidate"]["id"]

        approve_resp = client_with_project.post(f"/projects/{name}/candidates/{cid}/approve")
        assert approve_resp.status_code == 200
        assert approve_resp.json()["candidate"]["status"] == "approved"


class TestCharacterDraftsEndpoints:
    def test_list_drafts_empty(self, client_with_project, tmp_path):
        name = _get_project_name(tmp_path)
        resp = client_with_project.get(f"/projects/{name}/drafts")
        assert resp.status_code == 200
        data = resp.json()
        assert "drafts" in data

    def test_generate_draft(self, client_with_project, tmp_path):
        name, chapter_id, _, _ = _first_segment(tmp_path)
        resp = client_with_project.post(
            f"/projects/{name}/drafts/generate",
            params={"chapter_id": chapter_id},
        )
        assert resp.status_code in (200, 422)

    def test_approve_draft(self, client_with_project, tmp_path):
        name = _get_project_name(tmp_path)
        did, _ = _insert_draft_for_test(tmp_path)
        resp = client_with_project.post(f"/projects/{name}/drafts/{did}/approve")
        assert resp.status_code == 200
        assert resp.json()["draft"]["status"] == "approved"

    def test_reject_draft(self, client_with_project, tmp_path):
        name = _get_project_name(tmp_path)
        did, _ = _insert_draft_for_test(tmp_path)
        resp = client_with_project.post(f"/projects/{name}/drafts/{did}/reject")
        assert resp.status_code == 200
        assert resp.json()["draft"]["status"] == "rejected"

    def test_draft_not_found(self, client_with_project, tmp_path):
        name = _get_project_name(tmp_path)
        resp = client_with_project.post(f"/projects/{name}/drafts/nonexistent/approve")
        assert resp.status_code == 404
