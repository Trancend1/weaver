"""Provider/model + secret config endpoints (Sprint 10C).

Thin adapter over ``services/provider_config`` — no domain logic here. Closes
FastAPI parity gap #2 (the Flask ``/config`` route's persistence) so providers,
models, and API keys can be configured from the API instead of per-request
overrides only.

Security (CLAUDE.md §4.2, ADR ``0017``/``0020``): API-key *values* are only ever
accepted via ``POST /config/secrets/{env_name}`` and are **never returned** by
any endpoint — responses report key *presence* (a bool) and secret *names* only.
The CLI ``secrets`` group is untouched.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from weaver.api.schemas import (
    ConfigUpdateRequest,
    ProviderConfigResponse,
    SecretResponse,
    SecretUpdateRequest,
)
from weaver.errors import SecretNotFoundError, WeaverError
from weaver.services.provider_config import (
    ProviderConfigView,
    read_config,
    remove_secret,
    store_secret,
    write_config,
)

router = APIRouter(prefix="/config", tags=["config"])


def _base_dir(request: Request) -> Path:
    return request.app.state.base_dir  # type: ignore[no-any-return]


def _view_response(view: ProviderConfigView) -> ProviderConfigResponse:
    return ProviderConfigResponse(
        default_provider=view.default_provider,
        default_model=view.default_model,
        project_name=view.project_name,
        provider_type=view.provider_type,
        protocol=view.protocol,
        model=view.model,
        base_url=view.base_url,
        api_key_env=view.api_key_env,
        api_key_set=view.api_key_set,
        secret_names=list(view.secret_names),
    )


@router.get("", response_model=ProviderConfigResponse)
def get_config(request: Request, project: str | None = None) -> ProviderConfigResponse:
    """Return the redacted provider/model config.

    Always includes global defaults + stored secret names. Pass ``?project=`` to
    also include that project's ``[provider]`` block. No key value is returned.
    """
    try:
        view = read_config(_base_dir(request), project=project)
    except WeaverError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _view_response(view)


@router.patch("", response_model=ProviderConfigResponse)
def update_config(request: Request, body: ConfigUpdateRequest) -> ProviderConfigResponse:
    """Persist provider/model config to project or global scope.

    No API-key value is accepted here — only ``api_key_env`` (the env-var name).
    Use ``POST /config/secrets/{env_name}`` to store the value.
    """
    try:
        view = write_config(
            _base_dir(request),
            scope=body.scope,
            project=body.project,
            provider_type=body.provider_type,
            protocol=body.protocol,
            model=body.model,
            base_url=body.base_url,
            api_key_env=body.api_key_env,
        )
    except WeaverError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _view_response(view)


@router.post("/secrets/{env_name}", response_model=SecretResponse, status_code=201)
def set_secret_value(env_name: str, body: SecretUpdateRequest) -> SecretResponse:
    """Store an API-key secret under env-var name ``env_name``.

    The value goes only to the local secret store (``~/.weaver/secrets.toml``,
    ``0o600``) and is never echoed back.
    """
    try:
        presence = store_secret(env_name, body.value)
    except WeaverError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return SecretResponse(name=presence.name, is_set=presence.is_set)


@router.delete("/secrets/{env_name}", response_model=SecretResponse)
def delete_secret_value(env_name: str) -> SecretResponse:
    """Remove the secret stored under ``env_name``. 404 when not present."""
    try:
        presence = remove_secret(env_name)
    except SecretNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return SecretResponse(name=presence.name, is_set=presence.is_set)
