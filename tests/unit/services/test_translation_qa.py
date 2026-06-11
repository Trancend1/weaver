"""Scope-aware translation QA service (Phase B / Stage B2)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest

from weaver.errors import ChapterNotFoundError, ConfigError, VolumeNotFoundError
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


def _set_qa_key(project_toml: Path, line: str) -> None:
    # The generated project.toml already has a `[qa]` table (per-segment flags);
    # insert the new key under that header rather than declaring `[qa]` twice.
    text = project_toml.read_text(encoding="utf-8")
    marker = "[qa]\n"
    index = text.index(marker) + len(marker)
    project_toml.write_text(text[:index] + line + "\n" + text[index:], encoding="utf-8")


def test_qa_config_threshold_changes_report(tmp_path) -> None:
    # The seeded chapter is fallback-heavy by default (>=50% of its segments have
    # no publishable translation), so `fallback_heavy_chapter` fires.
    seeded = _seed_project(tmp_path)
    default = analyze_novel(seeded.project_toml, cwd=tmp_path)
    assert "fallback_heavy_chapter" in {issue.rule for issue in default.issues}

    # Raising the ratio past the chapter's fallback share suppresses that finding,
    # proving the `[qa]` config threads through analyze_novel.
    _set_qa_key(seeded.project_toml, "fallback_heavy_ratio = 0.95")
    tuned = analyze_novel(seeded.project_toml, cwd=tmp_path)
    assert "fallback_heavy_chapter" not in {issue.rule for issue in tuned.issues}


def test_qa_invalid_config_raises_through_analyze(tmp_path) -> None:
    seeded = _seed_project(tmp_path)
    _set_qa_key(seeded.project_toml, "fallback_heavy_ratio = 2.0")
    with pytest.raises(ConfigError, match="between 0.0 and 1.0"):
        analyze_novel(seeded.project_toml, cwd=tmp_path)


def _seed_structure_validation(database_path: Path, volume_id: int) -> None:
    """Insert a minimal preservation snapshot carrying one error structure issue."""
    now = datetime.now(UTC).isoformat()
    with connect_database(database_path) as connection, transaction(connection):
        connection.execute(
            """
            INSERT INTO epub_snapshots (
                volume_id, source_hash, parser_version, package_path,
                opf_path, spine_toc, page_progression_direction,
                metadata_json, preservation_context_json, created_at, updated_at
            ) VALUES (?, 'deadbeef', 1, 'book.epub', NULL, NULL, NULL, '{}', '{}', ?, ?)
            """,
            (volume_id, now, now),
        )
        connection.execute(
            "INSERT INTO epub_snapshot_validation (volume_id, position, data_json) "
            "VALUES (?, 0, ?)",
            (
                volume_id,
                json.dumps(
                    {
                        "severity": "error",
                        "code": "missing_spine_item",
                        "message": "A spine item is missing from the manifest.",
                    }
                ),
            ),
        )


def test_structure_validation_joins_into_volume_report(tmp_path) -> None:
    seeded = _seed_project(tmp_path)
    _seed_structure_validation(seeded.database_path, seeded.volume_id)

    report = analyze_volume(seeded.project_toml, seeded.volume_id, cwd=tmp_path)

    structure_issues = [issue for issue in report.issues if issue.source == "structure"]
    assert len(structure_issues) == 1
    issue = structure_issues[0]
    assert issue.rule == "missing_spine_item"
    assert issue.category == "structure"
    # EPUB 'error' is mapped to advisory 'warning' — never critical (advisory only).
    assert issue.severity == "warning"
    assert issue.segment_id is None and issue.chapter_id is None


def test_structure_validation_joins_into_novel_report(tmp_path) -> None:
    seeded = _seed_project(tmp_path)
    _seed_structure_validation(seeded.database_path, seeded.volume_id)

    report = analyze_novel(seeded.project_toml, cwd=tmp_path)

    assert any(issue.source == "structure" for issue in report.issues)


def test_structure_join_does_not_reparse_source(tmp_path, monkeypatch) -> None:
    seeded = _seed_project(tmp_path)
    _seed_structure_validation(seeded.database_path, seeded.volume_id)

    import weaver.readers.epub as epub_reader

    def _boom(*_args: object):  # pragma: no cover - must never run
        raise AssertionError("QA render must not re-parse the EPUB source")

    monkeypatch.setattr(epub_reader, "parse_epub_structure", _boom)

    report = analyze_novel(seeded.project_toml, cwd=tmp_path)
    assert any(issue.source == "structure" for issue in report.issues)


def test_chapter_report_has_no_structure_issues(tmp_path) -> None:
    seeded = _seed_project(tmp_path)
    _seed_structure_validation(seeded.database_path, seeded.volume_id)

    report = analyze_chapter(seeded.project_toml, seeded.chapter_id, cwd=tmp_path)

    assert all(issue.source == "translation" for issue in report.issues)


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
