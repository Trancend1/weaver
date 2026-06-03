"""Server-rendered browser UI for the FastAPI cockpit (Sprint 11A, ADR ``007``).

Jinja2 + HTMX, no build, no SPA. **Presentation only**: every route is a thin
adapter that calls the same shared services the JSON routers use
(``services/project_discovery``, ``services/project_tree``, ``core/global_config``)
and renders a template. No business logic, no storage access here (CLAUDE.md §4.2).

All HTML lives under ``/ui`` so the JSON API surface stays cleanly separable
(``/`` redirects to ``/ui``). Flask remains the default ``weaver serve`` cockpit;
this UI ships on ``weaver serve-api`` alongside the JSON API. No default flip.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from weaver.api.templating import templates
from weaver.core.global_config import load_global_config, resolve_config_value
from weaver.errors import WeaverError
from weaver.services.import_source import import_volume
from weaver.services.project import initialize_project, project_exists
from weaver.services.project_discovery import discover_projects, find_project
from weaver.services.project_tree import project_tree
from weaver.services.source_browser import list_directory
from weaver.services.source_intake import resolve_intake_source

router = APIRouter(tags=["ui"], include_in_schema=False)


def _base_dir(request: Request) -> Path:
    return request.app.state.base_dir  # type: ignore[no-any-return]


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
    return templates.TemplateResponse(request, "new.html", {})


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
        return templates.TemplateResponse(request, "new.html", {"error": str(exc)}, status_code=400)
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
