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


def _cached_for(connection_name: str | None) -> tuple[list[str], bool]:
    """Return (cached models, stale?) for a connection — cache read only, no probe."""
    if not connection_name:
        return [], False
    cached = connections_service.cached_models(connection_name)
    if cached is None:
        return [], False
    return list(cached.models), cached.is_stale()


def _models_fragment(
    request: Request, models: list[str], *, error: str | None, stale: bool
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "partials/_routing_models.html",
        {"models": models, "models_error": error, "models_stale": stale},
    )


def _panel(request: Request, name: str, toml: Path, **extra: object) -> HTMLResponse:
    active = resolve_active_ai(toml, TaskType.translate)
    models, stale = _cached_for(active.connection_name)
    ctx: dict[str, object] = {
        "project_name": name,
        "active_ai": active,
        "connections": connections_service.list_connection_views(),
        "models": models,
        "models_stale": stale,
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
    """Live-probe one connection's models (explicit POST) and refresh its cache."""
    if get_connection(connection) is None:
        return _models_fragment(
            request, [], error=f"No connection named {connection!r}.", stale=False
        )
    try:
        result = connections_service.refresh_models(connection)
    except WeaverError as exc:
        # Don't strand the user: fall back to the last cached snapshot if any.
        cached, _ = _cached_for(connection)
        return _models_fragment(request, cached, error=str(exc), stale=bool(cached))
    return _models_fragment(request, list(result.models), error=None, stale=False)


@router.get("/ui/projects/{name}/routing/cached-models", response_class=HTMLResponse)
def routing_cached_models(name: str, request: Request, connection: str) -> HTMLResponse:
    """Render a connection's cached models (cache read only — no probe, Gate B1)."""
    models, stale = _cached_for(connection)
    return _models_fragment(request, models, error=None, stale=stale)
