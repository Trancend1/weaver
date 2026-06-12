"""Canonical status label helpers for Jinja2 UI templates (Sprint P6, WV-006).

Maps raw DB enum values to human-facing labels that agree across all UI surfaces.
DB values are intentionally **unchanged** (no migration); these are presentation-only.

Usage in templates:
  {% from "api/status_labels.py" import translation_status_label, job_status_label %}
  <span class="badge">{{ translation_status_label(seg.status) }}</span>
"""

from __future__ import annotations

# Translation status (per segment) — mirrors SOURCEOFARCHITECTURE §5.1
TRANSLATION_LABELS: dict[str, str] = {
    "pending": "Untranslated",
    "in_progress": "Translating",
    "translated": "Translated",
    "manual": "Manual",
    "failed": "Failed",
    "stale": "Stale",
    "skipped": "Skipped",
}

# Review status (per segment, human axis) — mirrors WV-003 / SOURCEOFARCHITECTURE §5.2
REVIEW_LABELS: dict[str, str] = {
    "not_reviewed": "Not reviewed",
    "needs_review": "Needs review",
    "needs_revision": "Needs revision",
    "approved": "Reviewed",
    "rejected": "Rejected",
}

# Job status (per job) — mirrors SOURCEOFARCHITECTURE §5.5
JOB_LABELS: dict[str, str] = {
    "queued": "Waiting",
    "running": "Processing",
    "stale_running": "Stale",
    "cancelled": "Cancelled",
    "done": "Completed",
    "failed": "Failed",
}


def translation_status_label(status: str) -> str:
    """Return the canonical user-facing label for a segment translation status."""
    return TRANSLATION_LABELS.get(status, status)


_JOB_ORDER = {"queued": 0, "running": 1, "cancelled": 2, "done": 3, "failed": 4}


def job_status_label(status: str) -> str:
    """Return the canonical user-facing label for a job status."""
    return JOB_LABELS.get(status, status)


def review_status_label(status: str) -> str:
    """Return the canonical user-facing label for a segment review status."""
    return REVIEW_LABELS.get(status, status)


def badge_class_for_review(status: str) -> str:
    """Return a CSS badge modifier class for a review status."""
    if status == "approved":
        return "ok"
    if status in ("needs_revision", "rejected"):
        return "bad"
    if status == "needs_review":
        return "warn"
    return ""


def badge_class_for_translation(status: str) -> str:
    """Return a CSS badge modifier class for a translation status."""
    if status in ("translated", "manual"):
        return "ok"
    if status in ("failed", "stale"):
        return "bad"
    if status == "in_progress":
        return "warn"
    return ""


def badge_class_for_job(status: str) -> str:
    """Return a CSS badge modifier class for a job status."""
    if status in ("done",):
        return "ok"
    if status in ("failed", "stale_running"):
        return "bad"
    if status == "running":
        return "info"
    if status == "queued":
        return "warn"
    return ""
