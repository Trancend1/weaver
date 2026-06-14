"""Volume import service tests (Sprint 1a)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from weaver.errors import WeaverError
from weaver.services.import_source import import_volume
from weaver.services.project import initialize_project
from weaver.storage.db import connect_readonly_database

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
FIXTURE_EPUB_A = FIXTURES / "aozora_sample.epub"
FIXTURE_EPUB_B = FIXTURES / "synthetic_200_chapter.epub"


def test_import_volume_adds_a_second_volume_with_its_own_chapters(tmp_path) -> None:
    init = initialize_project(FIXTURE_EPUB_A, cwd=tmp_path, provider="fake")

    result = import_volume(init.project_toml, FIXTURE_EPUB_B, cwd=tmp_path)

    with connect_readonly_database(init.database_path) as connection:
        volume_count = connection.execute("SELECT COUNT(*) AS n FROM volumes").fetchone()["n"]
        new_volume_chapters = connection.execute(
            "SELECT COUNT(*) AS n FROM chapters WHERE volume_id = ?",
            (result.volume_id,),
        ).fetchone()["n"]
        orders = [
            row["volume_order"]
            for row in connection.execute("SELECT volume_order FROM volumes ORDER BY volume_order")
        ]

    assert volume_count == 2
    assert result.chapter_count > 0
    assert new_volume_chapters == result.chapter_count
    assert orders == [0, 1]


def test_import_volume_accepts_a_txt_source(tmp_path) -> None:
    init = initialize_project(FIXTURE_EPUB_A, cwd=tmp_path, provider="fake")
    txt_source = tmp_path / "volume.txt"
    txt_source.write_text("第一章 はじまり\n本文。\n", encoding="utf-8")

    result = import_volume(init.project_toml, txt_source, cwd=tmp_path)

    with connect_readonly_database(init.database_path) as connection:
        fmt = connection.execute(
            "SELECT source_format FROM volumes WHERE id = ?", (result.volume_id,)
        ).fetchone()["source_format"]
        volume_count = connection.execute("SELECT COUNT(*) AS n FROM volumes").fetchone()["n"]

    assert fmt == "txt"
    assert volume_count == 2
    assert result.chapter_count >= 1


def test_import_volume_rejects_unsupported_format(tmp_path) -> None:
    init = initialize_project(FIXTURE_EPUB_A, cwd=tmp_path, provider="fake")
    bad_source = tmp_path / "volume.pdf"
    bad_source.write_text("not supported", encoding="utf-8")

    with pytest.raises(WeaverError, match="Unsupported source format"):
        import_volume(init.project_toml, bad_source, cwd=tmp_path)


def test_import_volume_snapshot_failure_rolls_back(tmp_path) -> None:
    """If EPUB snapshot persistence fails during import, the volume and
    its associated rows must roll back — no orphan volume without snapshot."""
    init = initialize_project(FIXTURE_EPUB_A, cwd=tmp_path, provider="fake")
    original_volume_count = _count_volumes(init.database_path)

    with (
        patch(
            "weaver.services.import_source.store_snapshot",
            side_effect=WeaverError("simulated snapshot failure"),
        ),
        pytest.raises(WeaverError, match="simulated snapshot failure"),
    ):
        import_volume(init.project_toml, FIXTURE_EPUB_B, cwd=tmp_path)

    assert _count_volumes(init.database_path) == original_volume_count, (
        "Volume must NOT be committed when snapshot persistence fails"
    )


def _count_volumes(db_path: Path) -> int:
    with connect_readonly_database(db_path) as connection:
        return int(connection.execute("SELECT COUNT(*) AS n FROM volumes").fetchone()["n"])
