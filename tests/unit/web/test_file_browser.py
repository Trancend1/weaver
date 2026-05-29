"""Unit tests for the sandboxed file browser (ADR ``0017``)."""

from __future__ import annotations

from pathlib import Path

import pytest

from weaver.errors import ConfigError
from weaver.web.file_browser import list_directory, resolve_epub


def _make_tree(root: Path) -> None:
    (root / "sub").mkdir()
    (root / "a.epub").write_bytes(b"x")
    (root / "b.txt").write_text("not an epub", encoding="utf-8")
    (root / "sub" / "c.epub").write_bytes(b"y")


def test_list_root_filters_to_dirs_and_epubs(tmp_path: Path) -> None:
    _make_tree(tmp_path)

    listing = list_directory(tmp_path, "")

    assert listing.rel_dir == ""
    assert listing.parent is None
    kinds = {(e.name, e.kind) for e in listing.entries}
    assert ("sub", "dir") in kinds
    assert ("a.epub", "epub") in kinds
    assert all(e.name != "b.txt" for e in listing.entries)  # non-epub excluded
    # Directories sort before files.
    assert listing.entries[0].kind == "dir"


def test_list_subdirectory_sets_parent(tmp_path: Path) -> None:
    _make_tree(tmp_path)

    listing = list_directory(tmp_path, "sub")

    assert listing.rel_dir == "sub"
    assert listing.parent == ""
    assert any(e.name == "c.epub" for e in listing.entries)


def test_traversal_escape_rejected(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    with pytest.raises(ConfigError):
        list_directory(tmp_path, "..")


def test_resolve_epub_ok_and_rejects_non_epub(tmp_path: Path) -> None:
    _make_tree(tmp_path)

    resolved = resolve_epub(tmp_path, "a.epub")
    assert resolved == (tmp_path / "a.epub").resolve()

    with pytest.raises(ConfigError):
        resolve_epub(tmp_path, "b.txt")
    with pytest.raises(ConfigError):
        resolve_epub(tmp_path, "../a.epub")
