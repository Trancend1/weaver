"""Per-task AI routing resolver (ADR 018 D4/D7, framework-agnostic).

Resolves which connection + model a project uses for a given task. A project may
declare ``[routing.<task>]`` (``connection`` + ``model``) pointing at a registered
workspace connection; precedence falls back to the legacy ``[provider]`` block so
projects that never opt in behave exactly as before.

Pure (no web/CLI types). The translate pipeline calls
:func:`resolve_provider_config` to pick the engine; the cockpit calls
:func:`resolve_active_ai` to show the Active AI. Simple per-segment fallback chains
are a later step (ADR 018 D4) — this module resolves a single active engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from weaver.core.config import load_project_config
from weaver.core.connection_registry import get_connection
from weaver.core.task_types import TaskType
from weaver.errors import ConfigError


@dataclass(frozen=True)
class ActiveAI:
    """The resolved AI for a project + task, for display in the cockpit."""

    model: str
    connection_name: str | None
    source: str  # "routing" | "provider" | "unset"
    connection_exists: bool


def _routing_entry(data: dict[str, Any], task: TaskType) -> dict[str, Any]:
    routing = data.get("routing")
    if not isinstance(routing, dict):
        return {}
    entry = routing.get(task.value)
    return entry if isinstance(entry, dict) else {}


def resolve_provider_config(
    project_toml: Path, task: TaskType, *, data: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Return the provider-config dict for ``task`` (feed to ``build_provider``).

    ``[routing.<task>]`` → the named workspace connection (model from the routing
    entry, else the connection's ``default_model``). No routing entry → the legacy
    ``[provider]`` block, unchanged.

    Raises:
        ConfigError: when the routing entry names a connection that is not
            registered (a clear, actionable failure — never a silent fallback).
    """

    data = data if data is not None else load_project_config(project_toml)
    entry = _routing_entry(data, task)
    connection_name = _clean(entry.get("connection"))
    if connection_name is None:
        return dict(data.get("provider") or {})

    connection = get_connection(connection_name)
    if connection is None:
        raise ConfigError(
            f"Routing for `{task.value}` points at unknown connection "
            f"`{connection_name}`. "
            "Likely cause: the connection was renamed or deleted. "
            "Next command: open Connections and pick an existing connection, or "
            "re-add it."
        )
    return {
        "type": connection.name,
        "protocol": connection.protocol,
        "base_url": connection.base_url,
        "api_key_env": connection.api_key_env,
        "model": _clean(entry.get("model")) or connection.default_model,
    }


def resolve_active_ai(
    project_toml: Path, task: TaskType, *, data: dict[str, Any] | None = None
) -> ActiveAI:
    """Return the Active AI (connection + model) for ``task`` for display."""

    data = data if data is not None else load_project_config(project_toml)
    entry = _routing_entry(data, task)
    connection_name = _clean(entry.get("connection"))
    if connection_name is not None:
        connection = get_connection(connection_name)
        model = _clean(entry.get("model")) or (connection.default_model if connection else "")
        return ActiveAI(
            model=model or "—",
            connection_name=connection_name,
            source="routing",
            connection_exists=connection is not None,
        )

    provider = data.get("provider")
    model = _clean(provider.get("model")) if isinstance(provider, dict) else None
    if model is None:
        return ActiveAI(model="—", connection_name=None, source="unset", connection_exists=True)
    return ActiveAI(model=model, connection_name=None, source="provider", connection_exists=True)


def _clean(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
