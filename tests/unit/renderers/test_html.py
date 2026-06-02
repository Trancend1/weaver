"""Tests for the standalone HTML export renderer (Sprint 8C)."""

from __future__ import annotations

from pathlib import Path

from weaver.renderers.html import render_html
from weaver.renderers.rendered_document import RenderChapter


def test_render_html_maps_blocks(tmp_path: Path) -> None:
    chapters = [
        RenderChapter(title="C", blocks=(("heading", "H"), ("paragraph", "P"), ("quote", "Q")))
    ]
    out = tmp_path / "out" / "v.html"

    result = render_html(output_path=out, title="Title", language="en", chapters=chapters)

    assert out.exists()
    assert result.chapters == 1
    assert result.blocks == 3
    html = out.read_text(encoding="utf-8")
    assert "<h1>Title</h1>" in html
    assert "<h2>H</h2>" in html
    assert "<p>P</p>" in html
    assert "<blockquote>Q</blockquote>" in html
    assert '<html lang="en">' in html


def test_render_html_escapes_special_chars(tmp_path: Path) -> None:
    chapters = [RenderChapter(title=None, blocks=(("paragraph", "a < b & c"),))]
    out = tmp_path / "v.html"

    render_html(output_path=out, title="X & Y", language="en", chapters=chapters)

    html = out.read_text(encoding="utf-8")
    assert "a &lt; b &amp; c" in html
    assert "<title>X &amp; Y</title>" in html
