"""Tests for the FastAPI translate/retranslate + export job UI (Stage 11B-3)."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from weaver.api.app import create_api_app
from weaver.services.chapter_workspace import chapter_workspace
from weaver.services.project_discovery import find_project
from weaver.services.workspace_translate import ChapterTranslationResult
from weaver.storage.segments import SegmentRecord


@pytest.fixture
def jobs_client(tmp_path: Path) -> TestClient:
    from weaver.services.project import initialize_project

    fixtures = Path(__file__).parent.parent.parent / "fixtures"
    epubs = list(fixtures.glob("*.epub"))
    if not epubs:
        pytest.skip("no EPUB fixture available")
    init = initialize_project(epubs[0], cwd=tmp_path)
    toml = Path(init.project_toml)
    toml.write_text(
        toml.read_text(encoding="utf-8").replace('type = "deepseek"', 'type = "fake"'),
        encoding="utf-8",
    )
    return TestClient(create_api_app(tmp_path))


def _name(client: TestClient) -> str:
    return client.get("/projects").json()["projects"][0]["name"]


def _first_chapter(client: TestClient, name: str) -> str:
    return client.get(f"/projects/{name}/tree").json()["volumes"][0]["chapters"][0]["id"]


def _wait_terminal(client: TestClient, url: str, *, tries: int = 200) -> str:
    for _ in range(tries):
        status = client.get(url).json()["status"]
        if status != "running":
            return status
        time.sleep(0.02)
    return "running"


def _first_segment_record(client: TestClient, name: str, chapter_id: str) -> SegmentRecord:
    dp = find_project(client.app.state.base_dir, name)  # type: ignore[attr-defined]
    assert dp is not None
    ws = chapter_workspace(dp.project_toml, chapter_id, cwd=client.app.state.base_dir)  # type: ignore[attr-defined]
    seg = ws.segments[0]
    return SegmentRecord(
        id=seg.id,
        chapter_id=chapter_id,
        block_order=0,
        kind=seg.kind,
        source_text=seg.source_text,
        source_hash="test",
        status=seg.status,
    )


def _translation_result(chapter_id: str) -> ChapterTranslationResult:
    return ChapterTranslationResult(
        chapter_id=chapter_id,
        selected=1,
        translated=1,
        reused_from_memory=0,
        failed=0,
        skipped=0,
        input_tokens=0,
        output_tokens=0,
        cancelled=False,
    )


# --- translate --------------------------------------------------------------


def test_translate_button_starts_job_and_renders_panel(jobs_client: TestClient) -> None:
    name = _name(jobs_client)
    cid = _first_chapter(jobs_client, name)
    r = jobs_client.post(f"/ui/projects/{name}/chapters/{cid}/translate")
    assert r.status_code == 200
    assert 'id="job-panel"' in r.text
    assert "Translate" in r.text


def test_translate_job_progresses_to_done_with_result(jobs_client: TestClient) -> None:
    name = _name(jobs_client)
    cid = _first_chapter(jobs_client, name)
    jobs_client.post(f"/ui/projects/{name}/chapters/{cid}/translate")
    job_id = next(iter(jobs_client.app.state.jobs._jobs))  # type: ignore[attr-defined]

    assert _wait_terminal(jobs_client, f"/projects/{name}/jobs/{job_id}") == "done"
    panel = jobs_client.get(f"/ui/projects/{name}/jobs/{job_id}").text
    assert "done" in panel
    assert "translated" in panel
    assert "load delay:500ms" not in panel


def test_running_translate_job_updates_only_changed_segment(jobs_client: TestClient) -> None:
    name = _name(jobs_client)
    cid = _first_chapter(jobs_client, name)
    segment = _first_segment_record(jobs_client, name, cid)
    release = threading.Event()

    def runner(should_cancel, progress):
        release.wait(timeout=5)
        return _translation_result(cid)

    job = jobs_client.app.state.jobs.submit(  # type: ignore[attr-defined]
        project_name=name,
        chapter_id=cid,
        mode="chapter",
        total=1,
        runner=runner,
    )
    job.on_progress(1, 1, segment, True, None, None)
    try:
        r = jobs_client.get(f"/ui/projects/{name}/jobs/{job.id}")
        assert r.headers.get("HX-Trigger") is None
        assert "load delay:500ms" in r.text
        assert 'id="ws-grid"' not in r.text
        assert f'id="seg-{segment.id}"' in r.text
        assert 'hx-swap-oob="outerHTML"' in r.text
    finally:
        release.set()
        job.wait(timeout=5)


def test_terminal_translate_job_does_not_force_grid_refresh(jobs_client: TestClient) -> None:
    name = _name(jobs_client)
    cid = _first_chapter(jobs_client, name)
    jobs_client.post(f"/ui/projects/{name}/chapters/{cid}/translate")
    job_id = next(iter(jobs_client.app.state.jobs._jobs))  # type: ignore[attr-defined]
    assert _wait_terminal(jobs_client, f"/projects/{name}/jobs/{job_id}") == "done"

    r = jobs_client.get(f"/ui/projects/{name}/jobs/{job_id}")
    assert r.headers.get("HX-Trigger") is None
    assert "load delay:500ms" not in r.text
    assert 'id="ws-grid"' not in r.text


def test_workspace_grid_listens_for_refresh(jobs_client: TestClient) -> None:
    name = _name(jobs_client)
    cid = _first_chapter(jobs_client, name)
    page = jobs_client.get(f"/ui/projects/{name}/chapters/{cid}").text
    assert 'id="ws-grid"' in page
    assert "refreshGrid from:body" in page


def test_workspace_reattaches_running_job_without_nested_panel(jobs_client: TestClient) -> None:
    name = _name(jobs_client)
    cid = _first_chapter(jobs_client, name)
    release = threading.Event()

    def runner(should_cancel, progress):
        release.wait(timeout=5)
        return _translation_result(cid)

    job = jobs_client.app.state.jobs.submit(  # type: ignore[attr-defined]
        project_name=name,
        chapter_id=cid,
        mode="chapter",
        total=1,
        runner=runner,
    )
    try:
        page = jobs_client.get(f"/ui/projects/{name}/chapters/{cid}").text
        assert page.count('id="job-panel"') == 1
        assert f"/ui/projects/{name}/jobs/{job.id}" in page
        assert "load delay:500ms" in page
        panel = jobs_client.get(f"/ui/projects/{name}/chapters/{cid}/running-job").text
        assert f"/ui/projects/{name}/jobs/{job.id}" in panel
        assert 'id="ws-grid"' not in panel
    finally:
        release.set()
        job.wait(timeout=5)


def test_translate_unhealthy_provider_renders_error(tmp_path: Path) -> None:
    # project left on the default (deepseek) provider with no key → 502 → error panel
    from weaver.services.project import initialize_project

    fixtures = Path(__file__).parent.parent.parent / "fixtures"
    epubs = list(fixtures.glob("*.epub"))
    if not epubs:
        pytest.skip("no EPUB fixture available")
    initialize_project(epubs[0], cwd=tmp_path)
    client = TestClient(create_api_app(tmp_path))
    name = _name(client)
    cid = _first_chapter(client, name)
    r = client.post(f"/ui/projects/{name}/chapters/{cid}/translate")
    assert r.status_code == 200
    assert 'id="job-panel"' in r.text
    assert "error" in r.text.lower()


# --- retranslate modes ------------------------------------------------------


def test_retranslate_modes_submit(jobs_client: TestClient) -> None:
    name = _name(jobs_client)
    cid = _first_chapter(jobs_client, name)
    # translate first so there is something to re-translate
    jobs_client.post(f"/ui/projects/{name}/chapters/{cid}/translate")
    first = next(iter(jobs_client.app.state.jobs._jobs))  # type: ignore[attr-defined]
    _wait_terminal(jobs_client, f"/projects/{name}/jobs/{first}")

    for mode in ("skip_existing", "retranslate_non_manual", "force_selected"):
        r = jobs_client.post(f"/ui/projects/{name}/chapters/{cid}/retranslate", data={"mode": mode})
        # each valid mode is accepted by the service and starts a job panel
        assert r.status_code == 200
        assert 'id="job-panel"' in r.text
        job_id = list(jobs_client.app.state.jobs._jobs)[-1]  # type: ignore[attr-defined]
        assert _wait_terminal(jobs_client, f"/projects/{name}/jobs/{job_id}") in {
            "done",
            "cancelled",
        }


def test_retranslate_invalid_mode_errors(jobs_client: TestClient) -> None:
    name = _name(jobs_client)
    cid = _first_chapter(jobs_client, name)
    r = jobs_client.post(f"/ui/projects/{name}/chapters/{cid}/retranslate", data={"mode": "bogus"})
    assert r.status_code == 200
    assert "error" in r.text.lower()


def test_workspace_renders_translate_controls(jobs_client: TestClient) -> None:
    name = _name(jobs_client)
    cid = _first_chapter(jobs_client, name)
    page = jobs_client.get(f"/ui/projects/{name}/chapters/{cid}").text
    assert "Translate untranslated" in page
    for mode in ("skip_existing", "retranslate_non_manual", "force_selected"):
        assert mode in page


# --- cancel -----------------------------------------------------------------


def test_cancel_is_safe_and_renders(jobs_client: TestClient) -> None:
    name = _name(jobs_client)
    cid = _first_chapter(jobs_client, name)
    jobs_client.post(f"/ui/projects/{name}/chapters/{cid}/translate")
    job_id = next(iter(jobs_client.app.state.jobs._jobs))  # type: ignore[attr-defined]
    r = jobs_client.post(f"/ui/projects/{name}/jobs/{job_id}/cancel")
    assert r.status_code == 200
    assert 'id="job-panel"' in r.text
    # job reaches a terminal state (done or cancelled depending on timing)
    assert _wait_terminal(jobs_client, f"/projects/{name}/jobs/{job_id}") in {"done", "cancelled"}


def test_cancel_unknown_job_404(jobs_client: TestClient) -> None:
    name = _name(jobs_client)
    assert jobs_client.post(f"/ui/projects/{name}/jobs/ghost/cancel").status_code == 404


# --- export -----------------------------------------------------------------


def test_project_page_has_export_controls(jobs_client: TestClient) -> None:
    name = _name(jobs_client)
    page = jobs_client.get(f"/ui/projects/{name}").text
    assert "Export novel" in page
    for target in ("epub", "txt", "html", "docx"):
        assert f'value="{target}"' in page


@pytest.mark.parametrize("target", ["epub", "txt", "html", "docx"])
def test_export_starts_job_and_renders_artifacts(jobs_client: TestClient, target: str) -> None:
    name = _name(jobs_client)
    r = jobs_client.post(f"/ui/projects/{name}/export", data={"target": target})
    assert r.status_code == 200
    assert 'id="export-panel"' in r.text
    job_id = next(iter(jobs_client.app.state.jobs._export_jobs))  # type: ignore[attr-defined]

    assert _wait_terminal(jobs_client, f"/projects/{name}/export/jobs/{job_id}") == "done"
    panel = jobs_client.get(f"/ui/projects/{name}/export/jobs/{job_id}").text
    assert "done" in panel
    assert f".{target}" in panel  # an artifact path with the target extension
    assert "hx-trigger" not in panel


def test_project_page_has_bundle_checkbox(jobs_client: TestClient) -> None:
    name = _name(jobs_client)
    page = jobs_client.get(f"/ui/projects/{name}").text
    assert 'name="bundle"' in page


def test_export_bundle_round_trips_through_ui(jobs_client: TestClient) -> None:
    name = _name(jobs_client)
    r = jobs_client.post(f"/ui/projects/{name}/export", data={"target": "txt", "bundle": "true"})
    assert r.status_code == 200
    job_id = next(iter(jobs_client.app.state.jobs._export_jobs))  # type: ignore[attr-defined]

    assert _wait_terminal(jobs_client, f"/projects/{name}/export/jobs/{job_id}") == "done"
    panel = jobs_client.get(f"/ui/projects/{name}/export/jobs/{job_id}").text
    assert "bundle-txt.zip" in panel


def test_export_cancel_unknown_404(jobs_client: TestClient) -> None:
    name = _name(jobs_client)
    assert jobs_client.post(f"/ui/projects/{name}/export/jobs/ghost/cancel").status_code == 404
