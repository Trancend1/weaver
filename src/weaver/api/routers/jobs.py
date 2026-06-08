"""Unified job list + detail endpoints (Sprint I, ADR 010).

Kind-agnostic: a single ``JobSummaryResponse`` covers translate / batch /
export / future parse / future ocr. Reads come from SQLite so a refresh after
process restart still sees the recovered state (Sprint I3).

The kind-specific status routes (``/projects/{name}/jobs/{job_id}`` etc.) and
SSE streams in ``translate.py`` / ``batch.py`` / ``export.py`` are unchanged —
this module is additive.
"""

from __future__ import annotations

import json
from contextlib import closing
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from weaver.api.schemas import (
    JobDetailResponse,
    JobEventResponse,
    JobListResponse,
    JobSummaryResponse,
)
from weaver.errors import WeaverError
from weaver.services.job_store import (
    JobRow,
    db_path_for,
    get_job,
    list_events_after,
    list_jobs_for_project,
)
from weaver.services.project_discovery import find_project
from weaver.storage.db import connect_database

router = APIRouter(prefix="/projects", tags=["jobs"])


def _base_dir(request: Request) -> Path:
    return request.app.state.base_dir  # type: ignore[no-any-return]


def _resolve_db(request: Request, name: str) -> Path:
    base = _base_dir(request)
    if find_project(base, name) is None:
        raise HTTPException(status_code=404, detail=f"Project '{name}' not found.")
    db_path = db_path_for(base, name)
    if db_path is None:
        raise HTTPException(status_code=422, detail=f"Project '{name}' has no resolvable database.")
    return db_path


def _to_summary(row: JobRow) -> JobSummaryResponse:
    return JobSummaryResponse(
        id=row.id,
        kind=row.kind,
        status=row.status,
        project_name=row.project_name,
        scope=row.scope,
        scope_id=row.scope_id,
        chapter_id=row.chapter_id,
        mode=row.mode,
        target=row.target,
        total_units=row.total_units,
        done_units=row.done_units,
        failed_units=row.failed_units,
        skipped_units=row.skipped_units,
        current_label=row.current_label,
        error_summary=row.error_summary,
        started_at=row.started_at,
        finished_at=row.finished_at,
    )


@router.get("/{name}/jobs", response_model=JobListResponse)
def list_project_jobs(name: str, request: Request) -> JobListResponse:
    """Return every persisted job for one project, newest first."""
    db_path = _resolve_db(request, name)
    try:
        with closing(connect_database(db_path)) as conn:
            rows = list_jobs_for_project(conn)
    except WeaverError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return JobListResponse(jobs=[_to_summary(row) for row in rows])


@router.get("/{name}/jobs/{job_id}/detail", response_model=JobDetailResponse)
def get_job_detail(name: str, job_id: str, request: Request) -> JobDetailResponse:
    """Return one job's persisted state plus its full event log.

    The kind-specific ``GET /projects/{name}/jobs/{job_id}`` endpoint
    (translate jobs only) is unchanged. This endpoint is the unified surface
    Sprint I6's Job Detail UI consumes.
    """
    db_path = _resolve_db(request, name)
    try:
        with closing(connect_database(db_path)) as conn:
            row = get_job(conn, job_id=job_id)
            if row is None or row.project_name != name:
                raise HTTPException(
                    status_code=404,
                    detail=f"Job '{job_id}' not found for project '{name}'.",
                )
            events = list_events_after(conn, job_id=job_id, after_id=0)
    except WeaverError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    result_payload: dict[str, Any] | None = None
    if row.result_json:
        try:
            parsed = json.loads(row.result_json)
        except json.JSONDecodeError:
            parsed = None
        result_payload = parsed if isinstance(parsed, dict) else None

    return JobDetailResponse(
        job=_to_summary(row),
        result=result_payload,
        events=[
            JobEventResponse(
                id=event.id,
                event=event.event,
                data=event.data,
                created_at=event.created_at,
            )
            for event in events
        ],
    )
