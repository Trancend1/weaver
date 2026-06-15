"""Per-project Active AI + Switch AI (ADR 018 D7/D8).

The project page shows the **Active AI** for the translate task (model via
connection) and lets the user switch it in place. Switching writes
``[routing.translate]`` to the project's ``project.toml``; the next translation
run resolves through ``services/routing`` and uses the chosen connection + model.

Model discovery (the "Load models" action) is an explicit POST that probes one
connection's ``/v1/models`` — never on render, no background thread (Gate B1).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from weaver.api.templating import templates
from weaver.core.connection_registry import get_connection
from weaver.core.task_types import TaskType
from weaver.errors import WeaverError
from weaver.services import connections as connections_service
from weaver.services.config_writer import set_routing
from weaver.services.project_discovery import find_project
from weaver.services.routing import resolve_active_ai

router = APIRouter(tags=["ui"], include_in_schema=False)


def _base_dir(request: Request) -> Path:
    return request.app.state.base_dir  # type: ignore[no-any-return]


def _opt(value: str | None) -> str | None:
    return value.strip() if value and value.strip() else None


def _resolve_toml(request: Request, name: str) -> Path | None:
    dp = find_project(_base_dir(request), name)
    if dp is None or dp.error:
        return None
    toml = getattr(dp, "project_toml", None)
    return toml if isinstance(toml, Path) else None


def _task(value: str) -> TaskType:
    try:
        return TaskType(value)
    except ValueError:
        return TaskType.translate


def _panel(request: Request, name: str, toml: Path, **extra: object) -> HTMLResponse:
    active = resolve_active_ai(toml, TaskType.translate)
    ctx: dict[str, object] = {
        "project_name": name,
        "active_ai": active,
        "connections": connections_service.list_connection_views(),
        "models": [],
    }
    ctx.update(extra)
    return templates.TemplateResponse(request, "partials/_active_ai.html", ctx)


@router.get("/ui/projects/{name}/routing", response_class=HTMLResponse)
def routing_panel(name: str, request: Request) -> HTMLResponse:
    """Render the Active AI panel for the project (TOML read only — Gate-B1 safe)."""
    toml = _resolve_toml(request, name)
    if toml is None:
        return HTMLResponse(f"<p class='error' role='alert'>No project named {name!r}.</p>")
    return _panel(request, name, toml)


@router.post("/ui/projects/{name}/routing/switch", response_class=HTMLResponse)
def routing_switch(
    name: str,
    request: Request,
    connection: str = Form(...),
    model: str | None = Form(None),
    task: str = Form("translate"),
) -> HTMLResponse:
    """Persist the chosen (connection, model) for a task, then re-render the panel."""
    toml = _resolve_toml(request, name)
    if toml is None:
        return HTMLResponse(f"<p class='error' role='alert'>No project named {name!r}.</p>")
    try:
        set_routing(toml, task=_task(task).value, connection=connection, model=_opt(model))
    except WeaverError as exc:
        return _panel(request, name, toml, switch_error=str(exc))
    return _panel(request, name, toml, switch_saved=True)


@router.post("/ui/projects/{name}/routing/models", response_class=HTMLResponse)
def routing_models(name: str, request: Request, connection: str = Form(...)) -> HTMLResponse:
    """Probe one connection's models on demand (explicit POST) for the picker."""
    conn = get_connection(connection)
    models: list[str] = []
    error: str | None = None
    if conn is not None:
        try:
            result = connections_service.probe_connection(
                base_url=conn.base_url, api_key_env=conn.api_key_env or None, name=conn.name
            )
            models = list(result.models)
        except WeaverError as exc:
            error = str(exc)
            if conn.default_model:
                models = [conn.default_model]
    return templates.TemplateResponse(
        request,
        "partials/_routing_models.html",
        {"models": models, "models_error": error},
    )
