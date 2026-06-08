"""Tests for cold-start job recovery (Sprint I3 — ADR 010)."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from weaver.api.app import create_api_app
from weaver.services.job_store import (
    get_job,
    list_events_after,
    recover_all_projects,
    recover_interrupted_jobs,
)
from weaver.services.project_paths import resolve_database_path
from weaver.storage.db import connect_database


def _seed_running_job(connection: sqlite3.Connection, *, job_id: str, project_name: str) -> None:
    connection.execute(
        """
        INSERT INTO jobs (
            id, kind, project_name, scope, scope_id, chapter_id,
            status, mode, target, total_units, done_units, failed_units,
            skipped_units, current_label, result_json, error_summary,
            started_at, finished_at
        )
        VALUES (?, 'translate', ?, 'chapter', NULL, 'ch1',
                'running', 'skip_existing', NULL, 10, 5, 0, 0,
                NULL, NULL, NULL, '2026-06-08T00:00:00+00:00', NULL)
        """,
        (job_id, project_name),
    )
    connection.commit()


@pytest.fixture
def project_dir(tmp_path: Path) -> tuple[Path, Path]:
    from weaver.services.project import initialize_project

    fixtures = Path(__file__).parent.parent.parent / "fixtures"
    epubs = list(fixtures.glob("*.epub"))
    if not epubs:
        pytest.skip("no EPUB fixture available")
    result = initialize_project(epubs[0], cwd=tmp_path)
    return tmp_path, resolve_database_path(result.project_toml, cwd=tmp_path)


def test_recover_interrupted_jobs_marks_running_as_failed(project_dir) -> None:
    _, db_path = project_dir
    with closing(connect_database(db_path)) as connection:
        _seed_running_job(connection, job_id="ghost-1", project_name="any")

    with closing(connect_database(db_path)) as connection:
        ids = recover_interrupted_jobs(connection)

    assert ids == ["ghost-1"]

    with closing(connect_database(db_path)) as connection:
        row = get_job(connection, job_id="ghost-1")
        events = list_events_after(connection, job_id="ghost-1")

    assert row is not None
    assert row.status == "failed"
    assert row.error_summary == "process restart"
    assert row.finished_at is not None
    # The recovery emits one stable event so SSE replay can show the failure.
    recovered_events = [e for e in events if e.event == "recovered"]
    assert len(recovered_events) == 1
    assert recovered_events[0].data == {"reason": "process restart"}


def test_recover_is_idempotent(project_dir) -> None:
    _, db_path = project_dir
    with closing(connect_database(db_path)) as connection:
        _seed_running_job(connection, job_id="ghost-2", project_name="any")

    with closing(connect_database(db_path)) as connection:
        first = recover_interrupted_jobs(connection)
    with closing(connect_database(db_path)) as connection:
        second = recover_interrupted_jobs(connection)

    assert first == ["ghost-2"]
    assert second == []  # no rows left in `running`


def test_recover_does_not_resume_execution(project_dir) -> None:
    """Cold-start MUST NOT spawn a new worker for a recovered job."""
    base_dir, db_path = project_dir
    with closing(connect_database(db_path)) as connection:
        _seed_running_job(connection, job_id="ghost-3", project_name="any")

    client = TestClient(create_api_app(base_dir))
    # Registry has zero in-memory jobs even though the DB had a running row.
    assert len(client.app.state.jobs._jobs) == 0  # type: ignore[attr-defined]
    assert len(client.app.state.jobs._batch_jobs) == 0  # type: ignore[attr-defined]
    assert len(client.app.state.jobs._export_jobs) == 0  # type: ignore[attr-defined]

    with closing(connect_database(db_path)) as connection:
        row = get_job(connection, job_id="ghost-3")
    assert row is not None
    assert row.status == "failed"  # marked failed by the cold-start pass


def test_recover_walks_all_projects(tmp_path: Path) -> None:
    from weaver.services.project import initialize_project

    fixtures = Path(__file__).parent.parent.parent / "fixtures"
    epubs = list(fixtures.glob("*.epub"))
    if not epubs:
        pytest.skip("no EPUB fixture available")
    init = initialize_project(epubs[0], cwd=tmp_path)
    db_path = resolve_database_path(init.project_toml, cwd=tmp_path)
    with closing(connect_database(db_path)) as connection:
        _seed_running_job(connection, job_id="walk-1", project_name=init.project_name)
        _seed_running_job(connection, job_id="walk-2", project_name=init.project_name)

    summary = recover_all_projects(tmp_path)
    assert summary == {init.project_name: 2}


def test_app_factory_runs_cold_start_recovery(project_dir) -> None:
    base_dir, db_path = project_dir
    with closing(connect_database(db_path)) as connection:
        _seed_running_job(connection, job_id="boot-1", project_name="any")

    create_api_app(base_dir)

    with closing(connect_database(db_path)) as connection:
        row = get_job(connection, job_id="boot-1")
    assert row is not None
    assert row.status == "failed"
    assert row.error_summary == "process restart"
