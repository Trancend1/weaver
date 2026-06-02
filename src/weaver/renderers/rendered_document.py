"""Shared value types and helpers for rendering resolved chapter content.

A *resolved* chapter is the export service's per-chapter output: a title plus
ordered ``(kind, text)`` blocks where each text is already the translation or its
source fallback. The EPUB, TXT, and HTML renderers all consume this shape.
"""

from __future__ import annotations

from dataclasses import dataclass
from xml.sax.saxutils import escape


@dataclass(frozen=True)
class RenderChapter:
    """One chapter resolved for rendering: title + ordered ``(kind, text)`` blocks."""

    title: str | None
    blocks: tuple[tuple[str, str], ...]


def block_to_html(kind: str, text: str) -> str:
    """Map one ``(kind, text)`` block to an XHTML element (text is XML-escaped).

    Shared by the EPUB synthesis renderer and the standalone HTML renderer so the
    block-tag mapping stays identical.

    Args:
        kind: Block kind (``heading`` | ``quote`` | ``paragraph`` | other).
        text: Resolved block text (translation or source fallback).

    Returns:
        An XHTML element string.
    """

    safe = escape(text)
    if kind == "heading":
        return f"<h2>{safe}</h2>"
    if kind == "quote":
        return f"<blockquote>{safe}</blockquote>"
    return f"<p>{safe}</p>"
