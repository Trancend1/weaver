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
    identity_conflict: bool = False


def discover_projects(books_dir: Path) -> list[DiscoveredProject]:
    """Find all Weaver projects under ``books_dir/.weaver``.

    Args:
        books_dir: Root directory the cockpit was launched against.

    Returns:
        Discovered projects sorted by name. Projects whose state cannot be read
        are included with ``summary=None`` and a populated ``error`` so the
        dashboard can surface them instead of silently dropping them.
        Duplicate uuids caused by directory copies are flagged with
        ``identity_conflict=True`` on all colliding entries.
    """

    weaver_dir = books_dir / ".weaver"
    if not weaver_dir.is_dir():
        return []

    raw: list[DiscoveredProject] = []
    for project_toml in sorted(weaver_dir.glob("*/project.toml")):
        name = project_toml.parent.name
        try:
            summary = inspect_project(project_toml, cwd=books_dir)
        except WeaverError as exc:
            raw.append(
                DiscoveredProject(
                    name=name,
                    project_toml=project_toml,
                    summary=None,
                    error=str(exc),
                )
            )
            continue
        raw.append(
            DiscoveredProject(
                name=name,
                project_toml=project_toml,
                summary=summary,
                error=None,
            )
        )

    return _flag_duplicate_uuids(raw)


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


def find_project_by_uuid(books_dir: Path, project_uuid: str) -> DiscoveredProject | None:
    """Return a discovered project by its stable uuid, or None.

    Args:
        books_dir: Root directory the cockpit was launched against.
        project_uuid: The project's stable uuid.

    Returns:
        The matching DiscoveredProject, or None.

    Raises:
        ValueError: If more than one project shares the same uuid (duplicate
            identity). Callers should surface this as an error.
    """

    weaver_dir = books_dir / ".weaver"
    if not weaver_dir.is_dir():
        return None

    matches: list[DiscoveredProject] = []
    for project_toml in sorted(weaver_dir.glob("*/project.toml")):
        name = project_toml.parent.name
        try:
            summary = inspect_project(project_toml, cwd=books_dir)
        except WeaverError:
            continue
        if summary is not None and summary.uuid == project_uuid:
            matches.append(
                DiscoveredProject(
                    name=name,
                    project_toml=project_toml,
                    summary=summary,
                    error=None,
                )
            )

    if len(matches) > 1:
        raise ValueError(
            f"Duplicate project identity: uuid {project_uuid} found in "
            f"{', '.join(m.name for m in matches)}. "
            "Likely cause: directory copy. "
            "Next command: resolve the conflict by removing the copied project."
        )
    return matches[0] if matches else None


def _flag_duplicate_uuids(projects: list[DiscoveredProject]) -> list[DiscoveredProject]:
    """Flag projects whose uuid collides with another entry.

    Returns a new list where every colliding entry has
    ``identity_conflict=True``.
    """

    uuid_to_indices: dict[str, list[int]] = {}
    for idx, proj in enumerate(projects):
        if proj.summary is not None and proj.summary.uuid is not None:
            uuid_to_indices.setdefault(proj.summary.uuid, []).append(idx)

    conflict_indices = {
        idx for indices in uuid_to_indices.values() if len(indices) > 1 for idx in indices
    }

    result: list[DiscoveredProject] = []
    for idx, proj in enumerate(projects):
        if idx in conflict_indices:
            result.append(
                DiscoveredProject(
                    name=proj.name,
                    project_toml=proj.project_toml,
                    summary=proj.summary,
                    error=proj.error,
                    identity_conflict=True,
                )
            )
        else:
            result.append(proj)
    return result
