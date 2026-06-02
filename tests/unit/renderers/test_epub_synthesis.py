"""Tests for the from-scratch EPUB synthesis renderer (Sprint 8A)."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from ebooklib import epub

from weaver.renderers.epub_synthesis import synthesize_epub
from weaver.renderers.rendered_document import RenderChapter


def _chapter_bodies(path: Path) -> list[str]:
    book = epub.read_epub(str(path))
    items = sorted(
        (item for item in book.get_items() if item.get_name().startswith("chap_")),
        key=lambda item: item.get_name(),
    )
    return [item.get_content().decode("utf-8") for item in items]


def test_synthesize_writes_valid_epub_in_chapter_order(tmp_path: Path) -> None:
    chapters = [
        RenderChapter(title="第1章", blocks=(("heading", "第1章"), ("paragraph", "おはよう"))),
        RenderChapter(title=None, blocks=(("paragraph", "P2"), ("quote", "Q2"))),
    ]
    output_path = tmp_path / "out" / "vol.epub"

    result = synthesize_epub(
        output_path=output_path,
        title="My Volume",
        language="en",
        author="Author Name",
        identifier="id-1",
        chapters=chapters,
    )

    assert output_path.exists()
    assert result.chapters == 2
    assert result.blocks == 4

    book = epub.read_epub(str(output_path))
    assert book.get_metadata("DC", "title")[0][0] == "My Volume"
    assert book.get_metadata("DC", "language")[0][0] == "en"

    bodies = _chapter_bodies(output_path)
    assert len(bodies) == 2
    assert "<h2>第1章</h2>" in bodies[0]
    assert "<p>おはよう</p>" in bodies[0]
    assert "<p>P2</p>" in bodies[1]
    assert "<blockquote>Q2</blockquote>" in bodies[1]


def test_synthesize_escapes_xml_special_chars(tmp_path: Path) -> None:
    chapters = [RenderChapter(title="T", blocks=(("paragraph", "a < b & c > d"),))]
    output_path = tmp_path / "vol.epub"

    synthesize_epub(
        output_path=output_path,
        title="X & Y",
        language="en",
        author="A & B",
        identifier="id",
        chapters=chapters,
    )

    book = epub.read_epub(str(output_path))
    item = next(item for item in book.get_items() if item.get_name().startswith("chap_"))
    content = item.get_content()
    assert b"a &lt; b &amp; c &gt; d" in content
    # Well-formed XML (parse the bytes; a declaration-free str would also parse).
    ET.fromstring(content)


def test_synthesize_empty_chapters_still_writes_book(tmp_path: Path) -> None:
    output_path = tmp_path / "empty.epub"

    result = synthesize_epub(
        output_path=output_path,
        title="Empty",
        language="en",
        author=None,
        identifier="id",
        chapters=[],
    )

    assert output_path.exists()
    assert result.chapters == 0
    assert result.blocks == 0
