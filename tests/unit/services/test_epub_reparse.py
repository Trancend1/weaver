"""Tests for the parse-job + reparse service (Sprint J3)."""

from __future__ import annotations

from contextlib import closing
from pathlib import Path

import pytest

from weaver.api.jobs import (
    JOB_KIND_PARSE,
    JobRegistry,
    ParseJob,
    ParseResult,
)
from weaver.services.epub_reparse import reparse_volume, status_for_volume
from weaver.services.epub_snapshot import read_snapshot
from weaver.services.job_store import get_job, list_events_after, recover_interrupted_jobs
from weaver.services.project import initialize_project
from weaver.services.project_paths import resolve_database_path
from weaver.storage.db import connect_database


@pytest.fixture
def project_with_volume(tmp_path: Path):
    fixtures = Path(__file__).parent.parent.parent / "fixtures"
    epubs = list(fixtures.glob("*.epub"))
    if not epubs:
        pytest.skip("no EPUB fixture available")
    init = initialize_project(epubs[0], cwd=tmp_path)
    db_path = resolve_database_path(init.project_toml, cwd=tmp_path)
    with closing(connect_database(db_path)) as connection:
        row = connection.execute("SELECT id FROM volumes ORDER BY id LIMIT 1").fetchone()
        volume_id = int(row["id"])
    return tmp_path, init.project_toml, init.project_name, db_path, volume_id


def test_reparse_volume_writes_fresh_snapshot(project_with_volume) -> None:
    tmp_path, project_toml, _name, db_path, volume_id = project_with_volume

    status = reparse_volume(project_toml, volume_id, cwd=tmp_path)
    assert status.state == "fresh"
    assert status.is_fresh is True

    parsed = read_snapshot(db_path, volume_id)
    assert parsed is not None
    assert parsed.metadata.title  # round-trip preserved


def test_status_reports_missing_when_never_reparsed(project_with_volume) -> None:
    tmp_path, project_toml, _name, _db_path, volume_id = project_with_volume
    status = status_for_volume(project_toml, volume_id, cwd=tmp_path)
    assert status.state == "missing"


def test_reparse_volume_rejects_unknown_volume(project_with_volume) -> None:
    tmp_path, project_toml, _name, _db_path, _volume_id = project_with_volume
    from weaver.errors import VolumeNotFoundError

    with pytest.raises(VolumeNotFoundError):
        reparse_volume(project_toml, 999_999, cwd=tmp_path)


def test_parse_job_persists_terminal_row_and_event_log(project_with_volume) -> None:
    tmp_path, project_toml, name, db_path, volume_id = project_with_volume
    registry = JobRegistry(base_dir=tmp_path)

    def runner(should_cancel):
        # Run the real reparse so the snapshot row lands too.
        status = reparse_volume(project_toml, volume_id, cwd=tmp_path)
        return ParseResult(
            volume_id=volume_id,
            source_hash=status.source_hash or "",
            parser_version=status.parser_version or 0,
            manifest_count=0,
            spine_count=0,
            nav_count=0,
            image_count=0,
            validation_count=0,
        )

    job = registry.submit_parse(project_name=name, volume_id=volume_id, runner=runner)
    job.wait(timeout=10)

    assert isinstance(job, ParseJob)
    assert job.status == "done"
    with closing(connect_database(db_path)) as connection:
        row = get_job(connection, job_id=job.id)
        events = list_events_after(connection, job_id=job.id)
    assert row is not None
    assert row.kind == JOB_KIND_PARSE
    assert row.scope == "volume"
    assert row.scope_id == str(volume_id)
    assert row.status == "done"
    assert row.finished_at is not None
    assert row.result_json is not None  # terminal payload persisted
    assert events  # at least the terminal event landed
    assert any(e.event == "done" for e in events)


def test_parse_job_cold_start_recovery_marks_running_as_failed(
    project_with_volume,
) -> None:
    tmp_path, project_toml, _name, db_path, volume_id = project_with_volume
    # Seed a fake `running` parse row directly.
    with closing(connect_database(db_path)) as connection:
        connection.execute(
            """
            INSERT INTO jobs (
                id, kind, project_name, scope, scope_id, chapter_id,
                status, mode, target, total_units, done_units, failed_units,
                skipped_units, current_label, result_json, error_summary,
                started_at, finished_at
            )
            VALUES ('parse-ghost', 'parse', 'irrelevant', 'volume', ?, NULL,
                    'running', NULL, NULL, 1, 0, 0, 0, NULL, NULL, NULL,
                    '2026-06-08T00:00:00+00:00', NULL)
            """,
            (str(volume_id),),
        )
        connection.commit()

    with closing(connect_database(db_path)) as connection:
        recovered = recover_interrupted_jobs(connection)
    assert "parse-ghost" in recovered

    with closing(connect_database(db_path)) as connection:
        row = get_job(connection, job_id="parse-ghost")
    assert row is not None
    assert row.status == "failed"
    assert row.error_summary == "process restart"
    # Sprint I invariant: no auto-resume for any kind.
    _ = project_toml  # silence unused
