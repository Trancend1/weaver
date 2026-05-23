"""Tests for Phase A7/A8: glossary review progress counter, --find, [f] hotkey."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from typer.testing import CliRunner

from weaver.cli.main import app
from weaver.services.glossary_review import open_glossary_review_session
from weaver.services.project import initialize_project

FIXTURE_EPUB = Path(__file__).parents[1] / "fixtures" / "aozora_sample.epub"


def test_review_prompt_shows_counter_prefix(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    init = runner.invoke(app, ["init", str(FIXTURE_EPUB)])
    assert init.exit_code == 0, init.output
    project_toml = tmp_path / ".weaver" / "aozora_sample" / "project.toml"

    result = runner.invoke(app, ["glossary", "review", str(project_toml)], input="q\n")

    assert result.exit_code == 0, result.output
    assert "Reviewed 0 of " in result.output


def test_review_find_flag_jumps_to_matching_candidate(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    init = runner.invoke(app, ["init", str(FIXTURE_EPUB)])
    assert init.exit_code == 0, init.output
    project_toml = tmp_path / ".weaver" / "aozora_sample" / "project.toml"

    db_path = tmp_path / ".weaver" / "aozora_sample" / "weaver.db"
    with sqlite3.connect(db_path) as connection:
        first_source = connection.execute(
            "SELECT source FROM glossary_candidates WHERE status = 'pending' "
            "ORDER BY frequency DESC, source, id LIMIT 1"
        ).fetchone()[0]

    result = runner.invoke(
        app,
        ["glossary", "review", str(project_toml), "--find", first_source],
        input="q\n",
    )

    assert result.exit_code == 0, result.output
    assert f"Source: {first_source}" in result.output


def test_review_find_flag_falls_back_to_normal_queue_when_no_match(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    init = runner.invoke(app, ["init", str(FIXTURE_EPUB)])
    assert init.exit_code == 0, init.output
    project_toml = tmp_path / ".weaver" / "aozora_sample" / "project.toml"

    result = runner.invoke(
        app,
        ["glossary", "review", str(project_toml), "--find", "no_such_term_xyz"],
        input="q\n",
    )

    assert result.exit_code == 0, result.output
    assert "No pending candidate matches `no_such_term_xyz`" in result.output


def test_review_f_hotkey_prompts_for_substring(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    init = runner.invoke(app, ["init", str(FIXTURE_EPUB)])
    assert init.exit_code == 0, init.output
    project_toml = tmp_path / ".weaver" / "aozora_sample" / "project.toml"

    # f → empty substring → "Find cancelled" → next loop → q
    result = runner.invoke(app, ["glossary", "review", str(project_toml)], input="f\n\nq\n")

    assert result.exit_code == 0, result.output
    assert "Find substring" in result.output
    assert "Find cancelled" in result.output


def test_session_find_returns_none_for_empty_substring(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)

    with open_glossary_review_session(init.project_toml) as session:
        assert session.find("") is None
        assert session.find("   ") is None
