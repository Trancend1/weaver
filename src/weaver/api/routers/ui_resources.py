"""UI router: global Resources hub (Sprint Q5).

Read-only cross-project resource summary.  Uses
``services/workspace_resources`` with ``connect_readonly_database`` exclusively
— no writes, no migrations, no source hashing, no provider calls.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from weaver.api.templating import templates
from weaver.api.ui_context import ws_hub_layout
from weaver.services.workspace_resources import build_workspace_resources

router = APIRouter(tags=["ui"], include_in_schema=False)


def _base_dir(request: Request) -> Path:
    return request.app.state.base_dir  # type: ignore[no-any-return]


@router.get("/ui/resources", response_class=HTMLResponse)
def resources_page(request: Request) -> HTMLResponse:
    """Global Resources hub — cross-project glossary, characters, TM summary."""
    base = _base_dir(request)
    resources = build_workspace_resources(base)

    return templates.TemplateResponse(
        request,
        "resources_hub.html",
        {
            **ws_hub_layout("resources"),
            "resources": resources,
            "books_dir": str(base),
        },
    )
