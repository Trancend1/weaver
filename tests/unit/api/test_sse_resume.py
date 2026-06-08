"""Tests for SSE Last-Event-Id resume (Sprint I4 — ADR 010)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from weaver.api.app import create_api_app
from weaver.api.jobs import parse_last_event_id

FAKE_BODY = {"provider": "fake", "model": "fake-1"}


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


_ID_LINE = re.compile(r"^id:\s*(\d+)$", re.MULTILINE)
_EVENT_LINE = re.compile(r"^event:\s*(\S+)$", re.MULTILINE)


def _parse_stream(body: str) -> list[tuple[int, str]]:
    """Return (id, event_name) pairs in stream order."""
    pairs: list[tuple[int, str]] = []
    for chunk in body.split("\n\n"):
        if not chunk.strip():
            continue
        id_match = _ID_LINE.search(chunk)
        event_match = _EVENT_LINE.search(chunk)
        if event_match is None:
            continue
        ev = event_match.group(1)
        if id_match is None:
            continue  # only counted-id frames participate in resume
        pairs.append((int(id_match.group(1)), ev))
    return pairs


def test_parse_last_event_id_handles_garbage() -> None:
    assert parse_last_event_id(None) == 0
    assert parse_last_event_id("") == 0
    assert parse_last_event_id("   ") == 0
    assert parse_last_event_id("abc") == 0
    assert parse_last_event_id("-5") == 0
    assert parse_last_event_id("3") == 3
    assert parse_last_event_id("  9 ") == 9


def test_translate_stream_emits_id_lines(client_with_projects: TestClient) -> None:
    name = _project(client_with_projects)
    cid = _chapter(client_with_projects, name)
    job_id = client_with_projects.post(
        f"/projects/{name}/chapters/{cid}/translate", json=FAKE_BODY
    ).json()["job_id"]

    body = client_with_projects.get(f"/projects/{name}/jobs/{job_id}/events").text
    pairs = _parse_stream(body)
    assert pairs, "stream had no id-tagged frames"
    # IDs strictly increase.
    ids = [p[0] for p in pairs]
    assert ids == sorted(ids)
    assert len(set(ids)) == len(ids)
    # At least one progress and exactly one terminal event.
    events = [p[1] for p in pairs]
    assert "progress" in events
    terminals = [e for e in events if e in {"done", "failed", "cancelled"}]
    assert len(terminals) == 1


def test_translate_stream_resumes_from_last_event_id_via_query(
    client_with_projects: TestClient,
) -> None:
    name = _project(client_with_projects)
    cid = _chapter(client_with_projects, name)
    job_id = client_with_projects.post(
        f"/projects/{name}/chapters/{cid}/translate", json=FAKE_BODY
    ).json()["job_id"]

    full = _parse_stream(client_with_projects.get(f"/projects/{name}/jobs/{job_id}/events").text)
    assert len(full) >= 2

    cutoff = full[0][0]  # resume after the very first event
    body = client_with_projects.get(
        f"/projects/{name}/jobs/{job_id}/events?last_event_id={cutoff}"
    ).text
    resumed = _parse_stream(body)

    # Every resumed id is strictly greater than the cutoff.
    assert all(event_id > cutoff for event_id, _ in resumed)
    # No event id appears twice in the resumed stream (de-dupe with seen set).
    ids = [event_id for event_id, _ in resumed]
    assert len(set(ids)) == len(ids)
    # The terminal frame is still delivered.
    assert any(name_ in {"done", "failed", "cancelled"} for _, name_ in resumed)


def test_translate_stream_resumes_via_last_event_id_header(
    client_with_projects: TestClient,
) -> None:
    name = _project(client_with_projects)
    cid = _chapter(client_with_projects, name)
    job_id = client_with_projects.post(
        f"/projects/{name}/chapters/{cid}/translate", json=FAKE_BODY
    ).json()["job_id"]
    full = _parse_stream(client_with_projects.get(f"/projects/{name}/jobs/{job_id}/events").text)
    cutoff = full[0][0]

    body = client_with_projects.get(
        f"/projects/{name}/jobs/{job_id}/events",
        headers={"Last-Event-Id": str(cutoff)},
    ).text
    resumed = _parse_stream(body)
    assert all(event_id > cutoff for event_id, _ in resumed)


def test_finished_job_replays_full_log_from_sqlite(
    client_with_projects: TestClient,
) -> None:
    """A finished job's events MUST replay from SQLite, not just from queue."""
    name = _project(client_with_projects)
    cid = _chapter(client_with_projects, name)
    job_id = client_with_projects.post(
        f"/projects/{name}/chapters/{cid}/translate", json=FAKE_BODY
    ).json()["job_id"]

    # Drain the live stream once (consumes the in-memory queue end-to-end).
    first = client_with_projects.get(f"/projects/{name}/jobs/{job_id}/events").text
    assert "event: done" in first or "event: cancelled" in first

    # Reconnect with no Last-Event-Id — must still replay the full persisted
    # log (queue is empty, so without persistence we'd hang or get nothing).
    second = client_with_projects.get(f"/projects/{name}/jobs/{job_id}/events?last_event_id=0").text
    pairs = _parse_stream(second)
    assert pairs
    assert pairs == sorted(pairs, key=lambda p: p[0])
