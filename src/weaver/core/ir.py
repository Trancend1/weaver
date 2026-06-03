"""Intermediate representation emitted by source readers."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

from weaver.core.segment import scope_id_to_volume

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


def scope_document_to_volume(document: DocumentIR, volume_id: int) -> DocumentIR:
    """Return a copy of ``document`` with chapter/segment ids scoped to a volume.

    Reader ids are content/structure-derived and carry no volume component, so two
    volumes built from identical source content would share ids. Applying
    :func:`weaver.core.segment.scope_id_to_volume` to every chapter id and block id
    (and each block's ``chapter_id`` back-reference) makes a freshly-read document
    join 1:1 with the rows ``sync_document_segments`` persists for the same volume,
    and keeps two volumes' chapters/segments distinct (Stage 11B-1.5).

    Apply this once, immediately after reading a source that is being associated
    with a known volume (init, import, translate re-read, EPUB export write-back).
    ``sync_document_segments`` stores ids as-given, so a document must be scoped
    **exactly once** — never pass an already-scoped document through scoping again.
    """

    scoped_chapters: list[ChapterIR] = []
    for chapter in document.chapters:
        chapter_id = scope_id_to_volume(volume_id, chapter.id)
        scoped_blocks = [
            replace(block, id=scope_id_to_volume(volume_id, block.id), chapter_id=chapter_id)
            for block in chapter.blocks
        ]
        scoped_chapters.append(replace(chapter, id=chapter_id, blocks=scoped_blocks))
    return replace(document, chapters=scoped_chapters)
