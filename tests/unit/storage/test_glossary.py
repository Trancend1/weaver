"""Glossary repository tests."""

from __future__ import annotations

from weaver.storage.db import initialize_database
from weaver.storage.glossary import (
    approve_glossary_candidate,
    edit_glossary_candidate,
    insert_glossary_candidate,
    list_glossary_candidates,
    list_glossary_terms,
    reject_glossary_candidate,
)
from weaver.storage.projects import create_project


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
