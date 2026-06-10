"""Unit tests for project discovery (Phase 12a)."""

from __future__ import annotations

from pathlib import Path

from weaver.services.project import initialize_project
from weaver.services.project_discovery import (
    _flag_duplicate_uuids,
    discover_projects,
    find_project,
    find_project_by_uuid,
)

FIXTURE_EPUB = Path(__file__).parents[2] / "fixtures" / "aozora_sample.epub"


def test_discover_returns_empty_when_no_weaver_dir(tmp_path: Path) -> None:
    assert discover_projects(tmp_path) == []


def test_discover_finds_initialized_project(tmp_path: Path) -> None:
    initialize_project(FIXTURE_EPUB, cwd=tmp_path)

    projects = discover_projects(tmp_path)

    assert len(projects) == 1
    discovered = projects[0]
    assert discovered.name == "aozora_sample"
    assert discovered.error is None
    assert discovered.summary is not None
    assert discovered.summary.segment_count == 6


def test_discover_exposes_uuid_for_v10_projects(tmp_path: Path) -> None:
    initialize_project(FIXTURE_EPUB, cwd=tmp_path)

    projects = discover_projects(tmp_path)

    assert len(projects) == 1
    assert projects[0].summary is not None
    assert projects[0].summary.uuid is not None
    assert len(projects[0].summary.uuid) == 36


def test_discover_flags_duplicate_uuid(tmp_path: Path) -> None:
    initialize_project(FIXTURE_EPUB, cwd=tmp_path, project_name="original")

    # Copy the entire project directory, duplicating the uuid
    import shutil

    copy_dir = tmp_path / ".weaver" / "duplicate"
    shutil.copytree(tmp_path / ".weaver" / "original", copy_dir, dirs_exist_ok=True)

    projects = discover_projects(tmp_path)

    flags = {p.name: p.identity_conflict for p in projects}
    assert flags["original"] is True
    assert flags["duplicate"] is True


def test_find_project_by_name(tmp_path: Path) -> None:
    initialize_project(FIXTURE_EPUB, cwd=tmp_path)

    found = find_project(tmp_path, "aozora_sample")

    assert found is not None
    assert found.summary is not None
    assert found.summary.project_name == "aozora_sample"


def test_find_project_missing_returns_none(tmp_path: Path) -> None:
    initialize_project(FIXTURE_EPUB, cwd=tmp_path)

    assert find_project(tmp_path, "does_not_exist") is None


def test_find_project_by_uuid(tmp_path: Path) -> None:
    initialize_project(FIXTURE_EPUB, cwd=tmp_path, project_name="uuid_test")

    projects = discover_projects(tmp_path)
    assert projects[0].summary is not None
    project_uuid = projects[0].summary.uuid
    assert project_uuid is not None

    found = find_project_by_uuid(tmp_path, project_uuid)
    assert found is not None
    assert found.name == "uuid_test"
    assert found.summary is not None
    assert found.summary.uuid == project_uuid


def test_find_project_by_uuid_not_found(tmp_path: Path) -> None:
    assert find_project_by_uuid(tmp_path, "nonexistent-uuid") is None


def test_find_project_by_uuid_raises_on_duplicate(tmp_path: Path) -> None:
    initialize_project(FIXTURE_EPUB, cwd=tmp_path, project_name="original")

    import shutil

    copy_dir = tmp_path / ".weaver" / "duplicate"
    shutil.copytree(tmp_path / ".weaver" / "original", copy_dir, dirs_exist_ok=True)

    projects = discover_projects(tmp_path)
    assert projects[0].summary is not None
    project_uuid = projects[0].summary.uuid
    assert project_uuid is not None

    try:
        find_project_by_uuid(tmp_path, project_uuid)
        raise AssertionError("Expected ValueError")
    except ValueError as exc:
        assert "Duplicate project identity" in str(exc)


def test_flag_duplicate_uuids_flags_both() -> None:
    from weaver.services.project import InspectSummary
    from weaver.services.project_discovery import DiscoveredProject

    summary = InspectSummary(
        project_name="a",
        source_file="",
        provider="fake",
        model="fake-1",
        volume_count=0,
        chapter_count=0,
        segment_count=0,
        pending_count=0,
        translated_count=0,
        failed_count=0,
        stale_count=0,
        glossary_candidate_count=0,
        glossary_term_count=0,
        output_dir="",
        uuid="abc",
        schema_version=10,
    )
    summary2 = InspectSummary(
        project_name="c",
        source_file="",
        provider="fake",
        model="fake-1",
        volume_count=0,
        chapter_count=0,
        segment_count=0,
        pending_count=0,
        translated_count=0,
        failed_count=0,
        stale_count=0,
        glossary_candidate_count=0,
        glossary_term_count=0,
        output_dir="",
        uuid="def",
        schema_version=10,
    )
    projects = [
        DiscoveredProject("a", Path("a"), summary, None),
        DiscoveredProject("b", Path("b"), summary, None),
        DiscoveredProject("c", Path("c"), summary2, None),
    ]
    flagged = _flag_duplicate_uuids(projects)
    assert flagged[0].identity_conflict is True
    assert flagged[1].identity_conflict is True
    assert flagged[2].identity_conflict is False
