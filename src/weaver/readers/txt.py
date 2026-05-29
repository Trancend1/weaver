"""Plain-text (.txt) source reader.

Splits a text file into chapters on common JP/EN heading markers and groups
blank-line-separated runs into paragraph blocks. Falls back to a single chapter
when no heading is found.
"""

from __future__ import annotations

import re
from pathlib import Path

from weaver.core.ir import DocumentIR
from weaver.errors import WeaverError
from weaver.readers.html_blocks import collapse_whitespace
from weaver.readers.synthetic_document import BlockDraft, ChapterDraft, build_document

_HEADING = re.compile(
    r"^\s*("
    r"第[0-9０-９一二三四五六七八九十百千〇]+\s*[章話節幕部巻]"
    r"|Chapter\s+\d+"
    r"|Prologue|Epilogue"
    r"|序章|終章|プロローグ|エピローグ"
    r")",
    re.IGNORECASE,
)


def read_txt(path: Path, *, language: str = "ja") -> DocumentIR:
    """Read a .txt file into DocumentIR.

    Args:
        path: Path to a UTF-8 text file.
        language: Source language tag for metadata.

    Returns:
        DocumentIR with synthesized chapter/segment ids and no markup context.

    Raises:
        WeaverError: If the file cannot be read as UTF-8.
    """

    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise WeaverError(
            f"Failed to read text file '{path}'. "
            "Likely cause: the file is missing or not UTF-8 encoded. "
            "Next command: re-save the file as UTF-8 and import again."
        ) from exc

    chapters = _split_chapters(text)
    if not chapters:
        raise WeaverError(
            f"No translatable text found in '{path}'. "
            "Likely cause: the file is empty or whitespace-only. "
            "Next command: import a file with content."
        )
    return build_document(source_name=path.name, language=language, chapters=chapters)


def _split_chapters(text: str) -> list[ChapterDraft]:
    chapters: list[ChapterDraft] = []
    current: ChapterDraft | None = None
    paragraph: list[str] = []

    def flush_paragraph() -> None:
        nonlocal current
        if not paragraph:
            return
        merged = collapse_whitespace(" ".join(paragraph))
        paragraph.clear()
        if not merged:
            return
        if current is None:
            current = ChapterDraft(title=None, blocks=[])
            chapters.append(current)
        current.blocks.append(BlockDraft(kind="paragraph", text=merged))

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            flush_paragraph()
            continue
        if _HEADING.match(line):
            flush_paragraph()
            current = ChapterDraft(title=line, blocks=[BlockDraft(kind="heading", text=line)])
            chapters.append(current)
            continue
        paragraph.append(line)

    flush_paragraph()
    return [chapter for chapter in chapters if chapter.blocks]
