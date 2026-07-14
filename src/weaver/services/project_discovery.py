"""Project discovery: scan a books directory for Weaver projects.

Lists every ``.weaver/<name>/project.toml`` under a root directory and returns
read-only status summaries. Used by the web cockpit dashboard (Phase 12a) so a
user never types a project path; reusable by a future CLI ``--active`` flag.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from weaver.errors import WeaverError
from weaver.services.project import InspectSummary, inspect_project

# Cache-key prefix so discovery entries never collide with the per-project
# index entries the workspace index stores in the same shared app.state dict.
_DISCOVER_PREFIX = "discover:"


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


def discover_projects(
    books_dir: Path,
    *,
    cache: dict[str, Any] | None = None,
    ttl_seconds: float = 5.0,
) -> list[DiscoveredProject]:
    """Find all Weaver projects under ``books_dir/.weaver``.

    Args:
        books_dir: Root directory the cockpit was launched against.
        cache: Optional mutable dict for read-through caching of the per-project
            inspect (one read-only DB open + one ``project.toml`` parse each).
            Keyed by ``discover:<project_toml>``; values are
            ``(_CacheKey, DiscoveredProject, monotonic_ts)``. The caller (e.g.
            FastAPI ``app.state``) owns the dict lifetime. ``None`` (default)
            keeps the pre-v0.7.3 uncached behavior for every non-render caller.
        ttl_seconds: Maximum cache age before a project is re-inspected.

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

    now = time.monotonic()
    raw: list[DiscoveredProject] = [
        _discover_one(project_toml, books_dir, cache=cache, now=now, ttl_seconds=ttl_seconds)
        for project_toml in sorted(weaver_dir.glob("*/project.toml"))
    ]
    # Duplicate-uuid flagging is a cheap in-memory pass over the (possibly
    # cached) summaries, so conflict detection stays correct even on cache hits.
    return _flag_duplicate_uuids(raw)


@dataclass(frozen=True)
class _CacheKey:
    """Filesystem invalidation key for one project's discovery entry.

    Deliberately keyed on the ``project.toml`` + main ``weaver.db`` mtimes only,
    **not** the ``-wal`` mtime: a read-only inspect creates/touches the ``-wal``
    (so a wal-sensitive key would miss on every poll — the exact defect the M1.4
    counting-seam test caught), while read-only reads never change the main db
    mtime. A committed write bumps the db mtime once checkpointed; the 5 s TTL
    bounds staleness in the pre-checkpoint window, which a polling surface
    tolerates by design.
    """

    toml_mtime: int
    db_mtime: int


def _discovery_cache_key(project_toml: Path) -> _CacheKey | None:
    """Build an mtime invalidation key for one project's discovery entry."""

    db_path = project_toml.parent / "weaver.db"
    try:
        toml_mtime = project_toml.stat().st_mtime_ns
        db_mtime = db_path.stat().st_mtime_ns
        return _CacheKey(toml_mtime=toml_mtime, db_mtime=db_mtime)
    except OSError:
        return None


def _discover_one(
    project_toml: Path,
    books_dir: Path,
    *,
    cache: dict[str, Any] | None,
    now: float,
    ttl_seconds: float,
) -> DiscoveredProject:
    """Inspect one project, honoring the optional read-through cache."""

    name = project_toml.parent.name
    cache_key = _discovery_cache_key(project_toml) if cache is not None else None

    if cache is not None:
        cached = cache.get(_DISCOVER_PREFIX + str(project_toml))
        if cached is not None:
            cached_key, cached_project, cached_at = cached
            if (
                (now - cached_at) < ttl_seconds
                and cache_key is not None
                and cache_key == cached_key
            ):
                return cached_project

    try:
        summary = inspect_project(project_toml, cwd=books_dir)
        project = DiscoveredProject(
            name=name, project_toml=project_toml, summary=summary, error=None
        )
    except WeaverError as exc:
        project = DiscoveredProject(
            name=name, project_toml=project_toml, summary=None, error=str(exc)
        )

    if cache is not None and cache_key is not None:
        cache[_DISCOVER_PREFIX + str(project_toml)] = (cache_key, project, now)
    return project


def find_project(books_dir: Path, name: str) -> DiscoveredProject | None:
    """Return a single discovered project by directory name, or None.

    Args:
        books_dir: Root directory the cockpit was launched against.
        name: The ``.weaver/<name>`` directory name.

    Returns:
        The matching DiscoveredProject, or None when no such project exists.
    """

    # `name` is a single directory name. Reject path separators and traversal
    # tokens so a crafted route param cannot escape the `.weaver` root — on
    # Windows (the desktop target) a backslash is a separator, so `..\..\x` would
    # otherwise traverse. Legitimate project dir names never contain these.
    if not name or name in {".", ".."} or "/" in name or "\\" in name:
        return None
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
