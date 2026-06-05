"""Tests for the Word (.docx) export renderer — custom OOXML writer (Phase D)."""

from __future__ import annotations

import zipfile
from pathlib import Path

from weaver.renderers.docx import render_docx
from weaver.renderers.rendered_document import RenderChapter

_REQUIRED_PARTS = {
    "[Content_Types].xml",
    "_rels/.rels",
    "word/document.xml",
    "word/styles.xml",
    "word/_rels/document.xml.rels",
}


def _read_part(path: Path, name: str) -> str:
    with zipfile.ZipFile(path) as archive:
        return archive.read(name).decode("utf-8")


def test_render_docx_writes_valid_zip_with_required_parts(tmp_path: Path) -> None:
    chapters = [RenderChapter(title="第1章", blocks=(("paragraph", "おはよう"),))]
    out = tmp_path / "out" / "vol.docx"

    result = render_docx(output_path=out, title="My Volume", language="en", chapters=chapters)

    assert out.exists()
    assert out.suffix == ".docx"
    assert out.stat().st_size > 0
    assert zipfile.is_zipfile(out)
    with zipfile.ZipFile(out) as archive:
        assert _REQUIRED_PARTS.issubset(set(archive.namelist()))
    assert result.chapters == 1
    assert result.blocks == 1


def test_render_docx_block_kinds_map_to_styles(tmp_path: Path) -> None:
    chapters = [
        RenderChapter(
            title="C1",
            blocks=(
                ("heading", "Chapter One"),
                ("paragraph", "Plain body"),
                ("quote", "A quoted line"),
            ),
        )
    ]
    out = tmp_path / "styled.docx"

    render_docx(output_path=out, title="Title Text", language="en", chapters=chapters)

    document = _read_part(out, "word/document.xml")
    # Title paragraph.
    assert '<w:pStyle w:val="Title"/>' in document
    assert "Title Text" in document
    # Heading block → Heading1; quote block → Quote.
    assert '<w:pStyle w:val="Heading1"/>' in document
    assert "Chapter One" in document
    assert '<w:pStyle w:val="Quote"/>' in document
    assert "A quoted line" in document
    # Plain paragraph carries no pStyle but its text is present.
    assert "Plain body" in document
    # Styles part actually defines the referenced styles.
    styles = _read_part(out, "word/styles.xml")
    assert '<w:style w:type="paragraph" w:styleId="Title">' in styles
    assert '<w:style w:type="paragraph" w:styleId="Heading1">' in styles
    assert '<w:style w:type="paragraph" w:styleId="Quote">' in styles


def test_render_docx_page_break_before_chapter_two_only(tmp_path: Path) -> None:
    chapters = [
        RenderChapter(title="C1", blocks=(("heading", "One"), ("paragraph", "a"))),
        RenderChapter(title="C2", blocks=(("heading", "Two"), ("paragraph", "b"))),
        RenderChapter(title="C3", blocks=(("heading", "Three"),)),
    ]
    out = tmp_path / "breaks.docx"

    render_docx(output_path=out, title="T", language="en", chapters=chapters)

    document = _read_part(out, "word/document.xml")
    # One page break per chapter boundary after the first → 2 breaks for 3 chapters.
    assert document.count("<w:pageBreakBefore/>") == 2
    # The first chapter's heading must not carry a page break: the substring before
    # the first page break contains chapter one's heading text.
    first_break = document.index("<w:pageBreakBefore/>")
    assert "One" in document[:first_break]
    assert "Two" not in document[:first_break]


def test_render_docx_escapes_xml(tmp_path: Path) -> None:
    chapters = [RenderChapter(title=None, blocks=(("paragraph", 'A & B < C > D "q"'),))]
    out = tmp_path / "escaped.docx"

    render_docx(output_path=out, title="x & y", language="en", chapters=chapters)

    document = _read_part(out, "word/document.xml")
    assert "&amp;" in document
    assert "&lt;" in document
    assert "&gt;" in document
    assert "A & B" not in document  # raw ampersand must not leak
    # Parses as well-formed XML.
    from xml.dom.minidom import parseString

    parseString(document)


def test_render_docx_empty_chapters(tmp_path: Path) -> None:
    out = tmp_path / "empty.docx"
    result = render_docx(output_path=out, title="T", language="en", chapters=[])
    assert out.exists()
    assert zipfile.is_zipfile(out)
    assert result.chapters == 0
    assert result.blocks == 0
    # Still a well-formed document with the title only.
    document = _read_part(out, "word/document.xml")
    from xml.dom.minidom import parseString

    parseString(document)
    assert "<w:pageBreakBefore/>" not in document


def test_render_docx_blank_language_defaults_to_en(tmp_path: Path) -> None:
    out = tmp_path / "lang.docx"
    render_docx(output_path=out, title="T", language="", chapters=[])
    styles = _read_part(out, "word/styles.xml")
    assert '<w:lang w:val="en"/>' in styles
