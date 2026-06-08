"""Synthesize a fresh EPUB from translated chapter/block content (Sprint 8A).

EPUB-sourced volumes are exported by writing translations back into the original
EPUB (:mod:`weaver.renderers.epub`). TXT/HTML-sourced volumes have no source EPUB
and no markup context, so their EPUB export is built from scratch here from the
persisted chapter/segment content.

Pure renderer: callers pass already-resolved block text (a translation or its
source fallback) plus metadata. No database access and no fallback logic live
here — that is the export service's job.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from ebooklib import epub

from weaver.renderers._atomic import atomic_write_epub
from weaver.renderers.rendered_document import RenderChapter, block_to_html

_XHTML_TEMPLATE = (
    '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>{title}</title>'
    "</head><body>{body}</body></html>"
)


@dataclass(frozen=True)
class EpubSynthesisResult:
    """Result of synthesizing an EPUB."""

    output_path: Path
    chapters: int
    blocks: int


def synthesize_epub(
    *,
    output_path: Path,
    title: str,
    language: str,
    author: str | None,
    identifier: str,
    chapters: Sequence[RenderChapter],
) -> EpubSynthesisResult:
    """Build and write a fresh EPUB from resolved chapter content.

    Args:
        output_path: Destination path for the EPUB.
        title: Book title (used for metadata and as a navigation fallback).
        language: Language tag for metadata (the translated/target language).
        author: Optional author for metadata.
        identifier: Unique book identifier for metadata.
        chapters: Ordered chapters; each block is ``(kind, resolved_text)`` where
            the text is already the translation or its source fallback.

    Returns:
        EpubSynthesisResult with the output path and chapter/block counts.

    Raises:
        EpubWriteError: If the EPUB cannot be written.
    """

    book = epub.EpubBook()
    book.set_identifier(identifier)
    book.set_title(title)
    book.set_language(language or "en")
    if author:
        book.add_author(author)

    spine: list[Any] = ["nav"]
    toc: list[Any] = []
    total_blocks = 0
    for index, chapter in enumerate(chapters):
        chapter_title = chapter.title or f"Chapter {index + 1}"
        item = epub.EpubHtml(
            title=chapter_title,
            file_name=f"chap_{index + 1:04d}.xhtml",
            lang=language or "en",
        )
        item.content = _chapter_xhtml(chapter_title, chapter.blocks)
        total_blocks += len(chapter.blocks)
        book.add_item(item)
        spine.append(item)
        toc.append(item)

    book.toc = toc
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = spine

    output_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_epub(output_path, book)

    return EpubSynthesisResult(
        output_path=output_path,
        chapters=len(chapters),
        blocks=total_blocks,
    )


def _chapter_xhtml(title: str, blocks: tuple[tuple[str, str], ...]) -> str:
    body = "".join(block_to_html(kind, text) for kind, text in blocks)
    return _XHTML_TEMPLATE.format(title=escape(title), body=body)
