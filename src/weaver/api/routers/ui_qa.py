"""QA report UI pages (Stage B4).

Presentation-only over :mod:`weaver.services.translation_qa` (Jinja2 + HTMX, ADR
007). No auto-fix, no mutation, no provider call — the read-only QA service is
reused as-is. Per the Gate B1 decision, QA runs **only** on these explicit pages;
the project tree never triggers a novel-wide QA scan. Severity/badge wording stays
``info | warning | critical`` / ``clean | warnings | errors`` (ADR 008).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from weaver.api.templating import templates
from weaver.errors import ChapterNotFoundError, VolumeNotFoundError, WeaverError
from weaver.qa.report import QAReport
from weaver.services.project_discovery import find_project
from weaver.services.translation_qa import analyze_chapter, analyze_novel, analyze_volume

router = APIRouter(tags=["ui"], include_in_schema=False)

_BADGE_CLASS = {"clean": "ok", "warnings": "warn", "errors": "bad"}
_BADGE_LABEL = {"clean": "Clean", "warnings": "Warnings", "errors": "Errors"}
_CATEGORIES = ("completeness", "staleness", "consistency", "quality", "export_readiness")
_SEVERITIES = ("info", "warning", "critical")


def _base_dir(request: Request) -> Path:
    return request.app.state.base_dir  # type: ignore[no-any-return]


@router.get("/ui/projects/{name}/qa", response_class=HTMLResponse)
def novel_qa_page(
    name: str,
    request: Request,
    severity: str = Query(""),
    category: str = Query(""),
) -> HTMLResponse:
    """QA report for the whole novel (per-volume and per-chapter roll-ups)."""
    base = _base_dir(request)
    dp = find_project(base, name)
    if dp is None:
        return _not_found(request, f"No project named {name!r} under {base}.")
    if dp.error:
        return _error(request, dp.error)
    try:
        report = analyze_novel(dp.project_toml, cwd=base)
    except WeaverError as exc:
        return _error(request, str(exc))
    return _render(request, name, report, severity, category, "Novel", f"/ui/projects/{name}/qa")


@router.get("/ui/projects/{name}/volumes/{volume_id}/qa", response_class=HTMLResponse)
def volume_qa_page(
    name: str,
    volume_id: int,
    request: Request,
    severity: str = Query(""),
    category: str = Query(""),
) -> HTMLResponse:
    """QA report for one volume (per-chapter roll-up)."""
    base = _base_dir(request)
    dp = find_project(base, name)
    if dp is None:
        return _not_found(request, f"No project named {name!r} under {base}.")
    if dp.error:
        return _error(request, dp.error)
    try:
        report = analyze_volume(dp.project_toml, volume_id, cwd=base)
    except VolumeNotFoundError as exc:
        return _not_found(request, str(exc))
    except WeaverError as exc:
        return _error(request, str(exc))
    return _render(
        request,
        name,
        report,
        severity,
        category,
        f"Volume {volume_id}",
        f"/ui/projects/{name}/volumes/{volume_id}/qa",
    )


@router.get("/ui/projects/{name}/chapters/{chapter_id}/qa", response_class=HTMLResponse)
def chapter_qa_page(
    name: str,
    chapter_id: str,
    request: Request,
    severity: str = Query(""),
    category: str = Query(""),
) -> HTMLResponse:
    """QA report for one chapter (links back to its workspace)."""
    base = _base_dir(request)
    dp = find_project(base, name)
    if dp is None:
        return _not_found(request, f"No project named {name!r} under {base}.")
    if dp.error:
        return _error(request, dp.error)
    try:
        report = analyze_chapter(dp.project_toml, chapter_id, cwd=base)
    except ChapterNotFoundError as exc:
        return _not_found(request, str(exc))
    except WeaverError as exc:
        return _error(request, str(exc))
    return _render(
        request,
        name,
        report,
        severity,
        category,
        "Chapter",
        f"/ui/projects/{name}/chapters/{chapter_id}/qa",
    )


def _render(
    request: Request,
    name: str,
    report: QAReport,
    severity: str,
    category: str,
    scope_label: str,
    qa_url: str,
) -> HTMLResponse:
    issues = report.issues
    if severity in _SEVERITIES:
        issues = tuple(issue for issue in issues if issue.severity == severity)
    if category in _CATEGORIES:
        issues = tuple(issue for issue in issues if issue.category == category)
    return templates.TemplateResponse(
        request,
        "qa.html",
        {
            "name": name,
            "report": report,
            "issues": issues,
            "severity": severity,
            "category": category,
            "scope_label": scope_label,
            "qa_url": qa_url,
            "badge_class": _BADGE_CLASS[report.badge],
            "badge_label": _BADGE_LABEL[report.badge],
            "categories": _CATEGORIES,
            "severities": _SEVERITIES,
        },
    )


def _not_found(request: Request, message: str) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "not_found.html", {"message": message}, status_code=404
    )


def _error(request: Request, message: str) -> HTMLResponse:
    return templates.TemplateResponse(request, "error.html", {"message": message}, status_code=422)
