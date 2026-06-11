"""Tests for workspace_queue (Sprint Q4)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from weaver.services.project import initialize_project
from weaver.services.workspace_queue import WorkspaceQueue, build_workspace_queue

FIXTURE_EPUB = Path(__file__).parents[2] / "fixtures" / "aozora_sample.epub"


def _insert_job(
    connection: sqlite3.Connection,
    job_id: str,
    status: str,
    started_at: str,
    kind: str = "translate",
    scope: str | None = None,
    scope_id: str | None = None,
) -> None:
    connection.execute(
        """
        INSERT INTO jobs (
            id, kind, project_name, scope, scope_id, chapter_id, status,
            total_units, done_units, failed_units, skipped_units, started_at
        )
        VALUES (?, ?, 'test', ?, ?, NULL, ?, 10, 0, 0, 0, ?)
        """,
        (job_id, kind, scope, scope_id, status, started_at),
    )


# ---------- Basic behaviour ----------


def test_workspace_queue_empty_books_dir(tmp_path: Path) -> None:
    queue = build_workspace_queue(tmp_path)
    assert isinstance(queue, WorkspaceQueue)
    assert queue.jobs == []
    assert queue.degraded == []


def test_workspace_queue_lists_jobs(tmp_path: Path) -> None:
    initialize_project(FIXTURE_EPUB, cwd=tmp_path, project_name="alpha")
    initialize_project(FIXTURE_EPUB, cwd=tmp_path, project_name="beta")

    alpha_db = tmp_path / ".weaver" / "alpha" / "weaver.db"
    beta_db = tmp_path / ".weaver" / "beta" / "weaver.db"

    conn_a = sqlite3.connect(alpha_db)
    conn_a.row_factory = sqlite3.Row
    _insert_job(conn_a, "job-a1", "running", "2025-06-10T10:00:00+00:00")
    _insert_job(conn_a, "job-a2", "done", "2025-06-10T09:00:00+00:00")
    conn_a.commit()
    conn_a.close()

    conn_b = sqlite3.connect(beta_db)
    conn_b.row_factory = sqlite3.Row
    _insert_job(conn_b, "job-b1", "queued", "2025-06-10T08:00:00+00:00")
    conn_b.commit()
    conn_b.close()

    queue = build_workspace_queue(tmp_path)
    assert len(queue.jobs) == 3
    job_ids = {j.job_id for j in queue.jobs}
    assert job_ids == {"job-a1", "job-a2", "job-b1"}

    # running first, then queued, then done
    assert queue.jobs[0].status == "running"
    assert queue.jobs[1].status == "queued"
    assert queue.jobs[2].status == "done"


# ---------- stale_running ----------


def test_workspace_queue_stale_running_distinct(tmp_path: Path) -> None:
    initialize_project(FIXTURE_EPUB, cwd=tmp_path, project_name="stale")

    db_path = tmp_path / ".weaver" / "stale" / "weaver.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    _insert_job(conn, "job-alive", "running", "2025-06-10T10:00:00+00:00")
    _insert_job(conn, "job-dead", "running", "2025-06-10T09:00:00+00:00")
    conn.commit()
    conn.close()

    def live_check(project_name: str, job_id: str) -> bool:
        return job_id == "job-alive"

    queue = build_workspace_queue(tmp_path, registry_live_check=live_check)
    statuses = {j.job_id: j.status for j in queue.jobs}
    assert statuses["job-alive"] == "running"
    assert statuses["job-dead"] == "stale_running"


# ---------- Error isolation ----------


def test_workspace_queue_isolates_corrupt_project(tmp_path: Path) -> None:
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
        "schema_version = 10\n\n[languages]\nsource = 'ja'\ntarget = 'en'\n\n"
        "[provider]\ntype = 'fake'\nmodel = 'fake-1'\n",
        encoding="utf-8",
    )

    queue = build_workspace_queue(tmp_path)
    assert len(queue.degraded) == 1
    assert queue.degraded[0].name == "corrupt"
    assert queue.degraded[0].state == "error"
    # Healthy project still has zero jobs (no jobs inserted) but no degraded entry
    assert len([d for d in queue.degraded if d.name == "healthy"]) == 0


def test_workspace_queue_isolates_missing_db(tmp_path: Path) -> None:
    initialize_project(FIXTURE_EPUB, cwd=tmp_path, project_name="healthy")

    bad_dir = tmp_path / ".weaver" / "missing_db"
    bad_dir.mkdir(parents=True)
    bad_toml = bad_dir / "project.toml"
    bad_toml.write_text(
        "[project]\nname = 'missing_db'\nsource_file = ''"
        "\nproject_dir = '.weaver/missing_db'\n"
        "database_path = '.weaver/missing_db/weaver.db'\n"
        "output_dir = '.weaver/missing_db/output'\n"
        "schema_version = 10\n\n[languages]\nsource = 'ja'\ntarget = 'en'\n\n"
        "[provider]\ntype = 'fake'\nmodel = 'fake-1'\n",
        encoding="utf-8",
    )

    queue = build_workspace_queue(tmp_path)
    degraded_names = {d.name for d in queue.degraded}
    assert "missing_db" in degraded_names


# ---------- Schema version guard ----------


def test_workspace_queue_needs_upgrade_degraded(tmp_path: Path) -> None:
    from tests.unit.services.test_workspace_index import _create_v8_project

    _create_v8_project(tmp_path, "legacy")
    initialize_project(FIXTURE_EPUB, cwd=tmp_path, project_name="modern")

    queue = build_workspace_queue(tmp_path)
    degraded = {d.name: d.state for d in queue.degraded}
    assert degraded.get("legacy") == "needs_upgrade"
    assert "modern" not in degraded


# ---------- Identity conflict ----------


def test_workspace_queue_identity_conflict_degraded(tmp_path: Path) -> None:
    initialize_project(FIXTURE_EPUB, cwd=tmp_path, project_name="original")

    copy_dir = tmp_path / ".weaver" / "duplicate"
    (tmp_path / ".weaver" / "original").replace(copy_dir)
    import shutil

    shutil.copytree(copy_dir, tmp_path / ".weaver" / "original", dirs_exist_ok=True)

    queue = build_workspace_queue(tmp_path)
    degraded_states = {d.name: d.state for d in queue.degraded}
    assert degraded_states.get("original") == "identity_conflict"
    assert degraded_states.get("duplicate") == "identity_conflict"


# ---------- No-write regression ----------


def test_workspace_queue_does_not_modify_database(tmp_path: Path) -> None:
    initialize_project(FIXTURE_EPUB, cwd=tmp_path, project_name="readonly")

    db_path = tmp_path / ".weaver" / "readonly" / "weaver.db"
    mtime_before = db_path.stat().st_mtime_ns
    size_before = db_path.stat().st_size

    build_workspace_queue(tmp_path)

    mtime_after = db_path.stat().st_mtime_ns
    size_after = db_path.stat().st_size

    assert mtime_after == mtime_before
    assert size_after == size_before


# ---------- Bounded reads ----------


def test_workspace_queue_bounded_per_project(tmp_path: Path) -> None:
    initialize_project(FIXTURE_EPUB, cwd=tmp_path, project_name="bounded")

    db_path = tmp_path / ".weaver" / "bounded" / "weaver.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    for i in range(25):
        _insert_job(
            conn,
            f"job-{i:02d}",
            "done",
            f"2025-06-10T{9 + i // 60:02d}:{i % 60:02d}:00+00:00",
        )
    conn.commit()
    conn.close()

    queue = build_workspace_queue(tmp_path)
    project_jobs = [j for j in queue.jobs if j.project_name == "bounded"]
    assert len(project_jobs) == 20
