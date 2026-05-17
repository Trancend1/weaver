"""Phase 2 CLI integration tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from typer.testing import CliRunner

from weaver.cli.main import app

FIXTURE_EPUB = Path(__file__).parents[1] / "fixtures" / "aozora_sample.epub"


def test_weaver_init_writes_project_toml_and_complete_database(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    result = runner.invoke(app, ["init", str(FIXTURE_EPUB)])

    assert result.exit_code == 0, result.output
    assert "Created:" in result.output
    assert "Next:" in result.output

    project_toml = tmp_path / ".weaver" / "aozora_sample" / "project.toml"
    db_path = tmp_path / ".weaver" / "aozora_sample" / "weaver.db"
    assert project_toml.exists()
    assert db_path.exists()

    with sqlite3.connect(db_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        chapter_count = connection.execute("SELECT COUNT(*) FROM chapters").fetchone()[0]
        segment_count = connection.execute("SELECT COUNT(*) FROM segments").fetchone()[0]
        statuses = {
            row[0] for row in connection.execute("SELECT DISTINCT status FROM segments").fetchall()
        }

    assert {"projects", "chapters", "segments", "translations"}.issubset(tables)
    assert chapter_count == 2
    assert segment_count == 6
    assert statuses == {"pending"}


def test_weaver_inspect_reads_project_without_modifying_database(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    init_result = runner.invoke(app, ["init", str(FIXTURE_EPUB)])
    assert init_result.exit_code == 0, init_result.output
    project_toml = tmp_path / ".weaver" / "aozora_sample" / "project.toml"
    db_path = tmp_path / ".weaver" / "aozora_sample" / "weaver.db"
    before = db_path.stat().st_mtime_ns

    inspect_result = runner.invoke(app, ["inspect", str(project_toml)])
    after = db_path.stat().st_mtime_ns

    assert inspect_result.exit_code == 0, inspect_result.output
    assert "aozora_sample" in inspect_result.output
    assert "Chapters" in inspect_result.output
    assert "Segments" in inspect_result.output
    assert "Pending" in inspect_result.output
    assert after == before
