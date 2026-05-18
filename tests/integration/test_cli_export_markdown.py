"""CLI tests for Phase 6 Markdown export."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from typer.testing import CliRunner

from weaver.cli.main import app
from weaver.storage.db import connect_database, transaction
from weaver.storage.segments import update_segment_status

FIXTURE_EPUB = Path(__file__).parents[1] / "fixtures" / "aozora_sample.epub"


def test_weaver_export_markdown_writes_review_index_and_chapter_files(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    project_toml = _init_fake_and_translate(runner, tmp_path)

    result = runner.invoke(app, ["export", str(project_toml), "--mode", "markdown"])

    assert result.exit_code == 0, result.output
    assert "review.md" in result.output
    review_dir = tmp_path / ".weaver" / "aozora_sample" / "output" / "markdown"
    review_md = review_dir / "review.md"
    chapter_files = sorted(review_dir.glob("chapter-*.md"))
    assert review_md.exists()
    assert len(chapter_files) == 2
    assert "chapter-001.md" in review_md.read_text(encoding="utf-8")
    first_chapter = chapter_files[0].read_text(encoding="utf-8")
    assert "## Source" in first_chapter
    assert "## Translation" in first_chapter
    assert "EN: " in first_chapter


def test_weaver_export_markdown_translation_only_omits_source_blocks(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    project_toml = _init_fake_and_translate(runner, tmp_path)

    result = runner.invoke(
        app,
        ["export", str(project_toml), "--mode", "markdown", "--translation-only"],
    )

    assert result.exit_code == 0, result.output
    first_chapter = (
        tmp_path / ".weaver" / "aozora_sample" / "output" / "markdown" / "chapter-001.md"
    ).read_text(encoding="utf-8")
    assert "## Source" not in first_chapter
    assert "EN: " in first_chapter


def test_weaver_export_markdown_marks_failed_stale_and_missing_segments(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    init = runner.invoke(app, ["init", str(FIXTURE_EPUB)])
    assert init.exit_code == 0, init.output
    project_toml = tmp_path / ".weaver" / "aozora_sample" / "project.toml"
    db_path = tmp_path / ".weaver" / "aozora_sample" / "weaver.db"
    segment_ids = _segment_ids(db_path)
    with connect_database(db_path) as connection, transaction(connection):
        update_segment_status(connection, segment_id=segment_ids[0], status="failed")
        update_segment_status(connection, segment_id=segment_ids[1], status="stale")

    result = runner.invoke(app, ["export", str(project_toml), "--mode", "markdown"])

    assert result.exit_code == 0, result.output
    first_chapter = (
        tmp_path / ".weaver" / "aozora_sample" / "output" / "markdown" / "chapter-001.md"
    ).read_text(encoding="utf-8")
    assert f"[FAILED: {segment_ids[0]}]" in first_chapter
    assert f"[STALE: {segment_ids[1]}]" in first_chapter
    assert "[MISSING:" in first_chapter


def _init_fake_and_translate(runner: CliRunner, tmp_path: Path) -> Path:
    init = runner.invoke(app, ["init", str(FIXTURE_EPUB)])
    assert init.exit_code == 0, init.output
    project_toml = tmp_path / ".weaver" / "aozora_sample" / "project.toml"
    _set_fake_provider(project_toml)
    translate = runner.invoke(app, ["translate", str(project_toml)])
    assert translate.exit_code == 0, translate.output
    return project_toml


def _set_fake_provider(project_toml: Path) -> None:
    text = project_toml.read_text(encoding="utf-8")
    text = text.replace('type = "deepseek"', 'type = "fake"')
    text = text.replace('model = "deepseek-chat"', 'model = "fake-1"')
    text = text.replace('base_url = "http://localhost:11434"', 'pattern = "EN: {source}"')
    project_toml.write_text(text, encoding="utf-8")


def _segment_ids(db_path: Path) -> list[str]:
    with sqlite3.connect(db_path) as connection:
        return [
            str(row[0])
            for row in connection.execute(
                """
                SELECT s.id
                FROM segments s
                JOIN chapters c ON c.id = s.chapter_id
                ORDER BY c.spine_order, s.block_order
                """
            ).fetchall()
        ]
