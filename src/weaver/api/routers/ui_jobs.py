"""UI router: jobs (Sprint Q2a split).

Split from the monolithic `ui.py` router.  Zero behaviour change.
"""

from __future__ import annotations

from contextlib import closing
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from weaver.api.routers.ui import _base_dir, _jobs
from weaver.api.templating import templates
from weaver.api.ui_context import project_layout
from weaver.errors import (
    WeaverError,
)
from weaver.services.job_store import (
    db_path_for as _resolve_jobs_db_path,
)
from weaver.services.job_store import (
    get_job,
    list_events_after,
    list_jobs_for_project,
)
from weaver.services.project_discovery import find_project
from weaver.storage.db import connect_database

router = APIRouter(tags=["ui"], include_in_schema=False)


# --- jobs (Sprint I6 — unified Job Detail UI) ------------------------------


@router.get("/ui/projects/{name}/jobs", response_class=HTMLResponse)
def project_jobs_page(name: str, request: Request) -> HTMLResponse:
    """List every persisted job for one project, newest first."""
    base = _base_dir(request)
    dp = find_project(base, name)
    if dp is None:
        return templates.TemplateResponse(
            request,
            "not_found.html",
            {"message": f"No project named {name!r} under {base}."},
            status_code=404,
        )
    db_path = _resolve_jobs_db_path(base, name)
    rows = []
    error: str | None = None
    if db_path is None:
        error = "Project database is not resolvable."
    else:
        try:
            with closing(connect_database(db_path)) as conn:
                rows = list_jobs_for_project(conn)
        except WeaverError as exc:
            error = str(exc)
    return templates.TemplateResponse(
        request,
        "jobs_list.html",
        {
            **project_layout(request, name, active_nav="jobs"),
            "jobs": rows,
            "error": error,
        },
    )


@router.get("/ui/projects/{name}/jobs/{job_id}/detail", response_class=HTMLResponse)
def job_detail_page(name: str, job_id: str, request: Request) -> HTMLResponse:
    """Render one job's status, progress, result/error, and event log."""
    base = _base_dir(request)
    dp = find_project(base, name)
    if dp is None:
        return templates.TemplateResponse(
            request,
            "not_found.html",
            {"message": f"No project named {name!r} under {base}."},
            status_code=404,
        )
    db_path = _resolve_jobs_db_path(base, name)
    if db_path is None:
        return templates.TemplateResponse(
            request,
            "error.html",
            {"message": "Project database is not resolvable."},
            status_code=422,
        )

    with closing(connect_database(db_path)) as conn:
        row = get_job(conn, job_id=job_id)
        if row is None or row.project_name != name:
            return templates.TemplateResponse(
                request,
                "not_found.html",
                {"message": f"Job '{job_id}' not found for project '{name}'."},
                status_code=404,
            )
        events = list_events_after(conn, job_id=job_id, after_id=0)

    result_payload: dict[str, Any] | None = None
    if row.result_json:
        import json as _json

        try:
            parsed = _json.loads(row.result_json)
        except _json.JSONDecodeError:
            parsed = None
        result_payload = parsed if isinstance(parsed, dict) else None

    return templates.TemplateResponse(
        request,
        "job_detail.html",
        {
            **project_layout(request, name, active_nav="jobs"),
            "job": row,
            "events": events,
            "result": result_payload,
        },
    )


@router.post("/ui/projects/{name}/jobs/{job_id}/detail/cancel", response_class=HTMLResponse)
def job_detail_cancel(name: str, job_id: str, request: Request) -> HTMLResponse:
    """Cancel any kind of running job and re-render the detail page.

    Distinct from the existing translate-cancel route at
    ``/ui/projects/{name}/jobs/{job_id}/cancel``, which is specific to the
    workspace job-panel partial — this one belongs to the unified Job Detail
    UI (Sprint I6) and renders the full ``job_detail.html`` page back.
    """
    jobs = _jobs(request)
    job = jobs.get(job_id) or jobs.get_batch(job_id) or jobs.get_export(job_id)
    if job is not None and job.project_name == name:
        job.request_cancel()
    return job_detail_page(name, job_id, request)
