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

# Translations this many times longer than their (sufficiently long) source are
# flagged as runaway/duplicated output. JP→EN legitimately expands, so the
# default is generous; the floor avoids false positives on very short sources.
DEFAULT_MAX_LENGTH_RATIO = 8.0
MAX_RATIO_MIN_SOURCE_LEN = 10

# Trailing characters stripped before locating a segment's terminal punctuation
# (closing quotes/brackets in either script). Pure presentation wrappers.
_TERMINAL_TRAILERS = frozenset("\"'」』）)】〕》〉”’]｝}")


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


def check_max_length_ratio(
    seg: SegmentInput, *, maximum_ratio: float = DEFAULT_MAX_LENGTH_RATIO
) -> QAWarning | None:
    """Flag translations far longer than their source (runaway/duplicated output).

    Complements :func:`check_length_ratio` (too short). Only applies once the
    source is at least :data:`MAX_RATIO_MIN_SOURCE_LEN` characters so a one- or
    two-character source cannot trip the ratio.
    """

    if seg.translation_text is None or not seg.translation_text.strip():
        return None
    source_len = len(seg.source_text)
    if source_len < MAX_RATIO_MIN_SOURCE_LEN:
        return None
    ratio = len(seg.translation_text) / source_len
    if ratio <= maximum_ratio:
        return None
    return QAWarning(
        segment_id=seg.segment_id,
        check_name="max_length_ratio",
        severity="warning",
        message=(f"Translation length ratio {ratio:.1f} exceeds maximum {maximum_ratio:.1f}."),
    )


def _terminal_char(text: str) -> str | None:
    """Return the final meaningful character, ignoring trailing quotes/brackets."""

    stripped = text.rstrip()
    while stripped and stripped[-1] in _TERMINAL_TRAILERS:
        stripped = stripped[:-1].rstrip()
    return stripped[-1] if stripped else None


def check_punctuation_mismatch(seg: SegmentInput) -> QAWarning | None:
    """Flag a question/exclamation in the source dropped from the translation.

    Conservative: only the two highest-signal sentence-final marks are checked
    (``？``/``?`` and ``！``/``!``), and only when the source's terminal mark has
    no counterpart at the end of the translation. Lower-confidence finding (info).
    """

    if seg.translation_text is None or not seg.translation_text.strip():
        return None
    source_terminal = _terminal_char(seg.source_text)
    if source_terminal is None:
        return None
    translation_terminal = _terminal_char(seg.translation_text)
    expected = {"？": "?", "?": "?", "！": "!", "!": "!"}.get(source_terminal)
    if expected is None:
        return None
    if translation_terminal == expected:
        return None
    label = "question" if expected == "?" else "exclamation"
    return QAWarning(
        segment_id=seg.segment_id,
        check_name="punctuation_mismatch",
        severity="info",
        message=(f"Source ends as a {label} ({source_terminal!r}) but the translation does not."),
    )


def check_broken_line_breaks(seg: SegmentInput) -> QAWarning | None:
    """Flag a multi-line source collapsed to a single line in the translation."""

    if seg.translation_text is None or not seg.translation_text.strip():
        return None
    if "\n" not in seg.source_text:
        return None
    if "\n" in seg.translation_text:
        return None
    return QAWarning(
        segment_id=seg.segment_id,
        check_name="broken_line_breaks",
        severity="info",
        message="Source contains line breaks that the translation does not preserve.",
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
    maximum_length_ratio: float = DEFAULT_MAX_LENGTH_RATIO,
) -> list[QAWarning]:
    """Run every enabled check and aggregate findings for one segment.

    `failed` and `stale` status checks are always on, as are the deterministic
    fidelity checks (max-length ratio, punctuation, line breaks) — they only
    fire on segments that already have a translation. The remaining checks follow
    the `[qa]` config flags.
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

    for fidelity_check in (
        lambda s: check_max_length_ratio(s, maximum_ratio=maximum_length_ratio),
        check_punctuation_mismatch,
        check_broken_line_breaks,
    ):
        finding = fidelity_check(seg)
        if finding is not None:
            findings.append(finding)

    failed = check_failed_segment(seg)
    if failed is not None:
        findings.append(failed)

    stale = check_stale_segment(seg)
    if stale is not None:
        findings.append(stale)

    return findings
