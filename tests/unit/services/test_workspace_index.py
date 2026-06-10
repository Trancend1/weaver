"""Tests for workspace_index (Sprint Q1 / WV-010)."""
# ruff: noqa: E501

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

import pytest

from weaver.services.project import initialize_project
from weaver.services.project_discovery import (
    DiscoveredProject,
    _flag_duplicate_uuids,
    find_project_by_uuid,
)
from weaver.services.workspace_index import (
    WorkspaceIndex,
    _cache_key_for,
    build_workspace_index,
)

FIXTURE_EPUB = Path(__file__).parents[2] / "fixtures" / "aozora_sample.epub"


def _create_v8_project(books_dir: Path, name: str) -> Path:
    """Create a v8-schema project (no uuid column)."""

    project_dir = books_dir / ".weaver" / name
    project_dir.mkdir(parents=True)
    db_path = project_dir / "weaver.db"
    toml_path = project_dir / "project.toml"

    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        CREATE TABLE projects (
          id INTEGER PRIMARY KEY,
          name TEXT NOT NULL,
          source_path TEXT NOT NULL,
          source_lang TEXT NOT NULL,
          target_lang TEXT NOT NULL,
          created_at TEXT NOT NULL,
          schema_version INTEGER NOT NULL
        );
        CREATE TABLE volumes (
          id INTEGER PRIMARY KEY,
          project_id INTEGER NOT NULL REFERENCES projects(id),
          title TEXT NOT NULL,
          source_path TEXT NOT NULL,
          source_format TEXT NOT NULL CHECK (source_format IN ('epub', 'txt', 'html')),
          volume_order INTEGER NOT NULL,
          created_at TEXT NOT NULL
        );
        CREATE TABLE chapters (id TEXT PRIMARY KEY, project_id INTEGER REFERENCES projects(id), volume_id INTEGER REFERENCES volumes(id), title TEXT, href TEXT, spine_order INTEGER NOT NULL);
        CREATE TABLE segments (
          id TEXT PRIMARY KEY, chapter_id TEXT REFERENCES chapters(id), block_order INTEGER NOT NULL,
          kind TEXT NOT NULL, source_text TEXT NOT NULL, source_hash TEXT NOT NULL,
          status TEXT NOT NULL CHECK (status IN ('pending','in_progress','translated','failed','stale','skipped','manual'))
        );
        CREATE TABLE glossary_candidates (
          id INTEGER PRIMARY KEY, project_id INTEGER REFERENCES projects(id),
          source TEXT NOT NULL, target TEXT, category TEXT, notes TEXT,
          status TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'rejected', 'edited')),
          frequency INTEGER NOT NULL
        );
        CREATE TABLE glossary_terms (
          id INTEGER PRIMARY KEY, project_id INTEGER REFERENCES projects(id),
          source TEXT NOT NULL, target TEXT NOT NULL, category TEXT, notes TEXT,
          case_sensitive INTEGER NOT NULL DEFAULT 0,
          UNIQUE(project_id, source)
        );
        CREATE TABLE characters (
          id INTEGER PRIMARY KEY, project_id INTEGER REFERENCES projects(id),
          jp_name TEXT NOT NULL, en_name TEXT NOT NULL, gender TEXT, role TEXT, notes TEXT,
          UNIQUE(project_id, jp_name)
        );
        CREATE TABLE translation_memory (
          id INTEGER PRIMARY KEY, project_id INTEGER REFERENCES projects(id),
          source_text TEXT NOT NULL, source_hash TEXT NOT NULL, target_text TEXT NOT NULL,
          provider TEXT, model TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
          UNIQUE(project_id, source_hash)
        );
        CREATE TABLE translations (
          segment_id TEXT, attempt INTEGER NOT NULL, text TEXT NOT NULL,
          source_hash TEXT NOT NULL, provider TEXT NOT NULL, model TEXT NOT NULL,
          created_at TEXT NOT NULL, raw_response TEXT, input_tokens INTEGER, output_tokens INTEGER,
          PRIMARY KEY (segment_id, attempt)
        );
        CREATE TABLE job_events (
          id INTEGER PRIMARY KEY, project_id INTEGER REFERENCES projects(id),
          job_id TEXT, event TEXT NOT NULL, data_json TEXT, created_at TEXT NOT NULL
        );
        CREATE TABLE jobs (
          id TEXT PRIMARY KEY, kind TEXT NOT NULL, project_name TEXT NOT NULL,
          scope TEXT, scope_id TEXT, chapter_id TEXT,
          status TEXT NOT NULL CHECK (status IN ('queued','running','done','failed','cancelled','processed','finalizing')),
          mode TEXT, target TEXT, total_units INTEGER NOT NULL DEFAULT 0,
          done_units INTEGER NOT NULL DEFAULT 0, failed_units INTEGER NOT NULL DEFAULT 0,
          skipped_units INTEGER NOT NULL DEFAULT 0, current_label TEXT,
          result_json TEXT, error_summary TEXT, started_at TEXT NOT NULL, finished_at TEXT
        );
        CREATE TABLE qa_warnings (
          id INTEGER PRIMARY KEY, segment_id TEXT REFERENCES segments(id),
          check_name TEXT NOT NULL, severity TEXT NOT NULL CHECK (severity IN ('info','warning','critical')),
          message TEXT NOT NULL, created_at TEXT NOT NULL
        );
        """
    )
    connection.execute(
        "INSERT INTO projects (id, name, source_path, source_lang, target_lang, created_at, schema_version) "
        "VALUES (1, ?, 'legacy.epub', 'ja', 'en', '2025-01-01T00:00:00+00:00', 8)",
        (name,),
    )
    connection.execute("PRAGMA user_version = 8")
    connection.commit()
    connection.close()

    toml_path.write_text(
        f"""[project]
name = "{name}"
source_file = "legacy.epub"
project_dir = ".weaver/{name}"
database_path = ".weaver/{name}/weaver.db"
output_dir = ".weaver/{name}/output"
schema_version = 8

[languages]
source = "ja"
target = "en"

[provider]
type = "fake"
model = "fake-1"

[translation]
quality = "balanced"
honorifics = "preserve"
context_window_segments = 5
timeout_seconds = 180
max_retries = 2
""",
        encoding="utf-8",
    )
    return toml_path


def _insert_job(connection: sqlite3.Connection, job_id: str, status: str, started_at: str) -> None:
    connection.execute(
        """
        INSERT INTO jobs (id, kind, project_name, status, total_units, done_units, failed_units, skipped_units, started_at)
        VALUES (?, 'translate', 'test', ?, 10, 0, 0, 0, ?)
        """,
        (job_id, status, started_at),
    )


# ---------- Basic behaviour ----------


def test_workspace_index_builds_entries(tmp_path: Path) -> None:
    initialize_project(FIXTURE_EPUB, cwd=tmp_path)

    index = build_workspace_index(tmp_path)

    assert isinstance(index, WorkspaceIndex)
    assert len(index.entries) == 1
    entry = index.entries[0]
    assert entry.name == "aozora_sample"
    assert entry.state == "ready"
    assert entry.uuid is not None and len(entry.uuid) == 36
    assert entry.schema_version >= 10
    assert entry.volume_count == 1
    assert entry.segment_count == 6


def test_workspace_index_empty_books_dir(tmp_path: Path) -> None:
    index = build_workspace_index(tmp_path)
    assert index.entries == []


# ---------- Error isolation ----------


def test_workspace_index_isolates_corrupt_project(tmp_path: Path) -> None:
    initialize_project(FIXTURE_EPUB, cwd=tmp_path, project_name="healthy")

    # Create a corrupt project
    bad_dir = tmp_path / ".weaver" / "corrupt"
    bad_dir.mkdir(parents=True)
    bad_db = bad_dir / "weaver.db"
    bad_db.write_bytes(b"not sqlite")
    bad_toml = bad_dir / "project.toml"
    bad_toml.write_text(
        "[project]\nname = 'corrupt'\nsource_file = ''\nproject_dir = '.weaver/corrupt'\n"
        "database_path = '.weaver/corrupt/weaver.db'\noutput_dir = '.weaver/corrupt/output'\n"
        "schema_version = 10\n\n[languages]\nsource = 'ja'\ntarget = 'en'\n\n[provider]\ntype = 'fake'\nmodel = 'fake-1'\n",
        encoding="utf-8",
    )

    index = build_workspace_index(tmp_path)

    names = {e.name: e.state for e in index.entries}
    assert names["healthy"] == "ready"
    assert names["corrupt"] == "error"
    corrupt_entry = next(e for e in index.entries if e.name == "corrupt")
    assert corrupt_entry.error is not None


def test_workspace_index_isolates_missing_db(tmp_path: Path) -> None:
    initialize_project(FIXTURE_EPUB, cwd=tmp_path, project_name="healthy")

    bad_dir = tmp_path / ".weaver" / "missing_db"
    bad_dir.mkdir(parents=True)
    bad_toml = bad_dir / "project.toml"
    bad_toml.write_text(
        "[project]\nname = 'missing_db'\nsource_file = ''\nproject_dir = '.weaver/missing_db'\n"
        "database_path = '.weaver/missing_db/weaver.db'\noutput_dir = '.weaver/missing_db/output'\n"
        "schema_version = 10\n\n[languages]\nsource = 'ja'\ntarget = 'en'\n\n[provider]\ntype = 'fake'\nmodel = 'fake-1'\n",
        encoding="utf-8",
    )

    index = build_workspace_index(tmp_path)

    names = {e.name: e.state for e in index.entries}
    assert names["missing_db"] == "error"


# ---------- Schema version guard ----------


def test_workspace_index_needs_upgrade_for_v8(tmp_path: Path) -> None:
    _create_v8_project(tmp_path, "legacy")
    initialize_project(FIXTURE_EPUB, cwd=tmp_path, project_name="modern")

    index = build_workspace_index(tmp_path)

    states = {e.name: e.state for e in index.entries}
    assert states["legacy"] == "needs_upgrade"
    assert states["modern"] == "ready"
    legacy = next(e for e in index.entries if e.name == "legacy")
    assert legacy.uuid is None


# ---------- Identity conflict ----------


def test_workspace_index_flags_duplicate_uuid(tmp_path: Path) -> None:
    initialize_project(FIXTURE_EPUB, cwd=tmp_path, project_name="original")

    # Copy the entire project directory, duplicating the uuid
    copy_dir = tmp_path / ".weaver" / "duplicate"
    (tmp_path / ".weaver" / "original").replace(copy_dir)
    # Restore original
    import shutil

    shutil.copytree(copy_dir, tmp_path / ".weaver" / "original", dirs_exist_ok=True)

    index = build_workspace_index(tmp_path)

    states = {e.name: e.state for e in index.entries}
    assert states["original"] == "identity_conflict"
    assert states["duplicate"] == "identity_conflict"


# ---------- Cache behaviour ----------


@pytest.mark.slow
def test_workspace_index_cache_hit_and_invalidation(tmp_path: Path) -> None:
    initialize_project(FIXTURE_EPUB, cwd=tmp_path, project_name="cached")

    cache: dict[str, Any] = {}
    index1 = build_workspace_index(tmp_path, cache=cache, ttl_seconds=60.0)
    assert index1.entries[0].name == "cached"

    # Immediate rebuild uses cache
    index2 = build_workspace_index(tmp_path, cache=cache, ttl_seconds=60.0)
    assert index2.entries[0].state == "ready"

    # Touch project.toml to invalidate cache
    toml = tmp_path / ".weaver" / "cached" / "project.toml"
    time.sleep(0.05)
    toml.touch()

    index3 = build_workspace_index(tmp_path, cache=cache, ttl_seconds=60.0)
    assert index3.entries[0].name == "cached"
    # Cache should have been rebuilt (new entry with new timestamp)
    cached = cache.get(str(toml))
    assert cached is not None
    assert cached[2] > 0


# ---------- No-write regression ----------


def test_workspace_index_does_not_modify_database(tmp_path: Path) -> None:
    initialize_project(FIXTURE_EPUB, cwd=tmp_path, project_name="readonly")

    db_path = tmp_path / ".weaver" / "readonly" / "weaver.db"
    mtime_before = db_path.stat().st_mtime_ns
    size_before = db_path.stat().st_size

    build_workspace_index(tmp_path)

    mtime_after = db_path.stat().st_mtime_ns
    size_after = db_path.stat().st_size

    assert mtime_after == mtime_before
    assert size_after == size_before


# ---------- Stale running ----------


def test_workspace_index_classifies_stale_running(tmp_path: Path) -> None:
    initialize_project(FIXTURE_EPUB, cwd=tmp_path, project_name="stale")

    db_path = tmp_path / ".weaver" / "stale" / "weaver.db"
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    _insert_job(connection, "job-alive", "running", "2025-06-10T10:00:00+00:00")
    _insert_job(connection, "job-dead", "running", "2025-06-10T09:00:00+00:00")
    connection.commit()
    connection.close()

    def live_check(project_name: str, job_id: str) -> bool:
        return job_id == "job-alive"

    index = build_workspace_index(tmp_path, registry_live_check=live_check)

    entry = index.entries[0]
    assert entry.job_counts.get("running") == 1
    assert entry.job_counts.get("stale_running") == 1


# ---------- Leak rule ----------


def test_entry_exposes_no_absolute_path(tmp_path: Path) -> None:
    initialize_project(FIXTURE_EPUB, cwd=tmp_path, project_name="leak")

    index = build_workspace_index(tmp_path)
    entry = index.entries[0]

    # Entry fields carry no filesystem paths
    assert not hasattr(entry, "project_toml")
    assert not hasattr(entry, "db_path")


# ---------- Perf smoke ----------


@pytest.mark.perf
@pytest.mark.slow
def test_workspace_index_perf_10_projects(tmp_path: Path) -> None:
    for i in range(10):
        initialize_project(FIXTURE_EPUB, cwd=tmp_path, project_name=f"proj{i:02d}")

    cache: dict[str, Any] = {}

    # Cold build (populates cache)
    t0 = time.perf_counter()
    index1 = build_workspace_index(tmp_path, cache=cache, ttl_seconds=60.0)
    cold_ms = (time.perf_counter() - t0) * 1000

    # Warm build (cache hit)
    t0 = time.perf_counter()
    index2 = build_workspace_index(tmp_path, cache=cache, ttl_seconds=60.0)
    warm_ms = (time.perf_counter() - t0) * 1000

    assert len(index1.entries) == 10
    assert len(index2.entries) == 10
    assert warm_ms < 400, f"warm build {warm_ms:.1f}ms exceeds 400ms budget"
    assert cold_ms < 1500, f"cold build {cold_ms:.1f}ms exceeds 1500ms budget"


# ---------- Flag duplicate uuids unit ----------


def test_flag_duplicate_uuids_flags_both() -> None:
    from weaver.services.project import InspectSummary

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


# ---------- find_project_by_uuid ----------


def test_find_project_by_uuid(tmp_path: Path) -> None:
    initialize_project(FIXTURE_EPUB, cwd=tmp_path, project_name="uuid_test")

    discovered = build_workspace_index(tmp_path)
    project_uuid = discovered.entries[0].uuid
    assert project_uuid is not None

    found = find_project_by_uuid(tmp_path, project_uuid)
    assert found is not None
    assert found.name == "uuid_test"
    assert found.summary is not None
    assert found.summary.uuid == project_uuid


def test_find_project_by_uuid_raises_on_duplicate(tmp_path: Path) -> None:
    initialize_project(FIXTURE_EPUB, cwd=tmp_path, project_name="original")

    copy_dir = tmp_path / ".weaver" / "duplicate"
    (tmp_path / ".weaver" / "original").replace(copy_dir)
    import shutil

    shutil.copytree(copy_dir, tmp_path / ".weaver" / "original", dirs_exist_ok=True)

    index = build_workspace_index(tmp_path)
    assert index.entries[0].uuid is not None
    project_uuid = index.entries[0].uuid

    with pytest.raises(ValueError, match="Duplicate project identity"):
        find_project_by_uuid(tmp_path, project_uuid)


def test_find_project_by_uuid_not_found(tmp_path: Path) -> None:
    result = find_project_by_uuid(tmp_path, "nonexistent-uuid")
    assert result is None


# ---------- _cache_key_for ----------


def test_cache_key_returns_none_when_missing() -> None:
    key = _cache_key_for(Path("/nonexistent/project.toml"), Path("/nonexistent/weaver.db"))
    assert key is None
