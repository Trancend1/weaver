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

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from weaver.api.templating import templates
from weaver.core.global_config import load_global_config, resolve_config_value
from weaver.errors import WeaverError
from weaver.services.project_discovery import discover_projects, find_project
from weaver.services.project_tree import project_tree

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
