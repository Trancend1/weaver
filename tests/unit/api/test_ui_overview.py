"""Tests for the project overview UI (Sprint P5, WV-005)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from weaver.api.app import create_api_app
from weaver.services.project import initialize_project

SOURCE = """第一章 テスト

最初の段落の説明文。

二番目の段落の説明文。
"""


@pytest.fixture
def overview_client(tmp_path: Path) -> TestClient:
    src = tmp_path / "book.txt"
    src.write_text(SOURCE, encoding="utf-8")
    initialize_project(src, cwd=tmp_path, provider="fake")
    return TestClient(create_api_app(tmp_path))


def _name(client: TestClient) -> str:
    return client.get("/projects").json()["projects"][0]["name"]


def test_project_overview_renders_summary_cards(overview_client: TestClient) -> None:
    name = _name(overview_client)
    page = overview_client.get(f"/ui/projects/{name}").text
    assert "Volume" in page
    assert "Chapter" in page
    assert "Segment" in page
    assert "Done" in page
    assert "Pending" in page


def test_project_overview_shows_import_and_export(overview_client: TestClient) -> None:
    name = _name(overview_client)
    page = overview_client.get(f"/ui/projects/{name}").text
    assert "Import another volume" in page or "Import first volume" in page
    assert "Export project" in page
    assert "Delete project" in page
    assert "Volumes" in page
    assert "Inspect" in page
    assert "Preview" in page
    assert "Review queue" in page


def test_project_overview_shows_volume_grid(overview_client: TestClient) -> None:
    name = _name(overview_client)
    page = overview_client.get(f"/ui/projects/{name}").text
    assert "Volumes" in page
    # volume card should show snapshot status
    assert "missing" in page or "fresh" in page


def test_project_overview_preserves_tree_and_import(overview_client: TestClient) -> None:
    name = _name(overview_client)
    page = overview_client.get(f"/ui/projects/{name}").text
    # existing HTMX targets must still be present
    assert 'id="tree"' in page
    assert 'id="import_error"' in page
    assert 'id="browser"' in page
    assert 'id="export-panel"' in page
    assert 'id="qa-badge-status"' in page
