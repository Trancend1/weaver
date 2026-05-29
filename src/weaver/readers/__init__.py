"""Source readers that emit DocumentIR."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from weaver.core.ir import DocumentIR
from weaver.errors import WeaverError
from weaver.readers.epub import read_epub
from weaver.readers.html import read_html
from weaver.readers.txt import read_txt

SourceFormat = Literal["epub", "txt", "html"]

_SUFFIX_FORMATS: dict[str, SourceFormat] = {
    ".epub": "epub",
    ".txt": "txt",
    ".html": "html",
    ".htm": "html",
}


def detect_format(path: Path) -> SourceFormat:
    """Return the source format for a path by file suffix.

    Args:
        path: Source file path.

    Returns:
        The detected source format.

    Raises:
        WeaverError: If the suffix is not a supported format.
    """

    suffix = path.suffix.lower()
    fmt = _SUFFIX_FORMATS.get(suffix)
    if fmt is None:
        supported = ", ".join(sorted(_SUFFIX_FORMATS))
        raise WeaverError(
            f"Unsupported source format `{suffix or path.name}`. "
            f"Likely cause: only these formats are supported: {supported}. "
            "Next command: import a supported source file."
        )
    return fmt


def read_source(path: Path) -> DocumentIR:
    """Read any supported source file into DocumentIR.

    Dispatches by file suffix to the EPUB, TXT, or HTML reader.

    Args:
        path: Source file path.

    Returns:
        DocumentIR emitted by the matching reader.

    Raises:
        WeaverError: If the format is unsupported or the read fails.
    """

    fmt = detect_format(path)
    if fmt == "epub":
        return read_epub(path)
    if fmt == "txt":
        return read_txt(path)
    return read_html(path)


__all__ = ["SourceFormat", "detect_format", "read_source", "read_epub", "read_html", "read_txt"]
