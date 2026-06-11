"""Q9 tests: Content Explorer (tabbed structure surface).

Verifies:
- explorer route renders; the five tabs render their expected sections
- Segments tab lists rows with workspace jump links + reader cross-link
- Assets tab exposes only the gated per-manifest preview endpoint
- Warnings render from the persisted snapshot only
- zero reparse / source hashing / QA / provider calls on render (spies)
- missing-snapshot state is safe; Segments tab still works without a snapshot
- legacy `volume:` reference still renders; source-inspect mode retitled
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from weaver.api.app import create_api_app
from weaver.services.project import initialize_project

FIXTURES = Path(__file__).parent.parent.parent / "fixtures"


def _epub() -> Path:
    epubs = list(FIXTURES.glob("*.epub"))
    if not epubs:
        pytest.skip("no EPUB fixture available")
    return epubs[0]


@pytest.fixture
def explorer(tmp_path: Path) -> tuple[TestClient, str, int]:
    initialize_project(_epub(), cwd=tmp_path, project_name="alpha")
    client = TestClient(create_api_app(tmp_path))
    tree = client.get("/projects/alpha/tree").json()
    volume_id = int(tree["volumes"][0]["id"])
    return client, "alpha", volume_id


def _url(name: str, volume_id: int, **params: str) -> str:
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    return f"/ui/projects/{name}/volumes/{volume_id}/structure" + (f"?{qs}" if qs else "")


# --- page + tabs --------------------------------------------------------------


def test_explorer_renders_with_tabs(explorer: tuple[TestClient, str, int]) -> None:
    client, name, volume_id = explorer
    resp = client.get(_url(name, volume_id))
    assert resp.status_code == 200
    html = resp.text
    assert "Content Explorer" in html
    for tab in ("structure", "segments", "assets", "metadata", "warnings"):
        assert f"?tab={tab}" in html


def test_structure_tab_default(explorer: tuple[TestClient, str, int]) -> None:
    client, name, volume_id = explorer
    html = client.get(_url(name, volume_id)).text
    assert "Volume snapshot" in html
    assert "Table of contents" in html
    assert "Reading order" in html


def test_metadata_tab(explorer: tuple[TestClient, str, int]) -> None:
    client, name, volume_id = explorer
    html = client.get(_url(name, volume_id, tab="metadata")).text
    assert "Metadata" in html
    assert "Title" in html
    assert "Language" in html


def test_warnings_tab_renders_from_snapshot(explorer: tuple[TestClient, str, int]) -> None:
    client, name, volume_id = explorer
    html = client.get(_url(name, volume_id, tab="warnings")).text
    assert "Warnings" in html
    assert "preservation snapshot" in html


def test_assets_tab(explorer: tuple[TestClient, str, int]) -> None:
    client, name, volume_id = explorer
    html = client.get(_url(name, volume_id, tab="assets")).text
    assert "Assets" in html


def test_unknown_tab_falls_back_to_structure(explorer: tuple[TestClient, str, int]) -> None:
    client, name, volume_id = explorer
    html = client.get(_url(name, volume_id, tab="bogus")).text
    assert "Volume snapshot" in html


def test_back_and_reader_links(explorer: tuple[TestClient, str, int]) -> None:
    client, name, volume_id = explorer
    html = client.get(_url(name, volume_id)).text
    assert "Back to project" in html
    assert f'href="/ui/projects/{name}"' in html
    assert f"/ui/projects/{name}#volume-{volume_id}" in html
    assert f"/ui/projects/{name}/volumes/{volume_id}/preview" in html  # View as reader


# --- segments tab ---------------------------------------------------------------


def test_segments_tab_lists_segments_with_links(
    explorer: tuple[TestClient, str, int],
) -> None:
    client, name, volume_id = explorer
    html = client.get(_url(name, volume_id, tab="segments")).text
    assert "Segments" in html
    assert "Open in editor" in html
    assert f"/ui/projects/{name}/chapters/" in html
    assert "#seg-" in html  # workspace anchor contract (§4.2)
    assert "/preview" in html  # reading-preview cross-link
    assert "Open chapter in workspace" in html


def test_segments_tab_filter_by_status(explorer: tuple[TestClient, str, int], tmp_path) -> None:
    client, name, volume_id = explorer
    db_path = tmp_path / ".weaver" / name / "weaver.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT id, chapter_id FROM segments LIMIT 1").fetchone()
    conn.execute("UPDATE segments SET status = 'failed' WHERE id = ?", (row["id"],))
    conn.commit()
    conn.close()

    html = client.get(
        _url(name, volume_id, tab="segments", status="failed", chapter=str(row["chapter_id"]))
    ).text
    assert "1 match" in html
    assert f"seg-{row['id']}" in html


def test_segments_tab_works_without_snapshot(
    explorer: tuple[TestClient, str, int], tmp_path
) -> None:
    """Segments come from the project DB — a missing snapshot must not break them."""
    client, name, volume_id = explorer
    db_path = tmp_path / ".weaver" / name / "weaver.db"
    conn = sqlite3.connect(db_path)
    for table in (
        "epub_snapshot_manifest",
        "epub_snapshot_spine",
        "epub_snapshot_navigation",
        "epub_snapshot_images",
        "epub_snapshot_validation",
        "epub_snapshots",
    ):
        conn.execute(f"DELETE FROM {table}")
    conn.commit()
    conn.close()

    resp = client.get(_url(name, volume_id, tab="segments"))
    assert resp.status_code == 200
    assert "Open in editor" in resp.text


def test_missing_snapshot_renders_safe_hint(
    explorer: tuple[TestClient, str, int], tmp_path
) -> None:
    client, name, volume_id = explorer
    db_path = tmp_path / ".weaver" / name / "weaver.db"
    conn = sqlite3.connect(db_path)
    for table in (
        "epub_snapshot_manifest",
        "epub_snapshot_spine",
        "epub_snapshot_navigation",
        "epub_snapshot_images",
        "epub_snapshot_validation",
        "epub_snapshots",
    ):
        conn.execute(f"DELETE FROM {table}")
    conn.commit()
    conn.close()

    resp = client.get(_url(name, volume_id))
    assert resp.status_code == 200
    assert "Snapshot missing" in resp.text


# --- security: assets stay behind the gate ---------------------------------------


def test_assets_expose_only_gated_endpoint(explorer: tuple[TestClient, str, int], tmp_path) -> None:
    client, name, volume_id = explorer
    html = client.get(_url(name, volume_id, tab="assets")).text
    # Any preview link must go through the ADR 012 gate (manifest-id keyed).
    if "Preview image" in html:
        assert f"/projects/{name}/volumes/{volume_id}/images/" in html
    # No filesystem path or traversal token is rendered.
    assert str(tmp_path) not in html
    assert "../" not in html


# --- no side effects on render -----------------------------------------------------


def test_no_reparse_hash_qa_or_provider_on_render(
    explorer: tuple[TestClient, str, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, name, volume_id = explorer

    def _forbid(label: str):
        def _spy(*args: object, **kwargs: object) -> object:
            _ = (args, kwargs)
            raise AssertionError(f"{label} must not run on Content Explorer render")

        return _spy

    monkeypatch.setattr("weaver.readers.epub.parse_epub_structure", _forbid("parse_epub_structure"))
    monkeypatch.setattr(
        "weaver.services.epub_snapshot.compute_source_hash", _forbid("compute_source_hash")
    )
    monkeypatch.setattr(
        "weaver.services.epub_reparse.compute_source_hash", _forbid("compute_source_hash")
    )
    monkeypatch.setattr("weaver.services.translation_qa.analyze_novel", _forbid("analyze_novel"))
    monkeypatch.setattr("weaver.providers.registry.build_provider", _forbid("build_provider"))

    for tab in ("structure", "segments", "assets", "metadata", "warnings"):
        resp = client.get(_url(name, volume_id, tab=tab))
        assert resp.status_code == 200, tab


def test_render_does_not_write_database(explorer: tuple[TestClient, str, int], tmp_path) -> None:
    client, name, volume_id = explorer
    db_path = tmp_path / ".weaver" / name / "weaver.db"
    mtime_before = db_path.stat().st_mtime_ns

    for tab in ("structure", "segments", "assets", "metadata", "warnings"):
        client.get(_url(name, volume_id, tab=tab))

    assert db_path.stat().st_mtime_ns == mtime_before


# --- legacy + naming ---------------------------------------------------------------


def test_legacy_volume_reference_renders_explorer(
    explorer: tuple[TestClient, str, int],
) -> None:
    client, _, volume_id = explorer
    html = client.get(f"/ui/epub-preview?source_path=volume:{volume_id}").text
    assert "Content Explorer" in html
    assert f"volume:{volume_id}" in html


def test_source_inspect_mode_retitled(explorer: tuple[TestClient, str, int]) -> None:
    client, _, _ = explorer
    html = client.get("/ui/epub-preview").text
    assert "Inspect a source" in html
    assert "Sandbox source path" in html


def test_unknown_project_404(explorer: tuple[TestClient, str, int]) -> None:
    client, _, _ = explorer
    assert client.get("/ui/projects/nope/volumes/1/structure").status_code == 404


# --- structural gate ---------------------------------------------------------------


def test_explorer_route_is_thin() -> None:
    import inspect

    from weaver.api.routers import ui_explorer

    source = inspect.getsource(ui_explorer)
    assert "connect_database" not in source
    assert "connect_readonly_database" not in source  # reads go through services
    assert "SELECT " not in source  # no raw SQL in the router
