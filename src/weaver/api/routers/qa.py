"""Translation QA report endpoints (Stage B3).

Read-only JSON adapter over :mod:`weaver.services.translation_qa`. No QA logic
lives here: the router resolves the project, calls ``analyze_*``, and serializes
the resulting :class:`~weaver.qa.report.QAReport`. No mutation, no provider call.
Severity stays ``info | warning | critical`` (ADR 008) — no ``error`` at the API
boundary.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from weaver.api.schemas import QAIssueResponse, QAReportResponse, QAScopeSummaryResponse
from weaver.errors import ChapterNotFoundError, VolumeNotFoundError, WeaverError
from weaver.qa.report import QAReport, QAScopeSummary
from weaver.services.project_discovery import find_project
from weaver.services.translation_qa import analyze_chapter, analyze_novel, analyze_volume

router = APIRouter(prefix="/projects", tags=["qa"])


@router.get("/{name}/qa", response_model=QAReportResponse)
def get_novel_qa(name: str, request: Request) -> QAReportResponse:
    """Return the QA report for a whole novel (per-chapter and per-volume roll-ups).

    Rejects unknown project (404); a clean novel returns a report with zero issues.
    """
    project_toml, base = _resolve_project(request, name)
    try:
        report = analyze_novel(project_toml, cwd=base)
    except WeaverError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _to_response(report)


@router.get("/{name}/volumes/{volume_id}/qa", response_model=QAReportResponse)
def get_volume_qa(name: str, volume_id: int, request: Request) -> QAReportResponse:
    """Return the QA report for one volume (per-chapter roll-up).

    Rejects unknown project (404) and unknown volume (404).
    """
    project_toml, base = _resolve_project(request, name)
    try:
        report = analyze_volume(project_toml, volume_id, cwd=base)
    except VolumeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except WeaverError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _to_response(report)


@router.get("/{name}/chapters/{chapter_id}/qa", response_model=QAReportResponse)
def get_chapter_qa(name: str, chapter_id: str, request: Request) -> QAReportResponse:
    """Return the QA report for one chapter.

    Rejects unknown project (404) and unknown chapter (404).
    """
    project_toml, base = _resolve_project(request, name)
    try:
        report = analyze_chapter(project_toml, chapter_id, cwd=base)
    except ChapterNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except WeaverError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _to_response(report)


def _resolve_project(request: Request, name: str) -> tuple[Path, Path]:
    base: Path = request.app.state.base_dir
    discovered = find_project(base, name)
    if discovered is None:
        raise HTTPException(status_code=404, detail=f"Project '{name}' not found.")
    if discovered.error:
        raise HTTPException(status_code=422, detail=discovered.error)
    return discovered.project_toml, base


def _to_response(report: QAReport) -> QAReportResponse:
    return QAReportResponse(
        schema_version=report.schema_version,
        project=report.project,
        scope=report.scope,
        scope_id=report.scope_id,
        total_segments=report.total_segments,
        total_issues=report.total_issues,
        info_count=report.info_count,
        warning_count=report.warning_count,
        critical_count=report.critical_count,
        badge=report.badge,
        issues=[
            QAIssueResponse(
                rule=issue.rule,
                category=issue.category,
                severity=issue.severity,
                message=issue.message,
                segment_id=issue.segment_id,
                chapter_id=issue.chapter_id,
            )
            for issue in report.issues
        ],
        summary_by_category={str(key): value for key, value in report.summary_by_category.items()},
        summary_by_chapter=[_summary(summary) for summary in report.summary_by_chapter],
        summary_by_volume=[_summary(summary) for summary in report.summary_by_volume],
    )


def _summary(summary: QAScopeSummary) -> QAScopeSummaryResponse:
    return QAScopeSummaryResponse(
        scope=summary.scope,
        id=summary.id,
        title=summary.title,
        total_issues=summary.total_issues,
        info_count=summary.info_count,
        warning_count=summary.warning_count,
        critical_count=summary.critical_count,
        badge=summary.badge,
    )
