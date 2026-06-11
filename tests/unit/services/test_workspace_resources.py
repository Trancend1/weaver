"""Tests for workspace_resources (Sprint Q5)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from weaver.services.project import initialize_project
from weaver.services.workspace_resources import (
    WorkspaceResources,
    build_workspace_resources,
)

FIXTURE_EPUB = Path(__file__).parents[2] / "fixtures" / "aozora_sample.epub"


def _insert_glossary_term(connection: sqlite3.Connection, source: str, target: str) -> None:
    connection.execute(
        "INSERT INTO glossary_terms (project_id, source, target) VALUES (1, ?, ?)",
        (source, target),
    )


def _insert_character(connection: sqlite3.Connection, jp_name: str, en_name: str) -> None:
    connection.execute(
        "INSERT INTO characters (project_id, jp_name, en_name) VALUES (1, ?, ?)",
        (jp_name, en_name),
    )


def _insert_memory_entry(
    connection: sqlite3.Connection,
    source_text: str,
    source_hash: str,
    target_text: str,
) -> None:
    connection.execute(
        "INSERT INTO translation_memory "
        "(project_id, source_text, source_hash, target_text, created_at, updated_at) "
        "VALUES (1, ?, ?, ?, '2025-01-01T00:00:00+00:00', '2025-01-01T00:00:00+00:00')",
        (source_text, source_hash, target_text),
    )


# ---------- Basic behaviour ----------


def test_workspace_resources_empty_books_dir(tmp_path: Path) -> None:
    resources = build_workspace_resources(tmp_path)
    assert isinstance(resources, WorkspaceResources)
    assert resources.projects == []
    assert resources.degraded == []


def test_workspace_resources_builds_summary(tmp_path: Path) -> None:
    initialize_project(FIXTURE_EPUB, cwd=tmp_path, project_name="alpha")

    resources = build_workspace_resources(tmp_path)
    assert len(resources.projects) == 1
    p = resources.projects[0]
    assert p.project_name == "alpha"
    assert p.state == "ready"
    assert p.project_uuid is not None and len(p.project_uuid) == 36
    assert p.glossary_term_count == 0
    assert p.character_count == 0
    assert p.memory_entry_count == 0
    assert p.prompt_template_count is None
    assert p.style_guide_count is None


def test_workspace_resources_counts_across_tables(tmp_path: Path) -> None:
    initialize_project(FIXTURE_EPUB, cwd=tmp_path, project_name="alpha")

    db_path = tmp_path / ".weaver" / "alpha" / "weaver.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    _insert_glossary_term(conn, "魔女", "witch")
    _insert_glossary_term(conn, "剣", "sword")
    _insert_character(conn, "佐藤", "Sato")
    _insert_memory_entry(conn, "こんにちは", "hash1", "Hello")
    _insert_memory_entry(conn, "さようなら", "hash2", "Goodbye")
    _insert_memory_entry(conn, "ありがとう", "hash3", "Thank you")
    conn.commit()
    conn.close()

    resources = build_workspace_resources(tmp_path)
    assert len(resources.projects) == 1
    p = resources.projects[0]
    assert p.glossary_term_count == 2
    assert p.character_count == 1
    assert p.memory_entry_count == 3


def test_workspace_resources_sorts_projects(tmp_path: Path) -> None:
    initialize_project(FIXTURE_EPUB, cwd=tmp_path, project_name="zeta")
    initialize_project(FIXTURE_EPUB, cwd=tmp_path, project_name="alpha")
    initialize_project(FIXTURE_EPUB, cwd=tmp_path, project_name="beta")

    resources = build_workspace_resources(tmp_path)
    names = [p.project_name for p in resources.projects]
    assert names == ["alpha", "beta", "zeta"]


# ---------- Error isolation ----------


def test_workspace_resources_isolates_corrupt_project(tmp_path: Path) -> None:
    initialize_project(FIXTURE_EPUB, cwd=tmp_path, project_name="healthy")

    bad_dir = tmp_path / ".weaver" / "corrupt"
    bad_dir.mkdir(parents=True)
    bad_db = bad_dir / "weaver.db"
    bad_db.write_bytes(b"not sqlite")
    bad_toml = bad_dir / "project.toml"
    bad_toml.write_text(
        "[project]\nname = 'corrupt'\nsource_file = ''"
        "\nproject_dir = '.weaver/corrupt'\n"
        "database_path = '.weaver/corrupt/weaver.db'\n"
        "output_dir = '.weaver/corrupt/output'\n"
        "schema_version = 10\n\n[languages]\nsource = 'ja'"
        "\ntarget = 'en'\n\n[provider]\ntype = 'fake'\nmodel = 'fake-1'\n",
        encoding="utf-8",
    )

    resources = build_workspace_resources(tmp_path)
    assert len(resources.projects) == 1
    assert resources.projects[0].project_name == "healthy"
    assert len(resources.degraded) == 1
    assert resources.degraded[0].name == "corrupt"
    assert resources.degraded[0].state == "error"


def test_workspace_resources_isolates_missing_db(tmp_path: Path) -> None:
    initialize_project(FIXTURE_EPUB, cwd=tmp_path, project_name="healthy")

    bad_dir = tmp_path / ".weaver" / "missing_db"
    bad_dir.mkdir(parents=True)
    bad_toml = bad_dir / "project.toml"
    bad_toml.write_text(
        "[project]\nname = 'missing_db'\nsource_file = ''"
        "\nproject_dir = '.weaver/missing_db'\n"
        "database_path = '.weaver/missing_db/weaver.db'\n"
        "output_dir = '.weaver/missing_db/output'\n"
        "schema_version = 10\n\n[languages]\nsource = 'ja'"
        "\ntarget = 'en'\n\n[provider]\ntype = 'fake'\nmodel = 'fake-1'\n",
        encoding="utf-8",
    )

    resources = build_workspace_resources(tmp_path)
    degraded_names = {d.name for d in resources.degraded}
    assert "missing_db" in degraded_names


# ---------- Schema version guard ----------


def test_workspace_resources_needs_upgrade_for_v8(tmp_path: Path) -> None:
    from tests.unit.services.test_workspace_index import _create_v8_project

    _create_v8_project(tmp_path, "legacy")
    initialize_project(FIXTURE_EPUB, cwd=tmp_path, project_name="modern")

    resources = build_workspace_resources(tmp_path)
    degraded_states = {d.name: d.state for d in resources.degraded}
    assert degraded_states.get("legacy") == "needs_upgrade"
    project_names = {p.project_name for p in resources.projects}
    assert "modern" in project_names


# ---------- Identity conflict ----------


def test_workspace_resources_identity_conflict_degraded(tmp_path: Path) -> None:
    initialize_project(FIXTURE_EPUB, cwd=tmp_path, project_name="original")

    copy_dir = tmp_path / ".weaver" / "duplicate"
    (tmp_path / ".weaver" / "original").replace(copy_dir)
    import shutil

    shutil.copytree(copy_dir, tmp_path / ".weaver" / "original", dirs_exist_ok=True)

    resources = build_workspace_resources(tmp_path)
    degraded_states = {d.name: d.state for d in resources.degraded}
    assert degraded_states.get("original") == "identity_conflict"
    assert degraded_states.get("duplicate") == "identity_conflict"


# ---------- No-write regression ----------


def test_workspace_resources_does_not_modify_database(tmp_path: Path) -> None:
    initialize_project(FIXTURE_EPUB, cwd=tmp_path, project_name="readonly")

    db_path = tmp_path / ".weaver" / "readonly" / "weaver.db"
    mtime_before = db_path.stat().st_mtime_ns
    size_before = db_path.stat().st_size

    build_workspace_resources(tmp_path)

    mtime_after = db_path.stat().st_mtime_ns
    size_after = db_path.stat().st_size

    assert mtime_after == mtime_before
    assert size_after == size_before
