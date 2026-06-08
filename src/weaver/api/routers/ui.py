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

from contextlib import closing
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from weaver.api.jobs import JobRegistry
from weaver.api.routers.candidates import (
    apply_candidate_endpoint,
    approve_candidate_endpoint,
    reject_candidate_endpoint,
)
from weaver.api.routers.export import _start_export
from weaver.api.routers.translate import _start_job as _start_translate_job
from weaver.api.schemas import ExportRequest
from weaver.api.templating import templates
from weaver.api.ui_context import global_layout, project_layout, workspace_layout
from weaver.core.global_config import load_global_config, resolve_config_value
from weaver.errors import (
    ChapterNotFoundError,
    SegmentNotFoundError,
    VolumeNotFoundError,
    WeaverError,
)
from weaver.providers.registry import known_provider_types
from weaver.services.chapter_workspace import chapter_workspace
from weaver.services.epub_structure_preview import preview_epub_structure
from weaver.services.import_source import import_volume
from weaver.services.job_store import (
    db_path_for as _resolve_jobs_db_path,
)
from weaver.services.job_store import (
    get_job,
    list_events_after,
    list_jobs_for_project,
)
from weaver.services.project import delete_project, initialize_project, project_exists
from weaver.services.project_discovery import discover_projects, find_project
from weaver.services.project_paths import resolve_database_path
from weaver.services.project_tree import project_tree
from weaver.services.segment_history import segment_translation_history
from weaver.services.source_browser import list_directory, resolve_source
from weaver.services.source_intake import resolve_intake_source
from weaver.services.volume import delete_volume_from_project
from weaver.services.workspace_edit import save_segment_translation
from weaver.storage.db import connect_database

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
            **global_layout("dashboard"),
            "projects": _project_rows(base),
            "books_dir": str(base),
            "default_provider": default_provider,
            "default_model": default_model,
        },
    )


@router.get("/ui/epub-preview", response_class=HTMLResponse)
def epub_preview_page(request: Request, source_path: str = Query("")) -> HTMLResponse:
    """Read-only EPUB structure preview page for a sandboxed source path."""

    preview: dict[str, Any] | None = None
    error: str | None = None
    if source_path.strip():
        try:
            preview = preview_epub_structure(resolve_source(_base_dir(request), source_path))
        except WeaverError as exc:
            error = str(exc)
    return templates.TemplateResponse(
        request,
        "epub_preview.html",
        {
            **global_layout("epub-preview"),
            "source_path": source_path,
            "preview": preview,
            "error": error,
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
        tree = project_tree(dp.project_toml, cwd=base, jobs=_jobs(request))
    except WeaverError as exc:
        return templates.TemplateResponse(
            request, "error.html", {"message": str(exc)}, status_code=422
        )
    return templates.TemplateResponse(
        request,
        "project.html",
        {**project_layout(request, name, active_nav="project", sidebar_tree=tree), "tree": tree},
    )


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
            from contextlib import closing

            from weaver.storage.db import connect_database

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
    from contextlib import closing

    from weaver.storage.db import connect_database

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


@router.post("/ui/projects/{name}/delete")
def delete_project_submit(name: str, request: Request) -> Response:
    """Permanently delete a project, then send the browser back to the dashboard.

    HTMX-only: the button posts here and the ``HX-Redirect`` header navigates the
    browser to ``/ui`` on success. The original imported source file is untouched.
    """
    base = _base_dir(request)
    dp = find_project(base, name)
    if dp is None:
        raise HTTPException(status_code=404, detail=f"No project named {name!r}.")
    try:
        delete_project(dp.project_toml)
    except WeaverError as exc:
        return HTMLResponse(
            f'<div class="error error-state" role="alert">{exc}</div>',
            status_code=422,
            headers={"HX-Reswap": "innerHTML", "HX-Retarget": "#qa-badge-status"},
        )
    return Response(status_code=200, headers={"HX-Redirect": "/ui"})


@router.post("/ui/projects/{name}/volumes/{volume_id}/delete", response_class=HTMLResponse)
def delete_volume_submit(name: str, volume_id: int, request: Request) -> HTMLResponse:
    """Delete one volume and re-render the project tree (Sprint H3).

    HTMX target is ``#tree`` so the project page swaps the partial in place; on
    error we retarget to the import-error slot so the tree stays intact.
    """
    base = _base_dir(request)
    dp = find_project(base, name)
    if dp is None:
        raise HTTPException(status_code=404, detail=f"No project named {name!r}.")
    if dp.error:
        return _import_error(request, dp.error)
    try:
        delete_volume_from_project(dp.project_toml, volume_id, cwd=base)
        tree = project_tree(dp.project_toml, cwd=base, jobs=_jobs(request))
    except VolumeNotFoundError as exc:
        return _import_error(request, str(exc))
    except WeaverError as exc:
        return _import_error(request, str(exc))
    return templates.TemplateResponse(request, "partials/_tree.html", {"tree": tree})


# --- snapshot (Sprint J4 — EPUB preservation snapshot) ---------------------


@router.get("/ui/projects/{name}/volumes/{volume_id}/snapshot", response_class=HTMLResponse)
def ui_volume_snapshot_status(name: str, volume_id: int, request: Request) -> HTMLResponse:
    """Inspect snapshot freshness for one volume; HTMX swap-in replacement."""
    from weaver.errors import VolumeNotFoundError as _VNF
    from weaver.services.epub_reparse import status_for_volume

    base = _base_dir(request)
    dp = find_project(base, name)
    if dp is None:
        raise HTTPException(status_code=404, detail=f"No project named {name!r}.")
    if dp.error:
        return _import_error(request, dp.error)
    try:
        status = status_for_volume(dp.project_toml, volume_id, cwd=base)
    except _VNF as exc:
        return _import_error(request, str(exc))
    except WeaverError as exc:
        return _import_error(request, str(exc))
    return templates.TemplateResponse(
        request,
        "partials/_snapshot.html",
        {
            "project_name": name,
            "volume_id": volume_id,
            "status": status,
            "active_job_id": None,
        },
    )


@router.post("/ui/projects/{name}/volumes/{volume_id}/reparse", response_class=HTMLResponse)
def ui_volume_reparse(name: str, volume_id: int, request: Request) -> HTMLResponse:
    """Submit a Sprint I parse job and swap a "running" snapshot card in place."""
    from weaver.services.epub_reparse import reparse_volume

    base = _base_dir(request)
    dp = find_project(base, name)
    if dp is None:
        raise HTTPException(status_code=404, detail=f"No project named {name!r}.")
    if dp.error:
        return _import_error(request, dp.error)

    jobs = _jobs(request)
    project_toml = dp.project_toml

    def runner(should_cancel):  # noqa: ARG001 — single-unit parse
        from weaver.api.jobs import ParseResult
        from weaver.services.epub_snapshot import read_snapshot
        from weaver.services.project_paths import resolve_database_path

        status = reparse_volume(project_toml, volume_id, cwd=base)
        db_path = resolve_database_path(project_toml, cwd=base)
        parsed = read_snapshot(db_path, volume_id)
        return ParseResult(
            volume_id=volume_id,
            source_hash=status.source_hash or "",
            parser_version=status.parser_version or 0,
            manifest_count=len(parsed.manifest) if parsed else 0,
            spine_count=len(parsed.spine) if parsed else 0,
            nav_count=len(parsed.navigation) if parsed else 0,
            image_count=len(parsed.images) if parsed else 0,
            validation_count=len(parsed.validation_issues) if parsed else 0,
        )

    try:
        job = jobs.submit_parse(project_name=name, volume_id=volume_id, runner=runner)
    except WeaverError as exc:
        return _import_error(request, str(exc))
    from weaver.services.epub_snapshot import SnapshotStatus

    return templates.TemplateResponse(
        request,
        "partials/_snapshot.html",
        {
            "project_name": name,
            "volume_id": volume_id,
            "status": SnapshotStatus(
                volume_id=volume_id,
                state="reparsing",
                source_hash=None,
                parser_version=None,
                created_at=None,
                updated_at=None,
            ),
            "active_job_id": job.id,
        },
    )


@router.get("/ui/projects/{name}/volumes/{volume_id}/structure", response_class=HTMLResponse)
def ui_volume_structure(name: str, volume_id: int, request: Request) -> HTMLResponse:
    """Render the persisted snapshot for a volume as a Phase F preview page.

    Reuses the existing Phase F ``epub_preview.html`` shell so the structure
    surface is one page, not two. Falls back to "missing snapshot" when the
    volume has never been parsed.
    """
    from weaver.services.epub_reparse import status_for_volume
    from weaver.services.epub_snapshot import read_snapshot
    from weaver.services.epub_structure_preview import serialize_parsed_epub
    from weaver.services.project_paths import resolve_database_path

    base = _base_dir(request)
    dp = find_project(base, name)
    if dp is None:
        raise HTTPException(status_code=404, detail=f"No project named {name!r}.")
    if dp.error:
        return _import_error(request, dp.error)
    db_path = resolve_database_path(dp.project_toml, cwd=base)
    parsed = read_snapshot(db_path, volume_id)
    try:
        status = status_for_volume(dp.project_toml, volume_id, cwd=base)
    except WeaverError as exc:
        return _import_error(request, str(exc))
    preview: dict[str, Any] | None
    if parsed is None:
        preview = None
    else:
        try:
            preview = serialize_parsed_epub(parsed)
        except WeaverError as exc:
            return _import_error(request, str(exc))
    return templates.TemplateResponse(
        request,
        "epub_preview.html",
        {
            **project_layout(request, name, active_nav="project"),
            "source_path": f"volume:{volume_id}",
            "preview": preview,
            "snapshot_status": status,
            "error": None if parsed is not None else "Snapshot missing — click Reparse EPUB.",
        },
    )


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
        request,
        "new.html",
        {**global_layout("new"), "provider_types": known_provider_types()},
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
            {**global_layout("new"), "error": str(exc), "provider_types": known_provider_types()},
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
        tree = project_tree(dp.project_toml, cwd=base, jobs=_jobs(request))
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


def _job_error(request: Request, message: str, *, panel_id: str) -> HTMLResponse:
    """Render a job-panel error fragment (keeps the panel id so HTMX swaps it)."""
    return templates.TemplateResponse(
        request, "partials/_job_error.html", {"message": message, "panel_id": panel_id}
    )


def _render_translate_job(request: Request, name: str, job_id: str) -> HTMLResponse:
    job = _jobs(request).get(job_id)
    if job is None or job.project_name != name:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found for '{name}'.")
    updated_segments = []
    updated_segment_ids = set(job.drain_updated_segment_ids())
    if updated_segment_ids:
        try:
            project_toml = _resolve_project_toml(request, name)
            ws = chapter_workspace(project_toml, job.chapter_id, cwd=_base_dir(request))
            updated_segments = [seg for seg in ws.segments if seg.id in updated_segment_ids]
        except WeaverError:
            updated_segments = []
    response = templates.TemplateResponse(
        request,
        "partials/_job_with_grid.html",
        {
            "job": job,
            "progress": job.snapshot(),
            "name": name,
            "chapter_id": job.chapter_id,
            "updated_segments": updated_segments,
        },
    )
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


# --- candidate review UI (Sprint L3 — HTMX surfaces) ------------------------


@router.get("/ui/projects/{name}/candidates", response_class=HTMLResponse)
def ui_candidates_page(name: str, request: Request) -> HTMLResponse:
    """Translation candidates review page."""
    return templates.TemplateResponse(
        request,
        "candidates.html",
        {**project_layout(request, name, active_nav="candidates"), "name": name},
    )


@router.get("/ui/projects/{name}/candidates/list", response_class=HTMLResponse)
def ui_candidates_list(name: str, request: Request) -> HTMLResponse:
    """HTMX fragment: list of candidates for a project."""
    from weaver.storage.candidates import list_candidates_for_project

    project_toml = _resolve_project_toml(request, name)
    db_path = resolve_database_path(project_toml, cwd=_base_dir(request))
    candidates: list[dict] = []
    total = 0
    try:
        with closing(connect_database(db_path)) as conn:
            project = conn.execute("SELECT id FROM projects ORDER BY id LIMIT 1").fetchone()
            if project is not None:
                pid = int(project["id"])
                rows = list_candidates_for_project(conn, project_id=pid, limit=200)
                total = len(rows)
                candidates = [_candidate_to_ui_json(r) for r in rows]
    except WeaverError:
        pass
    return templates.TemplateResponse(
        request,
        "partials/_candidates_list.html",
        {"candidates": candidates, "total_count": total, "name": name},
    )


@router.post("/ui/projects/{name}/candidates/{candidate_id}/approve", response_class=HTMLResponse)
def ui_candidate_approve(name: str, candidate_id: str, request: Request) -> HTMLResponse:
    """Approve a candidate (HTMX). Re-renders the candidate card."""
    from contextlib import suppress

    with suppress(HTTPException):
        approve_candidate_endpoint(name, candidate_id, request)
    return ui_candidates_rerender_card(request, name, candidate_id)


@router.post("/ui/projects/{name}/candidates/{candidate_id}/reject", response_class=HTMLResponse)
def ui_candidate_reject(name: str, candidate_id: str, request: Request) -> HTMLResponse:
    """Reject a candidate (HTMX). Re-renders the candidate card."""
    from contextlib import suppress

    with suppress(HTTPException):
        reject_candidate_endpoint(name, candidate_id, request)
    return ui_candidates_rerender_card(request, name, candidate_id)


@router.post("/ui/projects/{name}/candidates/{candidate_id}/apply", response_class=HTMLResponse)
def ui_candidate_apply(name: str, candidate_id: str, request: Request) -> HTMLResponse:
    """Apply a candidate to its segment (HTMX). Re-renders the candidate card."""
    from contextlib import suppress

    with suppress(HTTPException):
        apply_candidate_endpoint(name, candidate_id, request)
    return ui_candidates_rerender_card(request, name, candidate_id)


def ui_candidates_rerender_card(request: Request, name: str, candidate_id: str) -> HTMLResponse:
    """Re-render one candidate card after a status transition."""
    from weaver.storage.candidates import get_candidate

    project_toml = _resolve_project_toml(request, name)
    db_path = resolve_database_path(project_toml, cwd=_base_dir(request))
    c = None
    try:
        with closing(connect_database(db_path)) as conn:
            c = get_candidate(conn, candidate_id=candidate_id)
    except (LookupError, WeaverError):
        return HTMLResponse(
            f'<div class="error" id="candidate-{candidate_id}">Candidate not found.</div>'
        )
    candidate = _candidate_to_ui_json(c)
    return templates.TemplateResponse(
        request,
        "partials/_candidates_list.html",
        {
            "candidates": [candidate],
            "total_count": 1,
            "name": name,
        },
    )


def _candidate_to_ui_json(c: Any) -> dict:
    import json

    prov = c.provenance_json
    return {
        "id": c.id,
        "project_id": c.project_id,
        "volume_id": c.volume_id,
        "chapter_id": c.chapter_id,
        "segment_id": c.segment_id,
        "source_text": c.source_text,
        "candidate_text": c.candidate_text,
        "provider": c.provider,
        "model": c.model,
        "status": c.status,
        "provenance": json.loads(prov) if isinstance(prov, str) else prov,
        "created_at": c.created_at,
        "updated_at": c.updated_at,
    }


# --- character drafts UI (Sprint L4 — HTMX surfaces) ------------------------


@router.get("/ui/projects/{name}/character-drafts", response_class=HTMLResponse)
def ui_drafts_page(name: str, request: Request) -> HTMLResponse:
    """Character page drafts review page."""
    return templates.TemplateResponse(
        request,
        "character_drafts.html",
        {**project_layout(request, name, active_nav="drafts"), "name": name},
    )


@router.get("/ui/projects/{name}/drafts/list", response_class=HTMLResponse)
def ui_drafts_list(name: str, request: Request) -> HTMLResponse:
    """HTMX fragment: list of character drafts for a project."""
    from weaver.storage.character_drafts import list_drafts_for_project

    project_toml = _resolve_project_toml(request, name)
    db_path = resolve_database_path(project_toml, cwd=_base_dir(request))
    drafts: list[dict] = []
    total = 0
    try:
        with closing(connect_database(db_path)) as conn:
            project = conn.execute("SELECT id FROM projects ORDER BY id LIMIT 1").fetchone()
            if project is not None:
                pid = int(project["id"])
                rows = list_drafts_for_project(conn, project_id=pid, limit=200)
                total = len(rows)
                for r in rows:
                    drafts.append(_draft_to_ui_json(r))
    except WeaverError:
        pass
    return templates.TemplateResponse(
        request,
        "partials/_drafts_list.html",
        {"drafts": drafts, "total_count": total, "name": name},
    )


@router.post("/ui/projects/{name}/drafts/{draft_id}/approve", response_class=HTMLResponse)
def ui_draft_approve(name: str, draft_id: str, request: Request) -> HTMLResponse:
    """Approve a character draft (HTMX). Re-renders the draft card."""
    from contextlib import suppress

    from weaver.api.routers.candidates import approve_draft_endpoint

    with suppress(HTTPException):
        approve_draft_endpoint(name, draft_id, request)
    return ui_drafts_rerender_card(request, name, draft_id)


@router.post("/ui/projects/{name}/drafts/{draft_id}/reject", response_class=HTMLResponse)
def ui_draft_reject(name: str, draft_id: str, request: Request) -> HTMLResponse:
    """Reject a character draft (HTMX). Re-renders the draft card."""
    from contextlib import suppress

    from weaver.api.routers.candidates import reject_draft_endpoint

    with suppress(HTTPException):
        reject_draft_endpoint(name, draft_id, request)
    return ui_drafts_rerender_card(request, name, draft_id)


def ui_drafts_rerender_card(request: Request, name: str, draft_id: str) -> HTMLResponse:
    """Re-render one draft card after a status transition."""
    from weaver.storage.character_drafts import get_draft

    project_toml = _resolve_project_toml(request, name)
    db_path = resolve_database_path(project_toml, cwd=_base_dir(request))
    d = None
    try:
        with closing(connect_database(db_path)) as conn:
            d = get_draft(conn, draft_id=draft_id)
    except (LookupError, WeaverError):
        return HTMLResponse(f'<div class="error" id="draft-{draft_id}">Draft not found.</div>')
    draft = _draft_to_ui_json(d)
    return templates.TemplateResponse(
        request,
        "partials/_drafts_list.html",
        {
            "drafts": [draft],
            "total_count": 1,
            "name": name,
        },
    )


def _draft_to_ui_json(d: Any) -> dict:
    import json

    prov = d.provenance_json
    return {
        "id": d.id,
        "project_id": d.project_id,
        "volume_id": d.volume_id,
        "chapter_id": d.chapter_id,
        "segment_id": d.segment_id,
        "source_text": d.source_text,
        "draft_text": d.draft_text,
        "heading": d.heading,
        "page_identifier": d.page_identifier,
        "status": d.status,
        "provenance": json.loads(prov) if isinstance(prov, str) else prov,
        "created_at": d.created_at,
        "updated_at": d.updated_at,
    }
