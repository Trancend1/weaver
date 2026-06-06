"""Word (.docx) export renderer — custom minimal OOXML writer (Phase D).

Renders resolved chapter content (each block already the translation or its
source fallback, decided by the export service) to a single ``.docx`` file. A
``.docx`` is a ZIP of flat WordprocessingML (OOXML) parts; this module hand-writes
the minimal valid set with no third-party dependency (:mod:`python-docx` is *not*
used — see ``docs/PHASE_D_DOCX_EXPORT_PLAN.md``).

Like the TXT/HTML renderers this is a **pure renderer**: no database access and no
fallback logic. DOCX is always synthesized from the resolved
:class:`~weaver.renderers.rendered_document.RenderChapter` blocks — there is no
write-back path (unlike EPUB), so the source file is never re-read.

Formatting baseline:

- document title → ``Title`` style
- ``heading`` block → ``Heading1`` style
- ``quote`` block → built-in ``Quote`` style
- every other block → normal paragraph
- a page break is inserted before the first block of chapters 2..N (not chapter 1)
"""

from __future__ import annotations

import contextlib
import io
import os
import tempfile
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

from weaver.errors import ExportError
from weaver.renderers.rendered_document import RenderChapter

# --- static OOXML parts -----------------------------------------------------

_CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels"'
    ' ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml"'
    ' ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'  # noqa: E501
    '<Override PartName="/word/styles.xml"'
    ' ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
    "</Types>"
)

_ROOT_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1"'
    ' Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"'
    ' Target="word/document.xml"/>'
    "</Relationships>"
)

_DOCUMENT_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1"'
    ' Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles"'
    ' Target="styles.xml"/>'
    "</Relationships>"
)

_STYLES_TEMPLATE = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    "<w:docDefaults><w:rPrDefault><w:rPr>"
    '<w:lang w:val="{lang}"/>'
    "</w:rPr></w:rPrDefault></w:docDefaults>"
    '<w:style w:type="paragraph" w:default="1" w:styleId="Normal">'
    '<w:name w:val="Normal"/></w:style>'
    '<w:style w:type="paragraph" w:styleId="Title">'
    '<w:name w:val="Title"/><w:basedOn w:val="Normal"/>'
    '<w:pPr><w:spacing w:after="240"/></w:pPr>'
    '<w:rPr><w:b/><w:sz w:val="56"/></w:rPr></w:style>'
    '<w:style w:type="paragraph" w:styleId="Heading1">'
    '<w:name w:val="heading 1"/><w:basedOn w:val="Normal"/>'
    '<w:pPr><w:keepNext/><w:spacing w:before="240" w:after="120"/><w:outlineLvl w:val="0"/></w:pPr>'
    '<w:rPr><w:b/><w:sz w:val="36"/></w:rPr></w:style>'
    '<w:style w:type="paragraph" w:styleId="Quote">'
    '<w:name w:val="Quote"/><w:basedOn w:val="Normal"/>'
    '<w:pPr><w:ind w:left="720" w:right="720"/></w:pPr>'
    "<w:rPr><w:i/></w:rPr></w:style>"
    "</w:styles>"
)

_DOCUMENT_OPEN = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    "<w:body>"
)
_DOCUMENT_CLOSE = "<w:sectPr/></w:body></w:document>"

# Block kind → paragraph style id. Unmapped kinds render as the Normal paragraph
# (no ``w:pStyle``), mirroring the ``block_to_html`` fallback to ``<p>``.
_BLOCK_STYLE = {"heading": "Heading1", "quote": "Quote"}

# Fixed ZIP timestamp so identical input yields byte-stable output (determinism).
_ZIP_DATE_TIME = (1980, 1, 1, 0, 0, 0)


@dataclass(frozen=True)
class DocxRenderResult:
    """Result of rendering a DOCX export."""

    output_path: Path
    chapters: int
    blocks: int


def render_docx(
    *,
    output_path: Path,
    title: str,
    language: str,
    chapters: Sequence[RenderChapter],
) -> DocxRenderResult:
    """Render resolved chapters to a single ``.docx`` (custom OOXML writer).

    Args:
        output_path: Destination path for the Word document.
        title: Book/volume title, written as a ``Title``-styled paragraph.
        language: Language tag for the document default ``w:lang`` (metadata).
        chapters: Ordered resolved chapters; each block is ``(kind, text)`` where
            the text is already the translation or its source fallback.

    Returns:
        DocxRenderResult with the output path and chapter/block counts.

    Raises:
        ExportError: If the file cannot be written.
    """

    document_xml = _build_document_xml(title, chapters)
    styles_xml = _STYLES_TEMPLATE.format(lang=escape(language or "en", {'"': "&quot;"}))
    package = _build_package(document_xml=document_xml, styles_xml=styles_xml)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        _atomic_write_bytes(output_path, package)
    except OSError as exc:
        raise ExportError(
            f"Failed to write DOCX export to '{output_path}'. "
            "Likely cause: target directory is not writable or disk is full. "
            "Next command: check filesystem permissions or free space."
        ) from exc

    total_blocks = sum(len(chapter.blocks) for chapter in chapters)
    return DocxRenderResult(output_path=output_path, chapters=len(chapters), blocks=total_blocks)


def _build_document_xml(title: str, chapters: Sequence[RenderChapter]) -> str:
    """Assemble ``word/document.xml`` from the resolved chapters."""

    parts = [_DOCUMENT_OPEN]
    if title:
        parts.append(_paragraph("Title", title))
    for chapter_index, chapter in enumerate(chapters):
        for block_index, (kind, text) in enumerate(chapter.blocks):
            page_break = chapter_index > 0 and block_index == 0
            parts.append(_block_paragraph(kind, text, page_break_before=page_break))
    parts.append(_DOCUMENT_CLOSE)
    return "".join(parts)


def _paragraph(style: str, text: str) -> str:
    """A single styled paragraph (used for the document title)."""

    return (
        f'<w:p><w:pPr><w:pStyle w:val="{style}"/></w:pPr>'
        f'<w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>'
    )


def _block_paragraph(kind: str, text: str, *, page_break_before: bool) -> str:
    """Map one ``(kind, text)`` block to a ``<w:p>`` paragraph.

    ``w:pStyle`` (if any) precedes ``w:pageBreakBefore`` to satisfy the OOXML
    ``CT_PPr`` element order.
    """

    style = _BLOCK_STYLE.get(kind)
    ppr_inner = ""
    if style is not None:
        ppr_inner += f'<w:pStyle w:val="{style}"/>'
    if page_break_before:
        ppr_inner += "<w:pageBreakBefore/>"
    ppr = f"<w:pPr>{ppr_inner}</w:pPr>" if ppr_inner else ""
    return f'<w:p>{ppr}<w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>'


def _build_package(*, document_xml: str, styles_xml: str) -> bytes:
    """Build the in-memory ``.docx`` ZIP (deflated, fixed timestamps)."""

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in (
            ("[Content_Types].xml", _CONTENT_TYPES),
            ("_rels/.rels", _ROOT_RELS),
            ("word/_rels/document.xml.rels", _DOCUMENT_RELS),
            ("word/styles.xml", styles_xml),
            ("word/document.xml", document_xml),
        ):
            info = zipfile.ZipInfo(name, date_time=_ZIP_DATE_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data.encode("utf-8"))
    return buffer.getvalue()


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write ``data`` to ``path`` atomically via a temp file + ``os.replace``."""

    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".docx.tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.replace(tmp, path)
    except OSError:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
