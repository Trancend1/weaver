"""Tests for the persistent JobRegistry (Sprint I2 — ADR 010)."""

from __future__ import annotations

import threading
from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from weaver.api.app import create_api_app
from weaver.services.job_store import (
    get_job,
    list_events_after,
    list_jobs_for_project,
)
from weaver.services.project_paths import resolve_database_path
from weaver.storage.db import connect_database


@pytest.fixture
def client_with_projects(tmp_path: Path) -> TestClient:
    from weaver.services.project import initialize_project

    fixtures = Path(__file__).parent.parent.parent / "fixtures"
    epubs = list(fixtures.glob("*.epub"))
    if not epubs:
        pytest.skip("no EPUB fixture available")
    initialize_project(epubs[0], cwd=tmp_path)
    return TestClient(create_api_app(tmp_path))


def _project(client: TestClient) -> str:
    return client.get("/projects").json()["projects"][0]["name"]


def _chapter(client: TestClient, name: str) -> str:
    return client.get(f"/projects/{name}/tree").json()["volumes"][0]["chapters"][0]["id"]


def _open(client: TestClient, name: str):
    base = client.app.state.base_dir  # type: ignore[attr-defined]
    project_toml = base / ".weaver" / name / "project.toml"
    return closing(connect_database(resolve_database_path(project_toml, cwd=base)))


def _wait_terminal(client: TestClient, name: str, job_id: str, *, tries: int = 200) -> str:
    for _ in range(tries):
        body = client.get(f"/projects/{name}/jobs/{job_id}").json()
        if body["status"] in {"done", "failed", "cancelled"}:
            return body["status"]
        threading.Event().wait(0.05)
    msg = "job did not finish in time"
    raise AssertionError(msg)


FAKE_BODY = {"provider": "fake", "model": "fake-1"}


def test_translate_job_is_persisted_with_terminal_row(client_with_projects: TestClient) -> None:
    name = _project(client_with_projects)
    chapter_id = _chapter(client_with_projects, name)
    job_id = client_with_projects.post(
        f"/projects/{name}/chapters/{chapter_id}/translate", json=FAKE_BODY
    ).json()["job_id"]

    _wait_terminal(client_with_projects, name, job_id)

    with _open(client_with_projects, name) as conn:
        row = get_job(conn, job_id=job_id)

    assert row is not None
    assert row.kind == "translate"
    assert row.project_name == name
    assert row.chapter_id == chapter_id
    assert row.status in {"done", "cancelled"}
    assert row.finished_at is not None
    assert row.result_json is not None  # terminal payload persisted before terminal SSE


def test_persisted_events_replay_progress_then_terminal(client_with_projects: TestClient) -> None:
    name = _project(client_with_projects)
    chapter_id = _chapter(client_with_projects, name)
    job_id = client_with_projects.post(
        f"/projects/{name}/chapters/{chapter_id}/translate", json=FAKE_BODY
    ).json()["job_id"]

    _wait_terminal(client_with_projects, name, job_id)

    with _open(client_with_projects, name) as conn:
        events = list_events_after(conn, job_id=job_id)

    assert events, "no events were persisted"
    progress_events = [e for e in events if e.event == "progress"]
    terminal_events = [e for e in events if e.event in {"done", "failed", "cancelled"}]
    assert progress_events
    assert len(terminal_events) == 1
    # IDs increase monotonically — required for SSE Last-Event-Id resume.
    assert [e.id for e in events] == sorted(e.id for e in events)


def test_jobs_table_lists_recent_jobs_newest_first(client_with_projects: TestClient) -> None:
    name = _project(client_with_projects)
    chapter_id = _chapter(client_with_projects, name)
    first = client_with_projects.post(
        f"/projects/{name}/chapters/{chapter_id}/translate", json=FAKE_BODY
    ).json()["job_id"]
    _wait_terminal(client_with_projects, name, first)
    second = client_with_projects.post(
        f"/projects/{name}/chapters/{chapter_id}/translate",
        json={**FAKE_BODY, "mode": "force_selected"},
    ).json()["job_id"]
    _wait_terminal(client_with_projects, name, second)

    with _open(client_with_projects, name) as conn:
        rows = list_jobs_for_project(conn)

    persisted_ids = [row.id for row in rows]
    assert first in persisted_ids
    assert second in persisted_ids
    # Newest job first — ADR 010 §I2 (started_at DESC).
    assert persisted_ids.index(second) <= persisted_ids.index(first)


def test_storage_disabled_when_registry_has_no_base_dir(tmp_path: Path) -> None:
    # In-memory tests still work — no DB writes, no errors.
    from weaver.api.jobs import JobRegistry, JobStorage

    registry = JobRegistry(base_dir=None)
    assert registry.base_dir is None
    storage = registry._storage_for("any-project", "abc123")  # type: ignore[attr-defined]
    assert isinstance(storage, JobStorage)
    assert storage.enabled is False
    # Calls on a disabled storage are no-ops, never raise.
    storage.insert(
        kind="translate",
        project_name="any",
        scope=None,
        scope_id=None,
        chapter_id=None,
        mode=None,
        target=None,
        total_units=0,
    )
    storage.flush_progress(done_units=0, failed_units=0)
    storage.append_event(event="progress", data={})
    storage.finish(status="done", result=None, error_summary=None)
