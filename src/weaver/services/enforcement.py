"""Translate-time enforcement gate + bounded repair (ADR 019 E1+E2).

Makes the project's glossary/character database **binding** instead of advisory.

- **Detection (E1, free):** :func:`evaluate_translation` returns the deterministic
  violations in a fresh translation — glossary target absent, character EN-name
  absent, untranslated-Japanese residue, catastrophic truncation — reusing the
  existing QA primitives so the translate-time gate and the advisory QA report
  agree. No model call, no DB, no web (pure).
- **Repair (E2, bounded):** :func:`repair_translation` issues **one** targeted
  re-ask via the provider's ``complete()`` primitive (ADR 014) and re-parses it.
  Single pass — no loop, no circuit breaker (ADR 018 D9). The ``provider`` is
  passed in (ADR 019 §5 routing seam: a future ``[routing.repair]`` swaps the
  engine with no refactor). The caller re-validates once and treats a failure as
  "keep the original attempt" — never a block, never a silent source substitution.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from weaver.providers.base import LLMProvider
from weaver.providers.parser import parse_response
from weaver.providers.prompts import (
    ENFORCEMENT_REPAIR_SYSTEM,
    render_enforcement_repair_prompt,
)
from weaver.providers.types import CharacterContext, GlossaryTerm, TranslationResponse
from weaver.qa.checks import SegmentInput, check_glossary_mismatch, check_untranslated_japanese
from weaver.qa.consistency_checks import CharacterName, check_character_name_missing

# A translation shorter than this fraction of its source's character length is
# treated as catastrophic truncation. A **loose** anti-truncation floor only
# (ADR 019 §6, Q4): NOT the QA `minimum_length_ratio` — forcing length toward a
# ratio makes the model pad with filler, which is itself slop.
TRUNCATION_FLOOR_RATIO = 0.15

# Output budget for the single repair re-ask (one segment's worth).
REPAIR_MAX_OUTPUT_TOKENS = 2000


@dataclass(frozen=True)
class EnforcementResult:
    """Deterministic violations found in a fresh translation (empty = clean)."""

    violations: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.violations


def evaluate_translation(
    *,
    segment_id: str,
    source_text: str,
    normalized_source_text: str,
    translation_text: str,
    glossary_terms: Iterable[GlossaryTerm] = (),
    characters: Iterable[CharacterContext] = (),
) -> EnforcementResult:
    """Return the deterministic enforcement violations for one fresh translation.

    Pure (no model call, no DB). Reuses :func:`check_glossary_mismatch`,
    :func:`check_character_name_missing`, and :func:`check_untranslated_japanese`
    so the gate agrees with the advisory QA report, plus a loose anti-truncation
    floor.
    """

    seg = SegmentInput(
        segment_id=segment_id,
        source_text=source_text,
        normalized_source_text=normalized_source_text,
        status="translated",
        translation_text=translation_text,
    )
    messages: list[str] = [w.message for w in check_glossary_mismatch(seg, tuple(glossary_terms))]
    names = tuple(CharacterName(jp_name=c.jp_name, en_name=c.en_name) for c in characters)
    messages.extend(w.message for w in check_character_name_missing(seg, names))
    jp_residue = check_untranslated_japanese(seg)
    if jp_residue is not None:
        messages.append(jp_residue.message)
    if _is_truncated(source_text, translation_text):
        messages.append(
            "Translation is empty or far shorter than the source (possible truncation)."
        )
    return EnforcementResult(violations=tuple(messages))


def _is_truncated(source_text: str, translation_text: str) -> bool:
    if not translation_text.strip():
        return True
    source_len = len(source_text)
    if source_len == 0:
        return False
    return (len(translation_text) / source_len) < TRUNCATION_FLOOR_RATIO


def repair_translation(
    provider: LLMProvider,
    *,
    source_text: str,
    previous_translation: str,
    violations: Sequence[str],
    source_language: str,
    target_language: str,
) -> TranslationResponse:
    """Issue ONE targeted repair re-ask and return the re-parsed response.

    Bounded single pass (ADR 018 D9). ``provider`` is passed in (ADR 019 §5 seam).
    Raises whatever ``complete()`` / :func:`parse_response` raise; the caller treats
    a failure as "keep the original attempt".
    """

    prompt = render_enforcement_repair_prompt(
        source_text=source_text,
        previous_translation=previous_translation,
        violations=violations,
        source_language=source_language,
        target_language=target_language,
    )
    completion = provider.complete(
        prompt,
        system=ENFORCEMENT_REPAIR_SYSTEM,
        max_output_tokens=REPAIR_MAX_OUTPUT_TOKENS,
    )
    return parse_response(
        completion.text,
        input_tokens=completion.input_tokens,
        output_tokens=completion.output_tokens,
    )
