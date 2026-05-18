"""Tests for glossary candidate extraction and conflict checks."""

from __future__ import annotations

import pytest

from weaver.core.ir import (
    BlockIR,
    ChapterIR,
    DocumentIR,
    DocumentMetadata,
    EpubMarkupContext,
)
from weaver.errors import GlossaryConflictError
from weaver.services.glossary import extract_glossary_candidates, raise_on_glossary_conflicts
from weaver.storage.db import initialize_database
from weaver.storage.glossary import insert_glossary_candidate
from weaver.storage.projects import create_project


def test_extract_glossary_candidates_finds_katakana_and_honorific_terms() -> None:
    document = _document(
        title="カイとミナ様",
        blocks=[
            "カイは剣を抜いた。ミナ様は笑った。",
            "カイたちは門を開けた。ミナ様の声が響いた。",
        ],
    )

    candidates = extract_glossary_candidates(document)

    by_source = {candidate.source: candidate for candidate in candidates}
    assert by_source["カイ"].frequency == 2
    assert by_source["カイ"].category == "katakana"
    assert by_source["ミナ"].frequency == 2
    assert by_source["ミナ"].category == "honorific"


def test_extract_glossary_candidates_filters_singletons_not_in_title() -> None:
    document = _document(title="序章", blocks=["ルナは去った。カイは残った。カイは笑った。"])

    candidates = extract_glossary_candidates(document)

    assert [candidate.source for candidate in candidates] == ["カイ"]


def test_raise_on_glossary_conflicts_detects_approved_candidate_disagreement(
    tmp_path,
) -> None:
    db_path = tmp_path / "weaver.db"
    with initialize_database(db_path) as connection:
        project_id = create_project(
            connection,
            name="fixture",
            source_path="fixture.epub",
            source_lang="ja",
            target_lang="en",
        )
        insert_glossary_candidate(
            connection,
            project_id=project_id,
            source="カイ",
            target="Kai",
            category="katakana",
            notes=None,
            status="approved",
            frequency=4,
        )
        insert_glossary_candidate(
            connection,
            project_id=project_id,
            source="カイ",
            target="Kye",
            category="katakana",
            notes=None,
            status="edited",
            frequency=4,
        )

        with pytest.raises(GlossaryConflictError):
            raise_on_glossary_conflicts(connection, project_id=project_id)


def _document(*, title: str, blocks: list[str]) -> DocumentIR:
    return DocumentIR(
        metadata=DocumentMetadata(
            title="Fixture",
            author=None,
            language="ja",
            identifier="fixture-id",
            publisher=None,
            description=None,
        ),
        assets=[],
        chapters=[
            ChapterIR(
                id="chapter-1",
                title=title,
                href="text/chapter.xhtml",
                order=0,
                blocks=[
                    BlockIR(
                        id=f"seg-{index}",
                        chapter_id="chapter-1",
                        order=index,
                        kind="paragraph",
                        source_text=text,
                        normalized_source_text=text,
                        markup_context=EpubMarkupContext(
                            file_href="text/chapter.xhtml",
                            xpath=f"/html/body/p[{index + 1}]",
                            tag="p",
                            attrs={},
                            text_node_index=0,
                        ),
                    )
                    for index, text in enumerate(blocks)
                ],
            )
        ],
    )
