"""Deterministic scope-level QA checks (chapter and cross-segment).

These rules look at a collection of segments (a chapter) rather than a single
segment. Pure and read-only. Repeated-translation findings are per-segment
(:class:`~weaver.qa.checks.QAWarning`); fallback-heavy and mixed-status are
chapter-scoped (:class:`ScopeWarning`, which carries no ``segment_id``).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from weaver.qa.checks import PUBLISHED_STATUSES, QAWarning, SegmentInput, Severity

# Thresholds are module-level constants (ADR 008): not `[qa]`-configurable in
# Phase B. A config surface can be added later if users need it.
FALLBACK_HEAVY_RATIO = 0.5
FALLBACK_HEAVY_MIN_SEGMENTS = 5
REPEATED_MIN_CHARS = 8


@dataclass(frozen=True)
class ScopeWarning:
    """A chapter-scoped finding with no owning segment."""

    check_name: str
    severity: Severity
    message: str


def check_repeated_identical_translation(segments: Sequence[SegmentInput]) -> list[QAWarning]:
    """Flag segments that share an identical published translation while their
    sources differ.

    Short interjections (e.g. "Yes.") legitimately repeat, so translations
    shorter than :data:`REPEATED_MIN_CHARS` are ignored. A group is flagged only
    when it contains at least two *distinct* source texts.
    """

    groups: dict[str, list[SegmentInput]] = {}
    for seg in segments:
        if seg.status not in PUBLISHED_STATUSES:
            continue
        text = seg.translation_text
        if text is None:
            continue
        stripped = text.strip()
        if len(stripped) < REPEATED_MIN_CHARS:
            continue
        groups.setdefault(stripped, []).append(seg)

    findings: list[QAWarning] = []
    for members in groups.values():
        if len(members) < 2:
            continue
        if len({member.source_text for member in members}) < 2:
            continue
        for member in members:
            findings.append(
                QAWarning(
                    segment_id=member.segment_id,
                    check_name="repeated_identical_translation",
                    severity="warning",
                    message=(
                        f"{len(members)} segments with differing source share an identical "
                        "translation."
                    ),
                )
            )
    return findings


def check_fallback_heavy(*, total_segments: int, fallback_segments: int) -> ScopeWarning | None:
    """Flag a chapter where most segments would export as source fallback.

    ``fallback_segments`` is the count of segments with no publishable
    translation (export's own rule, via ``list_export_segment_states``).
    """

    if total_segments < FALLBACK_HEAVY_MIN_SEGMENTS:
        return None
    ratio = fallback_segments / total_segments
    if ratio < FALLBACK_HEAVY_RATIO:
        return None
    return ScopeWarning(
        check_name="fallback_heavy_chapter",
        severity="warning",
        message=(
            f"{fallback_segments} of {total_segments} segments "
            f"({ratio:.0%}) have no publishable translation and would export as source."
        ),
    )


def check_mixed_status(segments: Sequence[SegmentInput]) -> ScopeWarning | None:
    """Flag a chapter that mixes published and unpublished segments (partial work)."""

    published = sum(1 for seg in segments if seg.status in PUBLISHED_STATUSES)
    unpublished = sum(1 for seg in segments if seg.status not in PUBLISHED_STATUSES)
    if published == 0 or unpublished == 0:
        return None
    return ScopeWarning(
        check_name="mixed_status_chapter",
        severity="info",
        message=(f"Chapter mixes {published} published and {unpublished} unpublished segments."),
    )
