"""Tests for the GlossaryReviewSession service."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from weaver.services.glossary_review import (
    list_project_glossary_conflicts,
    open_glossary_review_session,
)
from weaver.services.project import initialize_project

FIXTURE_EPUB = Path(__file__).resolve().parents[2] / "fixtures" / "aozora_sample.epub"


def test_session_status_counts_starts_all_pending(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)

    with open_glossary_review_session(init.project_toml) as session:
        counts = session.status_counts()

    assert counts.pending == init.glossary_candidate_count
    assert counts.approved == 0
    assert counts.rejected == 0


def test_session_next_pending_returns_none_when_queue_empty(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)

    with open_glossary_review_session(init.project_toml) as session:
        while True:
            candidate = session.next_pending()
            if candidate is None:
                break
            session.reject(candidate)
        assert session.next_pending() is None
        assert session.status_counts().pending == 0


def test_session_examples_for_returns_segment_source_text(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)

    with open_glossary_review_session(init.project_toml) as session:
        candidate = session.next_pending()
        assert candidate is not None
        examples = session.examples_for(candidate.source, limit=5)

    assert examples, "expected at least one example sentence"
    assert all(candidate.source in line for line in examples)


def test_session_approve_persists_term_and_commits_independently(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)

    with open_glossary_review_session(init.project_toml) as session:
        candidate = session.next_pending()
        assert candidate is not None
        session.approve(candidate)

    with sqlite3.connect(init.database_path) as connection:
        status = connection.execute(
            "SELECT status FROM glossary_candidates WHERE id = ?", (candidate.id,)
        ).fetchone()[0]
        term_count = connection.execute(
            "SELECT COUNT(*) FROM glossary_terms WHERE source = ?", (candidate.source,)
        ).fetchone()[0]

    assert status == "approved"
    assert term_count == 1


def test_session_edit_records_edited_status_and_translator_wording(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)

    with open_glossary_review_session(init.project_toml) as session:
        candidate = session.next_pending()
        assert candidate is not None
        session.edit(candidate, target="Hand-picked", notes="Translator preference")

    with sqlite3.connect(init.database_path) as connection:
        row = connection.execute(
            "SELECT status, target, notes FROM glossary_candidates WHERE id = ?",
            (candidate.id,),
        ).fetchone()
        term = connection.execute(
            "SELECT target, notes FROM glossary_terms WHERE source = ?",
            (candidate.source,),
        ).fetchone()

    assert tuple(row) == ("edited", "Hand-picked", "Translator preference")
    assert tuple(term) == ("Hand-picked", "Translator preference")


def test_session_reject_clears_existing_term(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)

    with open_glossary_review_session(init.project_toml) as session:
        candidate = session.next_pending()
        assert candidate is not None
        session.approve(candidate)
        session.reject(candidate)

    with sqlite3.connect(init.database_path) as connection:
        status = connection.execute(
            "SELECT status FROM glossary_candidates WHERE id = ?", (candidate.id,)
        ).fetchone()[0]
        term_count = connection.execute(
            "SELECT COUNT(*) FROM glossary_terms WHERE source = ?", (candidate.source,)
        ).fetchone()[0]

    assert status == "rejected"
    assert term_count == 0


def test_session_undo_restores_last_action_then_clears(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)

    with open_glossary_review_session(init.project_toml) as session:
        candidate = session.next_pending()
        assert candidate is not None
        session.approve(candidate)
        assert session.undo() is True
        assert session.undo() is False

    with sqlite3.connect(init.database_path) as connection:
        status = connection.execute(
            "SELECT status FROM glossary_candidates WHERE id = ?", (candidate.id,)
        ).fetchone()[0]
        term_count = connection.execute(
            "SELECT COUNT(*) FROM glossary_terms WHERE source = ?", (candidate.source,)
        ).fetchone()[0]

    assert status == "pending"
    assert term_count == 0


def test_session_undo_with_no_history_returns_false(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)

    with open_glossary_review_session(init.project_toml) as session:
        assert session.undo() is False


def test_list_project_glossary_conflicts_returns_conflicting_sources(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)

    with open_glossary_review_session(init.project_toml) as session:
        candidate = session.next_pending()
        assert candidate is not None
        session.edit(candidate, target="Variant A", notes=None)
        with sqlite3.connect(init.database_path) as connection:
            connection.execute(
                """
                INSERT INTO glossary_candidates (
                  project_id, source, target, category, notes, status, frequency
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session.project_id,
                    candidate.source,
                    "Variant B",
                    candidate.category,
                    None,
                    "approved",
                    candidate.frequency,
                ),
            )
            connection.commit()

    conflicts = list_project_glossary_conflicts(init.project_toml)
    assert any(source == candidate.source for source, _ in conflicts)
    matching = next(targets for source, targets in conflicts if source == candidate.source)
    assert "Variant A" in matching
    assert "Variant B" in matching
