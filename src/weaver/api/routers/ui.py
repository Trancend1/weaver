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
from weaver.api.routers.export import EXPORT_GATE_BLOCKED_STATUS, _start_export
from weaver.api.schemas import ExportRequest
from weaver.api.templating import templates
from weaver.api.ui_context import global_layout, project_layout, ws_hub_layout
from weaver.errors import (
    ChapterNotFoundError,
    VolumeNotFoundError,
    WeaverError,
)
from weaver.providers.registry import known_provider_types
from weaver.services.chapter_workspace import chapter_workspace
from weaver.services.epub_structure_preview import preview_epub_structure
from weaver.services.import_source import import_volume
from weaver.services.project import delete_project, initialize_project, project_name_exists
from weaver.services.project_discovery import discover_projects, find_project
from weaver.services.project_overview import project_overview
from weaver.services.project_paths import resolve_database_path
from weaver.services.project_tree import project_tree
from weaver.services.source_browser import list_directory, resolve_source
from weaver.services.source_intake import resolve_intake_source
from weaver.services.volume import delete_volume_from_project
from weaver.services.workspace_index import build_workspace_index
from weaver.storage.db import connect_readonly_database
from weaver.storage.volumes import get_volume

router = APIRouter(tags=["ui"], include_in_schema=False)


def _base_dir(request: Request) -> Path:
    return request.app.state.base_dir  # type: ignore[no-any-return]


def _jobs(request: Request) -> JobRegistry:
    return request.app.state.jobs  # type: ignore[no-any-return]


def _resolve_project_toml(request: Request, name: str) -> Path:
    base = _base_dir(request)
    dp = find_project(base, name)
    if dp is None:
        raise ChapterNotFoundError(f"No project named {name!r} under {base}.")
    if dp.error:
        raise WeaverError(dp.error)
    return dp.project_toml


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


@router.get("/ui", response_class=HTMLResponse)
def dashboard(request: Request) -> HTMLResponse:
    """Home: workspace command center — cross-project index via workspace_index."""
    base = _base_dir(request)
    registry = _jobs(request)
    index = build_workspace_index(
        base,
        registry_live_check=lambda pname, jid: (
            (job := registry.get(jid)) is not None and job.status == "running"
        ),
        cache=request.app.state.workspace_cache,
    )
    identity_conflicts = [e for e in index.entries if e.state == "identity_conflict"]
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            **ws_hub_layout("projects"),
            "entries": index.entries,
            "identity_conflicts": identity_conflicts,
            "active_job_count": registry.running_count(),
            "books_dir": str(base),
        },
    )


@router.get("/ui/empty", response_class=HTMLResponse)
def empty_fragment() -> HTMLResponse:
    """Return an empty HTMX fragment, mainly for closing contextual panels."""

    return HTMLResponse("")


@router.get("/ui/epub-preview", response_class=HTMLResponse)
def epub_preview_page(request: Request, source_path: str = Query("")) -> HTMLResponse:
    """Read-only EPUB structure preview page for a sandboxed source path."""

    preview: dict[str, Any] | None = None
    error: str | None = None
    if source_path.strip():
        try:
            if source_path.startswith("volume:"):
                return _volume_reference_preview(request, source_path)
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


def _volume_reference_preview(request: Request, source_path: str) -> HTMLResponse:
    """Render a persisted volume snapshot for legacy ``volume:<id>`` preview URLs."""

    try:
        volume_id = int(source_path.split(":", 1)[1])
    except (IndexError, ValueError) as exc:
        raise WeaverError(
            f"Invalid volume preview reference: {source_path}. "
            "Likely cause: a stale preview URL. "
            "Next command: open the project page and use View structure."
        ) from exc

    matches: list[tuple[str, Path]] = []
    base = _base_dir(request)
    for discovered in discover_projects(base):
        if discovered.error:
            continue
        db_path = resolve_database_path(discovered.project_toml, cwd=base)
        try:
            with closing(connect_readonly_database(db_path)) as connection:
                get_volume(connection, volume_id)
        except (LookupError, WeaverError):
            continue
        matches.append((discovered.name, discovered.project_toml))

    if len(matches) != 1:
        error = (
            f"Volume preview reference is ambiguous: {source_path}. "
            "Likely cause: volume ids are project-scoped or the tab is stale. "
            "Next command: open the project page and use View structure."
        )
        return templates.TemplateResponse(
            request,
            "epub_preview.html",
            {
                **global_layout("epub-preview"),
                "source_path": source_path,
                "preview": None,
                "error": error,
            },
        )

    project_name, project_toml = matches[0]
    return _render_volume_structure_preview(request, project_name, volume_id, project_toml)


@router.get("/ui/projects/{name}", response_class=HTMLResponse)
def project_view(name: str, request: Request) -> HTMLResponse:
    """Project hub: overview cards, volume summaries, and content tree."""
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
        overview = project_overview(dp.project_toml, cwd=base, jobs=_jobs(request))
    except WeaverError as exc:
        return templates.TemplateResponse(
            request, "error.html", {"message": str(exc)}, status_code=422
        )
    return templates.TemplateResponse(
        request,
        "project.html",
        {
            **project_layout(request, name, active_nav="project", sidebar_tree=tree),
            "tree": tree,
            "overview": overview,
        },
    )


# --- jobs (Sprint I6 — unified Job Detail UI) ------------------------------


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
    base = _base_dir(request)
    dp = find_project(base, name)
    if dp is None:
        raise HTTPException(status_code=404, detail=f"No project named {name!r}.")
    if dp.error:
        return _import_error(request, dp.error)
    return _render_volume_structure_preview(request, name, volume_id, dp.project_toml)


@router.get("/ui/projects/{name}/volumes/{volume_id}/structure/modal", response_class=HTMLResponse)
def ui_volume_structure_modal(name: str, volume_id: int, request: Request) -> HTMLResponse:
    """Contextual modal shell for inspecting a volume without leaving the project hub."""
    from weaver.errors import VolumeNotFoundError as _VNF
    from weaver.services.epub_reparse import status_for_volume

    base = _base_dir(request)
    dp = find_project(base, name)
    if dp is None:
        raise HTTPException(status_code=404, detail=f"No project named {name!r}.")
    if dp.error:
        return _import_error(request, dp.error)
    tree = project_tree(dp.project_toml, cwd=base, jobs=_jobs(request))
    volume = next((item for item in tree.volumes if item.id == volume_id), None)
    if volume is None:
        raise HTTPException(status_code=404, detail=f"No volume with id {volume_id}.")
    try:
        status = status_for_volume(dp.project_toml, volume_id, cwd=base)
    except _VNF as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except WeaverError as exc:
        return _import_error(request, str(exc))
    first_chapter = volume.chapters[0] if volume and volume.chapters else None
    return templates.TemplateResponse(
        request,
        "partials/_preview_modal.html",
        {
            "name": name,
            "volume_id": volume_id,
            "volume_title": volume.title,
            "snapshot_status": status,
            "first_chapter": first_chapter,
        },
    )


def _render_volume_structure_preview(
    request: Request, name: str, volume_id: int, project_toml: Path
) -> HTMLResponse:
    """Render one imported volume's persisted EPUB snapshot."""

    from weaver.services.epub_reparse import status_for_volume
    from weaver.services.epub_snapshot import read_snapshot
    from weaver.services.epub_structure_preview import serialize_parsed_epub

    base = _base_dir(request)
    db_path = resolve_database_path(project_toml, cwd=base)
    parsed = read_snapshot(db_path, volume_id)
    try:
        status = status_for_volume(project_toml, volume_id, cwd=base)
    except WeaverError as exc:
        return _import_error(request, str(exc))
    preview: dict[str, Any] | None
    if parsed is None:
        preview = None
    else:
        try:
            preview = serialize_parsed_epub(parsed, project_name=name, volume_id=volume_id)
        except WeaverError as exc:
            return _import_error(request, str(exc))
    return templates.TemplateResponse(
        request,
        "epub_preview.html",
        {
            **project_layout(request, name, active_nav="project"),
            "source_path": f"volume:{volume_id}",
            "volume_preview": True,
            "project_name": name,
            "volume_id": volume_id,
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
    project_name: str | None = Form(None),
) -> HTMLResponse | RedirectResponse:
    """Create a project, optionally importing an uploaded/browsed first volume.

    Reuses the same services as ``POST /projects/create`` (no logic here). On
    failure the form is re-rendered with the error; on success → 303 to the
    project view.
    """
    base = _base_dir(request)
    uploaded = (file.filename, await file.read()) if file is not None and file.filename else None
    try:
        source = None
        if uploaded is not None or source_path:
            source = resolve_intake_source(base, uploaded=uploaded, source_path=source_path)
        name = (project_name or "").strip() or (source.stem if source is not None else "")
        if not name:
            raise WeaverError("Project name is required.")
        if project_name_exists(name, cwd=base):
            raise WeaverError(f"A project named {name!r} already exists.")
        result = initialize_project(
            source,
            cwd=base,
            template=template or None,
            provider=provider or None,
            project_name=name,
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
    name: str,
    request: Request,
    target: str = Form("epub"),
    bundle: bool = Form(False),
    kind: str = Form("draft"),
    require_clean: bool = Form(False),
) -> HTMLResponse:
    """Start a novel-scope export job for the chosen target (HTMX panel).

    Draft (default) is always allowed; a Final export with the require-clean
    toggle is refused while critical QA issues exist (Q7 gate), rendering a
    blocked fragment with a Draft escape hatch.
    """
    try:
        started = _start_export(
            request,
            name,
            scope="novel",
            target_id=None,
            body=ExportRequest(
                target=target, bundle=bundle, kind=kind, require_clean=require_clean
            ),
        )
    except HTTPException as exc:
        if exc.status_code == EXPORT_GATE_BLOCKED_STATUS:
            return templates.TemplateResponse(
                request,
                "partials/_export_gate_blocked.html",
                {"name": name, "target": target, "bundle": bundle, "reason": str(exc.detail)},
            )
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
