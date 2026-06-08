"""Tests for the unified Job Detail UI + JSON endpoints (Sprint I5/I6)."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from weaver.api.app import create_api_app

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


def _wait_terminal(client: TestClient, name: str, job_id: str, *, tries: int = 200) -> None:
    for _ in range(tries):
        body = client.get(f"/projects/{name}/jobs/{job_id}/detail").json()
        if body["job"]["status"] in {"done", "failed", "cancelled"}:
            return
        time.sleep(0.05)
    msg = "job did not finish in time"
    raise AssertionError(msg)


def test_jobs_list_endpoint_returns_persisted_rows_newest_first(
    client_with_projects: TestClient,
) -> None:
    name = _project(client_with_projects)
    chapter_id = _chapter(client_with_projects, name)
    first = client_with_projects.post(
        f"/projects/{name}/chapters/{chapter_id}/translate", json=FAKE_BODY
    ).json()["job_id"]
    _wait_terminal(client_with_projects, name, first)

    body = client_with_projects.get(f"/projects/{name}/jobs").json()
    assert body["jobs"]
    summary = body["jobs"][0]
    assert summary["id"] == first
    assert summary["kind"] == "translate"
    assert summary["status"] in {"done", "failed", "cancelled"}
    assert summary["chapter_id"] == chapter_id


def test_job_detail_endpoint_returns_job_and_events(
    client_with_projects: TestClient,
) -> None:
    name = _project(client_with_projects)
    chapter_id = _chapter(client_with_projects, name)
    job_id = client_with_projects.post(
        f"/projects/{name}/chapters/{chapter_id}/translate", json=FAKE_BODY
    ).json()["job_id"]
    _wait_terminal(client_with_projects, name, job_id)

    body = client_with_projects.get(f"/projects/{name}/jobs/{job_id}/detail").json()
    assert body["job"]["id"] == job_id
    assert body["events"]
    # Replay surface uses the same event-id ordering as SSE.
    ids = [event["id"] for event in body["events"]]
    assert ids == sorted(ids)
    # Result payload survives the trip back through SQLite.
    assert body["result"] is not None


def test_job_detail_endpoint_404_for_unknown_job(client_with_projects: TestClient) -> None:
    name = _project(client_with_projects)
    response = client_with_projects.get(f"/projects/{name}/jobs/nope/detail")
    assert response.status_code == 404


def test_jobs_list_endpoint_404_for_unknown_project(client_with_projects: TestClient) -> None:
    response = client_with_projects.get("/projects/no-such-project/jobs")
    assert response.status_code == 404


def test_ui_jobs_list_renders_all_jobs(client_with_projects: TestClient) -> None:
    name = _project(client_with_projects)
    chapter_id = _chapter(client_with_projects, name)
    client_with_projects.post(f"/projects/{name}/chapters/{chapter_id}/translate", json=FAKE_BODY)
    # No need to wait for terminal — the row exists in `running` immediately.
    page = client_with_projects.get(f"/ui/projects/{name}/jobs").text
    assert page.count('class="jobs-row') >= 1
    assert "job-status--" in page


def test_ui_job_detail_renders_status_progress_and_events(
    client_with_projects: TestClient,
) -> None:
    name = _project(client_with_projects)
    chapter_id = _chapter(client_with_projects, name)
    job_id = client_with_projects.post(
        f"/projects/{name}/chapters/{chapter_id}/translate", json=FAKE_BODY
    ).json()["job_id"]
    _wait_terminal(client_with_projects, name, job_id)

    page = client_with_projects.get(f"/ui/projects/{name}/jobs/{job_id}/detail").text
    assert "Event log" in page
    assert "job-status--" in page
    assert job_id[:8] in page


def test_ui_job_detail_running_panel_polls_for_refresh(
    client_with_projects: TestClient,
) -> None:
    """A running job's detail page wires a 1-second hx-get refresh."""
    name = _project(client_with_projects)
    chapter_id = _chapter(client_with_projects, name)
    release = threading.Event()

    from weaver.services.workspace_translate import ChapterTranslationResult

    def runner(should_cancel, progress):
        release.wait(timeout=5)
        return ChapterTranslationResult(
            chapter_id=chapter_id,
            selected=0,
            translated=0,
            reused_from_memory=0,
            failed=0,
            skipped=0,
            input_tokens=0,
            output_tokens=0,
            cancelled=False,
        )

    job = client_with_projects.app.state.jobs.submit(  # type: ignore[attr-defined]
        project_name=name,
        chapter_id=chapter_id,
        mode="chapter",
        total=1,
        runner=runner,
    )
    try:
        page = client_with_projects.get(f"/ui/projects/{name}/jobs/{job.id}/detail").text
        assert 'hx-trigger="every 1s"' in page
        assert "Cancel" in page
    finally:
        release.set()
        job.wait(timeout=5)


def test_ui_jobs_link_visible_in_project_subnav(client_with_projects: TestClient) -> None:
    name = _project(client_with_projects)
    page = client_with_projects.get(f"/ui/projects/{name}").text
    assert f"/ui/projects/{name}/jobs" in page
