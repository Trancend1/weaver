"""Provider/model config + secret orchestration (framework-agnostic, Sprint 10C).

A thin read/write facade over the existing primitives so the FastAPI cockpit can
manage provider configuration without reaching into core directly:

- read project ``[provider]`` + global ``[defaults]`` (``core/config`` /
  ``core/global_config``),
- write provider/model/base_url/api_key_env (``services/config_writer``),
- store/remove/list API-key secrets (``core/secret_store``).

**Secrets never appear here in plaintext.** This module only ever reports whether
a key is *present* (a bool) and lists secret *names*; values are written through
``set_secret`` and read by providers from ``os.environ`` — never returned. Holds
no web types (CLAUDE.md §4.2).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from weaver.core.config import load_project_config
from weaver.core.global_config import default_global_config_path, load_global_config
from weaver.core.secret_store import (
    delete_secret,
    list_secret_names,
    set_secret,
)
from weaver.errors import ConfigError, SecretNotFoundError
from weaver.services.config_writer import set_provider
from weaver.services.project_discovery import find_project

CONFIG_SCOPES = ("project", "global")


@dataclass(frozen=True)
class ProviderConfigView:
    """Redacted view of provider/model config. Never carries a key value."""

    default_provider: str | None
    default_model: str | None
    project_name: str | None
    provider_type: str | None
    model: str | None
    base_url: str | None
    api_key_env: str | None
    api_key_set: bool
    secret_names: tuple[str, ...]


@dataclass(frozen=True)
class SecretPresence:
    """Redacted secret state: a name and whether it is stored. No value."""

    name: str
    is_set: bool


def _key_is_set(api_key_env: str | None) -> bool:
    """Report whether ``api_key_env`` resolves to a value, without revealing it.

    True when the name is in the local secret store or already in the process
    environment (a real shell env var wins; startup also injects store keys).
    """

    if not api_key_env:
        return False
    return api_key_env in list_secret_names() or bool(os.environ.get(api_key_env))


def read_config(base_dir: Path, *, project: str | None = None) -> ProviderConfigView:
    """Return the current redacted provider/model config.

    Always includes the global ``[defaults]`` and stored secret *names*. When
    ``project`` is given, also includes that project's ``[provider]`` block.

    Raises:
        WeaverError: When ``project`` is given but no such project exists.
    """

    global_config = load_global_config()
    defaults = global_config.get("defaults", {})
    default_provider = _opt_str(defaults.get("default_provider"))
    default_model = _opt_str(defaults.get("default_model"))

    project_name: str | None = None
    provider_type = model = base_url = api_key_env = None
    if project is not None:
        discovered = find_project(base_dir, project)
        if discovered is None:
            raise ConfigError(
                f"No project named {project!r} under {base_dir}. "
                "Likely cause: wrong name or the project was not created. "
                "Next command: list projects, then retry with an existing name."
            )
        project_name = discovered.name
        provider = load_project_config(discovered.project_toml).get("provider", {})
        provider_type = _opt_str(provider.get("type"))
        model = _opt_str(provider.get("model"))
        base_url = _opt_str(provider.get("base_url"))
        api_key_env = _opt_str(provider.get("api_key_env"))

    return ProviderConfigView(
        default_provider=default_provider,
        default_model=default_model,
        project_name=project_name,
        provider_type=provider_type,
        model=model,
        base_url=base_url,
        api_key_env=api_key_env,
        api_key_set=_key_is_set(api_key_env),
        secret_names=tuple(list_secret_names()),
    )


def write_config(
    base_dir: Path,
    *,
    scope: str,
    project: str | None = None,
    provider_type: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    api_key_env: str | None = None,
) -> ProviderConfigView:
    """Write provider/model config to the project or global scope.

    No key *value* is ever accepted here — only ``api_key_env`` (the env-var
    *name*). Provider type is validated against the live registry by
    ``set_provider``. Returns a fresh redacted view.

    Raises:
        WeaverError: Unknown scope, missing project, unknown provider type, or no
            field supplied.
    """

    if scope not in CONFIG_SCOPES:
        raise ConfigError(
            f"Unknown config scope {scope!r}. "
            f"Likely cause: scope must be one of: {', '.join(CONFIG_SCOPES)}. "
            "Next command: retry with scope=project or scope=global."
        )

    if scope == "global":
        target = default_global_config_path()
    else:
        if project is None:
            raise ConfigError(
                "Project scope requires a project name. "
                "Likely cause: scope=project without a project. "
                "Next command: pass the project name or use scope=global."
            )
        discovered = find_project(base_dir, project)
        if discovered is None:
            raise ConfigError(
                f"No project named {project!r} under {base_dir}. "
                "Likely cause: wrong name or the project was not created. "
                "Next command: list projects, then retry with an existing name."
            )
        target = discovered.project_toml

    set_provider(
        target,
        provider_type=provider_type,
        model=model,
        base_url=base_url,
        api_key_env=api_key_env,
    )
    return read_config(base_dir, project=project if scope == "project" else None)


def store_secret(env_name: str, value: str) -> SecretPresence:
    """Store an API-key secret under env-var name ``env_name`` (value never echoed).

    Raises:
        WeaverError: Invalid env-var name or empty value (from ``set_secret``).
    """

    set_secret(env_name, value)
    return SecretPresence(name=env_name, is_set=True)


def remove_secret(env_name: str) -> SecretPresence:
    """Remove the secret stored under ``env_name``.

    Raises:
        WeaverError: When no such secret exists (so the caller can map to 404).
    """

    removed = delete_secret(env_name)
    if not removed:
        raise SecretNotFoundError(
            f"No stored secret named {env_name!r}. "
            "Likely cause: it was never set or already removed. "
            "Next command: list config to see stored secret names."
        )
    return SecretPresence(name=env_name, is_set=False)


def _opt_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
