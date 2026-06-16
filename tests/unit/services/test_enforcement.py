"""Tests for the translate-time enforcement gate + bounded repair (ADR 019 E1+E2)."""

from __future__ import annotations

import pytest

from weaver.providers.fake import FakeProvider
from weaver.providers.types import CharacterContext, GlossaryTerm
from weaver.services.enforcement import (
    EnforcementResult,
    evaluate_translation,
    repair_translation,
)

_GLOSSARY = (GlossaryTerm(source="李晨", target="Li Chen"),)
_CHARACTERS = (CharacterContext(jp_name="花子", en_name="Hanako"),)


def _evaluate(translation: str, *, source: str = "李晨は花子に会った。") -> EnforcementResult:
    return evaluate_translation(
        segment_id="s1",
        source_text=source,
        normalized_source_text=source,
        translation_text=translation,
        glossary_terms=_GLOSSARY,
        characters=_CHARACTERS,
    )


def test_clean_translation_has_no_violations() -> None:
    result = _evaluate("Li Chen met Hanako.")
    assert result.ok
    assert result.violations == ()


def test_missing_glossary_target_is_a_violation() -> None:
    result = _evaluate("He met Hanako.")  # Li Chen dropped
    assert not result.ok
    assert any("李晨" in v and "Li Chen" in v for v in result.violations)


def test_missing_character_name_is_a_violation() -> None:
    result = _evaluate("Li Chen met her.")  # Hanako dropped
    assert not result.ok
    assert any("花子" in v and "Hanako" in v for v in result.violations)


def test_untranslated_japanese_residue_is_a_violation() -> None:
    result = _evaluate("Li Chen met Hanako 日本語残留です.")
    assert not result.ok
    assert any("Japanese" in v for v in result.violations)


def test_empty_translation_is_truncation() -> None:
    result = _evaluate("   ")
    assert not result.ok
    assert any("truncation" in v for v in result.violations)


def test_catastrophically_short_translation_is_truncation() -> None:
    # Source is long; a 1-char output is below the 0.15 floor.
    result = _evaluate("x", source="李晨は花子に会い、長い物語の始まりとなった。")
    assert any("truncation" in v for v in result.violations)


def test_terse_but_valid_translation_is_not_truncation() -> None:
    # JP→EN legitimately compresses; a reasonable short line must not trip the floor.
    result = evaluate_translation(
        segment_id="s1",
        source_text="花子は走った。",
        normalized_source_text="花子は走った。",
        translation_text="Hanako ran.",
        characters=_CHARACTERS,
    )
    assert result.ok


def test_repair_returns_reparsed_response_and_tokens() -> None:
    provider = FakeProvider(completion='{"translation": "Li Chen met Hanako."}')
    response = repair_translation(
        provider,
        source_text="李晨は花子に会った。",
        previous_translation="He met Hanako.",
        violations=("Glossary term '李晨' -> 'Li Chen' matched source but target is absent.",),
        source_language="ja",
        target_language="en",
    )
    assert response.translation == "Li Chen met Hanako."
    # A clean re-validate of the repaired text passes.
    assert _evaluate(response.translation).ok


def test_repair_propagates_parser_error_on_garbage() -> None:
    from weaver.errors import ParserError

    provider = FakeProvider(completion="not json at all")
    with pytest.raises(ParserError):
        repair_translation(
            provider,
            source_text="李晨",
            previous_translation="x",
            violations=("v",),
            source_language="ja",
            target_language="en",
        )
