"""Provider request, response, and context types."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GlossaryTerm:
    """Approved glossary term pinned to a translation target."""

    source: str
    target: str
    category: str | None = None
    notes: str | None = None
    case_sensitive: bool = False


@dataclass(frozen=True)
class TranslationContext:
    """Per-segment context assembled by `build_context()`.

    `previous_segments` is ordered oldest-first so the immediately preceding
    segment is last. Capped at 5 entries / 600 tokens per PROMPT_DESIGN.md.
    `glossary_terms` is pre-filtered to entries that substring-match the
    current segment's normalized source text, capped at 20 entries.
    """

    previous_segments: tuple[tuple[str, str], ...]
    glossary_terms: tuple[GlossaryTerm, ...]
    honorific_policy: str


@dataclass(frozen=True)
class TranslationRequest:
    """Single-segment translation request handed to a provider."""

    segment_id: str
    source_text: str
    normalized_source_text: str
    source_language: str
    target_language: str
    context: TranslationContext
    provider_model: str


@dataclass(frozen=True)
class TranslationResponse:
    """Parsed provider response for one segment.

    `input_tokens` / `output_tokens` are None when the provider does not
    report usage (e.g. Ollama, Fake).
    """

    translation: str
    notes: tuple[str, ...]
    uncertain_terms: tuple[str, ...]
    raw_response: str
    input_tokens: int | None
    output_tokens: int | None
