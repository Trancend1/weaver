"""Candidate apply/approve/reject service tests (Sprint L5 safety boundary)."""

from __future__ import annotations

from pathlib import Path

import pytest

from weaver.errors import CandidateNotFoundError
from weaver.providers.fake import FakeProvider
from weaver.services.candidate_apply import apply_candidate, approve_candidate, reject_candidate
from weaver.services.candidate_generation import generate_candidate
from weaver.services.project import initialize_project

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
FIXTURE_EPUB = FIXTURES / "aozora_sample.epub"


def _first_segment_id(project_toml: Path, tmp_path: Path) -> tuple[str, str]:
    from weaver.services.project_tree import project_tree

    tree = project_tree(project_toml, cwd=tmp_path)
    chapter_id = tree.volumes[0].chapters[0].id
    from contextlib import closing

    from weaver.services.project_paths import resolve_database_path
    from weaver.storage.db import connect_database
    from weaver.storage.segments import list_chapter_segments

    db_path = resolve_database_path(project_toml, cwd=tmp_path)
    with closing(connect_database(db_path)) as conn:
        segments = list_chapter_segments(conn, chapter_id=chapter_id)
    return chapter_id, segments[0].id


def _generate_candidate(project_toml: Path, tmp_path: Path) -> str:
    chapter_id, segment_id = _first_segment_id(project_toml, tmp_path)
    provider = FakeProvider(pattern="[CANDIDATE] {source}")
    c = generate_candidate(project_toml, chapter_id, segment_id, cwd=tmp_path, provider=provider)
    return c.id


def test_approve_candidate(tmp_path: Path) -> None:
    init = initialize_project(FIXTURE_EPUB, cwd=tmp_path, provider="fake")
    cid = _generate_candidate(init.project_toml, tmp_path)

    result = approve_candidate(init.project_toml, cid, cwd=tmp_path)
    assert result.status == "approved"
    assert result.id == cid


def test_reject_candidate(tmp_path: Path) -> None:
    init = initialize_project(FIXTURE_EPUB, cwd=tmp_path, provider="fake")
    cid = _generate_candidate(init.project_toml, tmp_path)

    result = reject_candidate(init.project_toml, cid, cwd=tmp_path)
    assert result.status == "rejected"
    assert result.id == cid


def test_rejected_candidate_retained_for_audit(tmp_path: Path) -> None:
    init = initialize_project(FIXTURE_EPUB, cwd=tmp_path, provider="fake")
    cid = _generate_candidate(init.project_toml, tmp_path)

    reject_candidate(init.project_toml, cid, cwd=tmp_path)
    from contextlib import closing

    from weaver.services.project_paths import resolve_database_path
    from weaver.storage.candidates import get_candidate
    from weaver.storage.db import connect_database

    db_path = resolve_database_path(init.project_toml, cwd=tmp_path)
    with closing(connect_database(db_path)) as conn:
        c = get_candidate(conn, candidate_id=cid)
    assert c.status == "rejected"


def test_apply_candidate_creates_translation(tmp_path: Path) -> None:
    init = initialize_project(FIXTURE_EPUB, cwd=tmp_path, provider="fake")
    cid = _generate_candidate(init.project_toml, tmp_path)

    result = apply_candidate(init.project_toml, cid, cwd=tmp_path)
    assert result.status == "applied"

    from contextlib import closing

    from weaver.services.project_paths import resolve_database_path
    from weaver.storage.db import connect_database
    from weaver.storage.translations import get_latest_translation_text

    db_path = resolve_database_path(init.project_toml, cwd=tmp_path)
    with closing(connect_database(db_path)) as conn:
        text = get_latest_translation_text(conn, segment_id=result.segment_id)

    assert text is not None, "Apply must create a translation history entry"
    assert "[CANDIDATE]" in str(text)


def test_apply_candidate_with_edit(tmp_path: Path) -> None:
    init = initialize_project(FIXTURE_EPUB, cwd=tmp_path, provider="fake")
    cid = _generate_candidate(init.project_toml, tmp_path)

    edited = "Manually edited translation."
    result = apply_candidate(init.project_toml, cid, cwd=tmp_path, edited_text=edited)
    assert result.status == "applied"

    from contextlib import closing

    from weaver.services.project_paths import resolve_database_path
    from weaver.storage.db import connect_database
    from weaver.storage.translations import get_latest_translation_text

    db_path = resolve_database_path(init.project_toml, cwd=tmp_path)
    with closing(connect_database(db_path)) as conn:
        text = get_latest_translation_text(conn, segment_id=result.segment_id)

    assert str(text) == edited


def test_apply_supersedes_other_candidates(tmp_path: Path) -> None:
    init = initialize_project(FIXTURE_EPUB, cwd=tmp_path, provider="fake")
    chapter_id, segment_id = _first_segment_id(init.project_toml, tmp_path)

    p1 = FakeProvider(pattern="[V1] {source}")
    c1 = generate_candidate(init.project_toml, chapter_id, segment_id, cwd=tmp_path, provider=p1)

    p2 = FakeProvider(pattern="[V2] {source}")
    c2 = generate_candidate(init.project_toml, chapter_id, segment_id, cwd=tmp_path, provider=p2)

    apply_candidate(init.project_toml, c2.id, cwd=tmp_path)

    from contextlib import closing

    from weaver.services.project_paths import resolve_database_path
    from weaver.storage.candidates import get_candidate
    from weaver.storage.db import connect_database

    db_path = resolve_database_path(init.project_toml, cwd=tmp_path)
    with closing(connect_database(db_path)) as conn:
        c1_after = get_candidate(conn, candidate_id=c1.id)
        c2_after = get_candidate(conn, candidate_id=c2.id)

    assert c1_after.status == "superseded"
    assert c2_after.status == "applied"


def test_apply_candidate_not_found(tmp_path: Path) -> None:
    init = initialize_project(FIXTURE_EPUB, cwd=tmp_path, provider="fake")
    with pytest.raises(CandidateNotFoundError):
        apply_candidate(init.project_toml, "nonexistent-id", cwd=tmp_path)


def test_approve_candidate_not_found(tmp_path: Path) -> None:
    init = initialize_project(FIXTURE_EPUB, cwd=tmp_path, provider="fake")
    with pytest.raises(CandidateNotFoundError):
        approve_candidate(init.project_toml, "nonexistent-id", cwd=tmp_path)


def test_reject_candidate_not_found(tmp_path: Path) -> None:
    init = initialize_project(FIXTURE_EPUB, cwd=tmp_path, provider="fake")
    with pytest.raises(CandidateNotFoundError):
        reject_candidate(init.project_toml, "nonexistent-id", cwd=tmp_path)


def test_apply_twice_fails(tmp_path: Path) -> None:
    init = initialize_project(FIXTURE_EPUB, cwd=tmp_path, provider="fake")
    cid = _generate_candidate(init.project_toml, tmp_path)

    apply_candidate(init.project_toml, cid, cwd=tmp_path)
    with pytest.raises(CandidateNotFoundError, match="cannot apply"):
        apply_candidate(init.project_toml, cid, cwd=tmp_path)
