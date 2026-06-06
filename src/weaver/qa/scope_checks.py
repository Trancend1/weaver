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
from weaver.qa.thresholds import (
    DEFAULT_FALLBACK_HEAVY_MIN_SEGMENTS,
    DEFAULT_FALLBACK_HEAVY_RATIO,
    DEFAULT_REPEATED_MIN_CHARS,
)

# Default thresholds (reproduce Phase B behavior). Per-project overrides arrive
# via the `[qa]` table (Phase D); see :mod:`weaver.qa.thresholds`. These aliases
# are the function-parameter defaults and stay importable for existing callers.
FALLBACK_HEAVY_RATIO = DEFAULT_FALLBACK_HEAVY_RATIO
FALLBACK_HEAVY_MIN_SEGMENTS = DEFAULT_FALLBACK_HEAVY_MIN_SEGMENTS
REPEATED_MIN_CHARS = DEFAULT_REPEATED_MIN_CHARS


@dataclass(frozen=True)
class ScopeWarning:
    """A chapter-scoped finding with no owning segment."""

    check_name: str
    severity: Severity
    message: str


def check_repeated_identical_translation(
    segments: Sequence[SegmentInput], *, min_chars: int = REPEATED_MIN_CHARS
) -> list[QAWarning]:
    """Flag segments that share an identical published translation while their
    sources differ.

    Short interjections (e.g. "Yes.") legitimately repeat, so translations
    shorter than ``min_chars`` are ignored. A group is flagged only when it
    contains at least two *distinct* source texts.
    """

    groups: dict[str, list[SegmentInput]] = {}
    for seg in segments:
        if seg.status not in PUBLISHED_STATUSES:
            continue
        text = seg.translation_text
        if text is None:
            continue
        stripped = text.strip()
        if len(stripped) < min_chars:
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


def check_fallback_heavy(
    *,
    total_segments: int,
    fallback_segments: int,
    heavy_ratio: float = FALLBACK_HEAVY_RATIO,
    min_segments: int = FALLBACK_HEAVY_MIN_SEGMENTS,
) -> ScopeWarning | None:
    """Flag a chapter where most segments would export as source fallback.

    ``fallback_segments`` is the count of segments with no publishable
    translation (export's own rule, via ``list_export_segment_states``).
    ``heavy_ratio`` / ``min_segments`` default to the Phase B constants and are
    overridden per project via the ``[qa]`` config.
    """

    if total_segments < min_segments:
        return None
    ratio = fallback_segments / total_segments
    if ratio < heavy_ratio:
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
