"""HTML reader tests (Sprint 1b)."""

from __future__ import annotations

import pytest

from weaver.errors import WeaverError
from weaver.readers.html import read_html

_SAMPLE = """<html><head><title>x</title>
<style>.c{color:red}</style></head>
<body>
<h1>Chapter One</h1>
<p>First paragraph.</p>
<p>Second paragraph.</p>
<script>var ignore = 1;</script>
<h1>Chapter Two</h1>
<blockquote>A quote.</blockquote>
</body></html>
"""


def test_read_html_splits_on_h1_and_skips_script_style(tmp_path) -> None:
    path = tmp_path / "doc.html"
    path.write_text(_SAMPLE, encoding="utf-8")

    document = read_html(path)

    assert [chapter.title for chapter in document.chapters] == ["Chapter One", "Chapter Two"]
    first = document.chapters[0]
    assert [block.kind for block in first.blocks] == ["heading", "paragraph", "paragraph"]
    assert first.blocks[1].source_text == "First paragraph."
    texts = [block.source_text for chapter in document.chapters for block in chapter.blocks]
    assert "var ignore = 1;" not in texts
    assert ".c{color:red}" not in texts
    assert document.chapters[1].blocks[1].kind == "quote"
    assert all(
        block.markup_context is None for chapter in document.chapters for block in chapter.blocks
    )


def test_read_html_rejects_textless_markup(tmp_path) -> None:
    path = tmp_path / "empty.html"
    path.write_text("<html><body><div></div></body></html>", encoding="utf-8")

    with pytest.raises(WeaverError, match="No translatable text"):
        read_html(path)
