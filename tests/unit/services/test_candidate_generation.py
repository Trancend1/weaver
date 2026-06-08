"""Candidate generation service tests (Sprint L2)."""

from __future__ import annotations

from pathlib import Path

from weaver.providers.fake import FakeProvider
from weaver.services.candidate_generation import generate_candidate
from weaver.services.project import initialize_project

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
FIXTURE_EPUB = FIXTURES / "aozora_sample.epub"


def test_generate_candidate_requires_segment(tmp_path: Path) -> None:
    init = initialize_project(FIXTURE_EPUB, cwd=tmp_path, provider="fake")
    from weaver.services.project_tree import project_tree

    tree = project_tree(init.project_toml, cwd=tmp_path)
    chapter_id = tree.volumes[0].chapters[0].id
    from contextlib import closing

    from weaver.services.project_paths import resolve_database_path
    from weaver.storage.db import connect_database
    from weaver.storage.segments import list_chapter_segments

    db_path = resolve_database_path(init.project_toml, cwd=tmp_path)
    with closing(connect_database(db_path)) as conn:
        segments = list_chapter_segments(conn, chapter_id=chapter_id)
    assert len(segments) > 0
    segment_id = segments[0].id

    provider = FakeProvider(pattern="[CANDIDATE] {source}")
    candidate = generate_candidate(
        init.project_toml,
        chapter_id,
        segment_id,
        cwd=tmp_path,
        provider=provider,
    )

    assert candidate.segment_id == segment_id
    assert candidate.status == "pending"
    assert candidate.candidate_text == f"[CANDIDATE] {segments[0].source_text}"
    assert candidate.provider == "fake"
    assert candidate.model == "fake-1"
    assert candidate.provenance_json is not None
    import json

    prov = json.loads(candidate.provenance_json)
    assert prov["provider"] == "fake"
    assert prov["prompt_version"] is not None
    assert prov["source_segments"] == [segment_id]
    assert prov["chapter_id"] == chapter_id


def test_generate_candidate_no_auto_apply(tmp_path: Path) -> None:
    init = initialize_project(FIXTURE_EPUB, cwd=tmp_path, provider="fake")
    from weaver.services.project_tree import project_tree

    tree = project_tree(init.project_toml, cwd=tmp_path)
    chapter_id = tree.volumes[0].chapters[0].id
    from contextlib import closing

    from weaver.services.project_paths import resolve_database_path
    from weaver.storage.db import connect_database
    from weaver.storage.segments import list_chapter_segments
    from weaver.storage.translations import get_latest_translation_text

    db_path = resolve_database_path(init.project_toml, cwd=tmp_path)
    with closing(connect_database(db_path)) as conn:
        segments = list_chapter_segments(conn, chapter_id=chapter_id)
    assert len(segments) > 0
    segment_id = segments[0].id

    provider = FakeProvider(pattern="[CANDIDATE] {source}")
    generate_candidate(init.project_toml, chapter_id, segment_id, cwd=tmp_path, provider=provider)

    with closing(connect_database(db_path)) as conn:
        current = get_latest_translation_text(conn, segment_id=segment_id)

    assert current is None, "Candidate generation must not mutate the current translation"


def test_generate_candidate_supersedes_previous(tmp_path: Path) -> None:
    init = initialize_project(FIXTURE_EPUB, cwd=tmp_path, provider="fake")
    from weaver.services.project_tree import project_tree
    from weaver.storage.candidates import list_candidates_for_segment

    tree = project_tree(init.project_toml, cwd=tmp_path)
    chapter_id = tree.volumes[0].chapters[0].id
    from contextlib import closing

    from weaver.services.project_paths import resolve_database_path
    from weaver.storage.db import connect_database
    from weaver.storage.segments import list_chapter_segments

    db_path = resolve_database_path(init.project_toml, cwd=tmp_path)
    with closing(connect_database(db_path)) as conn:
        segments = list_chapter_segments(conn, chapter_id=chapter_id)
    assert len(segments) > 0
    segment_id = segments[0].id

    provider = FakeProvider(pattern="[CANDIDATE V1] {source}")
    c1 = generate_candidate(
        init.project_toml, chapter_id, segment_id, cwd=tmp_path, provider=provider
    )
    assert c1.status == "pending"

    provider_v2 = FakeProvider(pattern="[CANDIDATE V2] {source}")
    c2 = generate_candidate(
        init.project_toml, chapter_id, segment_id, cwd=tmp_path, provider=provider_v2
    )
    assert c2.status == "pending"

    from contextlib import closing

    from weaver.services.project_paths import resolve_database_path
    from weaver.storage.db import connect_database

    db_path = resolve_database_path(init.project_toml, cwd=tmp_path)
    with closing(connect_database(db_path)) as conn:
        candidates = list_candidates_for_segment(conn, segment_id=segment_id)

    statuses = {c.id: c.status for c in candidates}
    assert statuses[c1.id] == "superseded", "Previous candidate must be superseded"
    assert statuses[c2.id] == "pending", "New candidate must be pending"


def test_generate_candidate_provider_error_creates_failed(tmp_path: Path) -> None:
    init = initialize_project(FIXTURE_EPUB, cwd=tmp_path, provider="fake")
    import json

    from weaver.services.project_tree import project_tree

    tree = project_tree(init.project_toml, cwd=tmp_path)
    chapter_id = tree.volumes[0].chapters[0].id
    from contextlib import closing

    from weaver.services.project_paths import resolve_database_path
    from weaver.storage.db import connect_database
    from weaver.storage.segments import list_chapter_segments

    db_path = resolve_database_path(init.project_toml, cwd=tmp_path)
    with closing(connect_database(db_path)) as conn:
        segments = list_chapter_segments(conn, chapter_id=chapter_id)
    assert len(segments) > 0
    segment_id = segments[0].id

    failing_provider = FakeProvider(pattern="[FAIL] {source}", fail_rate=1.0)
    result = generate_candidate(
        init.project_toml,
        chapter_id,
        segment_id,
        cwd=tmp_path,
        provider=failing_provider,
    )

    assert result.status == "pending"
    assert result.candidate_text == ""
    prov = json.loads(result.provenance_json)
    assert prov.get("error") == "provider_error"


def test_generate_candidate_includes_provenance(tmp_path: Path) -> None:
    init = initialize_project(FIXTURE_EPUB, cwd=tmp_path, provider="fake")
    import json

    from weaver.services.project_tree import project_tree

    tree = project_tree(init.project_toml, cwd=tmp_path)
    chapter_id = tree.volumes[0].chapters[0].id
    from contextlib import closing

    from weaver.services.project_paths import resolve_database_path
    from weaver.storage.db import connect_database
    from weaver.storage.segments import list_chapter_segments

    db_path = resolve_database_path(init.project_toml, cwd=tmp_path)
    with closing(connect_database(db_path)) as conn:
        segments = list_chapter_segments(conn, chapter_id=chapter_id)
    segment_id = segments[0].id

    provider = FakeProvider(pattern="[PROV] {source}")
    candidate = generate_candidate(
        init.project_toml, chapter_id, segment_id, cwd=tmp_path, provider=provider
    )

    prov = json.loads(candidate.provenance_json)
    assert "provider" in prov
    assert "model" in prov
    assert "prompt_version" in prov
    assert "chapter_id" in prov
    assert "source_segments" in prov
    assert "created_at" in prov
    assert prov["provider"] == "fake"
    assert prov["model"] == "fake-1"
    assert prov["chapter_id"] == chapter_id
