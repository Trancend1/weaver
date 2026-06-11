"""QA report value types (framework-agnostic, ADR 008).

Severity reuses :data:`weaver.qa.checks.Severity` (``info | warning | critical``);
Phase B does **not** introduce an ``error`` value in the data layer — the UI may
label ``critical`` as "Error" for presentation only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from weaver.qa.checks import Severity

QASeverity = Severity
QACategory = Literal[
    "completeness", "staleness", "consistency", "quality", "export_readiness", "structure"
]
QASource = Literal["translation", "structure"]
QAScope = Literal["chapter", "volume", "novel"]
QABadge = Literal["clean", "warnings", "errors"]

QA_REPORT_SCHEMA_VERSION = 2

# Every rule's category. Keyed by ``check_name`` from the check functions.
RULE_CATEGORY: dict[str, QACategory] = {
    "failed_segment": "completeness",
    "empty_translation": "completeness",
    "untranslated_segment": "completeness",
    "stale_segment": "staleness",
    "glossary_mismatch": "consistency",
    "character_name_missing": "consistency",
    "untranslated_japanese": "quality",
    "length_ratio": "quality",
    "max_length_ratio": "quality",
    "punctuation_mismatch": "quality",
    "broken_line_breaks": "quality",
    "repeated_identical_translation": "quality",
    "fallback_heavy_chapter": "export_readiness",
    "mixed_status_chapter": "export_readiness",
}


@dataclass(frozen=True)
class QAIssue:
    """One QA finding, normalized across per-segment and scope-level rules.

    ``source`` distinguishes translation-content findings (``translation``) from
    EPUB structural findings joined from the preservation snapshot (``structure``,
    WV-007). Defaults to ``translation`` so existing call sites are unchanged.
    """

    rule: str
    category: QACategory
    severity: QASeverity
    message: str
    segment_id: str | None
    chapter_id: str | None
    source: QASource = "translation"


@dataclass(frozen=True)
class QAScopeSummary:
    """Per-chapter or per-volume roll-up inside a wider report."""

    scope: Literal["chapter", "volume"]
    id: str
    title: str | None
    total_issues: int
    info_count: int
    warning_count: int
    critical_count: int
    badge: QABadge


@dataclass(frozen=True)
class QAReport:
    """A QA report for a chapter, volume, or whole novel."""

    schema_version: int
    project: str
    scope: QAScope
    scope_id: str
    total_segments: int
    total_issues: int
    info_count: int
    warning_count: int
    critical_count: int
    badge: QABadge
    issues: tuple[QAIssue, ...]
    summary_by_category: dict[QACategory, int]
    summary_by_chapter: tuple[QAScopeSummary, ...]
    summary_by_volume: tuple[QAScopeSummary, ...]


def category_for(rule: str) -> QACategory:
    """Return the category for a rule's ``check_name`` (defaults to ``quality``)."""

    return RULE_CATEGORY.get(rule, "quality")


def badge_for(*, warning_count: int, critical_count: int) -> QABadge:
    """Map severity counts to a badge state (info alone does not raise a badge)."""

    if critical_count > 0:
        return "errors"
    if warning_count > 0:
        return "warnings"
    return "clean"
