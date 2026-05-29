"""Sandboxed directory listing for the new-project file picker (ADR ``0017``).

Lists sub-directories and importable source files (``.epub``/``.txt``/``.html``)
under the cockpit's ``--books-dir`` root. Every requested path is resolved and
confirmed to stay inside the root — ``..`` traversal escapes are rejected. The
web layer never exposes paths outside the sandbox.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from weaver.errors import ConfigError

SOURCE_SUFFIXES = {".epub", ".txt", ".html", ".htm"}


@dataclass(frozen=True)
class BrowseEntry:
    """One listed item: a sub-directory or an importable source file."""

    name: str
    kind: str  # "dir" | "epub" | "txt" | "html"
    rel_path: str  # POSIX path relative to the books-dir root


@dataclass(frozen=True)
class BrowseListing:
    """A sandboxed directory listing relative to the books-dir root."""

    rel_dir: str  # "" for the root
    parent: str | None  # parent rel path, or None at the root
    entries: tuple[BrowseEntry, ...]


def list_directory(books_dir: Path, rel_dir: str = "") -> BrowseListing:
    """List sub-directories and ``.epub`` files under ``books_dir / rel_dir``.

    Args:
        books_dir: Sandbox root (the cockpit's ``--books-dir``).
        rel_dir: Directory to list, relative to ``books_dir``. ``""`` is the root.

    Returns:
        A BrowseListing with directories first, then ``.epub`` files, each sorted
        case-insensitively.

    Raises:
        ConfigError: When the resolved path escapes the sandbox or is not an
            existing directory.
    """

    root = books_dir.resolve()
    target = _safe_join(root, rel_dir)
    if not target.is_dir():
        raise ConfigError(
            f"Not a directory: {rel_dir or '.'}. "
            "Likely cause: stale link or the folder was removed. "
            "Next command: go back and pick an existing folder."
        )

    dirs: list[BrowseEntry] = []
    files: list[BrowseEntry] = []
    for child in target.iterdir():
        rel = child.relative_to(root).as_posix()
        if child.is_dir():
            dirs.append(BrowseEntry(name=child.name, kind="dir", rel_path=rel))
        elif child.is_file() and child.suffix.lower() in SOURCE_SUFFIXES:
            files.append(BrowseEntry(name=child.name, kind=_kind(child), rel_path=rel))

    dirs.sort(key=lambda e: e.name.casefold())
    files.sort(key=lambda e: e.name.casefold())

    rel_norm = target.relative_to(root).as_posix()
    rel_norm = "" if rel_norm == "." else rel_norm
    parent = None if target == root else target.parent.relative_to(root).as_posix()
    parent = "" if parent == "." else parent

    return BrowseListing(rel_dir=rel_norm, parent=parent, entries=tuple(dirs + files))


def resolve_source(books_dir: Path, rel_path: str) -> Path:
    """Resolve a browsed source path, confirming it stays in the sandbox.

    Args:
        books_dir: Sandbox root.
        rel_path: Source path relative to ``books_dir``.

    Returns:
        The absolute, sandbox-confirmed path to the source file.

    Raises:
        ConfigError: When the path escapes the sandbox, is missing, or is not a
            supported source file.
    """

    root = books_dir.resolve()
    target = _safe_join(root, rel_path)
    if not target.is_file() or target.suffix.lower() not in SOURCE_SUFFIXES:
        supported = ", ".join(sorted(SOURCE_SUFFIXES))
        raise ConfigError(
            f"Not a supported source file: {rel_path}. "
            f"Likely cause: the file was moved or is not one of: {supported}. "
            "Next command: pick a supported source file from the browser."
        )
    return target


def _kind(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".html", ".htm"}:
        return "html"
    return suffix.lstrip(".")


def _safe_join(root: Path, rel: str) -> Path:
    """Join ``rel`` onto ``root`` and reject any escape of the sandbox."""

    candidate = (root / rel).resolve()
    if candidate != root and root not in candidate.parents:
        raise ConfigError(
            "Path escapes the books directory. "
            "Likely cause: a '..' traversal or absolute path was supplied. "
            "Next command: pick a folder inside the books directory."
        )
    return candidate
