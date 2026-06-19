"""Tests for the project-page 'Translate volume' inline batch panel.

The cockpit surface reuses the JSON batch path (volume scope, ``skip_existing``)
and renders a self-polling fragment in the volume row. The provider is the
deterministic ``fake`` engine — never a live model.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from weaver.api.app import create_api_app
from weaver.services.project import initialize_project


@pytest.fixture
def fake_client(tmp_path: Path) -> TestClient:
    fixtures = Path(__file__).parent.parent.parent / "fixtures"
    epubs = sorted(fixtures.glob("*.epub"))
    if not epubs:
        pytest.skip("no EPUB fixture available")
    initialize_project(epubs[0], cwd=tmp_path, provider="fake")
    return TestClient(create_api_app(tmp_path))


def _name(client: TestClient) -> str:
    return str(client.get("/projects").json()["projects"][0]["name"])


def _volume_id(client: TestClient, name: str) -> str:
    return str(client.get(f"/projects/{name}/tree").json()["volumes"][0]["id"])


def _wait_latest_batch(client: TestClient) -> str:
    jobs = client.app.state.jobs  # type: ignore[attr-defined]
    assert jobs._batch_jobs, "no batch job was submitted"
    job_id = list(jobs._batch_jobs.keys())[-1]
    jobs.get_batch(job_id).wait(timeout=30)
    return job_id


def test_tree_fragment_has_translate_volume_button(fake_client: TestClient) -> None:
    name = _name(fake_client)
    frag = fake_client.get(f"/ui/projects/{name}/tree")
    assert frag.status_code == 200
    assert "Translate volume" in frag.text
    assert 'id="batch-vol-' in frag.text  # inline progress slot exists


def test_translate_volume_starts_and_completes(fake_client: TestClient) -> None:
    name = _name(fake_client)
    vid = _volume_id(fake_client, name)

    start = fake_client.post(f"/ui/projects/{name}/volumes/{vid}/translate")
    assert start.status_code == 200
    assert f'id="batch-vol-{vid}"' in start.text  # panel landed in the row slot

    job_id = _wait_latest_batch(fake_client)
    panel = fake_client.get(f"/ui/projects/{name}/batch/jobs/{job_id}")
    assert panel.status_code == 200
    assert "translated" in panel.text  # done summary with counts
    assert "Refresh progress" in panel.text  # bar-refresh affordance
    assert "Cancel" not in panel.text  # terminal: no cancel


def test_second_run_skips_already_translated(fake_client: TestClient) -> None:
    """skip_existing: a second volume run translates nothing (only untranslated work)."""
    name = _name(fake_client)
    vid = _volume_id(fake_client, name)

    fake_client.post(f"/ui/projects/{name}/volumes/{vid}/translate")
    first_id = _wait_latest_batch(fake_client)
    first = fake_client.app.state.jobs.get_batch(first_id).result  # type: ignore[attr-defined]
    assert first is not None and first.translated > 0

    fake_client.post(f"/ui/projects/{name}/volumes/{vid}/translate")
    second_id = _wait_latest_batch(fake_client)
    second = fake_client.app.state.jobs.get_batch(second_id).result  # type: ignore[attr-defined]
    assert second is not None
    assert second.translated == 0  # everything already done → nothing re-translated


def test_translate_unknown_volume_shows_visible_error(fake_client: TestClient) -> None:
    name = _name(fake_client)
    r = fake_client.post(f"/ui/projects/{name}/volumes/999999/translate")
    assert r.status_code == 200  # fragment swap, not a 5xx
    assert 'id="batch-vol-999999"' in r.text  # keeps the slot id for the swap
    assert "error" in r.text.lower() or "not found" in r.text.lower()


def test_batch_cancel_route_renders_panel(fake_client: TestClient) -> None:
    name = _name(fake_client)
    vid = _volume_id(fake_client, name)
    fake_client.post(f"/ui/projects/{name}/volumes/{vid}/translate")
    job_id = _wait_latest_batch(fake_client)
    # Cancel on a finished job is a safe no-op and still renders the panel.
    r = fake_client.post(f"/ui/projects/{name}/batch/jobs/{job_id}/cancel")
    assert r.status_code == 200
    assert f'id="batch-vol-{vid}"' in r.text
