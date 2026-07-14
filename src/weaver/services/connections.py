"""Connection orchestration facade (ADR 018 D2/D3/D7, framework-agnostic).

Bridges the connection registry (``core/connection_registry``), the secret store
(``core/secret_store``), and model discovery (``providers/discovery``) so the
cockpit can register, test, list, and remove connections without reaching into
core directly. Holds no web types (CLAUDE.md §4.2).

Key handling is **hybrid** (ADR 018 D7): by default the user types the raw key and
this service derives an env-var name (``WEAVER_CONN_<NAME>``), stores the *value*
in ``secrets.toml``, and records only the *name* on the connection. Power users
may override the env name or point at an existing shell env var. The key value is
never stored on the connection and never returned by this module.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from weaver.core.connection_models import CachedModels, get_cached, load_all, save_cached
from weaver.core.connection_registry import (
    Connection,
    delete_connection,
    get_connection,
    list_connections,
    register_connection,
)
from weaver.core.secret_store import list_secret_names, load_secrets, set_secret
from weaver.errors import ConfigError
from weaver.providers.discovery import DiscoveryResult, list_models

ENV_PREFIX = "WEAVER_CONN_"
_NON_ENV_CHARS = re.compile(r"[^A-Z0-9]+")


@dataclass(frozen=True)
class ConnectionView:
    """Redacted card view of a registered connection. Never carries a key value."""

    name: str
    base_url: str
    default_model: str
    api_key_env: str
    requires_key: bool
    secret_present: bool


def derive_env_name(connection_name: str) -> str:
    """Return the auto env-var name for a connection (``WEAVER_CONN_<NAME>``)."""

    slug = _NON_ENV_CHARS.sub("_", connection_name.strip().upper()).strip("_")
    return f"{ENV_PREFIX}{slug or 'CONNECTION'}"


def add_connection(
    *,
    name: str,
    base_url: str,
    api_key: str | None = None,
    api_key_env: str | None = None,
    use_shell_env: bool = False,
    default_model: str = "",
    requires_key: bool = True,
) -> ConnectionView:
    """Register a connection, storing the key value only when one is supplied.

    Resolution of the key env-var **name**:
    - explicit ``api_key_env`` (Advanced override) wins;
    - otherwise it is derived from ``name`` (``WEAVER_CONN_<NAME>``).

    A raw ``api_key`` value (the default path) is stored in ``secrets.toml`` under
    that name. ``use_shell_env`` records the name without storing a value (the key
    already lives in the shell environment). Keyless endpoints
    (``requires_key=False``) record an empty name and store nothing.

    Raises:
        ConfigError: invalid name/endpoint (from the registry) or a key was
            required but neither typed nor available in the shell env.
    """

    if not requires_key:
        register_connection(
            Connection(
                name=name.strip(),
                base_url=base_url.strip(),
                api_key_env="",
                default_model=default_model.strip(),
                requires_key=False,
            )
        )
        return _view(name.strip())

    env_name = (api_key_env or "").strip() or derive_env_name(name)
    if use_shell_env:
        if not os.environ.get(env_name):
            raise ConfigError(
                f"No value for `{env_name}` in the environment. "
                "Likely cause: 'Use existing shell env var' was chosen but the "
                f"variable is not set. "
                f"Next command: export {env_name}, or type the key instead."
            )
    elif api_key:
        set_secret(env_name, api_key)
    elif not _secret_present(env_name):
        raise ConfigError(
            "This connection needs an API key. "
            "Likely cause: the API Key field was empty and no stored/shell key "
            f"named `{env_name}` exists. "
            "Next command: type the key, or mark the connection as keyless."
        )

    register_connection(
        Connection(
            name=name.strip(),
            base_url=base_url.strip(),
            api_key_env=env_name,
            default_model=default_model.strip(),
            requires_key=True,
        )
    )
    return _view(name.strip())


def probe_connection(
    *,
    base_url: str,
    api_key: str | None = None,
    api_key_env: str | None = None,
    use_shell_env: bool = False,
    name: str = "",
    timeout_seconds: float = 60.0,
    client: object | None = None,
) -> DiscoveryResult:
    """Probe an endpoint (``/v1/models``) to prove connectivity + auth.

    Resolves the key value to use for the probe: a typed ``api_key`` wins;
    otherwise the value is read from the shell env / secret store under the
    resolved env-var name. Raises a typed ``ProviderError`` on failure so the
    caller can render it inline.
    """

    key_value = api_key or _resolve_key_value(
        api_key_env=api_key_env, name=name, use_shell_env=use_shell_env
    )
    return list_models(
        base_url=base_url.strip(),
        api_key=key_value,
        timeout_seconds=timeout_seconds,
        client=client,
    )


def refresh_models(name: str, *, client: object | None = None) -> DiscoveryResult:
    """Probe a saved connection's ``/v1/models`` and cache the snapshot.

    Explicit-POST only (Test / Refresh / Load models) — never on render. Raises
    a typed ``ProviderError`` on probe failure (the cache is left untouched).
    """

    conn = get_connection(name)
    if conn is None:
        raise ConfigError(
            f"No connection named {name!r}. "
            "Likely cause: it was renamed or deleted. "
            "Next command: open Connections and pick an existing one."
        )
    result = probe_connection(
        base_url=conn.base_url,
        api_key_env=conn.api_key_env or None,
        name=conn.name,
        timeout_seconds=conn.timeout_seconds,
        client=client,
    )
    save_cached(name, result.models)
    return result


def cached_models(name: str) -> CachedModels | None:
    """Return the last cached model snapshot for a connection (no probe)."""

    return get_cached(name)


def all_cached_models() -> dict[str, CachedModels]:
    """Return every connection's cached model snapshot (no probe, Gate B1)."""

    return load_all()


def list_connection_views() -> list[ConnectionView]:
    """Return card views for all registered connections (no provider call)."""

    # Parse secrets.toml once for the whole render instead of once per
    # connection (the previous `_secret_present` per card re-parsed the file).
    secret_names = set(list_secret_names())
    return [_to_view(conn, secret_names=secret_names) for conn in list_connections()]


def remove_connection(name: str) -> bool:
    """Remove a connection (its stored secret, if any, is left in place)."""

    return delete_connection(name)


def _resolve_key_value(*, api_key_env: str | None, name: str, use_shell_env: bool) -> str:
    env_name = (api_key_env or "").strip() or (derive_env_name(name) if name else "")
    if not env_name:
        return ""
    if use_shell_env:
        return os.environ.get(env_name, "")
    return os.environ.get(env_name) or load_secrets().get(env_name, "")


def _secret_present(env_name: str, *, secret_names: set[str] | None = None) -> bool:
    if not env_name:
        return False
    # ``secret_names`` lets a bulk caller (``list_connection_views``) pass a
    # single pre-parsed set instead of re-reading secrets.toml per connection.
    stored = (
        env_name in secret_names if secret_names is not None else env_name in list_secret_names()
    )
    return stored or bool(os.environ.get(env_name))


def _to_view(conn: Connection, *, secret_names: set[str] | None = None) -> ConnectionView:
    return ConnectionView(
        name=conn.name,
        base_url=conn.base_url,
        default_model=conn.default_model,
        api_key_env=conn.api_key_env,
        requires_key=conn.requires_key,
        secret_present=(not conn.requires_key)
        or _secret_present(conn.api_key_env, secret_names=secret_names),
    )


def _view(name: str) -> ConnectionView:
    conn = get_connection(name)
    if conn is None:  # pragma: no cover — just registered
        raise ConfigError(f"Connection {name!r} could not be read back after save.")
    return _to_view(conn)
