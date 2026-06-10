"""UI router: workspace (Sprint Q2a split).

Split from the monolithic `ui.py` router.  Zero behaviour change.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse

from weaver.api.routers.translate import _start_job as _start_translate_job
from weaver.api.routers.ui import (
    _base_dir,
    _job_error,
    _jobs,
    _render_translate_job,
    _resolve_project_toml,
)
from weaver.api.templating import templates
from weaver.api.ui_context import workspace_layout
from weaver.errors import (
    ChapterNotFoundError,
    SegmentNotFoundError,
    WeaverError,
)
from weaver.services.chapter_workspace import chapter_workspace
from weaver.services.segment_history import segment_translation_history
from weaver.services.workspace_edit import save_segment_translation

router = APIRouter(tags=["ui"], include_in_schema=False)


# --- workspace read / save / history (Stage 11B-2) --------------------------


@router.get("/ui/projects/{name}/chapters/{chapter_id}", response_class=HTMLResponse)
def workspace_view(name: str, chapter_id: str, request: Request) -> HTMLResponse:
    """Two-column JP/EN workspace for one chapter (read-only render of segments)."""
    base = _base_dir(request)
    try:
        project_toml = _resolve_project_toml(request, name)
        ws = chapter_workspace(project_toml, chapter_id, cwd=base)
    except (ChapterNotFoundError, SegmentNotFoundError) as exc:
        return templates.TemplateResponse(
            request, "not_found.html", {"message": str(exc)}, status_code=404
        )
    except WeaverError as exc:
        return templates.TemplateResponse(
            request, "error.html", {"message": str(exc)}, status_code=422
        )
    running_job = _jobs(request).find_running(project_name=name, chapter_id=chapter_id)
    ctx: dict[str, Any] = {
        **workspace_layout(request, name, active_chapter_id=chapter_id),
        "ws": ws,
    }
    if running_job is not None:
        ctx["running_job"] = running_job
        ctx["running_job_progress"] = running_job.snapshot()
    return templates.TemplateResponse(request, "workspace.html", ctx)


def _render_segment(
    request: Request,
    name: str,
    chapter_id: str,
    segment_id: str,
    *,
    saved: bool = False,
    error: str | None = None,
) -> HTMLResponse:
    """Render one segment row from its latest stored state (used after save)."""
    base = _base_dir(request)
    project_toml = _resolve_project_toml(request, name)
    ws = chapter_workspace(project_toml, chapter_id, cwd=base)
    seg = next((s for s in ws.segments if s.id == segment_id), None)
    if seg is None:
        raise SegmentNotFoundError(f"Segment {segment_id!r} not found in chapter {chapter_id!r}.")
    return templates.TemplateResponse(
        request,
        "partials/_segment.html",
        {"seg": seg, "name": name, "chapter_id": chapter_id, "saved": saved, "error": error},
    )


@router.post(
    "/ui/projects/{name}/chapters/{chapter_id}/segments/{segment_id}",
    response_class=HTMLResponse,
)
def workspace_save(
    name: str,
    chapter_id: str,
    segment_id: str,
    request: Request,
    translated_text: str = Form(...),
) -> HTMLResponse:
    """Save one segment's translation (status → manual); return the refreshed row."""
    base = _base_dir(request)
    try:
        project_toml = _resolve_project_toml(request, name)
        save_segment_translation(project_toml, chapter_id, segment_id, translated_text, cwd=base)
    except ValueError as exc:
        return _render_segment(request, name, chapter_id, segment_id, error=str(exc))
    except (ChapterNotFoundError, SegmentNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except WeaverError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _render_segment(request, name, chapter_id, segment_id, saved=True)


@router.get(
    "/ui/projects/{name}/chapters/{chapter_id}/segments/{segment_id}/history",
    response_class=HTMLResponse,
)
def workspace_history(
    name: str, chapter_id: str, segment_id: str, request: Request
) -> HTMLResponse:
    """Render one segment's full translation attempt history (HTMX fragment)."""
    base = _base_dir(request)
    try:
        project_toml = _resolve_project_toml(request, name)
        history = segment_translation_history(project_toml, chapter_id, segment_id, cwd=base)
    except (ChapterNotFoundError, SegmentNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except WeaverError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return templates.TemplateResponse(request, "partials/_history.html", {"history": history})


# --- translate / retranslate + job progress (Stage 11B-3) -------------------


@router.post("/ui/projects/{name}/chapters/{chapter_id}/translate", response_class=HTMLResponse)
def ui_translate(name: str, chapter_id: str, request: Request) -> HTMLResponse:
    """Start a translate job for a chapter's untranslated segments (HTMX panel)."""
    try:
        started = _start_translate_job(
            request,
            name,
            chapter_id,
            segment_ids=None,
            mode="skip_existing",
            provider=None,
            model=None,
        )
    except HTTPException as exc:
        return _job_error(request, str(exc.detail), panel_id="job-panel")
    return _render_translate_job(request, name, started.job_id)


@router.post("/ui/projects/{name}/chapters/{chapter_id}/retranslate", response_class=HTMLResponse)
def ui_retranslate(
    name: str, chapter_id: str, request: Request, mode: str = Form("skip_existing")
) -> HTMLResponse:
    """Start a retranslate job under an explicit safe mode (HTMX panel)."""
    try:
        started = _start_translate_job(
            request, name, chapter_id, segment_ids=None, mode=mode, provider=None, model=None
        )
    except HTTPException as exc:
        return _job_error(request, str(exc.detail), panel_id="job-panel")
    return _render_translate_job(request, name, started.job_id)


@router.get("/ui/projects/{name}/chapters/{chapter_id}/running-job", response_class=HTMLResponse)
def ui_running_chapter_job(name: str, chapter_id: str, request: Request) -> HTMLResponse:
    """Render the active translate job for a chapter, if one is still running."""
    running_job = _jobs(request).find_running(project_name=name, chapter_id=chapter_id)
    if running_job is None:
        return HTMLResponse('<div id="job-panel"></div>')
    return _render_translate_job(request, name, running_job.id)


@router.get("/ui/projects/{name}/jobs/{job_id}", response_class=HTMLResponse)
def ui_job_status(name: str, job_id: str, request: Request) -> HTMLResponse:
    """Poll a translate job's status/progress (HTMX self-refresh until terminal)."""
    return _render_translate_job(request, name, job_id)


@router.post("/ui/projects/{name}/jobs/{job_id}/cancel", response_class=HTMLResponse)
def ui_job_cancel(name: str, job_id: str, request: Request) -> HTMLResponse:
    """Cooperatively cancel a translate job, then render its current state."""
    job = _jobs(request).get(job_id)
    if job is None or job.project_name != name:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found for '{name}'.")
    job.request_cancel()
    return _render_translate_job(request, name, job_id)
