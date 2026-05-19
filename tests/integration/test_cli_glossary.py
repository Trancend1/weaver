"""CLI tests for Phase 5 glossary workflow."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from typer.testing import CliRunner

from weaver.cli.main import app

FIXTURE_EPUB = Path(__file__).parents[1] / "fixtures" / "aozora_sample.epub"


def test_weaver_init_extracts_glossary_candidates_and_writes_tsv(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    result = runner.invoke(app, ["init", str(FIXTURE_EPUB)])

    assert result.exit_code == 0, result.output
    assert "Extracted" in result.output
    assert "weaver glossary review" in result.output
    candidate_tsv = tmp_path / ".weaver" / "aozora_sample" / "glossary_candidates.tsv"
    db_path = tmp_path / ".weaver" / "aozora_sample" / "weaver.db"
    assert candidate_tsv.exists()
    assert "source\ttarget\tcategory\tnotes\tstatus\tfrequency" in candidate_tsv.read_text(
        encoding="utf-8"
    )
    with sqlite3.connect(db_path) as connection:
        count = connection.execute("SELECT COUNT(*) FROM glossary_candidates").fetchone()[0]
    assert count >= 1


def test_weaver_glossary_review_approves_and_persists_first_candidate(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    init = runner.invoke(app, ["init", str(FIXTURE_EPUB)])
    assert init.exit_code == 0, init.output
    project_toml = tmp_path / ".weaver" / "aozora_sample" / "project.toml"

    result = runner.invoke(app, ["glossary", "review", str(project_toml)], input="a\nq\n")

    assert result.exit_code == 0, result.output
    assert "Approved" in result.output
    with sqlite3.connect(tmp_path / ".weaver" / "aozora_sample" / "weaver.db") as connection:
        approved = connection.execute("SELECT COUNT(*) FROM glossary_terms").fetchone()[0]
        pending = connection.execute(
            "SELECT COUNT(*) FROM glossary_candidates WHERE status = 'pending'"
        ).fetchone()[0]
    assert approved == 1
    assert pending >= 0


def test_weaver_glossary_review_shows_example_sentences(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    init = runner.invoke(app, ["init", str(FIXTURE_EPUB)])
    assert init.exit_code == 0, init.output
    project_toml = tmp_path / ".weaver" / "aozora_sample" / "project.toml"

    result = runner.invoke(app, ["glossary", "review", str(project_toml)], input="q\n")

    assert result.exit_code == 0, result.output
    assert "Examples:" in result.output


def test_weaver_glossary_review_edit_updates_target_and_notes(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    init = runner.invoke(app, ["init", str(FIXTURE_EPUB)])
    assert init.exit_code == 0, init.output
    project_toml = tmp_path / ".weaver" / "aozora_sample" / "project.toml"

    result = runner.invoke(
        app,
        ["glossary", "review", str(project_toml)],
        input="e\nEdited Target\nKeep this spelling\nq\n",
    )

    assert result.exit_code == 0, result.output
    assert "Edited" in result.output
    with sqlite3.connect(tmp_path / ".weaver" / "aozora_sample" / "weaver.db") as connection:
        term = connection.execute("SELECT target, notes FROM glossary_terms LIMIT 1").fetchone()
    assert tuple(term) == ("Edited Target", "Keep this spelling")
