"""CLI integration tests for `weaver edit`."""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path
from textwrap import dedent

from typer.testing import CliRunner

from weaver.cli.main import app

FIXTURE_EPUB = Path(__file__).parents[1] / "fixtures" / "aozora_sample.epub"


def test_weaver_edit_opens_editor_and_marks_segment_manual(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    init_result = runner.invoke(app, ["init", str(FIXTURE_EPUB)])
    assert init_result.exit_code == 0, init_result.output
    project_toml = tmp_path / ".weaver" / "aozora_sample" / "project.toml"
    db_path = tmp_path / ".weaver" / "aozora_sample" / "weaver.db"
    segment_id = _first_segment_id(db_path)
    editor_script = _write_editor_stub(tmp_path, "Hand-edited translation.")
    monkeypatch.setenv("EDITOR", editor_script)

    edit_result = runner.invoke(app, ["edit", str(project_toml), segment_id])

    assert edit_result.exit_code == 0, edit_result.output
    assert f"Saved. Segment {segment_id} marked manual." in edit_result.output
    with sqlite3.connect(db_path) as connection:
        status = connection.execute(
            "SELECT status FROM segments WHERE id = ?", (segment_id,)
        ).fetchone()[0]
        translation = connection.execute(
            "SELECT text, provider FROM translations WHERE segment_id = ? "
            "ORDER BY attempt DESC LIMIT 1",
            (segment_id,),
        ).fetchone()
    assert status == "manual"
    assert translation == ("Hand-edited translation.", "manual")


def test_weaver_edit_missing_segment_id_exits_with_clear_error(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    init_result = runner.invoke(app, ["init", str(FIXTURE_EPUB)])
    assert init_result.exit_code == 0, init_result.output
    project_toml = tmp_path / ".weaver" / "aozora_sample" / "project.toml"
    editor_script = _write_editor_stub(tmp_path, "Should not be used.")
    monkeypatch.setenv("EDITOR", editor_script)

    edit_result = runner.invoke(app, ["edit", str(project_toml), "missing-segment"])

    assert edit_result.exit_code == 5, edit_result.output
    assert "missing-segment" in edit_result.output


def test_weaver_edit_missing_editor_env_exits_with_config_hint(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    init_result = runner.invoke(app, ["init", str(FIXTURE_EPUB)])
    assert init_result.exit_code == 0, init_result.output
    project_toml = tmp_path / ".weaver" / "aozora_sample" / "project.toml"
    db_path = tmp_path / ".weaver" / "aozora_sample" / "weaver.db"
    segment_id = _first_segment_id(db_path)
    monkeypatch.delenv("EDITOR", raising=False)

    edit_result = runner.invoke(app, ["edit", str(project_toml), segment_id])

    assert edit_result.exit_code != 0, edit_result.output
    assert "EDITOR" in edit_result.output


def _write_editor_stub(tmp_path: Path, replacement_text: str) -> str:
    """Create a cross-platform stub that overwrites argv[1] with replacement text."""

    stub_path = tmp_path / "editor_stub.py"
    stub_path.write_text(
        dedent(
            f"""
            import sys
            from pathlib import Path

            target = Path(sys.argv[1])
            target.write_text({replacement_text!r}, encoding="utf-8")
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    if os.name == "nt":
        runner_path = tmp_path / "editor_stub.cmd"
        runner_path.write_text(
            f'@echo off\r\n"{sys.executable}" "{stub_path}" %1\r\n',
            encoding="utf-8",
        )
        return str(runner_path)
    runner_path = tmp_path / "editor_stub.sh"
    runner_path.write_text(
        f'#!/usr/bin/env bash\nexec "{sys.executable}" "{stub_path}" "$1"\n',
        encoding="utf-8",
    )
    runner_path.chmod(0o755)
    return str(runner_path)


def _first_segment_id(db_path: Path) -> str:
    with sqlite3.connect(db_path) as connection:
        return str(
            connection.execute("SELECT id FROM segments ORDER BY block_order LIMIT 1").fetchone()[0]
        )
