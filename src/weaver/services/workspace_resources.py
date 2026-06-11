"""Read-only cross-project Resources hub.

Aggregates glossary term, character, and translation-memory counts from every
project under a books directory.  Uses ``connect_readonly_database`` exclusively
— never migrates, never resets ``in_progress``, never hashes source files, and
never calls a provider.
"""

from __future__ import annotations

import sqlite3
import time
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from weaver.errors import WeaverError
from weaver.services.project_discovery import discover_projects
from weaver.storage.db import connect_readonly_database


@dataclass(frozen=True)
class ProjectResourceSummary:
    """Read-only resource summary for one project."""

    project_name: str
    project_uuid: str | None
    state: str  # ready | needs_upgrade | locked | error | identity_conflict
    error: str | None
    glossary_term_count: int
    character_count: int
    memory_entry_count: int
    memory_reuse_count: int
    prompt_template_count: int | None  # None = not yet implemented
    style_guide_count: int | None  # None = not yet implemented


@dataclass(frozen=True)
class ResourceDegradedProject:
    """A project that could not be read — rendered as a degraded row."""

    name: str
    uuid: str | None
    state: str  # locked | missing | needs_upgrade | identity_conflict | error
    error: str | None


@dataclass(frozen=True)
class WorkspaceResources:
    """Result of a workspace resources build."""

    projects: list[ProjectResourceSummary]
    degraded: list[ResourceDegradedProject]
    generated_at: float


@dataclass(frozen=True)
class _ProjectResourcesState:
    """Internal accumulator for one project."""

    summary: ProjectResourceSummary | None
    degraded: ResourceDegradedProject | None


def build_workspace_resources(books_dir: Path) -> WorkspaceResources:
    """Build a read-only cross-project resource summary.

    Args:
        books_dir: Root directory containing ``.weaver/<name>/`` projects.

    Returns:
        A :class:`WorkspaceResources` with one summary per discovered project.
        Broken projects appear in ``degraded`` — one bad project never blanks
        the hub.
    """
    discovered = discover_projects(books_dir)
    projects: list[ProjectResourceSummary] = []
    degraded: list[ResourceDegradedProject] = []

    for project in discovered:
        result = _resources_for_project(project)
        if result.degraded is not None:
            degraded.append(result.degraded)
        elif result.summary is not None:
            projects.append(result.summary)

    projects.sort(key=lambda p: p.project_name.lower())

    return WorkspaceResources(
        projects=projects,
        degraded=degraded,
        generated_at=time.time(),
    )


def _resources_for_project(
    discovered: object,
) -> _ProjectResourcesState:
    """Resolve resource counts for a single discovered project."""

    name: str = getattr(discovered, "name", "?")
    uuid: str | None = None
    summary = getattr(discovered, "summary", None)
    if summary is not None:
        uuid = getattr(summary, "uuid", None)

    # Discovery-level errors
    error = getattr(discovered, "error", None)
    if error is not None:
        return _ProjectResourcesState(
            summary=None,
            degraded=ResourceDegradedProject(
                name=name,
                uuid=uuid,
                state="error",
                error=str(error),
            ),
        )

    if summary is None:
        return _ProjectResourcesState(
            summary=None,
            degraded=ResourceDegradedProject(
                name=name, uuid=uuid, state="error", error="Missing project summary."
            ),
        )

    schema_version = getattr(summary, "schema_version", 0)

    # Schema too old to trust column access
    if schema_version < 10:
        return _ProjectResourcesState(
            summary=None,
            degraded=ResourceDegradedProject(
                name=name, uuid=uuid, state="needs_upgrade", error=None
            ),
        )

    base_state = "identity_conflict" if getattr(discovered, "identity_conflict", False) else "ready"
    project_toml_raw = getattr(discovered, "project_toml", None)
    if project_toml_raw is None or not isinstance(project_toml_raw, Path):
        return _ProjectResourcesState(
            summary=None,
            degraded=ResourceDegradedProject(
                name=name, uuid=uuid, state="error", error="Missing project.toml path."
            ),
        )
    project_toml: Path = project_toml_raw

    db_path = project_toml.parent / "weaver.db"

    try:
        with closing(connect_readonly_database(db_path)) as connection:
            guid = _load_project_uuid(connection)
            counts = _read_resource_counts(connection)
    except (WeaverError, sqlite3.Error) as exc:
        return _ProjectResourcesState(
            summary=None,
            degraded=ResourceDegradedProject(
                name=name,
                uuid=uuid,
                state="error",
                error=str(exc),
            ),
        )

    summary_obj = ProjectResourceSummary(
        project_name=name,
        project_uuid=guid,
        state=base_state,
        error=None,
        glossary_term_count=counts["glossary_terms"],
        character_count=counts["characters"],
        memory_entry_count=counts["translation_memory"],
        memory_reuse_count=counts["memory_reuses"],
        prompt_template_count=None,
        style_guide_count=None,
    )

    if base_state == "identity_conflict":
        return _ProjectResourcesState(
            summary=None,
            degraded=ResourceDegradedProject(
                name=name, uuid=guid, state="identity_conflict", error=None
            ),
        )

    return _ProjectResourcesState(summary=summary_obj, degraded=None)


def _load_project_uuid(connection: sqlite3.Connection) -> str | None:
    """Read the project UUID from a readonly connection (schema >= 10)."""
    row = connection.execute("SELECT uuid FROM projects ORDER BY id LIMIT 1").fetchone()
    if row is not None and row["uuid"] is not None:
        return str(row["uuid"])
    return None


def _read_resource_counts(connection: sqlite3.Connection) -> dict[str, int]:
    """Return resource table counts from a readonly connection."""

    glossary_terms = _count(connection, "glossary_terms")
    characters = _count(connection, "characters")
    translation_memory = _count(connection, "translation_memory")

    reuse_row = connection.execute(
        "SELECT COUNT(*) AS count FROM translations WHERE provider = 'memory'"
    ).fetchone()
    memory_reuses = int(reuse_row["count"]) if reuse_row is not None else 0

    return {
        "glossary_terms": glossary_terms,
        "characters": characters,
        "translation_memory": translation_memory,
        "memory_reuses": memory_reuses,
    }


def _count(connection: sqlite3.Connection, table_name: str) -> int:
    row = connection.execute(f"SELECT COUNT(*) AS count FROM {table_name}").fetchone()
    return int(row["count"])
