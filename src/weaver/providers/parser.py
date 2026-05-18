"""JSON output parser with regex fallback for provider responses."""

from __future__ import annotations

import json
import re
from typing import Any

from weaver.errors import ParserError
from weaver.providers.types import TranslationResponse

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)

MAX_TRANSLATION_CHARS = 8000
MAX_NOTES = 3
MAX_NOTE_CHARS = 200
MAX_UNCERTAIN_TERMS = 10


def parse_response(
    raw: str,
    *,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
) -> TranslationResponse:
    """Parse a raw provider response into a `TranslationResponse`.

    Attempts a direct `json.loads`, then falls back to extracting the first
    `{...}` block via regex (per PROMPT_DESIGN.md §Parse And Repair Flow).
    Raises `ParserError` if both attempts fail; the caller is expected to
    send a single repair prompt and re-invoke this function before marking
    the segment failed.

    Args:
        raw: Raw text returned by the provider.
        input_tokens: Optional upstream input token count.
        output_tokens: Optional upstream output token count.

    Returns:
        Validated TranslationResponse.

    Raises:
        ParserError: If raw text contains no parseable JSON object matching
            the expected schema.
    """

    parsed = _try_direct(raw) or _try_regex(raw)
    if parsed is None:
        raise ParserError(
            "Provider response is not valid JSON. "
            "Likely cause: model returned prose or truncated output. "
            "Next command: rerun translation; one repair attempt will be issued automatically."
        )

    translation = _require_translation(parsed)
    notes = _coerce_string_list(parsed.get("notes"), MAX_NOTES, MAX_NOTE_CHARS, "notes")
    uncertain = _coerce_string_list(
        parsed.get("uncertain_terms"), MAX_UNCERTAIN_TERMS, None, "uncertain_terms"
    )
    return TranslationResponse(
        translation=translation,
        notes=notes,
        uncertain_terms=uncertain,
        raw_response=raw,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def _try_direct(raw: str) -> dict[str, Any] | None:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _try_regex(raw: str) -> dict[str, Any] | None:
    match = _JSON_BLOCK_RE.search(raw)
    if match is None:
        return None
    try:
        value = json.loads(match.group())
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _require_translation(parsed: dict[str, Any]) -> str:
    value = parsed.get("translation")
    if not isinstance(value, str) or not value.strip():
        raise ParserError(
            "Provider response is missing a non-empty `translation` field. "
            "Likely cause: model returned empty output or wrong schema. "
            "Next command: rerun translation; a repair prompt will be issued."
        )
    if len(value) > MAX_TRANSLATION_CHARS:
        raise ParserError(
            f"Provider translation exceeds {MAX_TRANSLATION_CHARS} characters. "
            "Likely cause: model expanded source beyond budget. "
            "Next command: split the source segment or rerun."
        )
    return value


def _coerce_string_list(
    raw_value: Any,
    max_items: int,
    max_chars: int | None,
    field: str,
) -> tuple[str, ...]:
    if raw_value is None:
        return ()
    if not isinstance(raw_value, list):
        raise ParserError(
            f"Provider field `{field}` must be a JSON array of strings. "
            "Likely cause: model returned wrong type. "
            "Next command: rerun translation."
        )
    items: list[str] = []
    for entry in raw_value[:max_items]:
        if not isinstance(entry, str):
            raise ParserError(
                f"Provider field `{field}` contains non-string entries. "
                "Likely cause: model returned mixed types. "
                "Next command: rerun translation."
            )
        if max_chars is not None and len(entry) > max_chars:
            entry = entry[:max_chars]
        items.append(entry)
    return tuple(items)
