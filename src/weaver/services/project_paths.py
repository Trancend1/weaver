"""Shared project path resolution.

One place to turn a project's configured ``database_path`` into an absolute
path. Framework-agnostic; used by the read and write services.
"""

from __future__ import annotations

from pathlib import Path

from weaver.core.config import load_project_config


def resolve_database_path(project_toml: Path, *, cwd: Path | None = None) -> Path:
    """Resolve a project's database path to an absolute path.

    Reads ``project.database_path`` from the project config. An absolute value
    is returned unchanged. A relative value is resolved against ``cwd`` when that
    location exists, otherwise against the project file's own directory.

    Args:
        project_toml: Path to the project's ``project.toml``.
        cwd: Working directory used to resolve a relative database path.

    Returns:
        Absolute path to the project's SQLite database file.
    """

    base_dir = cwd or Path.cwd()
    data = load_project_config(project_toml)
    path = Path(str(data["project"]["database_path"]))
    if path.is_absolute():
        return path
    cwd_path = base_dir / path
    if cwd_path.exists():
        return cwd_path
    return project_toml.parent / path
