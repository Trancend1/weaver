"""Tests for the sandboxed source browser service (Sprint 10B)."""

from __future__ import annotations

from pathlib import Path

import pytest

from weaver.errors import ConfigError
from weaver.services.source_browser import (
    UPLOADS_DIRNAME,
    list_directory,
    resolve_source,
    sanitize_source_filename,
    store_uploaded_source,
)


def _make_tree(root: Path) -> None:
    (root / "sub").mkdir()
    (root / "sub" / "vol1.epub").write_bytes(b"epub")
    (root / "novel.txt").write_text("hi", encoding="utf-8")
    (root / "page.html").write_text("<p>", encoding="utf-8")
    (root / "notes.md").write_text("skip me", encoding="utf-8")


def test_list_directory_root_lists_dirs_then_sources(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    listing = list_directory(tmp_path, "")
    assert listing.rel_dir == ""
    assert listing.parent is None
    kinds = [(e.name, e.kind) for e in listing.entries]
    # dirs first, then sources; the .md is excluded
    assert kinds[0] == ("sub", "dir")
    names = {e.name for e in listing.entries}
    assert names == {"sub", "novel.txt", "page.html"}


def test_list_directory_nested_has_parent(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    listing = list_directory(tmp_path, "sub")
    assert listing.rel_dir == "sub"
    assert listing.parent == ""
    assert [e.name for e in listing.entries] == ["vol1.epub"]


def test_list_directory_rejects_traversal(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        list_directory(tmp_path, "../../etc")


def test_list_directory_missing_dir_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        list_directory(tmp_path, "nope")


def test_resolve_source_ok(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    assert resolve_source(tmp_path, "novel.txt") == (tmp_path / "novel.txt").resolve()


def test_resolve_source_rejects_unsupported(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    with pytest.raises(ConfigError):
        resolve_source(tmp_path, "notes.md")


def test_resolve_source_rejects_traversal(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        resolve_source(tmp_path, "../secret.epub")


def test_sanitize_strips_directory_components() -> None:
    assert sanitize_source_filename("../../evil.epub") == "evil.epub"
    assert sanitize_source_filename("a/b/c.txt") == "c.txt"


def test_sanitize_preserves_unicode() -> None:
    assert sanitize_source_filename("第1巻.epub") == "第1巻.epub"


def test_sanitize_rejects_unsupported_suffix() -> None:
    with pytest.raises(ConfigError):
        sanitize_source_filename("book.pdf")


def test_sanitize_rejects_empty() -> None:
    with pytest.raises(ConfigError):
        sanitize_source_filename("")


def test_store_uploaded_source_writes_under_uploads(tmp_path: Path) -> None:
    stored = store_uploaded_source(tmp_path, "第1巻.epub", b"payload")
    assert stored == (tmp_path / ".weaver" / UPLOADS_DIRNAME / "第1巻.epub").resolve()
    assert stored.read_bytes() == b"payload"
    # stem preserved so the eventual project name is meaningful
    assert stored.stem == "第1巻"


def test_store_uploaded_source_rejects_bad_suffix(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        store_uploaded_source(tmp_path, "book.pdf", b"x")
