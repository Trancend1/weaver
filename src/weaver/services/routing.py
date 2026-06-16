"""Per-task AI routing resolver (ADR 018 D4/D7, framework-agnostic).

Resolves which connection + model a project uses for a given task. A project may
declare ``[routing.<task>]`` (``connection`` + ``model``) pointing at a registered
workspace connection; precedence falls back to the legacy ``[provider]`` block so
projects that never opt in behave exactly as before.

Pure (no web/CLI types). The translate pipeline calls
:func:`resolve_provider_config` (single engine) and :func:`resolve_chain`
(primary + simple per-segment fallback, ADR 018 D4); the cockpit calls
:func:`resolve_active_ai` to show the Active AI.

Precedence for a task: ``[routing.<task>]`` → legacy ``[provider]`` → workspace
``[defaults].default_connection``. No circuit breaker / health-score (D9): the
chain is just primary + ordered fallbacks the caller tries in turn.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from weaver.core.config import load_project_config
from weaver.core.connection_registry import get_connection
from weaver.core.global_config import load_global_config
from weaver.core.task_types import TaskType
from weaver.errors import ConfigError
from weaver.providers.registry import normalize_provider_config


@dataclass(frozen=True)
class ActiveAI:
    """The resolved AI for a project + task, for display in the cockpit."""

    model: str
    connection_name: str | None
    source: str  # "routing" | "provider" | "unset"
    connection_exists: bool


@dataclass(frozen=True)
class Candidate:
    """One engine the pipeline can try for a segment (primary or a fallback)."""

    provider_config: dict[str, Any]
    connection_name: str | None
    model: str


def _routing_entry(data: dict[str, Any], task: TaskType) -> dict[str, Any]:
    routing = data.get("routing")
    if not isinstance(routing, dict):
        return {}
    entry = routing.get(task.value)
    return entry if isinstance(entry, dict) else {}


def _connection_config(task: TaskType, connection_name: str, model: str | None) -> dict[str, Any]:
    """Resolve a registered connection into a ``build_provider`` config dict."""

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
        "model": model or connection.default_model,
    }


def _defaults_config(task: TaskType) -> dict[str, Any] | None:
    """Resolve the workspace ``[defaults].default_connection``, or None when unset."""

    defaults = load_global_config().get("defaults", {})
    if not isinstance(defaults, dict):
        return None
    connection_name = _clean(defaults.get("default_connection"))
    if connection_name is None:
        return None
    return _connection_config(task, connection_name, _clean(defaults.get("default_model")))


def resolve_provider_config(
    project_toml: Path, task: TaskType, *, data: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Return the provider-config dict for ``task`` (feed to ``build_provider``).

    Precedence: ``[routing.<task>]`` connection → legacy ``[provider]`` (when it
    carries a model) → workspace ``[defaults].default_connection``.

    Raises:
        ConfigError: when a named connection (routing or default) is not
            registered — a clear, actionable failure, never a silent fallback.
    """

    data = data if data is not None else load_project_config(project_toml)
    entry = _routing_entry(data, task)
    connection_name = _clean(entry.get("connection"))
    if connection_name is not None:
        return _connection_config(task, connection_name, _clean(entry.get("model")))

    provider = data.get("provider")
    if isinstance(provider, dict) and _clean(provider.get("model")):
        return dict(provider)

    defaults_config = _defaults_config(task)
    if defaults_config is not None:
        return defaults_config
    return dict(provider) if isinstance(provider, dict) else {}


def resolve_consumer_config(
    project_toml: Path, task: TaskType, *, data: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Resolve a secondary on-demand task (``glossary_suggest``, ``candidate``).

    Same precedence as :func:`resolve_provider_config`, but when the task has no
    ``[routing.<task>]`` entry and no legacy ``[provider]`` model, it inherits the
    project's ``translate`` Active AI. So a connection-first project (its model
    set under ``[routing.translate]``, an empty ``[provider]``) drives these
    consumers too, without configuring each task separately — matching the task
    taxonomy's note that these are existing consumers of the project's AI.

    Raises:
        ConfigError: when a named connection in the resolved chain is not
            registered (never a silent fallback).
    """

    data = data if data is not None else load_project_config(project_toml)
    config = resolve_provider_config(project_toml, task, data=data)
    if _clean(config.get("model")):
        return config
    return resolve_provider_config(project_toml, TaskType.translate, data=data)


def resolve_chain(
    project_toml: Path, task: TaskType, *, data: dict[str, Any] | None = None
) -> list[Candidate]:
    """Return the primary engine followed by any ``[routing.<task>].fallback``.

    The fallback is an array of ``{connection, model}`` inline tables. An entry
    naming an unknown connection is **skipped** (a fallback is best-effort; the
    primary still translates) — only the primary raises on an unknown connection.
    """

    data = data if data is not None else load_project_config(project_toml)
    primary = resolve_provider_config(project_toml, task, data=data)
    chain = [Candidate(primary, _clean(primary.get("type")), str(primary.get("model", "")))]

    entry = _routing_entry(data, task)
    fallback = entry.get("fallback")
    if isinstance(fallback, list):
        for item in fallback:
            if not isinstance(item, dict):
                continue
            name = _clean(item.get("connection"))
            if name is None or get_connection(name) is None:
                continue
            config = _connection_config(task, name, _clean(item.get("model")))
            chain.append(Candidate(config, name, str(config.get("model", ""))))
    return chain


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
    if isinstance(provider, dict) and provider:
        # Normalize so a legacy brand alias (e.g. type=deepseek) still surfaces its
        # shim model ("deepseek-chat") instead of an empty raw field.
        model = _clean(normalize_provider_config(provider).get("model"))
        if model is not None:
            return ActiveAI(
                model=model, connection_name=None, source="provider", connection_exists=True
            )
    return ActiveAI(model="—", connection_name=None, source="unset", connection_exists=True)


def _clean(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
