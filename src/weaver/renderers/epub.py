"""Phase 8 EPUB renderer.

Reads the source EPUB, replaces translated block text in-place by walking
`markup_context.xpath`, and writes a new `.translated.epub` next to the
markdown export directory. Untranslated blocks remain on the source text.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

from ebooklib import epub
from ebooklib.epub import EpubBook, EpubException, EpubHtml, EpubNcx

from weaver.core.ir import BlockIR, DocumentIR
from weaver.errors import EpubWriteError

XHTML_NAMESPACE = "http://www.w3.org/1999/xhtml"
EPUB_NAMESPACE = "http://www.idpf.org/2007/ops"

ElementTree.register_namespace("", XHTML_NAMESPACE)
ElementTree.register_namespace("epub", EPUB_NAMESPACE)

XPATH_STEP_PATTERN = re.compile(r"^([^\[\]/]+)(?:\[(\d+)\])?$")


@dataclass(frozen=True)
class EpubRenderResult:
    """EPUB render result."""

    output_path: Path
    translated_blocks: int
    fallback_blocks: int


def render_translated_epub(
    *,
    source_epub_path: Path,
    output_path: Path,
    document: DocumentIR,
    translations_by_segment_id: dict[str, str],
) -> EpubRenderResult:
    """Write a translated EPUB to `output_path`.

    Args:
        source_epub_path: Path to the original EPUB.
        output_path: Destination for the translated EPUB.
        document: DocumentIR produced by the EPUB reader for `source_epub_path`.
        translations_by_segment_id: Mapping of segment id to translated text.
            Segments missing from the map keep their source text in the output.

    Returns:
        EpubRenderResult with output path and block counters.

    Raises:
        EpubWriteError: If the EPUB cannot be written.
    """

    try:
        book = epub.read_epub(source_epub_path)
    except (OSError, EpubException) as exc:
        raise EpubWriteError(
            f"Failed to reopen EPUB '{source_epub_path}'. "
            "Likely cause: source EPUB moved or became unreadable. "
            "Next command: rerun `weaver init <path-to-epub>` for a fresh project."
        ) from exc

    blocks_by_href = _group_blocks_by_href(document)
    items_by_href = {
        item.get_name(): item for item in book.get_items() if isinstance(item, EpubHtml)
    }

    translated = 0
    fallback = 0
    for href, blocks in blocks_by_href.items():
        item = items_by_href.get(href)
        if item is None:
            fallback += len(blocks)
            continue
        try:
            root = ElementTree.fromstring(item.get_content())
        except ElementTree.ParseError as exc:
            raise EpubWriteError(
                f"Failed to parse chapter '{href}'. "
                "Likely cause: source EPUB contains malformed XHTML. "
                "Next command: open the source EPUB in Calibre to repair structure."
            ) from exc

        for block in blocks:
            translation = translations_by_segment_id.get(block.id)
            if translation is None:
                fallback += 1
                continue
            element = _resolve_xpath(root, block.markup_context.xpath)
            if element is None:
                fallback += 1
                continue
            _replace_text(element, translation)
            translated += 1

        item.set_content(ElementTree.tostring(root, encoding="utf-8", xml_declaration=True))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    _ensure_navigation_items(book)
    try:
        epub.write_epub(str(output_path), book)
    except (OSError, EpubException) as exc:
        raise EpubWriteError(
            f"Failed to write translated EPUB to '{output_path}'. "
            "Likely cause: target directory is not writable or disk is full. "
            "Next command: check filesystem permissions or free space."
        ) from exc

    return EpubRenderResult(
        output_path=output_path,
        translated_blocks=translated,
        fallback_blocks=fallback,
    )


def _ensure_navigation_items(book: EpubBook) -> None:
    """Add an NCX item if the source EPUB did not ship one.

    ebooklib always writes `<spine toc="ncx">`. If no `EpubNcx` item is
    registered the resulting EPUB cannot be reopened by ebooklib and most
    EPUB 2 readers reject it.
    """

    if any(isinstance(item, EpubNcx) for item in book.get_items()):
        return
    book.add_item(EpubNcx(uid="ncx", file_name="toc.ncx"))


def _group_blocks_by_href(document: DocumentIR) -> dict[str, list[BlockIR]]:
    grouped: dict[str, list[BlockIR]] = defaultdict(list)
    for chapter in document.chapters:
        for block in chapter.blocks:
            grouped[block.markup_context.file_href].append(block)
    return grouped


def _resolve_xpath(root: ElementTree.Element, xpath: str) -> ElementTree.Element | None:
    steps = [step for step in xpath.split("/") if step]
    if not steps:
        return None
    root_match = XPATH_STEP_PATTERN.match(steps[0])
    if root_match is None or _local_name(root.tag) != root_match.group(1):
        return None
    current = root
    for step in steps[1:]:
        match = XPATH_STEP_PATTERN.match(step)
        if match is None:
            return None
        tag = match.group(1)
        index = int(match.group(2) or "1")
        children = [child for child in list(current) if _local_name(child.tag) == tag]
        if not 1 <= index <= len(children):
            return None
        current = children[index - 1]
    return current


def _replace_text(element: ElementTree.Element, translation: str) -> None:
    for child in list(element):
        element.remove(child)
    element.text = translation


def _local_name(tag: str) -> str:
    return tag.rsplit("}", maxsplit=1)[-1]
