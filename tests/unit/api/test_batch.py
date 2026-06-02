"""Tests for the Stage 7B batch-translation endpoints (novel/volume/chapter)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from weaver.providers.base import LLMProvider, ProviderStatus
from weaver.providers.registry import register_provider
from weaver.providers.types import TranslationRequest, TranslationResponse

FAKE_BODY = {"provider": "fake", "model": "fake-1"}


class _UnhealthyBatchProvider(LLMProvider):
    name = "unhealthybatch"

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


register_provider("unhealthybatch", lambda config: _UnhealthyBatchProvider())


def _name(client: TestClient) -> str:
    return str(client.get("/projects").json()["projects"][0]["name"])


def _volume_id(client: TestClient, name: str) -> str:
    tree = client.get(f"/projects/{name}/tree").json()
    return str(tree["volumes"][0]["id"])


def _first_chapter(client: TestClient, name: str) -> str:
    tree = client.get(f"/projects/{name}/tree").json()
    return str(tree["volumes"][0]["chapters"][0]["id"])


def _wait_batch(client: TestClient, job_id: str) -> None:
    job = client.app.state.jobs.get_batch(job_id)  # type: ignore[attr-defined]
    assert job is not None
    job.wait(timeout=10)


# --------------------------------------------------------------------------- #
# start each scope
# --------------------------------------------------------------------------- #


def test_batch_novel_starts_and_completes(client_with_projects: TestClient) -> None:
    name = _name(client_with_projects)
    resp = client_with_projects.post(f"/projects/{name}/batch/novel", json=FAKE_BODY)
    assert resp.status_code == 202
    data = resp.json()
    assert data["scope"] == "novel"
    assert data["scope_id"] is None
    job_id = data["job_id"]

    _wait_batch(client_with_projects, job_id)
    status = client_with_projects.get(f"/projects/{name}/batch/jobs/{job_id}").json()
    assert status["status"] == "done"
    result = status["result"]
    assert result["chapters_total"] >= 1
    assert result["chapters_done"] == result["chapters_total"]
    assert result["translated"] > 0
    assert result["translated"] + result["failed"] == result["segments_total"]
    assert status["error"] is None
    # per-chapter outcomes with token detail surfaced
    assert len(result["chapters"]) == result["chapters_total"]
    assert all("input_tokens" in c for c in result["chapters"])
    # timing fields present
    assert result["started_at"]
    assert result["finished_at"]
    assert result["duration_seconds"] >= 0.0


def test_batch_volume_starts_and_completes(client_with_projects: TestClient) -> None:
    name = _name(client_with_projects)
    volume_id = _volume_id(client_with_projects, name)
    resp = client_with_projects.post(f"/projects/{name}/batch/volumes/{volume_id}", json=FAKE_BODY)
    assert resp.status_code == 202
    data = resp.json()
    assert data["scope"] == "volume"
    assert data["scope_id"] == volume_id

    _wait_batch(client_with_projects, data["job_id"])
    result = client_with_projects.get(f"/projects/{name}/batch/jobs/{data['job_id']}").json()[
        "result"
    ]
    assert result["translated"] > 0


def test_batch_chapter_scope_starts_and_completes(client_with_projects: TestClient) -> None:
    name = _name(client_with_projects)
    chapter_id = _first_chapter(client_with_projects, name)
    resp = client_with_projects.post(
        f"/projects/{name}/batch/chapters/{chapter_id}", json=FAKE_BODY
    )
    assert resp.status_code == 202
    data = resp.json()
    assert data["scope"] == "chapter"
    assert data["scope_id"] == chapter_id

    _wait_batch(client_with_projects, data["job_id"])
    result = client_with_projects.get(f"/projects/{name}/batch/jobs/{data['job_id']}").json()[
        "result"
    ]
    assert result["chapters_total"] == 1
    assert result["translated"] > 0


# --------------------------------------------------------------------------- #
# progress + reuse
# --------------------------------------------------------------------------- #


def test_batch_status_progress_carries_mode_provider_model(
    client_with_projects: TestClient,
) -> None:
    name = _name(client_with_projects)
    job_id = client_with_projects.post(f"/projects/{name}/batch/novel", json=FAKE_BODY).json()[
        "job_id"
    ]
    _wait_batch(client_with_projects, job_id)

    progress = client_with_projects.get(f"/projects/{name}/batch/jobs/{job_id}").json()["progress"]
    assert progress["mode"] == "skip_existing"
    assert progress["provider"] == "fake"
    assert progress["model"] == "fake-1"
    assert progress["chapters_done"] == progress["chapters_total"]


def test_batch_reuses_from_memory_on_second_run(client_with_projects: TestClient) -> None:
    name = _name(client_with_projects)
    # First novel batch populates translation memory.
    first = client_with_projects.post(f"/projects/{name}/batch/novel", json=FAKE_BODY).json()
    _wait_batch(client_with_projects, first["job_id"])

    # Force a retranslate (non_manual) so the provider path runs again; reuse is
    # surfaced via the result field regardless.
    second = client_with_projects.post(
        f"/projects/{name}/batch/novel",
        json={"mode": "retranslate_non_manual", **FAKE_BODY},
    ).json()
    _wait_batch(client_with_projects, second["job_id"])
    result = client_with_projects.get(f"/projects/{name}/batch/jobs/{second['job_id']}").json()[
        "result"
    ]
    assert "reused_from_memory" in result


# --------------------------------------------------------------------------- #
# cancel + SSE
# --------------------------------------------------------------------------- #


def test_batch_cancel_endpoint_returns_status(client_with_projects: TestClient) -> None:
    name = _name(client_with_projects)
    job_id = client_with_projects.post(f"/projects/{name}/batch/novel", json=FAKE_BODY).json()[
        "job_id"
    ]
    resp = client_with_projects.post(f"/projects/{name}/batch/jobs/{job_id}/cancel")
    assert resp.status_code == 200
    assert resp.json()["status"] in {"running", "done", "cancelled"}


def test_batch_events_stream_emits_progress_then_terminal(
    client_with_projects: TestClient,
) -> None:
    name = _name(client_with_projects)
    job_id = client_with_projects.post(f"/projects/{name}/batch/novel", json=FAKE_BODY).json()[
        "job_id"
    ]
    body = client_with_projects.get(f"/projects/{name}/batch/jobs/{job_id}/events").text
    assert "event: progress" in body
    assert "event: done" in body


# --------------------------------------------------------------------------- #
# errors + namespace isolation
# --------------------------------------------------------------------------- #


def test_batch_unknown_project_returns_404(client_with_projects: TestClient) -> None:
    resp = client_with_projects.post("/projects/nope/batch/novel", json=FAKE_BODY)
    assert resp.status_code == 404


def test_batch_unknown_volume_returns_404(client_with_projects: TestClient) -> None:
    name = _name(client_with_projects)
    resp = client_with_projects.post(f"/projects/{name}/batch/volumes/9999", json=FAKE_BODY)
    assert resp.status_code == 404


def test_batch_unknown_chapter_returns_404(client_with_projects: TestClient) -> None:
    name = _name(client_with_projects)
    resp = client_with_projects.post(f"/projects/{name}/batch/chapters/missing", json=FAKE_BODY)
    assert resp.status_code == 404


def test_batch_invalid_mode_returns_422(client_with_projects: TestClient) -> None:
    name = _name(client_with_projects)
    resp = client_with_projects.post(
        f"/projects/{name}/batch/novel", json={"mode": "nuke", **FAKE_BODY}
    )
    assert resp.status_code == 422


def test_batch_unhealthy_provider_returns_502(client_with_projects: TestClient) -> None:
    name = _name(client_with_projects)
    resp = client_with_projects.post(
        f"/projects/{name}/batch/novel", json={"provider": "unhealthybatch", "model": "x"}
    )
    assert resp.status_code == 502


def test_batch_unknown_job_returns_404(client_with_projects: TestClient) -> None:
    name = _name(client_with_projects)
    resp = client_with_projects.get(f"/projects/{name}/batch/jobs/deadbeef")
    assert resp.status_code == 404


def test_batch_job_id_not_resolvable_via_chapter_jobs_route(
    client_with_projects: TestClient,
) -> None:
    name = _name(client_with_projects)
    job_id = client_with_projects.post(f"/projects/{name}/batch/novel", json=FAKE_BODY).json()[
        "job_id"
    ]
    _wait_batch(client_with_projects, job_id)
    # The chapter-job namespace must not resolve a batch job id (#9).
    resp = client_with_projects.get(f"/projects/{name}/jobs/{job_id}")
    assert resp.status_code == 404
