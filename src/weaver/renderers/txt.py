"""Plain-text (.txt) export renderer (Sprint 8C).

Renders resolved chapter content (each block already the translation or its
source fallback, decided by the export service) to a single UTF-8 text file:
blocks separated by blank lines, chapters by an extra blank line. Pure renderer —
no database access and no fallback logic.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from weaver.errors import ExportError
from weaver.renderers.rendered_document import RenderChapter


@dataclass(frozen=True)
class TxtRenderResult:
    """Result of rendering a TXT export."""

    output_path: Path
    chapters: int
    blocks: int


def render_txt(
    *, output_path: Path, title: str, chapters: Sequence[RenderChapter]
) -> TxtRenderResult:
    """Render resolved chapters to a single UTF-8 ``.txt`` file.

    Args:
        output_path: Destination path for the text file.
        title: Book/volume title, written as the first line.
        chapters: Ordered resolved chapters; each block is ``(kind, text)``.

    Returns:
        TxtRenderResult with the output path and chapter/block counts.

    Raises:
        ExportError: If the file cannot be written.
    """

    lines: list[str] = []
    if title:
        lines.append(title)
    total_blocks = 0
    for chapter in chapters:
        lines.append("")  # blank line before each chapter
        for _kind, text in chapter.blocks:
            lines.append(text)
            lines.append("")
            total_blocks += 1
    content = "\n".join(lines).strip() + "\n"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        output_path.write_text(content, encoding="utf-8")
    except OSError as exc:
        raise ExportError(
            f"Failed to write TXT export to '{output_path}'. "
            "Likely cause: target directory is not writable or disk is full. "
            "Next command: check filesystem permissions or free space."
        ) from exc

    return TxtRenderResult(output_path=output_path, chapters=len(chapters), blocks=total_blocks)
