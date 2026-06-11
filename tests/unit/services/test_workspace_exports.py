"""Tests for the export-history read layer (Sprint Q7)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from weaver.services.project import initialize_project
from weaver.services.workspace_exports import (
    WorkspaceExports,
    build_workspace_exports,
    list_project_exports,
    project_export_history,
)

FIXTURE_EPUB = Path(__file__).parents[2] / "fixtures" / "aozora_sample.epub"


def _volume_id(db_path: Path) -> int:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT id FROM volumes ORDER BY id LIMIT 1").fetchone()
    conn.close()
    return int(row["id"]) if row is not None else 1


def _seed_export(
    db_path: Path,
    *,
    id: str,
    volume_id: int | None,
    artifact_path: str | None,
    status: str = "succeeded",
    kind: str = "draft",
    created_at: str = "2025-01-01T00:00:00+00:00",
    byte_size: int | None = 100,
) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(
        "INSERT INTO export_history (id, volume_id, format, kind, status, qa_badge, "
        "artifact_path, byte_size, job_id, version_label, created_at) "
        "VALUES (?, ?, 'epub', ?, ?, 'clean', ?, ?, NULL, NULL, ?)",
        (id, volume_id, kind, status, artifact_path, byte_size, created_at),
    )
    conn.commit()
    conn.close()


def test_empty_books_dir(tmp_path: Path) -> None:
    exports = build_workspace_exports(tmp_path)
    assert isinstance(exports, WorkspaceExports)
    assert exports.rows == []
    assert exports.degraded == []


def test_cross_project_rows_basename_only(tmp_path: Path) -> None:
    initialize_project(FIXTURE_EPUB, cwd=tmp_path, project_name="alpha")
    db = tmp_path / ".weaver" / "alpha" / "weaver.db"
    artifact = tmp_path / "out" / "volume-01.epub"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"epub-bytes")
    _seed_export(db, id="e1", volume_id=_volume_id(db), artifact_path=str(artifact))

    exports = build_workspace_exports(tmp_path)
    assert len(exports.rows) == 1
    row = exports.rows[0]
    assert row.project_name == "alpha"
    assert row.artifact_basename == "volume-01.epub"
    assert row.exists is True
    # Leak rule: the absolute parent path is never on the row.
    assert not hasattr(row, "artifact_path")


def test_missing_artifact_marked_not_exists(tmp_path: Path) -> None:
    initialize_project(FIXTURE_EPUB, cwd=tmp_path, project_name="alpha")
    db = tmp_path / ".weaver" / "alpha" / "weaver.db"
    _seed_export(db, id="gone", volume_id=_volume_id(db), artifact_path=str(tmp_path / "nope.epub"))

    exports = build_workspace_exports(tmp_path)
    assert exports.rows[0].exists is False


def test_rows_sorted_newest_first_across_projects(tmp_path: Path) -> None:
    initialize_project(FIXTURE_EPUB, cwd=tmp_path, project_name="alpha")
    initialize_project(FIXTURE_EPUB, cwd=tmp_path, project_name="beta")
    db_a = tmp_path / ".weaver" / "alpha" / "weaver.db"
    db_b = tmp_path / ".weaver" / "beta" / "weaver.db"
    _seed_export(
        db_a,
        id="a-old",
        volume_id=_volume_id(db_a),
        artifact_path=None,
        created_at="2025-01-01T00:00:00+00:00",
    )
    _seed_export(
        db_b,
        id="b-new",
        volume_id=_volume_id(db_b),
        artifact_path=None,
        created_at="2025-09-01T00:00:00+00:00",
    )

    exports = build_workspace_exports(tmp_path)
    assert [r.created_at for r in exports.rows] == sorted(
        [r.created_at for r in exports.rows], reverse=True
    )
    assert exports.rows[0].created_at.startswith("2025-09")


def test_per_project_list_has_full_path(tmp_path: Path) -> None:
    result = initialize_project(FIXTURE_EPUB, cwd=tmp_path, project_name="alpha")
    db = tmp_path / ".weaver" / "alpha" / "weaver.db"
    artifact = tmp_path / "out" / "v.epub"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"x")
    _seed_export(db, id="e1", volume_id=_volume_id(db), artifact_path=str(artifact))

    rows = list_project_exports(result.project_toml, cwd=tmp_path)
    assert len(rows) == 1
    assert rows[0].artifact_path == str(artifact)
    assert rows[0].exists is True

    by_name = project_export_history(tmp_path, "alpha")
    assert len(by_name) == 1
    assert by_name[0].id == "e1"


def test_needs_upgrade_for_old_schema(tmp_path: Path) -> None:
    from tests.unit.services.test_workspace_index import _create_v8_project

    _create_v8_project(tmp_path, "legacy")
    initialize_project(FIXTURE_EPUB, cwd=tmp_path, project_name="modern")

    exports = build_workspace_exports(tmp_path)
    degraded_states = {d.name: d.state for d in exports.degraded}
    assert degraded_states.get("legacy") == "needs_upgrade"
