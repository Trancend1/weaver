"""Read-only cross-project Providers hub (Sprint Q6).

Summarises, per project, which provider/model is configured, whether its API
key is present (by env-var **name** only — values are never read), recent job
failures, and token consumption.  Uses ``connect_readonly_database`` and
``load_project_config`` exclusively — never migrates, never resets
``in_progress``, never hashes source files, and **never instantiates or calls a
provider** (health checks are an explicit, on-demand action in the router).
"""

from __future__ import annotations

import os
import sqlite3
import time
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from weaver.core.config import load_project_config
from weaver.core.secret_store import list_secret_names
from weaver.errors import WeaverError
from weaver.providers.deepseek import ENV_API_KEY as DEEPSEEK_ENV
from weaver.providers.gemini import ENV_API_KEY as GEMINI_ENV
from weaver.services.project_discovery import discover_projects
from weaver.storage.db import connect_readonly_database

_RECENT_FAILURES_PER_PROJECT = 5

# Canonical env-var name per built-in provider type.  ``custom`` reads its own
# ``api_key_env`` from project.toml; ``ollama``/``fake`` need no key.
_KEY_ENV_BY_TYPE: dict[str, str] = {
    "deepseek": DEEPSEEK_ENV,
    "gemini": GEMINI_ENV,
}
_KEYLESS_TYPES = frozenset({"ollama", "fake"})


@dataclass(frozen=True)
class ProviderFailure:
    """One recent failed job, for the recent-failures list (key-free)."""

    job_id: str
    kind: str
    error_summary: str | None
    finished_at: str | None


@dataclass(frozen=True)
class ProjectProviderSummary:
    """Read-only provider configuration + usage summary for one project."""

    project_name: str
    project_uuid: str | None
    state: str  # ready
    provider_type: str
    model: str
    api_key_env: str | None  # env-var NAME only — never a value
    requires_key: bool
    secret_present: bool
    input_tokens: int
    output_tokens: int
    failed_job_count: int
    recent_failures: list[ProviderFailure]


@dataclass(frozen=True)
class ProviderDegradedProject:
    """A project that could not be read — rendered as a degraded row."""

    name: str
    uuid: str | None
    state: str  # locked | missing | needs_upgrade | identity_conflict | error
    error: str | None


@dataclass(frozen=True)
class WorkspaceProviders:
    """Result of a workspace providers build."""

    projects: list[ProjectProviderSummary]
    degraded: list[ProviderDegradedProject]
    generated_at: float


@dataclass(frozen=True)
class _ProjectProviderState:
    """Internal accumulator for one project."""

    summary: ProjectProviderSummary | None
    degraded: ProviderDegradedProject | None


def build_workspace_providers(books_dir: Path) -> WorkspaceProviders:
    """Build a read-only cross-project provider summary.

    Args:
        books_dir: Root directory containing ``.weaver/<name>/`` projects.

    Returns:
        A :class:`WorkspaceProviders` with one summary per discovered project.
        Broken projects appear in ``degraded`` — one bad project never blanks
        the hub.  No provider is ever instantiated or called.
    """
    discovered = discover_projects(books_dir)
    stored_secrets = set(list_secret_names())
    projects: list[ProjectProviderSummary] = []
    degraded: list[ProviderDegradedProject] = []

    for project in discovered:
        result = _providers_for_project(project, stored_secrets=stored_secrets)
        if result.degraded is not None:
            degraded.append(result.degraded)
        if result.summary is not None:
            projects.append(result.summary)

    projects.sort(key=lambda p: p.project_name.lower())

    return WorkspaceProviders(
        projects=projects,
        degraded=degraded,
        generated_at=time.time(),
    )


def _providers_for_project(
    project: Any,
    *,
    stored_secrets: set[str],
) -> _ProjectProviderState:
    """Resolve provider config + usage for a single discovered project."""

    name: str = getattr(project, "name", "?")
    summary = getattr(project, "summary", None)
    uuid: str | None = getattr(summary, "uuid", None) if summary is not None else None

    error = getattr(project, "error", None)
    if error is not None:
        return _degraded(name, uuid, "error", str(error))

    if summary is None:
        return _degraded(name, uuid, "error", "Missing project summary.")

    schema_version = getattr(summary, "schema_version", 0)
    if schema_version < 10:
        return _degraded(name, uuid, "needs_upgrade", None)

    if getattr(project, "identity_conflict", False):
        return _degraded(name, uuid, "identity_conflict", None)

    project_toml = getattr(project, "project_toml", None)
    if not isinstance(project_toml, Path):
        return _degraded(name, uuid, "error", "Missing project.toml path.")

    try:
        config = load_project_config(project_toml)
        provider_cfg = config.get("provider", {})
        provider_type = str(provider_cfg.get("type", "")) or "unknown"
        model = str(provider_cfg.get("model", "")) or "—"
        api_key_env = _resolve_key_env(provider_type, provider_cfg)
    except WeaverError as exc:
        return _degraded(name, uuid, "error", str(exc))

    db_path = project_toml.parent / "weaver.db"
    try:
        with closing(connect_readonly_database(db_path)) as connection:
            tokens = _read_token_totals(connection)
            failed_count, recent = _read_failures(connection)
    except (WeaverError, sqlite3.Error) as exc:
        return _degraded(name, uuid, "error", str(exc))

    requires_key = api_key_env is not None
    secret_present = bool(api_key_env) and (
        api_key_env in os.environ or api_key_env in stored_secrets
    )

    return _ProjectProviderState(
        summary=ProjectProviderSummary(
            project_name=name,
            project_uuid=uuid,
            state="ready",
            provider_type=provider_type,
            model=model,
            api_key_env=api_key_env,
            requires_key=requires_key,
            secret_present=secret_present,
            input_tokens=tokens[0],
            output_tokens=tokens[1],
            failed_job_count=failed_count,
            recent_failures=recent,
        ),
        degraded=None,
    )


def _resolve_key_env(provider_type: str, provider_cfg: dict[str, Any]) -> str | None:
    """Return the env-var NAME the provider expects, or None for keyless types."""

    if provider_type in _KEYLESS_TYPES:
        return None
    if provider_type == "custom":
        env = str(provider_cfg.get("api_key_env", "")).strip()
        return env or None
    return _KEY_ENV_BY_TYPE.get(provider_type)


def _read_token_totals(connection: sqlite3.Connection) -> tuple[int, int]:
    """Return (input_tokens, output_tokens) summed over all translation attempts."""

    row = connection.execute(
        "SELECT COALESCE(SUM(input_tokens), 0) AS input_total, "
        "COALESCE(SUM(output_tokens), 0) AS output_total FROM translations"
    ).fetchone()
    if row is None:
        return (0, 0)
    return (int(row["input_total"]), int(row["output_total"]))


def _read_failures(
    connection: sqlite3.Connection,
) -> tuple[int, list[ProviderFailure]]:
    """Return total failed-job count and the most recent failures (key-free)."""

    count_row = connection.execute(
        "SELECT COUNT(*) AS count FROM jobs WHERE status = 'failed'"
    ).fetchone()
    failed_count = int(count_row["count"]) if count_row is not None else 0

    recent: list[ProviderFailure] = []
    for row in connection.execute(
        "SELECT id, kind, error_summary, finished_at FROM jobs "
        "WHERE status = 'failed' ORDER BY finished_at DESC, id DESC LIMIT ?",
        (_RECENT_FAILURES_PER_PROJECT,),
    ).fetchall():
        err = row["error_summary"]
        fin = row["finished_at"]
        recent.append(
            ProviderFailure(
                job_id=str(row["id"]),
                kind=str(row["kind"]),
                error_summary=str(err) if err is not None else None,
                finished_at=str(fin) if fin is not None else None,
            )
        )
    return failed_count, recent


def _degraded(name: str, uuid: str | None, state: str, error: str | None) -> _ProjectProviderState:
    return _ProjectProviderState(
        summary=None,
        degraded=ProviderDegradedProject(name=name, uuid=uuid, state=state, error=error),
    )
