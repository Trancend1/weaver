"""Tests for Sprint H4 lifecycle event logging.

Verifies that ``services/project.py``, ``services/import_source.py``, and
``services/volume.py`` emit one ``runtime.log`` entry per lifecycle action
using the Sprint G ``logging_setup`` JSON-lines surface.

Each test pins the app-data root to a tmp dir, installs logging, drives a
lifecycle action, and reads the resulting ``runtime.log`` events back.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from weaver.services.app_paths import AppPaths
from weaver.services.import_source import import_volume
from weaver.services.logging_setup import (
    install_logging,
    read_log_file,
    reset_logging,
)
from weaver.services.project import delete_project, initialize_project
from weaver.services.volume import delete_volume_from_project


def _epub_fixture() -> Path:
    fixtures = Path(__file__).parent.parent.parent / "fixtures"
    epubs = list(fixtures.glob("*.epub"))
    if not epubs:
        pytest.skip("no EPUB fixture available")
    return epubs[0]


@pytest.fixture
def logging_paths(tmp_path: Path):
    paths = AppPaths(root=tmp_path / "weaver-data")
    reset_logging()
    install_logging(paths)
    yield paths
    reset_logging()


def _runtime_events(paths: AppPaths) -> list[dict]:
    return read_log_file(paths, "runtime.log")


def test_project_created_event_lands_in_runtime_log(
    tmp_path: Path, logging_paths: AppPaths
) -> None:
    initialize_project(_epub_fixture(), cwd=tmp_path)

    events = [e for e in _runtime_events(logging_paths) if e["event"] == "project.created"]
    assert len(events) == 1
    entry = events[0]
    assert entry["project"]
    assert entry["chapters"] >= 0
    assert entry["segments"] >= 0
    assert "glossary_candidates" in entry
    assert "provider" in entry


def test_volume_imported_event_lands_in_runtime_log(
    tmp_path: Path, logging_paths: AppPaths
) -> None:
    epub = _epub_fixture()
    init = initialize_project(epub, cwd=tmp_path)
    # Use the same fixture again as an additional volume (its content is
    # immaterial for the event payload).
    import_volume(init.project_toml, epub, cwd=tmp_path)

    events = [e for e in _runtime_events(logging_paths) if e["event"] == "volume.imported"]
    assert events, "expected at least one volume.imported event"
    entry = events[-1]
    assert entry["project"]
    assert entry["volume_id"] >= 1
    assert entry["title"]
    assert entry["chapters"] >= 0
    assert entry["segments"] >= 0
    assert entry["format"]


def test_volume_deleted_event_lands_in_runtime_log(tmp_path: Path, logging_paths: AppPaths) -> None:
    epub = _epub_fixture()
    init = initialize_project(epub, cwd=tmp_path)
    import_result = import_volume(init.project_toml, epub, cwd=tmp_path)

    delete_volume_from_project(init.project_toml, import_result.volume_id, cwd=tmp_path)

    events = [e for e in _runtime_events(logging_paths) if e["event"] == "volume.deleted"]
    assert len(events) == 1
    entry = events[0]
    assert entry["volume_id"] == import_result.volume_id
    assert entry["title"] == import_result.volume_title


def test_project_deleted_event_lands_in_runtime_log(
    tmp_path: Path, logging_paths: AppPaths
) -> None:
    init = initialize_project(_epub_fixture(), cwd=tmp_path)

    delete_project(init.project_toml)

    events = [e for e in _runtime_events(logging_paths) if e["event"] == "project.deleted"]
    assert len(events) == 1
    assert events[0]["project"]


def test_lifecycle_events_carry_no_secret_shaped_fields(
    tmp_path: Path, logging_paths: AppPaths
) -> None:
    init = initialize_project(_epub_fixture(), cwd=tmp_path)
    delete_project(init.project_toml)

    raw = (logging_paths.logs_dir / "runtime.log").read_text(encoding="utf-8")
    # Defense in depth: lifecycle payloads must never include provider secrets.
    for needle in ("api_key", "API_KEY", "authorization", "secret", "password"):
        assert needle.lower() not in raw.lower()
