"""UI router: per-project Analytics page (Sprint Q8).

Read-only, deterministic, current-state analytics over
``services/project_analytics``. No QA scan, no provider call, no source
hashing on render — QA numbers live on the Quality page, on demand.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from weaver.api.templating import templates
from weaver.api.ui_context import project_layout
from weaver.errors import WeaverError
from weaver.services.project_analytics import build_project_analytics
from weaver.services.project_discovery import find_project

router = APIRouter(tags=["ui"], include_in_schema=False)


def _base_dir(request: Request) -> Path:
    return request.app.state.base_dir  # type: ignore[no-any-return]


@router.get("/ui/projects/{name}/analytics", response_class=HTMLResponse)
def project_analytics_page(name: str, request: Request) -> HTMLResponse:
    """Current-state analytics for one project (deterministic reads only)."""
    base = _base_dir(request)
    dp = find_project(base, name)
    if dp is None:
        return templates.TemplateResponse(
            request, "not_found.html", {"message": f"No project named {name!r}."}, status_code=404
        )
    if dp.error:
        return templates.TemplateResponse(
            request, "error.html", {"message": dp.error}, status_code=422
        )
    try:
        analytics = build_project_analytics(dp.project_toml, cwd=base)
    except WeaverError as exc:
        return templates.TemplateResponse(
            request, "error.html", {"message": str(exc)}, status_code=422
        )
    return templates.TemplateResponse(
        request,
        "project_analytics.html",
        {
            **project_layout(request, name, active_nav="analytics"),
            "name": name,
            "a": analytics,
        },
    )
