"""UI router: global Translation Queue hub (Sprint Q4).

Read-only cross-project queue surface.  Uses ``services/workspace_queue`` with
``connect_readonly_database`` exclusively — no writes, no migrations, no
source hashing, no provider calls.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from weaver.api.templating import templates
from weaver.api.ui_context import ws_hub_layout
from weaver.services.workspace_queue import build_workspace_queue

router = APIRouter(tags=["ui"], include_in_schema=False)


def _base_dir(request: Request) -> Path:
    return request.app.state.base_dir  # type: ignore[no-any-return]


def _jobs(request: Request):
    return request.app.state.jobs


@router.get("/ui/queue", response_class=HTMLResponse)
def queue_page(request: Request) -> HTMLResponse:
    """Global Translation Queue — cross-project job summary."""
    base = _base_dir(request)
    registry = _jobs(request)

    queue = build_workspace_queue(
        base,
        registry_live_check=lambda pname, jid: (
            (job := registry.get(jid)) is not None and job.status == "running"
        ),
    )

    return templates.TemplateResponse(
        request,
        "queue_hub.html",
        {
            **ws_hub_layout("queue"),
            "queue": queue,
            "books_dir": str(base),
        },
    )
