"""Intermediate representation emitted by source readers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

BlockKind = Literal["paragraph", "heading", "quote", "other"]


@dataclass(frozen=True)
class DocumentMetadata:
    """EPUB-level metadata captured from the source document."""

    title: str
    author: str | None
    language: str
    identifier: str | None
    publisher: str | None
    description: str | None


@dataclass(frozen=True)
class AssetIR:
    """Non-document EPUB asset carried through for later rendering."""

    href: str
    media_type: str
    content: bytes


@dataclass(frozen=True)
class EpubMarkupContext:
    """EPUB-specific location data so the renderer can write back."""

    file_href: str
    xpath: str
    tag: str
    attrs: dict[str, str]
    text_node_index: int


@dataclass(frozen=True)
class BlockIR:
    """Single translatable source block.

    ``markup_context`` carries EPUB write-back location data and is present only
    for EPUB-sourced blocks; TXT/HTML readers leave it ``None``.
    """

    id: str
    chapter_id: str
    order: int
    kind: BlockKind
    source_text: str
    normalized_source_text: str
    markup_context: EpubMarkupContext | None = None


@dataclass(frozen=True)
class ChapterIR:
    """Chapter-level grouping in EPUB spine order."""

    id: str
    title: str | None
    href: str
    order: int
    blocks: list[BlockIR]


@dataclass(frozen=True)
class DocumentIR:
    """Format-neutral document representation for translation services."""

    metadata: DocumentMetadata
    assets: list[AssetIR]
    chapters: list[ChapterIR]
