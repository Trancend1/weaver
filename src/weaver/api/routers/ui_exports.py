"""UI router: Exports hub + per-project export history (Sprint Q7 / WV-009).

Read-only surfaces over the ``export_history`` ledger. The hub GET uses
``services/workspace_exports`` with ``connect_readonly_database`` exclusively —
no writes, no migrations, no source hashing, no provider calls, no artifact byte
serving (presence is a cheap ``stat``).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from weaver.api.templating import templates
from weaver.api.ui_context import project_layout, ws_hub_layout
from weaver.services.project_discovery import find_project
from weaver.services.workspace_exports import (
    build_workspace_exports,
    project_export_history,
)

router = APIRouter(tags=["ui"], include_in_schema=False)


def _base_dir(request: Request) -> Path:
    return request.app.state.base_dir  # type: ignore[no-any-return]


@router.get("/ui/exports", response_class=HTMLResponse)
def exports_page(request: Request) -> HTMLResponse:
    """Global Exports hub — cross-project recent export history (basename only)."""
    base = _base_dir(request)
    exports = build_workspace_exports(base)

    return templates.TemplateResponse(
        request,
        "exports_hub.html",
        {
            **ws_hub_layout("exports"),
            "exports": exports,
            "books_dir": str(base),
        },
    )


@router.get("/ui/projects/{name}/exports", response_class=HTMLResponse)
def project_exports_page(name: str, request: Request) -> HTMLResponse:
    """Per-project export history (full path; with exists/missing state)."""
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
    rows = project_export_history(base, name)
    return templates.TemplateResponse(
        request,
        "project_exports.html",
        {
            **project_layout(request, name, active_nav="exports"),
            "name": name,
            "rows": rows,
        },
    )
