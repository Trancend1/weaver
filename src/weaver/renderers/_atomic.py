"""Atomic file write helpers for export renderers (Sprint K3).

Each renderer writes its output to a temp file in the same directory, then
renames atomically so a failed write never leaves a corrupted final artifact.
"""

from __future__ import annotations

import contextlib
import os
import tempfile
from pathlib import Path

from ebooklib import epub
from ebooklib.epub import EpubException

from weaver.errors import EpubWriteError


def atomic_write_epub(output_path: Path, book: epub.EpubBook) -> None:
    """Write an EPUB to ``output_path`` atomically via a temp file + rename.

    Args:
        output_path: Destination path for the EPUB.
        book: ebooklib ``EpubBook`` to write.

    Raises:
        EpubWriteError: If the write or rename fails. Any partial temp file is
            cleaned up.
    """

    suffix = f".{output_path.suffix}.partial" if output_path.suffix else ".partial"
    fd, tmp = tempfile.mkstemp(dir=str(output_path.parent), suffix=suffix)
    try:
        os.close(fd)
        epub.write_epub(tmp, book)
        os.replace(tmp, output_path)
    except (OSError, EpubException) as exc:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise EpubWriteError(
            f"Failed to write EPUB to '{output_path}'. "
            "Likely cause: target directory is not writable or disk is full. "
            "Next command: check filesystem permissions or free space."
        ) from exc


def atomic_write_text(output_path: Path, content: str) -> None:
    """Write string ``content`` to ``output_path`` atomically via temp file + rename.

    Args:
        output_path: Destination path.
        content: UTF-8 string content to write.

    Raises:
        OSError: If the write or rename fails. Any partial temp file is cleaned up.
    """

    suffix = f".{output_path.suffix}.partial" if output_path.suffix else ".partial"
    fd, tmp = tempfile.mkstemp(dir=str(output_path.parent), suffix=suffix)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.replace(tmp, output_path)
    except OSError:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
