"""Draft/Final export gate (Sprint Q7 / WV-009).

Advisory export stays the default (ADR 008): a **Draft** export is always
allowed. A **Final** export may opt in to "requires clean validation" — when it
does and unresolved ``critical`` QA issues exist, the gate refuses with an
explanation and a Draft escape hatch.

The gate reuses the existing novel QA report (``services/translation_qa``); it
does not duplicate the preflight logic. Evaluated only on the explicit export
action — never on a render path.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from weaver.services.translation_qa import analyze_novel

EXPORT_KINDS = frozenset({"draft", "final"})


@dataclass(frozen=True)
class ExportGateDecision:
    """Outcome of evaluating the Draft/Final export gate."""

    allowed: bool
    kind: str  # draft | final
    require_clean: bool
    qa_badge: str | None  # clean | warnings | errors (None when QA not run)
    critical_count: int
    reason: str | None


def evaluate_export_gate(
    project_toml: Path,
    *,
    kind: str,
    require_clean: bool,
    cwd: Path | None = None,
) -> ExportGateDecision:
    """Decide whether an export may proceed under the Draft/Final gate.

    Args:
        project_toml: Path to the project's ``project.toml``.
        kind: ``"draft"`` (always allowed) or ``"final"``.
        require_clean: When True and ``kind == "final"``, refuse while
            unresolved ``critical`` QA issues exist.
        cwd: Working directory used to resolve project-relative paths.

    Returns:
        An :class:`ExportGateDecision`. ``allowed`` is always True for Draft and
        for Final without ``require_clean``; the QA report is only computed when
        the gate could actually block (Final + ``require_clean``), so Draft stays
        cheap.
    """

    normalized = kind if kind in EXPORT_KINDS else "draft"

    if normalized != "final" or not require_clean:
        return ExportGateDecision(
            allowed=True,
            kind=normalized,
            require_clean=require_clean,
            qa_badge=None,
            critical_count=0,
            reason=None,
        )

    report = analyze_novel(project_toml, cwd=cwd)
    badge = report.badge  # clean | warnings | errors
    if report.critical_count > 0:
        reason = (
            f"Final export is blocked: {report.critical_count} unresolved critical "
            "quality issue(s). Resolve them on the Quality page, or export a Draft instead."
        )
        return ExportGateDecision(
            allowed=False,
            kind=normalized,
            require_clean=True,
            qa_badge=badge,
            critical_count=report.critical_count,
            reason=reason,
        )

    return ExportGateDecision(
        allowed=True,
        kind=normalized,
        require_clean=True,
        qa_badge=badge,
        critical_count=0,
        reason=None,
    )
