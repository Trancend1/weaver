"""Direct glossary term service tests + injection proof (Sprint 5A).

The injection proof asserts that terms managed here actually reach the
translation context (``build_context().glossary_terms``) — the real integration
point — and the rendered prompt's ``<glossary>`` block.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from weaver.errors import GlossaryTermNotFoundError
from weaver.providers.prompts import render_user_message
from weaver.providers.types import GlossaryTerm
from weaver.services.glossary_terms import (
    add_term,
    delete_term,
    list_terms,
    list_terms_page,
    update_term,
)
from weaver.services.project import initialize_project
from weaver.services.translation import build_context

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
FIXTURE_EPUB_A = FIXTURES / "aozora_sample.epub"


def test_add_list_update_delete_roundtrip(tmp_path) -> None:
    init = initialize_project(FIXTURE_EPUB_A, cwd=tmp_path, provider="fake")

    add_term(init.project_toml, source="魔王", target="Demon King", cwd=tmp_path)
    terms = list_terms(init.project_toml, cwd=tmp_path)
    assert [t.source for t in terms] == ["魔王"]
    assert terms[0].target == "Demon King"

    update_term(init.project_toml, source="魔王", target="Demon Lord", cwd=tmp_path)
    assert list_terms(init.project_toml, cwd=tmp_path)[0].target == "Demon Lord"

    delete_term(init.project_toml, source="魔王", cwd=tmp_path)
    assert list_terms(init.project_toml, cwd=tmp_path) == ()


def test_add_same_source_upserts(tmp_path) -> None:
    init = initialize_project(FIXTURE_EPUB_A, cwd=tmp_path, provider="fake")
    add_term(init.project_toml, source="勇者", target="Hero", cwd=tmp_path)
    add_term(init.project_toml, source="勇者", target="Brave Hero", cwd=tmp_path)
    terms = list_terms(init.project_toml, cwd=tmp_path)
    assert len(terms) == 1
    assert terms[0].target == "Brave Hero"


def test_update_missing_raises(tmp_path) -> None:
    init = initialize_project(FIXTURE_EPUB_A, cwd=tmp_path, provider="fake")
    with pytest.raises(GlossaryTermNotFoundError):
        update_term(init.project_toml, source="未登録", target="x", cwd=tmp_path)


def test_delete_missing_raises(tmp_path) -> None:
    init = initialize_project(FIXTURE_EPUB_A, cwd=tmp_path, provider="fake")
    with pytest.raises(GlossaryTermNotFoundError):
        delete_term(init.project_toml, source="未登録", cwd=tmp_path)


def test_empty_source_or_target_rejected(tmp_path) -> None:
    init = initialize_project(FIXTURE_EPUB_A, cwd=tmp_path, provider="fake")
    with pytest.raises(ValueError):
        add_term(init.project_toml, source="  ", target="x", cwd=tmp_path)
    with pytest.raises(ValueError):
        add_term(init.project_toml, source="猫", target="  ", cwd=tmp_path)


def test_managed_term_enters_translation_context(tmp_path) -> None:
    """Injection proof: a managed term reaches build_context().glossary_terms."""
    init = initialize_project(FIXTURE_EPUB_A, cwd=tmp_path, provider="fake")
    add_term(init.project_toml, source="魔王", target="Demon King", cwd=tmp_path)

    terms = list_terms(init.project_toml, cwd=tmp_path)
    context = build_context(
        normalized_source_text="その時、魔王が現れた。",
        glossary_terms=terms,
        previous_segments=[],
    )

    sources = [t.source for t in context.glossary_terms]
    assert "魔王" in sources

    rendered = render_user_message(context, source_text="その時、魔王が現れた。")
    assert "<glossary>" in rendered
    assert "魔王" in rendered
    assert "Demon King" in rendered


def test_list_terms_page_paginates_and_counts(tmp_path) -> None:
    init = initialize_project(FIXTURE_EPUB_A, cwd=tmp_path, provider="fake")
    for src, tgt in [("魔王", "Demon King"), ("勇者", "Hero"), ("カイ", "Kai")]:
        add_term(init.project_toml, source=src, target=tgt, cwd=tmp_path)

    first = list_terms_page(init.project_toml, cwd=tmp_path, offset=0, limit=2)
    assert first.total == 3
    assert first.offset == 0
    assert first.limit == 2
    assert [t.source for t in first.items] == ["魔王", "勇者"]

    second = list_terms_page(init.project_toml, cwd=tmp_path, offset=2, limit=2)
    assert [t.source for t in second.items] == ["カイ"]


def test_list_terms_page_find_filters_by_source_or_target(tmp_path) -> None:
    init = initialize_project(FIXTURE_EPUB_A, cwd=tmp_path, provider="fake")
    add_term(init.project_toml, source="魔王", target="Demon King", cwd=tmp_path)
    add_term(init.project_toml, source="勇者", target="Hero", cwd=tmp_path)

    page = list_terms_page(init.project_toml, cwd=tmp_path, find="king")
    assert page.find == "king"
    assert [t.source for t in page.items] == ["魔王"]
    assert page.total == 1


def test_list_terms_page_find_no_match_is_empty(tmp_path) -> None:
    init = initialize_project(FIXTURE_EPUB_A, cwd=tmp_path, provider="fake")
    add_term(init.project_toml, source="魔王", target="Demon King", cwd=tmp_path)

    page = list_terms_page(init.project_toml, cwd=tmp_path, find="ZZZ-nope")
    assert page.items == ()
    assert page.total == 0


def test_unmatched_term_filtered_from_context() -> None:
    """A term whose source is absent from the segment is filtered out."""
    context = build_context(
        normalized_source_text="こんにちは。",
        glossary_terms=[GlossaryTerm(source="魔王", target="Demon King")],
        previous_segments=[],
    )
    assert context.glossary_terms == ()
