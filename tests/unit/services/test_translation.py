"""Tests for `build_context()`."""

from __future__ import annotations

import pytest

from weaver.core.ir import BlockIR, EpubMarkupContext
from weaver.providers.types import GlossaryTerm
from weaver.services.translation import (
    MAX_CONTEXT_SEGMENTS,
    MAX_GLOSSARY_TERMS_PER_SEGMENT,
    build_context,
)


def _segment(text: str) -> BlockIR:
    return BlockIR(
        id="seg-1",
        chapter_id="ch-1",
        order=0,
        kind="paragraph",
        source_text=text,
        normalized_source_text=text,
        markup_context=EpubMarkupContext(
            file_href="text/ch1.xhtml",
            xpath="/html/body/p[1]",
            tag="p",
            attrs={},
            text_node_index=0,
        ),
    )


def test_build_context_filters_glossary_to_matching_terms() -> None:
    glossary = [
        GlossaryTerm(source="護衛", target="bodyguard"),
        GlossaryTerm(source="魔王", target="Demon King"),
    ]
    segment = _segment("護衛が来た。")

    ctx = build_context(
        segment=segment,
        glossary_terms=glossary,
        previous_segments=[],
    )

    assert [term.source for term in ctx.glossary_terms] == ["護衛"]


def test_build_context_returns_empty_glossary_when_no_matches() -> None:
    glossary = [GlossaryTerm(source="護衛", target="bodyguard")]
    segment = _segment("関係のない文章。")

    ctx = build_context(segment=segment, glossary_terms=glossary, previous_segments=[])

    assert ctx.glossary_terms == ()


def test_build_context_caps_glossary_at_twenty_terms() -> None:
    text = "".join(f"term{i}" for i in range(30))
    glossary = [GlossaryTerm(source=f"term{i}", target=f"t{i}") for i in range(30)]
    segment = _segment(text)

    ctx = build_context(segment=segment, glossary_terms=glossary, previous_segments=[])

    assert len(ctx.glossary_terms) == MAX_GLOSSARY_TERMS_PER_SEGMENT


def test_build_context_keeps_window_oldest_first_within_cap() -> None:
    window = [(f"src-{i}", f"trg-{i}") for i in range(8)]
    segment = _segment("次の段落。")

    ctx = build_context(segment=segment, glossary_terms=[], previous_segments=window)

    assert len(ctx.previous_segments) == MAX_CONTEXT_SEGMENTS
    assert ctx.previous_segments[0] == ("src-3", "trg-3")
    assert ctx.previous_segments[-1] == ("src-7", "trg-7")


def test_build_context_first_segment_yields_empty_window() -> None:
    ctx = build_context(
        segment=_segment("始まり。"),
        glossary_terms=[],
        previous_segments=[],
    )

    assert ctx.previous_segments == ()


def test_build_context_case_insensitive_match_by_default() -> None:
    glossary = [GlossaryTerm(source="Kai", target="カイ")]
    segment = _segment("kai walked away.")

    ctx = build_context(segment=segment, glossary_terms=glossary, previous_segments=[])

    assert ctx.glossary_terms == tuple(glossary)


def test_build_context_case_sensitive_term_requires_exact_case() -> None:
    glossary = [GlossaryTerm(source="Kai", target="カイ", case_sensitive=True)]
    segment_lower = _segment("kai walked away.")
    segment_exact = _segment("Kai walked away.")

    assert (
        build_context(
            segment=segment_lower, glossary_terms=glossary, previous_segments=[]
        ).glossary_terms
        == ()
    )
    assert build_context(
        segment=segment_exact, glossary_terms=glossary, previous_segments=[]
    ).glossary_terms == tuple(glossary)


def test_build_context_rejects_unknown_honorific_policy() -> None:
    with pytest.raises(ValueError):
        build_context(
            segment=_segment("テスト。"),
            glossary_terms=[],
            previous_segments=[],
            honorific_policy="rude",
        )


def test_build_context_drops_window_segments_when_over_token_budget() -> None:
    long_source = "あ" * 2000
    long_translation = "a" * 2000
    window = [(long_source, long_translation) for _ in range(5)]

    ctx = build_context(
        segment=_segment("次。"),
        glossary_terms=[],
        previous_segments=window,
    )

    assert len(ctx.previous_segments) < MAX_CONTEXT_SEGMENTS
