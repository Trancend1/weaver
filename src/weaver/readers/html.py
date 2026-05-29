"""HTML (.html/.htm) source reader.

Uses a tolerant ``HTMLParser`` (not strict XML) so real-world HTML imports
robustly. Extracts block-level text tags, splits chapters on top-level headings
(h1/h2), and emits markup-context-free blocks via the synthetic IR builder.
"""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path

from weaver.core.ir import DocumentIR
from weaver.errors import WeaverError
from weaver.readers.html_blocks import TEXT_BLOCK_TAGS, block_kind, collapse_whitespace
from weaver.readers.synthetic_document import BlockDraft, ChapterDraft, build_document

_CHAPTER_BREAK_TAGS = {"h1", "h2"}
_SKIP_CONTENT_TAGS = {"script", "style"}


def read_html(path: Path, *, language: str = "ja") -> DocumentIR:
    """Read a .html/.htm file into DocumentIR.

    Args:
        path: Path to a UTF-8 HTML file.
        language: Source language tag for metadata.

    Returns:
        DocumentIR with synthesized chapter/segment ids and no markup context.

    Raises:
        WeaverError: If the file cannot be read or contains no translatable text.
    """

    try:
        markup = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise WeaverError(
            f"Failed to read HTML file '{path}'. "
            "Likely cause: the file is missing or not UTF-8 encoded. "
            "Next command: re-save the file as UTF-8 and import again."
        ) from exc

    collector = _BlockCollector()
    collector.feed(markup)
    collector.close()

    chapters = _split_chapters(collector.blocks)
    if not chapters:
        raise WeaverError(
            f"No translatable text found in '{path}'. "
            "Likely cause: the HTML has no <p>/<h1-6>/<blockquote> text. "
            "Next command: import HTML with block-level text content."
        )
    return build_document(source_name=path.name, language=language, chapters=chapters)


def _split_chapters(tagged_blocks: list[tuple[str, str]]) -> list[ChapterDraft]:
    chapters: list[ChapterDraft] = []
    current: ChapterDraft | None = None
    for tag, text in tagged_blocks:
        kind = block_kind(tag)
        starts_chapter = tag in _CHAPTER_BREAK_TAGS
        if current is None or starts_chapter:
            current = ChapterDraft(title=text if kind == "heading" else None, blocks=[])
            chapters.append(current)
        current.blocks.append(BlockDraft(kind=kind, text=text))
    return [chapter for chapter in chapters if chapter.blocks]


class _BlockCollector(HTMLParser):
    """Collect ``(tag, text)`` pairs for block-level elements in source order."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[tuple[str, str]] = []
        self._tag: str | None = None
        self._buffer: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: object) -> None:
        if tag in _SKIP_CONTENT_TAGS:
            self._skip_depth += 1
            return
        if tag in TEXT_BLOCK_TAGS:
            self._flush(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_CONTENT_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
            return
        if tag == self._tag:
            self._flush(None)

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0 and self._tag is not None:
            self._buffer.append(data)

    def close(self) -> None:
        super().close()
        self._flush(None)

    def _flush(self, next_tag: str | None) -> None:
        if self._tag is not None:
            text = collapse_whitespace("".join(self._buffer))
            if text:
                self.blocks.append((self._tag, text))
        self._tag = next_tag
        self._buffer = []
