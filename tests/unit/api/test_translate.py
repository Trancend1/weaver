"""Tests for the Stage 4A AI-translation endpoints (chapter / selection / jobs)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from weaver.providers.base import LLMProvider, ProviderStatus
from weaver.providers.registry import register_provider
from weaver.providers.types import TranslationRequest, TranslationResponse

FAKE_BODY = {"provider": "fake", "model": "fake-1"}


class _UnhealthyProvider(LLMProvider):
    name = "unhealthytest"

    def translate(self, request: TranslationRequest) -> TranslationResponse:  # pragma: no cover
        raise NotImplementedError

    def healthcheck(self) -> ProviderStatus:
        return ProviderStatus(
            healthy=False,
            provider_name=self.name,
            model="unhealthy",
            message="provider down",
            latency_ms=0,
        )


register_provider("unhealthytest", lambda config: _UnhealthyProvider())


def _name(client: TestClient) -> str:
    return str(client.get("/projects").json()["projects"][0]["name"])


def _first_chapter(client: TestClient, name: str) -> str:
    tree = client.get(f"/projects/{name}/tree").json()
    return str(tree["volumes"][0]["chapters"][0]["id"])


def _wait(client: TestClient, job_id: str) -> None:
    job = client.app.state.jobs.get(job_id)  # type: ignore[attr-defined]
    assert job is not None
    job.wait(timeout=5)


def test_translate_chapter_starts_job_and_completes(client_with_projects: TestClient) -> None:
    name = _name(client_with_projects)
    chapter_id = _first_chapter(client_with_projects, name)

    resp = client_with_projects.post(
        f"/projects/{name}/chapters/{chapter_id}/translate", json=FAKE_BODY
    )
    assert resp.status_code == 202
    data = resp.json()
    assert data["mode"] == "chapter"
    job_id = data["job_id"]

    _wait(client_with_projects, job_id)
    status = client_with_projects.get(f"/projects/{name}/jobs/{job_id}").json()
    assert status["status"] == "done"
    assert status["result"]["translated"] == status["result"]["selected"]
    assert status["result"]["translated"] > 0
    assert status["error"] is None

    workspace = client_with_projects.get(
        f"/projects/{name}/chapters/{chapter_id}/workspace"
    ).json()
    assert any(seg["translated_text"] for seg in workspace["segments"])


def test_translate_selection_starts_job_and_completes(client_with_projects: TestClient) -> None:
    name = _name(client_with_projects)
    chapter_id = _first_chapter(client_with_projects, name)
    workspace = client_with_projects.get(
        f"/projects/{name}/chapters/{chapter_id}/workspace"
    ).json()
    segment_id = workspace["segments"][0]["id"]

    resp = client_with_projects.post(
        f"/projects/{name}/chapters/{chapter_id}/translate-segments",
        json={"segment_ids": [segment_id], **FAKE_BODY},
    )
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]
    assert resp.json()["mode"] == "selection"

    _wait(client_with_projects, job_id)
    result = client_with_projects.get(f"/projects/{name}/jobs/{job_id}").json()["result"]
    assert result["selected"] == 1
    assert result["translated"] == 1


def test_translate_unknown_project_returns_404(client_with_projects: TestClient) -> None:
    resp = client_with_projects.post("/projects/nope/chapters/ch/translate", json=FAKE_BODY)
    assert resp.status_code == 404


def test_translate_unknown_chapter_returns_404(client_with_projects: TestClient) -> None:
    name = _name(client_with_projects)
    resp = client_with_projects.post(
        f"/projects/{name}/chapters/missing/translate", json=FAKE_BODY
    )
    assert resp.status_code == 404


def test_translate_segments_unknown_segment_returns_404(client_with_projects: TestClient) -> None:
    name = _name(client_with_projects)
    chapter_id = _first_chapter(client_with_projects, name)
    resp = client_with_projects.post(
        f"/projects/{name}/chapters/{chapter_id}/translate-segments",
        json={"segment_ids": ["does-not-exist"], **FAKE_BODY},
    )
    assert resp.status_code == 404


def test_translate_segments_empty_selection_returns_422(client_with_projects: TestClient) -> None:
    name = _name(client_with_projects)
    chapter_id = _first_chapter(client_with_projects, name)
    resp = client_with_projects.post(
        f"/projects/{name}/chapters/{chapter_id}/translate-segments",
        json={"segment_ids": [], **FAKE_BODY},
    )
    assert resp.status_code == 422


def test_unknown_job_returns_404(client_with_projects: TestClient) -> None:
    name = _name(client_with_projects)
    resp = client_with_projects.get(f"/projects/{name}/jobs/deadbeef")
    assert resp.status_code == 404


def test_unhealthy_provider_returns_502(client_with_projects: TestClient) -> None:
    name = _name(client_with_projects)
    chapter_id = _first_chapter(client_with_projects, name)
    resp = client_with_projects.post(
        f"/projects/{name}/chapters/{chapter_id}/translate",
        json={"provider": "unhealthytest", "model": "x"},
    )
    assert resp.status_code == 502


def test_job_status_reports_progress(client_with_projects: TestClient) -> None:
    name = _name(client_with_projects)
    chapter_id = _first_chapter(client_with_projects, name)
    job_id = client_with_projects.post(
        f"/projects/{name}/chapters/{chapter_id}/translate", json=FAKE_BODY
    ).json()["job_id"]
    _wait(client_with_projects, job_id)

    status = client_with_projects.get(f"/projects/{name}/jobs/{job_id}").json()
    progress = status["progress"]
    assert progress["total"] > 0
    assert progress["current"] == progress["total"]
    assert progress["translated"] == status["result"]["translated"]


def test_job_events_stream_emits_progress_then_terminal(client_with_projects: TestClient) -> None:
    name = _name(client_with_projects)
    chapter_id = _first_chapter(client_with_projects, name)
    job_id = client_with_projects.post(
        f"/projects/{name}/chapters/{chapter_id}/translate", json=FAKE_BODY
    ).json()["job_id"]

    # The stream blocks until the worker finishes and pushes the sentinel.
    body = client_with_projects.get(f"/projects/{name}/jobs/{job_id}/events").text
    assert "event: progress" in body
    assert "event: done" in body


def test_cancel_endpoint_returns_status(client_with_projects: TestClient) -> None:
    name = _name(client_with_projects)
    chapter_id = _first_chapter(client_with_projects, name)
    job_id = client_with_projects.post(
        f"/projects/{name}/chapters/{chapter_id}/translate", json=FAKE_BODY
    ).json()["job_id"]

    resp = client_with_projects.post(f"/projects/{name}/jobs/{job_id}/cancel")
    assert resp.status_code == 200
    assert resp.json()["status"] in {"running", "done", "cancelled"}


def test_cancel_unknown_job_returns_404(client_with_projects: TestClient) -> None:
    name = _name(client_with_projects)
    resp = client_with_projects.post(f"/projects/{name}/jobs/deadbeef/cancel")
    assert resp.status_code == 404


def _translate_chapter(client: TestClient, name: str, chapter_id: str) -> None:
    job_id = client.post(
        f"/projects/{name}/chapters/{chapter_id}/translate", json=FAKE_BODY
    ).json()["job_id"]
    _wait(client, job_id)


def test_retranslate_skip_existing_does_nothing_when_translated(
    client_with_projects: TestClient,
) -> None:
    name = _name(client_with_projects)
    chapter_id = _first_chapter(client_with_projects, name)
    _translate_chapter(client_with_projects, name, chapter_id)

    resp = client_with_projects.post(
        f"/projects/{name}/chapters/{chapter_id}/retranslate", json={**FAKE_BODY}
    )
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]
    _wait(client_with_projects, job_id)
    result = client_with_projects.get(f"/projects/{name}/jobs/{job_id}").json()["result"]
    assert result["selected"] == 0


def test_retranslate_non_manual_retranslates_after_full_translate(
    client_with_projects: TestClient,
) -> None:
    name = _name(client_with_projects)
    chapter_id = _first_chapter(client_with_projects, name)
    _translate_chapter(client_with_projects, name, chapter_id)

    resp = client_with_projects.post(
        f"/projects/{name}/chapters/{chapter_id}/retranslate",
        json={"mode": "retranslate_non_manual", **FAKE_BODY},
    )
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]
    _wait(client_with_projects, job_id)
    result = client_with_projects.get(f"/projects/{name}/jobs/{job_id}").json()["result"]
    assert result["translated"] > 0


def test_force_selected_overwrites_manual_and_appends_history(
    client_with_projects: TestClient,
) -> None:
    name = _name(client_with_projects)
    chapter_id = _first_chapter(client_with_projects, name)
    workspace = client_with_projects.get(
        f"/projects/{name}/chapters/{chapter_id}/workspace"
    ).json()
    segment_id = workspace["segments"][0]["id"]
    # Make it manual via the save endpoint.
    client_with_projects.patch(
        f"/projects/{name}/chapters/{chapter_id}/segments/{segment_id}/translation",
        json={"translated_text": "hand edit"},
    )

    resp = client_with_projects.post(
        f"/projects/{name}/chapters/{chapter_id}/retranslate-segments",
        json={"segment_ids": [segment_id], "mode": "force_selected", **FAKE_BODY},
    )
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]
    _wait(client_with_projects, job_id)
    assert client_with_projects.get(f"/projects/{name}/jobs/{job_id}").json()["result"][
        "translated"
    ] == 1

    history = client_with_projects.get(
        f"/projects/{name}/chapters/{chapter_id}/segments/{segment_id}/translations"
    ).json()
    texts = [a["translated_text"] for a in history["attempts"]]
    assert "hand edit" in texts  # prior manual attempt preserved
    assert len(history["attempts"]) >= 2  # append-only


def test_retranslate_invalid_mode_returns_422(client_with_projects: TestClient) -> None:
    name = _name(client_with_projects)
    chapter_id = _first_chapter(client_with_projects, name)
    resp = client_with_projects.post(
        f"/projects/{name}/chapters/{chapter_id}/retranslate",
        json={"mode": "nuke_everything", **FAKE_BODY},
    )
    assert resp.status_code == 422
