"""Deterministic QA checks over (segment, translation, glossary)."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from weaver.providers.types import GlossaryTerm

Severity = Literal["info", "warning", "critical"]

JP_LEAK_PATTERN = re.compile(r"[぀-ゟ゠-ヿ㐀-䶿一-鿿]{4,}")

PUBLISHED_STATUSES = frozenset({"translated", "manual"})


@dataclass(frozen=True)
class SegmentInput:
    """Per-segment record consumed by QA checks.

    `translation_text` is the latest `translations.text` whose
    `source_hash` still matches `segments.source_hash`. None when no such
    translation exists.
    """

    segment_id: str
    source_text: str
    normalized_source_text: str
    status: str
    translation_text: str | None


@dataclass(frozen=True)
class QAWarning:
    """Single QA finding."""

    segment_id: str
    check_name: str
    severity: Severity
    message: str


def check_empty_translation(seg: SegmentInput) -> QAWarning | None:
    """Flag segments marked translated/manual whose translation text is empty."""

    if seg.status not in PUBLISHED_STATUSES:
        return None
    if seg.translation_text is not None and seg.translation_text.strip():
        return None
    return QAWarning(
        segment_id=seg.segment_id,
        check_name="empty_translation",
        severity="critical",
        message="Translation is empty for a translated/manual segment.",
    )


def check_untranslated_japanese(seg: SegmentInput) -> QAWarning | None:
    """Flag translations containing 4+ contiguous Japanese characters."""

    if seg.translation_text is None:
        return None
    match = JP_LEAK_PATTERN.search(seg.translation_text)
    if match is None:
        return None
    return QAWarning(
        segment_id=seg.segment_id,
        check_name="untranslated_japanese",
        severity="critical",
        message=(f"Translation contains >3 contiguous Japanese characters ({match.group(0)!r})."),
    )


def check_length_ratio(seg: SegmentInput, *, minimum_ratio: float) -> QAWarning | None:
    """Flag translations shorter than `minimum_ratio` of source length."""

    if seg.translation_text is None or not seg.translation_text.strip():
        return None
    source_len = len(seg.source_text)
    if source_len == 0:
        return None
    ratio = len(seg.translation_text) / source_len
    if ratio >= minimum_ratio:
        return None
    return QAWarning(
        segment_id=seg.segment_id,
        check_name="length_ratio",
        severity="warning",
        message=(f"Translation length ratio {ratio:.2f} is below minimum {minimum_ratio:.2f}."),
    )


def check_glossary_mismatch(seg: SegmentInput, terms: Sequence[GlossaryTerm]) -> list[QAWarning]:
    """Flag each approved glossary term whose source matches the segment but
    whose target is absent from the translation."""

    if seg.translation_text is None or not seg.translation_text.strip():
        return []
    findings: list[QAWarning] = []
    for term in terms:
        if not term.source or not term.target:
            continue
        source_haystack = (
            seg.normalized_source_text
            if term.case_sensitive
            else seg.normalized_source_text.casefold()
        )
        source_needle = term.source if term.case_sensitive else term.source.casefold()
        if source_needle not in source_haystack:
            continue
        translation_haystack = (
            seg.translation_text if term.case_sensitive else seg.translation_text.casefold()
        )
        target_needle = term.target if term.case_sensitive else term.target.casefold()
        if target_needle in translation_haystack:
            continue
        findings.append(
            QAWarning(
                segment_id=seg.segment_id,
                check_name="glossary_mismatch",
                severity="warning",
                message=(
                    f"Glossary term {term.source!r} -> {term.target!r} matched source "
                    "but target is absent from translation."
                ),
            )
        )
    return findings


def check_failed_segment(seg: SegmentInput) -> QAWarning | None:
    """Flag segments whose latest translation attempt failed."""

    if seg.status != "failed":
        return None
    return QAWarning(
        segment_id=seg.segment_id,
        check_name="failed_segment",
        severity="critical",
        message="Segment is marked failed.",
    )


def check_stale_segment(seg: SegmentInput) -> QAWarning | None:
    """Flag segments whose source changed after the last translation."""

    if seg.status != "stale":
        return None
    return QAWarning(
        segment_id=seg.segment_id,
        check_name="stale_segment",
        severity="warning",
        message="Source text changed since last translation; segment is stale.",
    )


def run_all_checks(
    seg: SegmentInput,
    glossary_terms: Sequence[GlossaryTerm],
    *,
    detect_empty: bool = True,
    detect_japanese: bool = True,
    detect_glossary_mismatch: bool = True,
    minimum_length_ratio: float = 0.3,
) -> list[QAWarning]:
    """Run every enabled check and aggregate findings for one segment.

    `failed` and `stale` status checks are always on. The other four checks
    follow the `[qa]` config flags.
    """

    findings: list[QAWarning] = []

    if detect_empty:
        empty = check_empty_translation(seg)
        if empty is not None:
            findings.append(empty)
        length = check_length_ratio(seg, minimum_ratio=minimum_length_ratio)
        if length is not None:
            findings.append(length)

    if detect_japanese:
        japanese = check_untranslated_japanese(seg)
        if japanese is not None:
            findings.append(japanese)

    if detect_glossary_mismatch:
        findings.extend(check_glossary_mismatch(seg, glossary_terms))

    failed = check_failed_segment(seg)
    if failed is not None:
        findings.append(failed)

    stale = check_stale_segment(seg)
    if stale is not None:
        findings.append(stale)

    return findings
