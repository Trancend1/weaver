"""Deterministic per-segment consistency checks (character names, status).

Extends the per-segment QA primitives in :mod:`weaver.qa.checks` with two rules
that the legacy ``weaver validate`` set does not cover. Pure and read-only: each
function inspects a single :class:`~weaver.qa.checks.SegmentInput` and returns
findings; no database, provider, or web access.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from weaver.qa.checks import QAWarning, SegmentInput

# Statuses that mean "not yet published" but are not already covered by the
# existing failed/stale checks. ``translated``/``manual`` are published.
UNTRANSLATED_STATUSES = frozenset({"pending", "in_progress", "skipped"})


@dataclass(frozen=True)
class CharacterName:
    """Minimal character record consumed by the name-consistency check.

    Decoupled from the storage layer on purpose: the QA service adapts stored
    ``CharacterRecord`` rows into this value type.
    """

    jp_name: str
    en_name: str


def check_untranslated_segment(seg: SegmentInput) -> QAWarning | None:
    """Flag segments that are not yet translated (and not already failed/stale)."""

    if seg.status not in UNTRANSLATED_STATUSES:
        return None
    return QAWarning(
        segment_id=seg.segment_id,
        check_name="untranslated_segment",
        severity="warning",
        message=f"Segment is not yet translated (status: {seg.status}).",
    )


def check_character_name_missing(
    seg: SegmentInput, characters: Sequence[CharacterName]
) -> list[QAWarning]:
    """Flag each character whose JP name is in the source but whose EN name is
    absent from the translation.

    Mirrors :func:`weaver.qa.checks.check_glossary_mismatch` for the character
    database. Skips segments with no translation text (emptiness is covered by
    :func:`weaver.qa.checks.check_empty_translation`).
    """

    if seg.translation_text is None or not seg.translation_text.strip():
        return []
    findings: list[QAWarning] = []
    for character in characters:
        if not character.jp_name or not character.en_name:
            continue
        if character.jp_name not in seg.source_text:
            continue
        if character.en_name in seg.translation_text:
            continue
        findings.append(
            QAWarning(
                segment_id=seg.segment_id,
                check_name="character_name_missing",
                severity="warning",
                message=(
                    f"Character {character.jp_name!r} -> {character.en_name!r} appears in "
                    "source but the English name is absent from the translation."
                ),
            )
        )
    return findings
