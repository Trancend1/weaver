"""EPUB source reader."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from xml.etree import ElementTree

from ebooklib import epub
from ebooklib.epub import EpubBook, EpubException, EpubItem

from weaver.core.ir import (
    AssetIR,
    BlockIR,
    ChapterIR,
    DocumentIR,
    DocumentMetadata,
    EpubMarkupContext,
)
from weaver.core.segment import compute_chapter_id, compute_segment_id, normalize_japanese_text
from weaver.errors import EpubReadError
from weaver.readers.html_blocks import (
    TEXT_BLOCK_TAGS,
    block_kind,
    collapse_whitespace,
    local_name,
)

DOCUMENT_MEDIA_TYPES = {"application/xhtml+xml", "text/html"}


def read_epub(path: Path) -> DocumentIR:
    """Read an EPUB into deterministic DocumentIR.

    Args:
        path: Path to a source EPUB.

    Returns:
        DocumentIR with metadata, assets, chapters, and text blocks.

    Raises:
        EpubReadError: If the EPUB cannot be opened or required package files are missing.
    """

    try:
        book = epub.read_epub(path)
        metadata = _read_metadata(book)
        spine_items = _read_spine_items(book)
        return DocumentIR(
            metadata=metadata,
            assets=_read_assets(book),
            chapters=[
                _read_chapter(item, order, metadata.identifier)
                for order, item in enumerate(spine_items)
            ],
        )
    except (OSError, KeyError, ElementTree.ParseError, EpubException) as exc:
        raise EpubReadError(
            f"Failed to read EPUB '{path}'. Likely cause: invalid EPUB structure. "
            "Next command: run `weaver init <path-to-epub>` with a valid EPUB file."
        ) from exc


def _read_metadata(book: EpubBook) -> DocumentMetadata:
    return DocumentMetadata(
        title=_metadata_text(book, "title") or "Untitled",
        author=_metadata_text(book, "creator"),
        language=_metadata_text(book, "language") or "ja",
        identifier=_metadata_text(book, "identifier"),
        publisher=_metadata_text(book, "publisher"),
        description=_metadata_text(book, "description"),
    )


def _metadata_text(book: EpubBook, name: str) -> str | None:
    entries = book.get_metadata("DC", name)
    if not entries:
        return None
    value = entries[0][0]
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _read_spine_items(book: EpubBook) -> list[EpubItem]:
    items: list[EpubItem] = []
    for item_id, _linear in book.spine:
        item = book.get_item_with_id(item_id)
        if item is not None and _item_media_type(item) in DOCUMENT_MEDIA_TYPES:
            items.append(item)
    return items


def _read_assets(book: EpubBook) -> list[AssetIR]:
    assets: list[AssetIR] = []
    for item in book.get_items():
        media_type = _item_media_type(item)
        if media_type in DOCUMENT_MEDIA_TYPES:
            continue
        assets.append(
            AssetIR(href=item.get_name(), media_type=media_type, content=item.get_content())
        )
    return assets


def _read_chapter(item: EpubItem, order: int, book_identifier: str | None) -> ChapterIR:
    href = item.get_name()
    root = ElementTree.fromstring(item.get_content())
    chapter_id = compute_chapter_id(book_identifier=book_identifier, spine_href=href)
    blocks = [
        _element_to_block(element, xpath, href, chapter_id, block_order)
        for block_order, (element, xpath) in enumerate(_iter_text_blocks(root))
    ]
    return ChapterIR(
        id=chapter_id,
        title=_chapter_title(blocks),
        href=href,
        order=order,
        blocks=blocks,
    )


def _item_media_type(item: EpubItem) -> str:
    media_type = getattr(item, "media_type", "")
    return media_type if isinstance(media_type, str) else ""


def _iter_text_blocks(root: ElementTree.Element) -> Iterable[tuple[ElementTree.Element, str]]:
    for element, xpath in _walk_with_xpath(root, f"/{local_name(root.tag)}"):
        if local_name(element.tag) in TEXT_BLOCK_TAGS and _element_text(element):
            yield element, xpath


def _element_to_block(
    element: ElementTree.Element,
    xpath: str,
    chapter_href: str,
    chapter_id: str,
    block_order: int,
) -> BlockIR:
    source_text = _element_text(element)
    tag = local_name(element.tag)
    return BlockIR(
        id=compute_segment_id(
            chapter_href=chapter_href,
            dom_path=xpath,
            paragraph_index=block_order,
        ),
        chapter_id=chapter_id,
        order=block_order,
        kind=block_kind(tag),
        source_text=source_text,
        normalized_source_text=normalize_japanese_text(source_text),
        markup_context=EpubMarkupContext(
            file_href=chapter_href,
            xpath=xpath,
            tag=tag,
            attrs=dict(element.attrib),
            text_node_index=0,
        ),
    )


def _element_text(element: ElementTree.Element) -> str:
    return collapse_whitespace("".join(element.itertext()))


def _walk_with_xpath(
    element: ElementTree.Element, xpath: str
) -> Iterable[tuple[ElementTree.Element, str]]:
    yield element, xpath
    tag_counts: dict[str, int] = defaultdict(int)
    for child in list(element):
        tag = local_name(child.tag)
        tag_counts[tag] += 1
        child_xpath = f"{xpath}/{tag}[{tag_counts[tag]}]"
        yield from _walk_with_xpath(child, child_xpath)


def _chapter_title(blocks: list[BlockIR]) -> str | None:
    for block in blocks:
        if block.kind == "heading":
            return block.source_text
    return None
