"""Parser unit tests covering direct, regex, and failure paths."""

from __future__ import annotations

import pytest

from weaver.errors import ParserError
from weaver.providers.parser import (
    MAX_NOTE_CHARS,
    MAX_TRANSLATION_CHARS,
    parse_response,
)


def test_parse_response_direct_json_returns_translation() -> None:
    raw = '{"translation": "Hello", "notes": ["n1"], "uncertain_terms": ["t1"]}'

    response = parse_response(raw, input_tokens=10, output_tokens=5)

    assert response.translation == "Hello"
    assert response.notes == ("n1",)
    assert response.uncertain_terms == ("t1",)
    assert response.input_tokens == 10
    assert response.output_tokens == 5
    assert response.raw_response == raw


def test_parse_response_recovers_json_block_from_markdown_wrapper() -> None:
    raw = '```json\n{"translation": "Hi"}\n```'

    response = parse_response(raw)

    assert response.translation == "Hi"
    assert response.notes == ()
    assert response.uncertain_terms == ()


def test_parse_response_recovers_json_block_with_prose_prefix() -> None:
    raw = 'Sure! Here is the JSON: {"translation": "Hi", "notes": [], "uncertain_terms": []}'

    response = parse_response(raw)

    assert response.translation == "Hi"


def test_parse_response_raises_when_no_json_present() -> None:
    with pytest.raises(ParserError):
        parse_response("not json at all")


def test_parse_response_raises_when_translation_missing() -> None:
    with pytest.raises(ParserError):
        parse_response('{"notes": [], "uncertain_terms": []}')


def test_parse_response_raises_when_translation_empty() -> None:
    with pytest.raises(ParserError):
        parse_response('{"translation": "   ", "notes": [], "uncertain_terms": []}')


def test_parse_response_raises_when_translation_exceeds_max_chars() -> None:
    oversized = "a" * (MAX_TRANSLATION_CHARS + 1)

    with pytest.raises(ParserError):
        parse_response(f'{{"translation": "{oversized}"}}')


def test_parse_response_caps_notes_to_three_entries() -> None:
    raw = '{"translation": "ok", "notes": ["a", "b", "c", "d"], "uncertain_terms": []}'

    response = parse_response(raw)

    assert response.notes == ("a", "b", "c")


def test_parse_response_truncates_long_note_entries() -> None:
    long_note = "x" * (MAX_NOTE_CHARS + 10)
    raw = f'{{"translation": "ok", "notes": ["{long_note}"], "uncertain_terms": []}}'

    response = parse_response(raw)

    assert len(response.notes[0]) == MAX_NOTE_CHARS


def test_parse_response_caps_uncertain_terms_to_ten_entries() -> None:
    terms = [f"t{i}" for i in range(15)]
    raw = (
        '{"translation": "ok", "notes": [], "uncertain_terms": '
        + str(terms).replace("'", '"')
        + "}"
    )

    response = parse_response(raw)

    assert len(response.uncertain_terms) == 10


def test_parse_response_rejects_non_list_notes_field() -> None:
    with pytest.raises(ParserError):
        parse_response('{"translation": "ok", "notes": "not a list"}')


def test_parse_response_rejects_non_string_note_entries() -> None:
    with pytest.raises(ParserError):
        parse_response('{"translation": "ok", "notes": [1, 2]}')
