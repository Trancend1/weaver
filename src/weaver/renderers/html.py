"""Standalone HTML (.html) export renderer (Sprint 8C).

Renders resolved chapter content to a single HTML5 document, one ``<section>``
per chapter, reusing the shared block→HTML mapping. Pure renderer — no database
access and no fallback logic.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

from weaver.errors import ExportError
from weaver.renderers._atomic import atomic_write_text
from weaver.renderers.rendered_document import RenderChapter, block_to_html

_HTML_TEMPLATE = (
    "<!DOCTYPE html>\n"
    '<html lang="{lang}"><head><meta charset="utf-8"/><title>{title}</title></head>'
    "<body>{body}</body></html>\n"
)


@dataclass(frozen=True)
class HtmlRenderResult:
    """Result of rendering an HTML export."""

    output_path: Path
    chapters: int
    blocks: int


def render_html(
    *,
    output_path: Path,
    title: str,
    language: str,
    chapters: Sequence[RenderChapter],
) -> HtmlRenderResult:
    """Render resolved chapters to a single UTF-8 ``.html`` document.

    Args:
        output_path: Destination path for the HTML file.
        title: Book/volume title (``<title>`` and the top ``<h1>``).
        language: Language tag for the ``<html lang>`` attribute.
        chapters: Ordered resolved chapters; each block is ``(kind, text)``.

    Returns:
        HtmlRenderResult with the output path and chapter/block counts.

    Raises:
        ExportError: If the file cannot be written.
    """

    sections: list[str] = []
    total_blocks = 0
    for chapter in chapters:
        parts = ["<section>"]
        for kind, text in chapter.blocks:
            parts.append(block_to_html(kind, text))
            total_blocks += 1
        parts.append("</section>")
        sections.append("".join(parts))

    body = f"<h1>{escape(title)}</h1>" + "".join(sections)
    content = _HTML_TEMPLATE.format(
        lang=escape(language or "en", {'"': "&quot;"}),
        title=escape(title),
        body=body,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        atomic_write_text(output_path, content)
    except OSError as exc:
        raise ExportError(
            f"Failed to write HTML export to '{output_path}'. "
            "Likely cause: target directory is not writable or disk is full. "
            "Next command: check filesystem permissions or free space."
        ) from exc

    return HtmlRenderResult(output_path=output_path, chapters=len(chapters), blocks=total_blocks)
