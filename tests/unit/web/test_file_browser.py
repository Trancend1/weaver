"""Unit tests for the sandboxed file browser (ADR ``0017``)."""

from __future__ import annotations

from pathlib import Path

import pytest

from weaver.errors import ConfigError
from weaver.web.file_browser import list_directory, resolve_source


def _make_tree(root: Path) -> None:
    (root / "sub").mkdir()
    (root / "a.epub").write_bytes(b"x")
    (root / "b.txt").write_text("a text source", encoding="utf-8")
    (root / "c.pdf").write_bytes(b"z")  # unsupported
    (root / "sub" / "c.epub").write_bytes(b"y")


def test_list_root_filters_to_dirs_and_sources(tmp_path: Path) -> None:
    _make_tree(tmp_path)

    listing = list_directory(tmp_path, "")

    assert listing.rel_dir == ""
    assert listing.parent is None
    kinds = {(e.name, e.kind) for e in listing.entries}
    assert ("sub", "dir") in kinds
    assert ("a.epub", "epub") in kinds
    assert ("b.txt", "txt") in kinds  # txt is now an importable source
    assert all(e.name != "c.pdf" for e in listing.entries)  # unsupported excluded
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


def test_resolve_source_ok_and_rejects_unsupported(tmp_path: Path) -> None:
    _make_tree(tmp_path)

    assert resolve_source(tmp_path, "a.epub") == (tmp_path / "a.epub").resolve()
    assert resolve_source(tmp_path, "b.txt") == (tmp_path / "b.txt").resolve()

    with pytest.raises(ConfigError):
        resolve_source(tmp_path, "c.pdf")
    with pytest.raises(ConfigError):
        resolve_source(tmp_path, "../a.epub")
