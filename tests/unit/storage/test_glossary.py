"""Glossary repository tests."""

from __future__ import annotations

from weaver.storage.db import initialize_database
from weaver.storage.glossary import (
    approve_glossary_candidate,
    count_glossary_terms,
    edit_glossary_candidate,
    insert_glossary_candidate,
    list_glossary_candidates,
    list_glossary_terms,
    reject_glossary_candidate,
    upsert_glossary_term,
)
from weaver.storage.projects import create_project


def _seed_terms(connection, project_id: int) -> None:
    for source, target, category in [
        ("魔王", "Demon King", "title"),
        ("勇者", "Hero", "title"),
        ("カイ", "Kai", "name"),
        ("ねこ", "cat", None),
    ]:
        upsert_glossary_term(
            connection,
            project_id=project_id,
            source=source,
            target=target,
            category=category,
        )


def test_candidate_review_actions_persist_and_update_terms(tmp_path) -> None:
    db_path = tmp_path / "weaver.db"
    with initialize_database(db_path) as connection:
        project_id = create_project(
            connection,
            name="fixture",
            source_path="fixture.epub",
            source_lang="ja",
            target_lang="en",
        )
        candidate_id = insert_glossary_candidate(
            connection,
            project_id=project_id,
            source="カイ",
            target="Kai",
            category="katakana",
            notes=None,
            status="pending",
            frequency=2,
        )

        approve_glossary_candidate(connection, candidate_id=candidate_id)
        approved = list_glossary_candidates(connection, project_id=project_id)[0]
        terms = list_glossary_terms(connection, project_id=project_id)

        assert approved.status == "approved"
        assert [(term.source, term.target) for term in terms] == [("カイ", "Kai")]

        edit_glossary_candidate(
            connection,
            candidate_id=candidate_id,
            target="Kye",
            notes="Use translator note",
        )
        edited = list_glossary_candidates(connection, project_id=project_id)[0]
        terms = list_glossary_terms(connection, project_id=project_id)

        assert edited.status == "edited"
        assert edited.notes == "Use translator note"
        assert [(term.source, term.target) for term in terms] == [("カイ", "Kye")]

        reject_glossary_candidate(connection, candidate_id=candidate_id)
        rejected = list_glossary_candidates(connection, project_id=project_id)[0]
        terms = list_glossary_terms(connection, project_id=project_id)

        assert rejected.status == "rejected"
        assert terms == []


def test_list_glossary_terms_default_returns_all_in_id_order(tmp_path) -> None:
    db_path = tmp_path / "weaver.db"
    with initialize_database(db_path) as connection:
        project_id = create_project(
            connection,
            name="fixture",
            source_path="fixture.epub",
            source_lang="ja",
            target_lang="en",
        )
        _seed_terms(connection, project_id)

        terms = list_glossary_terms(connection, project_id=project_id)

        # Default (no limit) preserves the all-rows, id-ordered contract that the
        # prompt-injection callers rely on.
        assert [t.source for t in terms] == ["魔王", "勇者", "カイ", "ねこ"]
        assert count_glossary_terms(connection, project_id=project_id) == 4


def test_list_glossary_terms_limit_offset_paginate(tmp_path) -> None:
    db_path = tmp_path / "weaver.db"
    with initialize_database(db_path) as connection:
        project_id = create_project(
            connection,
            name="fixture",
            source_path="fixture.epub",
            source_lang="ja",
            target_lang="en",
        )
        _seed_terms(connection, project_id)

        first = list_glossary_terms(connection, project_id=project_id, offset=0, limit=2)
        second = list_glossary_terms(connection, project_id=project_id, offset=2, limit=2)

        assert [t.source for t in first] == ["魔王", "勇者"]
        assert [t.source for t in second] == ["カイ", "ねこ"]


def test_list_glossary_terms_find_matches_source_or_target(tmp_path) -> None:
    db_path = tmp_path / "weaver.db"
    with initialize_database(db_path) as connection:
        project_id = create_project(
            connection,
            name="fixture",
            source_path="fixture.epub",
            source_lang="ja",
            target_lang="en",
        )
        _seed_terms(connection, project_id)

        # Matches an English target substring (case-insensitive)...
        by_target = list_glossary_terms(connection, project_id=project_id, find="king")
        assert [t.source for t in by_target] == ["魔王"]
        assert count_glossary_terms(connection, project_id=project_id, find="king") == 1

        # ...and a Japanese source substring.
        by_source = list_glossary_terms(connection, project_id=project_id, find="勇")
        assert [t.source for t in by_source] == ["勇者"]


def test_count_glossary_terms_no_match_is_zero(tmp_path) -> None:
    db_path = tmp_path / "weaver.db"
    with initialize_database(db_path) as connection:
        project_id = create_project(
            connection,
            name="fixture",
            source_path="fixture.epub",
            source_lang="ja",
            target_lang="en",
        )
        _seed_terms(connection, project_id)

        assert count_glossary_terms(connection, project_id=project_id, find="ZZZ") == 0
        assert list_glossary_terms(connection, project_id=project_id, find="ZZZ") == []
