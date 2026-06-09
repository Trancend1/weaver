"""Tests for the EPUB preservation snapshot service (Sprint J2)."""

from __future__ import annotations

from contextlib import closing
from pathlib import Path

import pytest

from weaver.readers.epub import PARSER_VERSION, parse_epub_structure
from weaver.services.epub_snapshot import (
    compute_source_hash,
    delete_snapshot,
    read_snapshot,
    snapshot_status,
    store_snapshot,
)
from weaver.services.project import initialize_project
from weaver.services.project_paths import resolve_database_path
from weaver.services.volume import delete_volume_from_project
from weaver.storage.db import connect_database, transaction


@pytest.fixture
def project_with_volume(tmp_path: Path):
    fixtures = Path(__file__).parent.parent.parent / "fixtures"
    epubs = list(fixtures.glob("*.epub"))
    if not epubs:
        pytest.skip("no EPUB fixture available")
    epub_path = epubs[0]
    init = initialize_project(epub_path, cwd=tmp_path)
    db_path = resolve_database_path(init.project_toml, cwd=tmp_path)
    # Resolve the volume id (initialize_project always creates exactly one).
    with closing(connect_database(db_path)) as connection:
        row = connection.execute("SELECT id FROM volumes ORDER BY id LIMIT 1").fetchone()
        assert row is not None
        volume_id = int(row["id"])
    return tmp_path, init.project_toml, db_path, volume_id, epub_path


def test_compute_source_hash_is_stable(tmp_path: Path) -> None:
    sample = tmp_path / "sample.bin"
    sample.write_bytes(b"hello-weaver")
    first = compute_source_hash(sample)
    second = compute_source_hash(sample)
    assert first == second
    sample.write_bytes(b"hello-weaver-changed")
    assert compute_source_hash(sample) != first


def test_round_trip_preserves_metadata_and_lists(project_with_volume) -> None:
    _, _, db_path, volume_id, epub_path = project_with_volume
    parsed = parse_epub_structure(epub_path)
    source_hash = compute_source_hash(epub_path)

    store_snapshot(db_path, volume_id=volume_id, parsed=parsed, source_hash=source_hash)
    restored = read_snapshot(db_path, volume_id)
    assert restored is not None

    assert restored.metadata.title == parsed.metadata.title
    assert restored.metadata.language == parsed.metadata.language
    assert len(restored.manifest) == len(parsed.manifest)
    assert len(restored.spine) == len(parsed.spine)
    assert len(restored.navigation) == len(parsed.navigation)
    assert len(restored.images) == len(parsed.images)
    assert len(restored.validation_issues) == len(parsed.validation_issues)
    # Resources mirror the manifest by contract on the persisted side.
    assert len(restored.resources) == len(parsed.manifest)
    assert restored.opf_path == parsed.opf_path


def test_status_reports_missing_then_fresh_then_stale(project_with_volume) -> None:
    _, _, db_path, volume_id, epub_path = project_with_volume
    parsed = parse_epub_structure(epub_path)
    source_hash = compute_source_hash(epub_path)

    with closing(connect_database(db_path)) as connection, transaction(connection):
        delete_snapshot(connection, volume_id)

    missing = snapshot_status(db_path, volume_id=volume_id, expected_source_hash=source_hash)
    assert missing.state == "missing"
    assert missing.source_hash is None

    store_snapshot(db_path, volume_id=volume_id, parsed=parsed, source_hash=source_hash)
    fresh = snapshot_status(db_path, volume_id=volume_id, expected_source_hash=source_hash)
    assert fresh.state == "fresh"
    assert fresh.is_fresh is True
    assert fresh.parser_version == PARSER_VERSION

    # Different source hash → stale.
    stale_hash = snapshot_status(db_path, volume_id=volume_id, expected_source_hash="x" * 64)
    assert stale_hash.state == "stale"
    assert stale_hash.is_stale is True

    # Same hash, newer parser → stale.
    stale_parser = snapshot_status(
        db_path,
        volume_id=volume_id,
        expected_source_hash=source_hash,
        expected_parser_version=PARSER_VERSION + 1,
    )
    assert stale_parser.state == "stale"


def test_store_replaces_existing_snapshot(project_with_volume) -> None:
    _, _, db_path, volume_id, epub_path = project_with_volume
    parsed = parse_epub_structure(epub_path)
    source_hash = compute_source_hash(epub_path)

    store_snapshot(db_path, volume_id=volume_id, parsed=parsed, source_hash=source_hash)
    # Re-store with a new hash — counters must NOT double up.
    store_snapshot(db_path, volume_id=volume_id, parsed=parsed, source_hash="b" * 64)

    with closing(connect_database(db_path)) as connection:
        manifest_count = connection.execute(
            "SELECT COUNT(*) FROM epub_snapshot_manifest WHERE volume_id = ?",
            (volume_id,),
        ).fetchone()[0]
        snapshot_count = connection.execute(
            "SELECT COUNT(*) FROM epub_snapshots WHERE volume_id = ?",
            (volume_id,),
        ).fetchone()[0]
        header = connection.execute(
            "SELECT source_hash FROM epub_snapshots WHERE volume_id = ?",
            (volume_id,),
        ).fetchone()
    assert manifest_count == len(parsed.manifest)
    assert snapshot_count == 1
    assert str(header["source_hash"]) == "b" * 64


def test_delete_snapshot_clears_all_tables(project_with_volume) -> None:
    _, _, db_path, volume_id, epub_path = project_with_volume
    parsed = parse_epub_structure(epub_path)
    source_hash = compute_source_hash(epub_path)
    store_snapshot(db_path, volume_id=volume_id, parsed=parsed, source_hash=source_hash)

    with closing(connect_database(db_path)) as connection:
        delete_snapshot(connection, volume_id)
        connection.commit()
        manifest_after = connection.execute(
            "SELECT COUNT(*) FROM epub_snapshot_manifest WHERE volume_id = ?",
            (volume_id,),
        ).fetchone()[0]
        header_after = connection.execute(
            "SELECT COUNT(*) FROM epub_snapshots WHERE volume_id = ?",
            (volume_id,),
        ).fetchone()[0]
    assert manifest_after == 0
    assert header_after == 0


def test_volume_delete_cleans_snapshot_rows(project_with_volume) -> None:
    tmp_path, project_toml, db_path, volume_id, epub_path = project_with_volume
    parsed = parse_epub_structure(epub_path)
    source_hash = compute_source_hash(epub_path)
    store_snapshot(db_path, volume_id=volume_id, parsed=parsed, source_hash=source_hash)

    delete_volume_from_project(project_toml, volume_id, cwd=tmp_path)

    with closing(connect_database(db_path)) as connection:
        for table in (
            "epub_snapshots",
            "epub_snapshot_manifest",
            "epub_snapshot_spine",
            "epub_snapshot_navigation",
            "epub_snapshot_images",
            "epub_snapshot_validation",
        ):
            count = connection.execute(
                f"SELECT COUNT(*) FROM {table} WHERE volume_id = ?", (volume_id,)
            ).fetchone()[0]
            assert count == 0, f"{table} kept {count} rows after volume delete"


def test_read_snapshot_returns_none_when_missing(tmp_path: Path) -> None:
    from weaver.storage.db import initialize_database

    db_path = tmp_path / "weaver.db"
    initialize_database(db_path).close()
    assert read_snapshot(db_path, 999) is None
