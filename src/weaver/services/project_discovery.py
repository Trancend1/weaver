"""Project discovery: scan a books directory for Weaver projects.

Lists every ``.weaver/<name>/project.toml`` under a root directory and returns
read-only status summaries. Used by the web cockpit dashboard (Phase 12a) so a
user never types a project path; reusable by a future CLI ``--active`` flag.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from weaver.errors import WeaverError
from weaver.services.project import InspectSummary, inspect_project


@dataclass(frozen=True)
class DiscoveredProject:
    """One project found under a books directory.

    Exactly one of ``summary`` / ``error`` is populated: ``summary`` when the
    project's ``project.toml`` and database read cleanly, ``error`` (a
    user-facing message) when the read failed.
    """

    name: str
    project_toml: Path
    summary: InspectSummary | None
    error: str | None


def discover_projects(books_dir: Path) -> list[DiscoveredProject]:
    """Find all Weaver projects under ``books_dir/.weaver``.

    Args:
        books_dir: Root directory the cockpit was launched against.

    Returns:
        Discovered projects sorted by name. Projects whose state cannot be read
        are included with ``summary=None`` and a populated ``error`` so the
        dashboard can surface them instead of silently dropping them.
    """

    weaver_dir = books_dir / ".weaver"
    if not weaver_dir.is_dir():
        return []

    discovered: list[DiscoveredProject] = []
    for project_toml in sorted(weaver_dir.glob("*/project.toml")):
        name = project_toml.parent.name
        try:
            summary = inspect_project(project_toml, cwd=books_dir)
        except WeaverError as exc:
            discovered.append(
                DiscoveredProject(
                    name=name,
                    project_toml=project_toml,
                    summary=None,
                    error=str(exc),
                )
            )
            continue
        discovered.append(
            DiscoveredProject(
                name=name,
                project_toml=project_toml,
                summary=summary,
                error=None,
            )
        )
    return discovered


def find_project(books_dir: Path, name: str) -> DiscoveredProject | None:
    """Return a single discovered project by directory name, or None.

    Args:
        books_dir: Root directory the cockpit was launched against.
        name: The ``.weaver/<name>`` directory name.

    Returns:
        The matching DiscoveredProject, or None when no such project exists.
    """

    project_toml = books_dir / ".weaver" / name / "project.toml"
    if not project_toml.is_file():
        return None
    try:
        summary = inspect_project(project_toml, cwd=books_dir)
    except WeaverError as exc:
        return DiscoveredProject(
            name=name,
            project_toml=project_toml,
            summary=None,
            error=str(exc),
        )
    return DiscoveredProject(
        name=name,
        project_toml=project_toml,
        summary=summary,
        error=None,
    )
