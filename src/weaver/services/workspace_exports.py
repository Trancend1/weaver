"""Read-only export-history read layer (Sprint Q7 / WV-009).

Two read surfaces over the ``export_history`` ledger:

- :func:`build_workspace_exports` — the cross-project Exports hub. Leak rule
  (R-03/R-05): the global hub exposes only the artifact **basename**, never the
  absolute path of another project's output dir.
- :func:`list_project_exports` — a single project's history, which may show the
  full path (it is the user's own output directory).

Both use ``connect_readonly_database`` exclusively — never migrate, never reset
``in_progress``, never hash source files, never call a provider. Artifact
presence is a cheap ``stat`` (``exists``), never a byte read.
"""

from __future__ import annotations

import sqlite3
import time
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from weaver.errors import WeaverError
from weaver.services.project_discovery import discover_projects, find_project
from weaver.storage.db import connect_readonly_database
from weaver.storage.export_history import list_export_history

_RECENT_PER_PROJECT = 20
_HUB_LIMIT = 100


@dataclass(frozen=True)
class ExportHubRow:
    """One cross-project export-history row (leak-safe: basename only)."""

    project_name: str
    project_uuid: str | None
    format: str
    kind: str
    status: str
    qa_badge: str | None
    artifact_basename: str | None
    byte_size: int | None
    exists: bool
    created_at: str


@dataclass(frozen=True)
class ProjectExportRow:
    """One per-project export-history row (full path; user's own output)."""

    id: str
    volume_id: int | None
    format: str
    kind: str
    status: str
    qa_badge: str | None
    artifact_path: str | None
    byte_size: int | None
    exists: bool
    version_label: str | None
    created_at: str


@dataclass(frozen=True)
class ExportDegradedProject:
    """A project that could not be read — rendered as a degraded row."""

    name: str
    uuid: str | None
    state: str
    error: str | None


@dataclass(frozen=True)
class WorkspaceExports:
    """Result of a cross-project exports build."""

    rows: list[ExportHubRow]
    degraded: list[ExportDegradedProject]
    generated_at: float


@dataclass(frozen=True)
class _ProjectExportsState:
    rows: list[ExportHubRow]
    degraded: ExportDegradedProject | None


def build_workspace_exports(books_dir: Path) -> WorkspaceExports:
    """Build a read-only cross-project export-history summary (newest first)."""

    discovered = discover_projects(books_dir)
    all_rows: list[ExportHubRow] = []
    degraded: list[ExportDegradedProject] = []

    for project in discovered:
        result = _exports_for_project(project)
        if result.degraded is not None:
            degraded.append(result.degraded)
        all_rows.extend(result.rows)

    all_rows.sort(key=lambda r: r.created_at, reverse=True)
    return WorkspaceExports(
        rows=all_rows[:_HUB_LIMIT],
        degraded=degraded,
        generated_at=time.time(),
    )


def _exports_for_project(project: Any) -> _ProjectExportsState:
    """Resolve recent export-history rows for one discovered project."""

    name: str = getattr(project, "name", "?")
    summary = getattr(project, "summary", None)
    uuid: str | None = getattr(summary, "uuid", None) if summary is not None else None

    error = getattr(project, "error", None)
    if error is not None:
        return _ProjectExportsState([], ExportDegradedProject(name, uuid, "error", str(error)))

    if summary is None:
        return _ProjectExportsState(
            [], ExportDegradedProject(name, uuid, "error", "Missing project summary.")
        )

    if getattr(summary, "schema_version", 0) < 11:
        return _ProjectExportsState([], ExportDegradedProject(name, uuid, "needs_upgrade", None))

    if getattr(project, "identity_conflict", False):
        return _ProjectExportsState(
            [], ExportDegradedProject(name, uuid, "identity_conflict", None)
        )

    project_toml = getattr(project, "project_toml", None)
    if not isinstance(project_toml, Path):
        return _ProjectExportsState(
            [], ExportDegradedProject(name, uuid, "error", "Missing project.toml path.")
        )

    db_path = project_toml.parent / "weaver.db"
    rows: list[ExportHubRow] = []
    try:
        with closing(connect_readonly_database(db_path)) as connection:
            history = list_export_history(connection, limit=_RECENT_PER_PROJECT)
    except (WeaverError, sqlite3.Error) as exc:
        return _ProjectExportsState([], ExportDegradedProject(name, uuid, "error", str(exc)))

    for row in history:
        basename = Path(row.artifact_path).name if row.artifact_path else None
        rows.append(
            ExportHubRow(
                project_name=name,
                project_uuid=uuid,
                format=row.format,
                kind=row.kind,
                status=row.status,
                qa_badge=row.qa_badge,
                artifact_basename=basename,
                byte_size=row.byte_size,
                exists=_artifact_exists(row.artifact_path),
                created_at=row.created_at,
            )
        )
    return _ProjectExportsState(rows, None)


def list_project_exports(
    project_toml: Path, *, cwd: Path | None = None, limit: int = _RECENT_PER_PROJECT
) -> list[ProjectExportRow]:
    """Return one project's export history (full path; with ``exists`` flag)."""

    base = cwd or Path.cwd()
    db_path = project_toml.parent / "weaver.db"
    if not db_path.exists():
        db_path = base / ".weaver" / project_toml.parent.name / "weaver.db"
    with closing(connect_readonly_database(db_path)) as connection:
        history = list_export_history(connection, limit=limit)
    return [
        ProjectExportRow(
            id=row.id,
            volume_id=row.volume_id,
            format=row.format,
            kind=row.kind,
            status=row.status,
            qa_badge=row.qa_badge,
            artifact_path=row.artifact_path,
            byte_size=row.byte_size,
            exists=_artifact_exists(row.artifact_path),
            version_label=row.version_label,
            created_at=row.created_at,
        )
        for row in history
    ]


def project_export_history(
    books_dir: Path, name: str, *, limit: int = _RECENT_PER_PROJECT
) -> list[ProjectExportRow]:
    """Resolve a project by name under ``books_dir`` and return its history."""

    dp = find_project(books_dir, name)
    if dp is None or dp.error:
        return []
    return list_project_exports(dp.project_toml, cwd=books_dir, limit=limit)


def _artifact_exists(artifact_path: str | None) -> bool:
    if not artifact_path:
        return False
    try:
        return Path(artifact_path).is_file()
    except OSError:
        return False
