"""Scope-aware translation QA service (Phase B / Stage B2)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from weaver.errors import ChapterNotFoundError, VolumeNotFoundError
from weaver.services.project import initialize_project
from weaver.services.translation_qa import analyze_chapter, analyze_novel, analyze_volume
from weaver.storage.characters import upsert_character
from weaver.storage.db import connect_database, connect_readonly_database, transaction
from weaver.storage.glossary import upsert_glossary_term
from weaver.storage.segments import update_segment_status
from weaver.storage.translations import record_translation

SOURCE_TXT = """第一章 テスト

エリナは魔法を使った。

失敗する場面の説明文。

古い場面の説明文。

空欄になる説明文。

日本語残留の説明文。

未訳のままの説明文。
"""


@dataclass(frozen=True)
class _Seeded:
    project_toml: Path
    database_path: Path
    project_id: int
    chapter_id: str
    volume_id: int


def _seed_project(tmp_path: Path) -> _Seeded:
    source = tmp_path / "novel.txt"
    source.write_text(SOURCE_TXT, encoding="utf-8")
    init = initialize_project(source, cwd=tmp_path, provider="fake")

    with connect_readonly_database(init.database_path) as connection:
        project_id = int(connection.execute("SELECT id FROM projects ORDER BY id").fetchone()["id"])
        volume_id = int(
            connection.execute("SELECT id FROM volumes ORDER BY volume_order").fetchone()["id"]
        )
        chapter_id = str(
            connection.execute("SELECT id FROM chapters ORDER BY spine_order").fetchone()["id"]
        )
        segments = [
            (str(row["id"]), str(row["source_text"]), str(row["source_hash"]))
            for row in connection.execute(
                "SELECT id, source_text, source_hash FROM segments "
                "WHERE chapter_id = ? ORDER BY block_order",
                (chapter_id,),
            ).fetchall()
        ]

    def find(marker: str) -> tuple[str, str, str]:
        return next(seg for seg in segments if marker in seg[1])

    consistency = find("魔法")
    empty = find("空欄")
    leak = find("残留")
    failed = find("失敗")
    stale = find("古い")

    with connect_database(init.database_path) as connection, transaction(connection):
        upsert_glossary_term(connection, project_id=project_id, source="魔法", target="magic")
        upsert_character(connection, project_id=project_id, jp_name="エリナ", en_name="Erina")

        # translated, but missing the glossary target and the character's EN name
        record_translation(
            connection,
            segment_id=consistency[0],
            text="She cast it.",
            source_hash=consistency[2],
            provider="fake",
            model="fake",
        )
        update_segment_status(connection, segment_id=consistency[0], status="translated")

        # published but empty text
        record_translation(
            connection,
            segment_id=empty[0],
            text="",
            source_hash=empty[2],
            provider="fake",
            model="fake",
        )
        update_segment_status(connection, segment_id=empty[0], status="translated")

        # published but left in Japanese (JP leak)
        record_translation(
            connection,
            segment_id=leak[0],
            text="日本語のままです",
            source_hash=leak[2],
            provider="fake",
            model="fake",
        )
        update_segment_status(connection, segment_id=leak[0], status="translated")

        update_segment_status(connection, segment_id=failed[0], status="failed")
        update_segment_status(connection, segment_id=stale[0], status="stale")
        # the 未訳 segment stays pending

    return _Seeded(init.project_toml, init.database_path, project_id, chapter_id, volume_id)


def test_analyze_chapter_detects_rules_and_scopes_issues(tmp_path) -> None:
    seeded = _seed_project(tmp_path)

    report = analyze_chapter(seeded.project_toml, seeded.chapter_id, cwd=tmp_path)

    rules = {issue.rule for issue in report.issues}
    assert {
        "glossary_mismatch",
        "character_name_missing",
        "failed_segment",
        "stale_segment",
        "empty_translation",
        "untranslated_japanese",
        "untranslated_segment",
        "mixed_status_chapter",
    } <= rules

    assert report.scope == "chapter"
    assert report.scope_id == seeded.chapter_id
    assert report.schema_version == 2
    assert report.critical_count >= 1
    assert report.badge == "errors"
    assert report.summary_by_chapter == ()
    assert report.summary_by_volume == ()
    # every issue is attributed to this chapter
    assert all(issue.chapter_id == seeded.chapter_id for issue in report.issues)
    # category roll-up is internally consistent
    assert sum(report.summary_by_category.values()) == report.total_issues


def test_analyze_volume_rolls_up_chapters(tmp_path) -> None:
    seeded = _seed_project(tmp_path)

    report = analyze_volume(seeded.project_toml, seeded.volume_id, cwd=tmp_path)

    assert report.scope == "volume"
    assert report.scope_id == str(seeded.volume_id)
    assert len(report.summary_by_chapter) >= 1
    assert report.summary_by_volume == ()
    assert report.badge == "errors"


def test_analyze_novel_rolls_up_volumes(tmp_path) -> None:
    seeded = _seed_project(tmp_path)

    report = analyze_novel(seeded.project_toml, cwd=tmp_path)

    assert report.scope == "novel"
    assert len(report.summary_by_volume) == 1
    assert len(report.summary_by_chapter) >= 1
    assert report.total_issues > 0
    assert report.badge == "errors"


def test_unknown_chapter_and_volume_raise(tmp_path) -> None:
    seeded = _seed_project(tmp_path)

    with pytest.raises(ChapterNotFoundError):
        analyze_chapter(seeded.project_toml, "no-such-chapter", cwd=tmp_path)
    with pytest.raises(VolumeNotFoundError):
        analyze_volume(seeded.project_toml, 999_999, cwd=tmp_path)


def test_qa_is_read_only(tmp_path) -> None:
    seeded = _seed_project(tmp_path)
    before = _snapshot(seeded.database_path)

    analyze_novel(seeded.project_toml, cwd=tmp_path)

    assert _snapshot(seeded.database_path) == before


def _snapshot(database_path: Path) -> tuple[tuple[tuple[str, str], ...], int]:
    with connect_readonly_database(database_path) as connection:
        statuses = tuple(
            (str(row["id"]), str(row["status"]))
            for row in connection.execute("SELECT id, status FROM segments ORDER BY id").fetchall()
        )
        translation_count = int(
            connection.execute("SELECT COUNT(*) AS n FROM translations").fetchone()["n"]
        )
    return statuses, translation_count
