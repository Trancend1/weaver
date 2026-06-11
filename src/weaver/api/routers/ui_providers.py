"""UI router: global Providers hub (Sprint Q6).

Read-only cross-project provider surface.  The hub GET uses
``services/workspace_providers`` with ``connect_readonly_database`` exclusively
— no writes, no migrations, no source hashing, **no provider calls on render**.

The only provider call lives behind an explicit per-project health-check POST
(R-22 / Gate B1 extension: provider calls cost money/quota, so they are never
triggered by a render).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from weaver.api.templating import templates
from weaver.api.ui_context import ws_hub_layout
from weaver.errors import WeaverError
from weaver.services.project import inspect_project
from weaver.services.project_discovery import find_project
from weaver.services.workspace_providers import build_workspace_providers

router = APIRouter(tags=["ui"], include_in_schema=False)


def _base_dir(request: Request) -> Path:
    return request.app.state.base_dir  # type: ignore[no-any-return]


@router.get("/ui/providers", response_class=HTMLResponse)
def providers_page(request: Request) -> HTMLResponse:
    """Global Providers hub — cross-project provider/model + usage summary."""
    base = _base_dir(request)
    providers = build_workspace_providers(base)

    return templates.TemplateResponse(
        request,
        "providers_hub.html",
        {
            **ws_hub_layout("providers"),
            "providers": providers,
            "books_dir": str(base),
        },
    )


@router.post("/ui/providers/{name}/healthcheck", response_class=HTMLResponse)
def provider_healthcheck(name: str, request: Request) -> HTMLResponse:
    """Run an explicit provider health check for one project (HTMX fragment).

    This is the **only** path that instantiates and calls a provider — it never
    fires on render.  Failures are reported as a status fragment, never raised.
    """
    base = _base_dir(request)
    dp = find_project(base, name)
    if dp is None or dp.error:
        message = dp.error if dp else f"No project named {name!r}."
        return templates.TemplateResponse(
            request,
            "partials/_provider_status.html",
            {"name": name, "status": None, "error": message},
        )
    try:
        summary = inspect_project(dp.project_toml, cwd=base, run_healthcheck=True)
        status = summary.provider_status
    except WeaverError as exc:
        return templates.TemplateResponse(
            request,
            "partials/_provider_status.html",
            {"name": name, "status": None, "error": str(exc)},
        )
    return templates.TemplateResponse(
        request,
        "partials/_provider_status.html",
        {"name": name, "status": status, "error": None},
    )
