"""Shared HTML/XHTML block classification helpers.

Used by both the EPUB reader (XHTML spine items) and the standalone HTML reader
so block-tag detection, kind mapping, and whitespace handling stay identical.
"""

from __future__ import annotations

import re

from weaver.core.ir import BlockKind

HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
TEXT_BLOCK_TAGS = {"p", "blockquote", *HEADING_TAGS}

_WHITESPACE = re.compile(r"\s+")


def block_kind(tag: str) -> BlockKind:
    """Map an HTML block tag to a Weaver block kind.

    Args:
        tag: Local (namespace-stripped) tag name.

    Returns:
        The matching BlockKind.
    """

    if tag in HEADING_TAGS:
        return "heading"
    if tag == "p":
        return "paragraph"
    if tag == "blockquote":
        return "quote"
    return "other"


def collapse_whitespace(text: str) -> str:
    """Collapse runs of whitespace to single spaces and strip ends.

    Args:
        text: Raw extracted text.

    Returns:
        Whitespace-normalized text.
    """

    return _WHITESPACE.sub(" ", text).strip()


def local_name(tag: str) -> str:
    """Return a tag name with any XML namespace prefix removed.

    Args:
        tag: Possibly namespaced element tag (e.g. ``{http://...}p``).

    Returns:
        The local tag name (e.g. ``p``).
    """

    return tag.rsplit("}", maxsplit=1)[-1]
