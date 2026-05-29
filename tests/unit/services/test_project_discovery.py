"""Unit tests for project discovery (Phase 12a)."""

from __future__ import annotations

from pathlib import Path

from weaver.services.project import initialize_project
from weaver.services.project_discovery import discover_projects, find_project

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


def test_find_project_by_name(tmp_path: Path) -> None:
    initialize_project(FIXTURE_EPUB, cwd=tmp_path)

    found = find_project(tmp_path, "aozora_sample")

    assert found is not None
    assert found.summary is not None
    assert found.summary.project_name == "aozora_sample"


def test_find_project_missing_returns_none(tmp_path: Path) -> None:
    initialize_project(FIXTURE_EPUB, cwd=tmp_path)

    assert find_project(tmp_path, "does_not_exist") is None
