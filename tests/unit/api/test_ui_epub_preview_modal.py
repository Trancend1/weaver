"""Tests for contextual EPUB preview modal workflow."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from weaver.api.app import create_api_app


@pytest.fixture
def modal_client(tmp_path: Path) -> TestClient:
    from weaver.services.project import initialize_project

    fixtures = Path(__file__).parent.parent.parent / "fixtures"
    epubs = list(fixtures.glob("*.epub"))
    if not epubs:
        pytest.skip("no EPUB fixture available")
    initialize_project(epubs[0], cwd=tmp_path)
    return TestClient(create_api_app(tmp_path))


def _project(client: TestClient) -> str:
    return str(client.get("/projects").json()["projects"][0]["name"])


def _volume(client: TestClient, name: str) -> int:
    return int(client.get(f"/projects/{name}/tree").json()["volumes"][0]["id"])


def test_project_page_exposes_contextual_preview_actions(modal_client: TestClient) -> None:
    name = _project(modal_client)
    volume_id = _volume(modal_client, name)

    page = modal_client.get(f"/ui/projects/{name}").text

    assert 'id="modal-root"' in page
    assert f'id="volume-{volume_id}"' in page
    assert "Preview EPUB" in page
    assert "Inspect status" in page
    assert "Full structure page" in page
    assert "Reparse EPUB" not in page
    assert 'hx-target="#modal-root"' in page


def test_preview_modal_has_close_back_and_contextual_next(
    modal_client: TestClient,
) -> None:
    name = _project(modal_client)
    volume_id = _volume(modal_client, name)

    page = modal_client.get(f"/ui/projects/{name}/volumes/{volume_id}/structure/modal").text

    assert 'role="dialog"' in page
    assert "Close" in page
    assert "Back to volume" in page
    assert f"/ui/projects/{name}#volume-{volume_id}" in page
    assert f"/ui/projects/{name}/volumes/{volume_id}/structure" in page
    assert "Next: open workspace" in page or "Next: reparse snapshot" in page
    assert 'href="/ui"' not in page


def test_volume_structure_page_keeps_project_context(
    modal_client: TestClient,
) -> None:
    name = _project(modal_client)
    volume_id = _volume(modal_client, name)

    page = modal_client.get(f"/ui/projects/{name}/volumes/{volume_id}/structure").text

    assert "Volume snapshot" in page
    assert f"volume:{volume_id}" in page
    assert f"/ui/projects/{name}#volume-{volume_id}" in page
    assert 'action="/ui/epub-preview"' not in page
    assert "Sandbox source path" not in page


def test_legacy_volume_preview_reference_still_renders(
    modal_client: TestClient,
) -> None:
    name = _project(modal_client)
    volume_id = _volume(modal_client, name)

    page = modal_client.get(f"/ui/epub-preview?source_path=volume:{volume_id}").text

    assert "Volume snapshot" in page
    assert f"volume:{volume_id}" in page
    assert "Not a supported source file" not in page
