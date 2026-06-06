"""Tests for the FastAPI translate/retranslate + export job UI (Stage 11B-3)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from weaver.api.app import create_api_app


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
    # terminal panel no longer self-polls
    assert "hx-trigger" not in panel


def test_terminal_translate_job_signals_grid_refresh(jobs_client: TestClient) -> None:
    # A finished translate job tells the workspace grid to refresh itself once,
    # via a response header (not an hx-trigger in the still-quiet panel).
    name = _name(jobs_client)
    cid = _first_chapter(jobs_client, name)
    jobs_client.post(f"/ui/projects/{name}/chapters/{cid}/translate")
    job_id = next(iter(jobs_client.app.state.jobs._jobs))  # type: ignore[attr-defined]
    assert _wait_terminal(jobs_client, f"/projects/{name}/jobs/{job_id}") == "done"

    r = jobs_client.get(f"/ui/projects/{name}/jobs/{job_id}")
    assert r.headers.get("HX-Trigger") == "refreshGrid"
    assert "hx-trigger" not in r.text


def test_workspace_grid_listens_for_refresh(jobs_client: TestClient) -> None:
    name = _name(jobs_client)
    cid = _first_chapter(jobs_client, name)
    page = jobs_client.get(f"/ui/projects/{name}/chapters/{cid}").text
    assert 'id="ws-grid"' in page
    assert "refreshGrid from:body" in page


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
