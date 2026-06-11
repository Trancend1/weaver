"""Sprint M image preview security endpoint tests."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from tests.unit.readers.test_epub_structure import _write_image_epub
from weaver.api.app import create_api_app
from weaver.core.epub_structure import ManifestResource
from weaver.services.epub_reparse import reparse_volume
from weaver.services.epub_snapshot import read_snapshot, store_snapshot
from weaver.services.image_preview import MAX_IMAGE_PREVIEW_BYTES
from weaver.services.import_source import import_volume
from weaver.services.project import initialize_project
from weaver.services.project_paths import resolve_database_path


def _client_with_image_snapshot(tmp_path: Path) -> tuple[TestClient, str, int, Path]:
    source = tmp_path / "images.epub"
    _write_image_epub(source)
    init = initialize_project(project_name="image-project", cwd=tmp_path, provider="fake")
    volume = import_volume(init.project_toml, source, cwd=tmp_path)
    reparse_volume(init.project_toml, volume.volume_id, cwd=tmp_path)
    return (
        TestClient(create_api_app(tmp_path)),
        "image-project",
        volume.volume_id,
        init.project_toml,
    )


def _first_image_manifest_id(project_toml: Path, volume_id: int, cwd: Path) -> str:
    parsed = read_snapshot(resolve_database_path(project_toml, cwd=cwd), volume_id)
    assert parsed is not None
    image = parsed.images[0]
    assert image.manifest_id is not None
    return image.manifest_id


def test_preview_endpoint_serves_manifest_backed_image(tmp_path: Path) -> None:
    client, name, volume_id, project_toml = _client_with_image_snapshot(tmp_path)
    manifest_id = _first_image_manifest_id(project_toml, volume_id, tmp_path)

    response = client.get(f"/projects/{name}/volumes/{volume_id}/images/{manifest_id}/preview")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.content


def test_preview_endpoint_rejects_missing_manifest_image(tmp_path: Path) -> None:
    client, name, volume_id, _ = _client_with_image_snapshot(tmp_path)

    response = client.get(f"/projects/{name}/volumes/{volume_id}/images/ghost/preview")

    assert response.status_code == 422
    assert "manifest image was not found" in response.text


def test_preview_endpoint_rejects_unsupported_mime(tmp_path: Path) -> None:
    client, name, volume_id, project_toml = _client_with_image_snapshot(tmp_path)
    db_path = resolve_database_path(project_toml, cwd=tmp_path)
    parsed = read_snapshot(db_path, volume_id)
    assert parsed is not None
    image = parsed.images[0]
    bad_image = ManifestResource(
        **{**image.__dict__, "media_type": "image/svg+xml", "manifest_id": "bad-svg"}
    )
    store_snapshot(
        db_path,
        volume_id=volume_id,
        parsed=parsed.__class__(**{**parsed.__dict__, "images": [bad_image]}),
        source_hash="mime-test",
    )

    response = client.get(f"/projects/{name}/volumes/{volume_id}/images/bad-svg/preview")
    assert response.status_code == 422
    assert "unsupported image MIME" in response.text


def test_preview_endpoint_rejects_oversized_image_metadata(tmp_path: Path) -> None:
    client, name, volume_id, project_toml = _client_with_image_snapshot(tmp_path)
    db_path = resolve_database_path(project_toml, cwd=tmp_path)
    parsed = read_snapshot(db_path, volume_id)
    assert parsed is not None
    image = parsed.images[0]
    oversized = ManifestResource(
        **{
            **image.__dict__,
            "byte_size": MAX_IMAGE_PREVIEW_BYTES + 1,
            "manifest_id": "oversized",
        }
    )
    store_snapshot(
        db_path,
        volume_id=volume_id,
        parsed=parsed.__class__(**{**parsed.__dict__, "images": [oversized]}),
        source_hash="oversized-test",
    )

    response = client.get(f"/projects/{name}/volumes/{volume_id}/images/oversized/preview")
    assert response.status_code == 422
    assert "byte-size cap" in response.text


def test_preview_endpoint_rejects_path_traversal_snapshot(tmp_path: Path) -> None:
    client, name, volume_id, project_toml = _client_with_image_snapshot(tmp_path)
    db_path = resolve_database_path(project_toml, cwd=tmp_path)
    parsed = read_snapshot(db_path, volume_id)
    assert parsed is not None
    image = parsed.images[0]
    traversal = ManifestResource(
        **{**image.__dict__, "resolved_path": "../evil.png", "manifest_id": "traversal"}
    )
    store_snapshot(
        db_path,
        volume_id=volume_id,
        parsed=parsed.__class__(**{**parsed.__dict__, "images": [traversal]}),
        source_hash="traversal-test",
    )

    response = client.get(f"/projects/{name}/volumes/{volume_id}/images/traversal/preview")
    assert response.status_code == 422
    assert "path escapes" in response.text


def test_preview_endpoint_rejects_missing_archive_member(tmp_path: Path) -> None:
    client, name, volume_id, project_toml = _client_with_image_snapshot(tmp_path)
    db_path = resolve_database_path(project_toml, cwd=tmp_path)
    parsed = read_snapshot(db_path, volume_id)
    assert parsed is not None
    image = parsed.images[0]
    missing = ManifestResource(
        **{**image.__dict__, "resolved_path": "images/missing.png", "manifest_id": "missing"}
    )
    store_snapshot(
        db_path,
        volume_id=volume_id,
        parsed=parsed.__class__(**{**parsed.__dict__, "images": [missing]}),
        source_hash="missing-test",
    )

    response = client.get(f"/projects/{name}/volumes/{volume_id}/images/missing/preview")
    assert response.status_code == 422
    assert "missing from the EPUB archive" in response.text


def test_preview_endpoint_does_not_mutate_source_epub(tmp_path: Path) -> None:
    client, name, volume_id, project_toml = _client_with_image_snapshot(tmp_path)
    manifest_id = _first_image_manifest_id(project_toml, volume_id, tmp_path)
    source = tmp_path / "images.epub"
    before = source.read_bytes()

    response = client.get(f"/projects/{name}/volumes/{volume_id}/images/{manifest_id}/preview")

    assert response.status_code == 200
    assert source.read_bytes() == before


def test_structure_page_renders_image_preview_affordance(tmp_path: Path) -> None:
    # Q9: the gated image affordance lives on the Content Explorer's Assets tab.
    client, name, volume_id, _ = _client_with_image_snapshot(tmp_path)

    page = client.get(f"/ui/projects/{name}/volumes/{volume_id}/structure?tab=assets")

    assert page.status_code == 200
    assert "Preview image" in page.text
    assert f"/projects/{name}/volumes/{volume_id}/images/" in page.text


def test_preview_endpoint_rejects_non_zip_source(tmp_path: Path) -> None:
    client, name, volume_id, project_toml = _client_with_image_snapshot(tmp_path)
    (tmp_path / "images.epub").write_text("not a zip", encoding="utf-8")
    manifest_id = _first_image_manifest_id(project_toml, volume_id, tmp_path)

    response = client.get(f"/projects/{name}/volumes/{volume_id}/images/{manifest_id}/preview")
    assert response.status_code == 422
    assert "cannot be opened" in response.text
