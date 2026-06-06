"""Server-rendered browser UI for the FastAPI cockpit (Sprint 11A, ADR ``007``).

Jinja2 + HTMX, no build, no SPA. **Presentation only**: every route is a thin
adapter that calls the same shared services the JSON routers use
(``services/project_discovery``, ``services/project_tree``, ``core/global_config``)
and renders a template. No business logic, no storage access here (CLAUDE.md §4.2).

All HTML lives under ``/ui`` so the JSON API surface stays cleanly separable
(``/`` redirects to ``/ui``). This UI is the default ``weaver serve`` cockpit and
ships on ``weaver serve-api`` alongside the JSON API (Flask removed in Sprint 13B).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from weaver.api.jobs import JobRegistry
from weaver.api.routers.export import _start_export
from weaver.api.routers.translate import _start_job as _start_translate_job
from weaver.api.schemas import ExportRequest
from weaver.api.templating import templates
from weaver.core.global_config import load_global_config, resolve_config_value
from weaver.errors import ChapterNotFoundError, SegmentNotFoundError, WeaverError
from weaver.providers.registry import known_provider_types
from weaver.services.chapter_workspace import chapter_workspace
from weaver.services.import_source import import_volume
from weaver.services.project import initialize_project, project_exists
from weaver.services.project_discovery import discover_projects, find_project
from weaver.services.project_tree import project_tree
from weaver.services.segment_history import segment_translation_history
from weaver.services.source_browser import list_directory
from weaver.services.source_intake import resolve_intake_source
from weaver.services.workspace_edit import save_segment_translation

router = APIRouter(tags=["ui"], include_in_schema=False)


def _base_dir(request: Request) -> Path:
    return request.app.state.base_dir  # type: ignore[no-any-return]


def _jobs(request: Request) -> JobRegistry:
    return request.app.state.jobs  # type: ignore[no-any-return]


def _project_rows(base_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for dp in discover_projects(base_dir):
        s = dp.summary
        rows.append(
            {
                "name": dp.name,
                "provider": s.provider if s else "",
                "model": s.model if s else "",
                "volume_count": s.volume_count if s else 0,
                "chapter_count": s.chapter_count if s else 0,
                "segment_count": s.segment_count if s else 0,
                "translated_count": s.translated_count if s else 0,
                "pending_count": s.pending_count if s else 0,
                "error": dp.error,
            }
        )
    return rows


@router.get("/ui", response_class=HTMLResponse)
def dashboard(request: Request) -> HTMLResponse:
    """Home: list discovered projects + the resolved global provider defaults."""
    base = _base_dir(request)
    global_config = load_global_config()
    default_provider = resolve_config_value(
        "default_provider",
        env_var="WEAVER_DEFAULT_PROVIDER",
        global_config=global_config,
        default="deepseek",
    )
    default_model = resolve_config_value(
        "default_model",
        env_var="WEAVER_DEFAULT_MODEL",
        global_config=global_config,
        default="—",
    )
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "projects": _project_rows(base),
            "books_dir": str(base),
            "default_provider": default_provider,
            "default_model": default_model,
        },
    )


@router.get("/ui/projects/{name}", response_class=HTMLResponse)
def project_view(name: str, request: Request) -> HTMLResponse:
    """Project view: the Novel → Volume → Chapter tree (read-only)."""
    base = _base_dir(request)
    dp = find_project(base, name)
    if dp is None:
        return templates.TemplateResponse(
            request,
            "not_found.html",
            {"message": f"No project named {name!r} under {base}."},
            status_code=404,
        )
    if dp.error:
        return templates.TemplateResponse(
            request, "error.html", {"message": dp.error}, status_code=422
        )
    try:
        tree = project_tree(dp.project_toml, cwd=base)
    except WeaverError as exc:
        return templates.TemplateResponse(
            request, "error.html", {"message": str(exc)}, status_code=422
        )
    return templates.TemplateResponse(request, "project.html", {"tree": tree})


# --- create / import (Stage 11B-1) ------------------------------------------


@router.get("/ui/browse", response_class=HTMLResponse)
def browse_fragment(request: Request, rel_dir: str = Query("", alias="dir")) -> HTMLResponse:
    """HTMX fragment: a sandboxed directory listing for the source picker."""
    base = _base_dir(request)
    try:
        listing = list_directory(base, rel_dir)
    except WeaverError as exc:
        return templates.TemplateResponse(request, "partials/_browse.html", {"error": str(exc)})
    return templates.TemplateResponse(request, "partials/_browse.html", {"listing": listing})


@router.get("/ui/new", response_class=HTMLResponse)
def new_project_page(request: Request) -> HTMLResponse:
    """New-project page: create form + sandboxed source browser."""
    return templates.TemplateResponse(
        request, "new.html", {"provider_types": known_provider_types()}
    )


@router.post("/ui/new", response_model=None)
async def create_project_submit(
    request: Request,
    file: UploadFile | None = File(None),
    source_path: str | None = Form(None),
    provider: str | None = Form(None),
    template: str | None = Form(None),
) -> HTMLResponse | RedirectResponse:
    """Create a novel from an uploaded/browsed source, then go to its view.

    Reuses the same services as ``POST /projects/create`` (no logic here). On
    failure the form is re-rendered with the error; on success → 303 to the
    project view.
    """
    base = _base_dir(request)
    uploaded = (file.filename, await file.read()) if file is not None and file.filename else None
    try:
        source = resolve_intake_source(base, uploaded=uploaded, source_path=source_path)
        if project_exists(source, cwd=base):
            raise WeaverError(f"A project named {source.stem!r} already exists.")
        result = initialize_project(
            source, cwd=base, template=template or None, provider=provider or None
        )
    except WeaverError as exc:
        return templates.TemplateResponse(
            request,
            "new.html",
            {"error": str(exc), "provider_types": known_provider_types()},
            status_code=400,
        )
    return RedirectResponse(url=f"/ui/projects/{result.project_name}", status_code=303)


@router.post("/ui/projects/{name}/import", response_class=HTMLResponse)
async def import_volume_submit(
    name: str,
    request: Request,
    file: UploadFile | None = File(None),
    source_path: str | None = Form(None),
) -> HTMLResponse:
    """Import a volume into an existing project; return the refreshed tree.

    On success the ``#tree`` fragment is swapped (HTMX). On failure an error
    fragment is returned and retargeted to ``#import_error`` so the tree stays.
    """
    base = _base_dir(request)
    dp = find_project(base, name)
    if dp is None:
        return _import_error(request, f"No project named {name!r}.")
    if dp.error:
        return _import_error(request, dp.error)

    uploaded = (file.filename, await file.read()) if file is not None and file.filename else None
    try:
        source = resolve_intake_source(base, uploaded=uploaded, source_path=source_path)
        import_volume(dp.project_toml, source, cwd=base)
        tree = project_tree(dp.project_toml, cwd=base)
    except WeaverError as exc:
        return _import_error(request, str(exc))
    return templates.TemplateResponse(request, "partials/_tree.html", {"tree": tree})


def _import_error(request: Request, message: str) -> HTMLResponse:
    """Render the import-error fragment, retargeted so it never clobbers the tree."""
    response = templates.TemplateResponse(
        request, "partials/_import_error.html", {"message": message}
    )
    response.headers["HX-Retarget"] = "#import_error"
    response.headers["HX-Reswap"] = "outerHTML"
    return response


# --- workspace read / save / history (Stage 11B-2) --------------------------


def _resolve_project_toml(request: Request, name: str) -> Path:
    base = _base_dir(request)
    dp = find_project(base, name)
    if dp is None:
        raise ChapterNotFoundError(f"No project named {name!r} under {base}.")
    if dp.error:
        raise WeaverError(dp.error)
    return dp.project_toml


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
    return templates.TemplateResponse(request, "workspace.html", {"ws": ws})


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


def _job_error(request: Request, message: str, *, panel_id: str) -> HTMLResponse:
    """Render a job-panel error fragment (keeps the panel id so HTMX swaps it)."""
    return templates.TemplateResponse(
        request, "partials/_job_error.html", {"message": message, "panel_id": panel_id}
    )


def _render_translate_job(request: Request, name: str, job_id: str) -> HTMLResponse:
    job = _jobs(request).get(job_id)
    if job is None or job.project_name != name:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found for '{name}'.")
    response = templates.TemplateResponse(
        request, "partials/_job.html", {"job": job, "progress": job.snapshot(), "name": name}
    )
    # When the job finishes, tell the workspace grid to refresh itself once. The
    # signal rides on a response header (not an hx-trigger in the panel) so the
    # terminal panel itself stays quiet (no further polling).
    if job.status in {"done", "cancelled"}:
        response.headers["HX-Trigger"] = "refreshGrid"
    return response


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


# --- export trigger + job progress (Stage 11B-3) ----------------------------


def _render_export_job(request: Request, name: str, job_id: str) -> HTMLResponse:
    job = _jobs(request).get_export(job_id)
    if job is None or job.project_name != name:
        raise HTTPException(
            status_code=404, detail=f"Export job '{job_id}' not found for '{name}'."
        )
    return templates.TemplateResponse(
        request, "partials/_export_job.html", {"job": job, "progress": job.snapshot(), "name": name}
    )


@router.post("/ui/projects/{name}/export", response_class=HTMLResponse)
def ui_export(
    name: str, request: Request, target: str = Form("epub"), bundle: bool = Form(False)
) -> HTMLResponse:
    """Start a novel-scope export job for the chosen target (HTMX panel)."""
    try:
        started = _start_export(
            request,
            name,
            scope="novel",
            target_id=None,
            body=ExportRequest(target=target, bundle=bundle),
        )
    except HTTPException as exc:
        return _job_error(request, str(exc.detail), panel_id="export-panel")
    return _render_export_job(request, name, started.job_id)


@router.get("/ui/projects/{name}/export/jobs/{job_id}", response_class=HTMLResponse)
def ui_export_status(name: str, job_id: str, request: Request) -> HTMLResponse:
    """Poll an export job's status/progress (HTMX self-refresh until terminal)."""
    return _render_export_job(request, name, job_id)


@router.post("/ui/projects/{name}/export/jobs/{job_id}/cancel", response_class=HTMLResponse)
def ui_export_cancel(name: str, job_id: str, request: Request) -> HTMLResponse:
    """Cooperatively cancel an export job, then render its current state."""
    job = _jobs(request).get_export(job_id)
    if job is None or job.project_name != name:
        raise HTTPException(
            status_code=404, detail=f"Export job '{job_id}' not found for '{name}'."
        )
    job.request_cancel()
    return _render_export_job(request, name, job_id)
