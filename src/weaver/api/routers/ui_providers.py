"""Providers hub (Sprint Q6) + provider/model + secret config editor (ADR ``015``).

The hub GET is render-safe (Gate B1): it uses ``services/workspace_providers``
(read-only DB) plus ``provider_config.read_config`` (TOML + secret-name list only)
— no writes, no migrations, no source hashing, **no provider calls on render**.

Write paths are explicit POSTs through the ``provider_config`` service:
``/ui/providers/config`` persists provider/model config (project or global scope);
``/ui/providers/secrets`` stores/removes API-key secrets in ``~/.weaver/secrets.toml``.
Secret *values* are only ever accepted by the secret form and are never rendered back.

The only provider call lives behind the explicit per-project health-check POST
(R-22 / Gate B1 extension: provider calls cost money/quota, so they are never
triggered by a render).
"""

from __future__ import annotations

from html import escape
from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from weaver.api.templating import templates
from weaver.api.ui_context import ws_hub_layout
from weaver.errors import SecretNotFoundError, WeaverError
from weaver.services import connections as connections_service
from weaver.services import provider_config as config_service
from weaver.services.config_writer import set_routing
from weaver.services.project import inspect_project
from weaver.services.project_discovery import discover_projects, find_project
from weaver.services.workspace_providers import build_workspace_providers

router = APIRouter(tags=["ui"], include_in_schema=False)


def _base_dir(request: Request) -> Path:
    return request.app.state.base_dir  # type: ignore[no-any-return]


def _opt(value: str | None) -> str | None:
    return value.strip() if value and value.strip() else None


def _config_ctx(request: Request, project: str | None) -> dict[str, object]:
    """Redacted provider/model + secret-name context for the hub editor panels.

    Reads TOML + the secret-name list only (no DB connect, no provider build,
    no source hashing) so the hub GET stays Gate-B1-safe.
    """
    base = _base_dir(request)
    view = config_service.read_config(base, project=_opt(project))
    return {
        "view": view,
        "project": _opt(project),
        "projects": [dp.name for dp in discover_projects(base)],
    }


@router.get("/ui/config", response_class=RedirectResponse)
def legacy_config_page(project: str | None = None) -> RedirectResponse:
    """Compatibility entry point for old bookmarks; editing lives in /ui/providers."""
    target = "/ui/providers"
    project_name = _opt(project)
    if project_name:
        target = f"{target}?{urlencode({'project': project_name})}"
    return RedirectResponse(f"{target}#connections", status_code=307)


@router.get("/ui/providers", response_class=HTMLResponse)
def providers_page(request: Request, project: str | None = None) -> HTMLResponse:
    """Global Providers hub — cross-project routing table + the provider/model +
    secret config editor (the single config surface). The table is read-only; edits
    flow through the ``provider_config`` service via the POST routes below."""
    base = _base_dir(request)
    providers = build_workspace_providers(base)
    try:
        config_ctx = _config_ctx(request, project)
    except WeaverError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return templates.TemplateResponse(
        request,
        "providers_hub.html",
        {
            **ws_hub_layout("providers"),
            "providers": providers,
            "books_dir": str(base),
            "connections": connections_service.list_connection_views(),
            **config_ctx,
        },
    )


def _project_summary(base: Path, name: str) -> object | None:
    """Find one project's read-only summary (rebuilds the workspace view)."""
    for summary in build_workspace_providers(base).projects:
        if summary.project_name == name:
            return summary
    return None


@router.post("/ui/providers/{name}/switch", response_class=HTMLResponse)
def provider_switch(
    name: str,
    request: Request,
    connection: str = Form(...),
    model: str | None = Form(None),
) -> HTMLResponse:
    """Switch a project's translate AI from the workspace table, then re-render its row."""
    base = _base_dir(request)
    dp = find_project(base, name)
    toml = getattr(dp, "project_toml", None) if dp is not None else None
    if dp is None or dp.error or not isinstance(toml, Path):
        msg = f"No project named {escape(name)!r}."
        return HTMLResponse(
            f"<tr><td colspan='6'><span class='error' role='alert'>{msg}</span></td></tr>"
        )
    error: str | None = None
    try:
        set_routing(toml, task="translate", connection=connection, model=_opt(model))
    except WeaverError as exc:
        error = str(exc)
    return templates.TemplateResponse(
        request,
        "partials/_provider_row.html",
        {
            "p": _project_summary(base, name),
            "connections": connections_service.list_connection_views(),
            "switch_error": error,
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


@router.post("/ui/providers/secrets", response_class=HTMLResponse)
def config_secret_set(
    request: Request,
    project: str | None = Form(None),
    env_name: str = Form(...),
    value: str = Form(...),
) -> HTMLResponse:
    """Store an API-key secret under an env-var name (value never echoed back)."""
    error: str | None = None
    try:
        config_service.store_secret(env_name, value)
    except WeaverError as exc:
        error = str(exc)
    ctx = _config_ctx(request, project)
    ctx["secret_error"] = error
    ctx["secret_saved"] = error is None
    return templates.TemplateResponse(request, "partials/_secrets.html", ctx)


@router.post("/ui/providers/secrets/{env_name}/delete", response_class=HTMLResponse)
def config_secret_delete(
    env_name: str, request: Request, project: str | None = Form(None)
) -> HTMLResponse:
    """Remove a stored secret, then re-render the secret list."""
    error: str | None = None
    try:
        config_service.remove_secret(env_name)
    except SecretNotFoundError as exc:
        error = str(exc)
    ctx = _config_ctx(request, project)
    ctx["secret_error"] = error
    return templates.TemplateResponse(request, "partials/_secrets.html", ctx)


def _connections_panel(request: Request, **extra: object) -> HTMLResponse:
    """Re-render the Connections panel (TOML read only — Gate-B1 safe)."""
    ctx: dict[str, object] = {"connections": connections_service.list_connection_views()}
    ctx.update(extra)
    return templates.TemplateResponse(request, "partials/_connections.html", ctx)


def _probe_result(request: Request, result: object | None, error: str | None) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "partials/_connection_test_result.html",
        {"result": result, "error": error},
    )


@router.post("/ui/providers/connections/test", response_class=HTMLResponse)
def connection_test(
    request: Request,
    name: str = Form(""),
    base_url: str = Form(""),
    api_key: str | None = Form(None),
    api_key_env: str | None = Form(None),
    use_shell_env: str | None = Form(None),
) -> HTMLResponse:
    """Probe a not-yet-saved endpoint with form values (explicit POST, never on render)."""
    try:
        result = connections_service.probe_connection(
            base_url=base_url,
            api_key=_opt(api_key),
            api_key_env=_opt(api_key_env),
            use_shell_env=bool(use_shell_env),
            name=name,
        )
    except WeaverError as exc:
        return _probe_result(request, None, str(exc))
    return _probe_result(request, result, None)


@router.post("/ui/providers/connections", response_class=HTMLResponse)
def connection_add(
    request: Request,
    name: str = Form(...),
    base_url: str = Form(...),
    api_key: str | None = Form(None),
    api_key_env: str | None = Form(None),
    use_shell_env: str | None = Form(None),
    keyless: str | None = Form(None),
    default_model: str | None = Form(None),
) -> HTMLResponse:
    """Register a connection (key value stored in secrets.toml, never echoed back)."""
    try:
        connections_service.add_connection(
            name=name,
            base_url=base_url,
            api_key=_opt(api_key),
            api_key_env=_opt(api_key_env),
            use_shell_env=bool(use_shell_env),
            default_model=_opt(default_model) or "",
            requires_key=not bool(keyless),
        )
    except WeaverError as exc:
        return _connections_panel(request, add_error=str(exc))
    return _connections_panel(request, add_saved=True)


@router.post("/ui/providers/connections/{name}/delete", response_class=HTMLResponse)
def connection_delete(name: str, request: Request) -> HTMLResponse:
    """Remove a connection (its stored secret is left in place)."""
    connections_service.remove_connection(name)
    return _connections_panel(request)


@router.post("/ui/providers/connections/{name}/test", response_class=HTMLResponse)
def connection_saved_test(name: str, request: Request) -> HTMLResponse:
    """Probe an already-saved connection (stored/shell key) and refresh its cache."""
    try:
        result = connections_service.refresh_models(name)
    except WeaverError as exc:
        return _probe_result(request, None, str(exc))
    return _probe_result(request, result, None)
