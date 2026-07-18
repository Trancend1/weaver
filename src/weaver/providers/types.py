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
class CharacterContext:
    """Project character pinned to a consistent English name for translation."""

    jp_name: str
    en_name: str
    gender: str | None = None
    role: str | None = None
    notes: str | None = None


@dataclass(frozen=True)
class TranslationProfile:
    """Project-level style contract emitted as the prompt `<profile>` block (ADR 019 E3).

    All fields optional and free-form (no enum): the user describes the desired
    register. `banned_phrases` is also a deterministic anti-slop check fed to the
    enforcement gate (a soft repair trigger), never a hard block.
    """

    tone: str | None = None
    dialog_style: str | None = None
    name_rendering: str | None = None
    tense: str | None = None
    banned_phrases: tuple[str, ...] = ()

    @property
    def has_style(self) -> bool:
        """True when any style field is set (drives whether to emit `<profile>`)."""
        return any((self.tone, self.dialog_style, self.name_rendering, self.tense))


@dataclass(frozen=True)
class TranslationContext:
    """Per-segment context assembled by `build_context()`.

    `previous_segments` is ordered oldest-first so the immediately preceding
    segment is last. Capped at 5 entries / 600 tokens per PROMPT_DESIGN.md.
    `glossary_terms` is pre-filtered to entries that substring-match the
    current segment's normalized source text, capped at 20 entries.
    `characters` is pre-filtered the same way (jp_name substring), capped at 20.
    `profile` is the project-level style contract (None when unset).
    """

    previous_segments: tuple[tuple[str, str], ...]
    glossary_terms: tuple[GlossaryTerm, ...]
    honorific_policy: str
    characters: tuple[CharacterContext, ...] = ()
    profile: TranslationProfile | None = None


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
    report usage (e.g. Ollama, Fake). When the provider needed an internal
    JSON-parse repair round-trip, `json_repair_used` is True and the token
    counts cover **both** calls, so the hidden round-trip's cost is never
    silently dropped (audit F6).
    """

    translation: str
    notes: tuple[str, ...]
    uncertain_terms: tuple[str, ...]
    raw_response: str
    input_tokens: int | None
    output_tokens: int | None
    json_repair_used: bool = False


@dataclass(frozen=True)
class Completion:
    """Raw text completion + token usage from a provider's `complete()` primitive.

    Domain-agnostic transport result: `text` is the model's verbatim output.
    `input_tokens`/`output_tokens` are None when the provider does not report usage.
    """

    text: str
    input_tokens: int | None
    output_tokens: int | None
    raw_response: str
