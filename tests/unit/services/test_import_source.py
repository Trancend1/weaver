"""Volume import service tests (Sprint 1a)."""

from __future__ import annotations

from pathlib import Path

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


def test_import_volume_rejects_not_yet_supported_txt(tmp_path) -> None:
    init = initialize_project(FIXTURE_EPUB_A, cwd=tmp_path, provider="fake")
    txt_source = tmp_path / "volume.txt"
    txt_source.write_text("第一章\n本文。\n", encoding="utf-8")

    with pytest.raises(WeaverError, match="not available yet"):
        import_volume(init.project_toml, txt_source, cwd=tmp_path)
