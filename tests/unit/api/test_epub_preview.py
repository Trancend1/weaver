"""Tests for read-only EPUB preview API/UI surfaces."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any, cast

from fastapi.testclient import TestClient

FIXTURE_EPUB = Path(__file__).resolve().parents[2] / "fixtures" / "aozora_sample.epub"


def _epub_upload() -> dict[str, tuple[str, BytesIO, str]]:
    return {
        "file": (
            "aozora_sample.epub",
            BytesIO(FIXTURE_EPUB.read_bytes()),
            "application/epub+zip",
        )
    }


def test_epub_preview_json_upload(client: TestClient) -> None:
    response = client.post(
        "/projects/epub-preview",
        files=_epub_upload(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["metadata"]["title"]
    assert body["counts"]["manifest"] >= 1
    assert "validation_issues" in body


def test_epub_preview_json_source_path_is_sandboxed(client: TestClient, tmp_path: Path) -> None:
    source = tmp_path / "aozora_sample.epub"
    source.write_bytes(FIXTURE_EPUB.read_bytes())

    response = client.post("/projects/epub-preview", data={"source_path": source.name})

    assert response.status_code == 200
    body = response.json()
    assert body["source_path"].endswith("aozora_sample.epub")
    assert body["counts"]["spine"] >= 1


def test_epub_preview_does_not_create_database(client: TestClient) -> None:
    response = client.post(
        "/projects/epub-preview",
        files=_epub_upload(),
    )

    assert response.status_code == 200
    app = cast(Any, client.app)
    assert not list(Path(app.state.base_dir).rglob("*.sqlite3"))


def test_epub_preview_ui_renders_reader_baseline_sections(
    client: TestClient, tmp_path: Path
) -> None:
    source = tmp_path / "aozora_sample.epub"
    source.write_bytes(FIXTURE_EPUB.read_bytes())

    response = client.get(f"/ui/epub-preview?source_path={source.name}")
    text = response.text

    assert response.status_code == 200
    assert "EPUB structure preview" in text
    # Reader-like inspection sections are all present.
    for heading in (
        "Summary",
        "Table of contents",
        "Reading order",
        "Chapter excerpts",
        "Images",
        "Validation",
    ):
        assert heading in text
    # Readiness badge renders one of the three states.
    assert any(label in text for label in ("Safe to translate", "Warnings", "Blocking errors"))
