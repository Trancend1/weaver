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

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse

from weaver.api.templating import templates
from weaver.api.ui_context import ws_hub_layout
from weaver.errors import SecretNotFoundError, WeaverError
from weaver.services import provider_config as config_service
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
            **config_ctx,
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


@router.post("/ui/providers/config", response_class=HTMLResponse)
def config_save(
    request: Request,
    scope: str = Form("project"),
    project: str | None = Form(None),
    provider_type: str | None = Form(None),
    protocol: str | None = Form(None),
    model: str | None = Form(None),
    base_url: str | None = Form(None),
    api_key_env: str | None = Form(None),
) -> HTMLResponse:
    """Persist provider/model config (no key value accepted), then re-render the form."""
    base = _base_dir(request)
    error: str | None = None
    try:
        config_service.write_config(
            base,
            scope=scope,
            project=_opt(project),
            provider_type=_opt(provider_type),
            protocol=_opt(protocol),
            model=_opt(model),
            base_url=_opt(base_url),
            api_key_env=_opt(api_key_env),
        )
    except WeaverError as exc:
        error = str(exc)
    ctx = _config_ctx(request, project)
    ctx["error"] = error
    ctx["saved"] = error is None
    return templates.TemplateResponse(request, "partials/_config_form.html", ctx)


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
