"""Enforcement provenance persistence on translation attempts (v0.7.3 M3, audit A4b)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from weaver.storage.db import initialize_database
from weaver.storage.projects import create_project
from weaver.storage.segments import insert_segment
from weaver.storage.translations import (
    list_translation_attempts,
    record_translation,
)


def _open_project_db(db_path: Path) -> sqlite3.Connection:
    connection = initialize_database(db_path)
    project_id = create_project(
        connection,
        name="fixture",
        source_path="fixture.epub",
        source_lang="ja",
        target_lang="en",
    )
    connection.execute(
        """
        INSERT INTO chapters (id, project_id, title, href, spine_order)
        VALUES ('chapter-1', ?, 'Chapter', 'text/chapter.xhtml', 0)
        """,
        (project_id,),
    )
    insert_segment(
        connection,
        segment_id="seg-1",
        chapter_id="chapter-1",
        block_order=0,
        kind="paragraph",
        source_text="一。",
        source_hash="hash-1",
    )
    return connection


def test_record_translation_persists_enforcement_provenance(tmp_path) -> None:
    with _open_project_db(tmp_path / "weaver.db") as connection:
        record_translation(
            connection,
            segment_id="seg-1",
            text="One.",
            source_hash="hash-1",
            provider="fake",
            model="fake-1",
            input_tokens=100,
            output_tokens=40,
            enforcement_violations=["Glossary term 'ネコ' missing its target 'Cat'."],
            repair_attempted=True,
            repair_outcome="accepted",
            repair_input_tokens=55,
            repair_output_tokens=20,
        )
        attempts = list_translation_attempts(connection, segment_id="seg-1")

    assert len(attempts) == 1
    attempt = attempts[0]
    assert attempt.enforcement_violations == ("Glossary term 'ネコ' missing its target 'Cat'.",)
    assert attempt.repair_attempted is True
    assert attempt.repair_outcome == "accepted"
    assert attempt.input_tokens == 100
    assert attempt.output_tokens == 40
    assert attempt.repair_input_tokens == 55
    assert attempt.repair_output_tokens == 20


def test_record_translation_defaults_read_back_as_not_evaluated(tmp_path) -> None:
    """A provenance-less write (memory reuse, manual save) stays 'not evaluated'."""

    with _open_project_db(tmp_path / "weaver.db") as connection:
        record_translation(
            connection,
            segment_id="seg-1",
            text="One.",
            source_hash="hash-1",
            provider="memory",
            model="memory",
        )
        attempts = list_translation_attempts(connection, segment_id="seg-1")

    attempt = attempts[0]
    assert attempt.enforcement_violations is None
    assert attempt.repair_attempted is False
    assert attempt.repair_outcome is None
    assert attempt.repair_input_tokens is None
    assert attempt.repair_output_tokens is None


def test_record_translation_evaluated_clean_is_distinct_from_not_evaluated(tmp_path) -> None:
    with _open_project_db(tmp_path / "weaver.db") as connection:
        record_translation(
            connection,
            segment_id="seg-1",
            text="One.",
            source_hash="hash-1",
            provider="fake",
            model="fake-1",
            enforcement_violations=[],
        )
        attempts = list_translation_attempts(connection, segment_id="seg-1")

    assert attempts[0].enforcement_violations == ()


def test_record_translation_rejects_unknown_repair_outcome(tmp_path) -> None:
    with (
        _open_project_db(tmp_path / "weaver.db") as connection,
        pytest.raises(ValueError, match="repair_outcome"),
    ):
        record_translation(
            connection,
            segment_id="seg-1",
            text="One.",
            source_hash="hash-1",
            provider="fake",
            model="fake-1",
            repair_outcome="bogus",
        )
