"""Character repository tests (schema v4)."""

from __future__ import annotations

from weaver.storage.characters import (
    delete_character,
    get_character,
    list_characters,
    upsert_character,
)
from weaver.storage.db import initialize_database, transaction


def _project(connection) -> int:
    cursor = connection.execute(
        """
        INSERT INTO projects (
          name, source_path, source_lang, target_lang, created_at, schema_version
        )
        VALUES ('n', 'n.epub', 'ja', 'en', '2025-01-01T00:00:00+00:00', 4)
        """
    )
    return int(cursor.lastrowid)


def test_upsert_insert_then_update(tmp_path) -> None:
    with initialize_database(tmp_path / "db.sqlite") as connection:
        with transaction(connection):
            pid = _project(connection)
            upsert_character(
                connection, project_id=pid, jp_name="エリナ", en_name="Elina", role="Heroine"
            )
        stored = get_character(connection, project_id=pid, jp_name="エリナ")
        assert stored is not None
        assert stored.en_name == "Elina"
        assert stored.role == "Heroine"

        with transaction(connection):
            upsert_character(connection, project_id=pid, jp_name="エリナ", en_name="Erina")
        rows = list_characters(connection, project_id=pid)
        assert len(rows) == 1
        assert rows[0].en_name == "Erina"
        assert rows[0].role is None


def test_get_missing_returns_none(tmp_path) -> None:
    with initialize_database(tmp_path / "db.sqlite") as connection:
        with transaction(connection):
            pid = _project(connection)
        assert get_character(connection, project_id=pid, jp_name="x") is None


def test_delete_returns_flag(tmp_path) -> None:
    with initialize_database(tmp_path / "db.sqlite") as connection:
        with transaction(connection):
            pid = _project(connection)
            upsert_character(connection, project_id=pid, jp_name="魔王", en_name="Demon King")
        with transaction(connection):
            assert delete_character(connection, project_id=pid, jp_name="魔王") is True
        with transaction(connection):
            assert delete_character(connection, project_id=pid, jp_name="魔王") is False


def test_scoped_by_project(tmp_path) -> None:
    with initialize_database(tmp_path / "db.sqlite") as connection:
        with transaction(connection):
            p1 = _project(connection)
            p2 = _project(connection)
            upsert_character(connection, project_id=p1, jp_name="猫", en_name="Cat")
        assert len(list_characters(connection, project_id=p1)) == 1
        assert list_characters(connection, project_id=p2) == []
