"""Tests for the export_history ledger storage layer (Sprint Q7)."""

from __future__ import annotations

from weaver.storage.db import initialize_database
from weaver.storage.export_history import list_export_history, record_export


def _seed_volume(connection) -> None:
    """Insert a project + volume so export_history.volume_id FK is satisfiable."""
    connection.execute(
        "INSERT INTO projects (id, name, source_path, source_lang, target_lang, "
        "created_at, schema_version, uuid) VALUES (1, 'p', 's.epub', 'ja', 'en', "
        "'2025-01-01T00:00:00+00:00', 11, 'u1')"
    )
    connection.execute(
        "INSERT INTO volumes (id, project_id, title, source_path, source_format, "
        "volume_order, created_at) VALUES (1, 1, 'Vol 1', 's.epub', 'epub', 0, "
        "'2025-01-01T00:00:00+00:00')"
    )


def _record(connection, **overrides) -> None:
    row = {
        "id": "e1",
        "volume_id": 1,
        "format": "epub",
        "kind": "draft",
        "status": "succeeded",
        "qa_badge": "clean",
        "artifact_path": "/out/vol-1.epub",
        "byte_size": 1234,
        "job_id": None,
        "version_label": None,
        "created_at": "2025-01-01T00:00:00+00:00",
    }
    row.update(overrides)
    record_export(connection, **row)


def test_record_and_list_round_trip(tmp_path) -> None:
    with initialize_database(tmp_path / "weaver.db") as connection:
        _seed_volume(connection)
        _record(connection, id="e1")
        connection.commit()
        rows = list_export_history(connection)

    assert len(rows) == 1
    r = rows[0]
    assert r.id == "e1"
    assert r.volume_id == 1
    assert r.format == "epub"
    assert r.kind == "draft"
    assert r.status == "succeeded"
    assert r.qa_badge == "clean"
    assert r.artifact_path == "/out/vol-1.epub"
    assert r.byte_size == 1234


def test_list_is_newest_first(tmp_path) -> None:
    with initialize_database(tmp_path / "weaver.db") as connection:
        _seed_volume(connection)
        _record(connection, id="old", created_at="2025-01-01T00:00:00+00:00")
        _record(connection, id="new", created_at="2025-06-01T00:00:00+00:00")
        connection.commit()
        rows = list_export_history(connection)

    assert [r.id for r in rows] == ["new", "old"]


def test_failed_row_has_null_artifact(tmp_path) -> None:
    with initialize_database(tmp_path / "weaver.db") as connection:
        _record(
            connection,
            id="f1",
            status="failed",
            volume_id=None,
            artifact_path=None,
            byte_size=None,
            qa_badge=None,
        )
        connection.commit()
        rows = list_export_history(connection)

    assert rows[0].status == "failed"
    assert rows[0].volume_id is None
    assert rows[0].artifact_path is None
    assert rows[0].byte_size is None
