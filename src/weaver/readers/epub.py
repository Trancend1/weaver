"""EPUB source reader."""

from __future__ import annotations

import posixpath
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import replace
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile

from ebooklib import epub
from ebooklib.epub import EpubBook, EpubException, EpubItem

from weaver.core.epub_structure import (
    ChapterTranslationContext,
    EpubPackageMetadata,
    ImageRole,
    ManifestResource,
    NavigationResource,
    ParsedEpub,
    PreservationRecord,
    ResourceCategory,
    SpineResource,
    TranslationPreservationContext,
)
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
from weaver.readers.epub_validation import validate_epub_structure
from weaver.readers.html_blocks import (
    TEXT_BLOCK_TAGS,
    block_kind,
    collapse_whitespace,
    local_name,
)

DOCUMENT_MEDIA_TYPES = {"application/xhtml+xml", "text/html"}
IMAGE_MEDIA_TYPES = {"image/jpeg", "image/png", "image/webp", "image/svg+xml"}


def parse_epub_structure(path: Path) -> ParsedEpub:
    """Parse EPUB package metadata and structure without changing import behavior.

    Phase F uses this additive contract as the safe foundation for richer EPUB
    import preview, validation, and export-preservation work. The existing
    ``read_epub`` -> ``DocumentIR`` path remains the active translation/import
    contract for now.
    """

    archive_info = _archive_info(path)
    opf_path = _container_opf_path(path)
    opf_root = _opf_root(path, opf_path) if opf_path is not None else None
    try:
        book = epub.read_epub(path)
    except (OSError, KeyError, ElementTree.ParseError, EpubException) as exc:
        if opf_root is None:
            raise _epub_structure_read_error(path) from exc
        book = None

    manifest = _read_manifest(book, opf_root=opf_root, opf_path=opf_path, archive_info=archive_info)
    if book is None:
        if opf_root is None:
            raise _epub_structure_read_error(path)
        metadata = _read_opf_package_metadata(opf_root)
    else:
        metadata = _read_package_metadata(book)
    spine = _read_spine_resources(book, manifest=manifest, opf_root=opf_root)
    manifest = _with_image_reference_data(path, manifest=manifest, spine=spine)
    resources = [item for item in manifest if item.category != "chapter"]
    images = [item for item in manifest if item.category == "image"]
    navigation = _read_navigation(path, manifest=manifest, spine=spine, opf_path=opf_path)
    return ParsedEpub(
        package_path=path,
        opf_path=opf_path or (None if book is None else _opf_path(book)),
        metadata=metadata,
        manifest=manifest,
        spine=spine,
        navigation=navigation,
        resources=resources,
        images=images,
        validation_issues=validate_epub_structure(
            manifest=manifest,
            spine=spine,
            navigation=navigation,
            image_reference_paths=_scan_image_references(path, manifest=manifest),
            metadata_title_missing=book is not None and _metadata_text(book, "title") is None,
            metadata_language_missing=book is not None and _metadata_text(book, "language") is None,
        ),
        spine_toc=_spine_toc(opf_root),
        page_progression_direction=_page_progression_direction(opf_root),
        preservation_context=_build_preservation_context(
            manifest=manifest,
            spine=spine,
            navigation=navigation,
        ),
    )


def _epub_structure_read_error(path: Path) -> EpubReadError:
    return EpubReadError(
        f"Failed to read EPUB structure for '{path}'. "
        "Likely cause: invalid EPUB structure. "
        "Next command: run `weaver init <path-to-epub>` with a valid EPUB file."
    )


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


def read_chapter_excerpt(path: Path, resolved_path: str, *, limit: int = 280) -> str | None:
    """Return a short, read-only text excerpt for a spine chapter.

    Used by the EPUB preview surface so translators can eyeball chapter text
    before import. It never translates, persists, or alters ``DocumentIR``.
    """

    root = _archive_xml_root(path, resolved_path)
    if root is None:
        return None
    body = next((el for el in root.iter() if local_name(el.tag) == "body"), root)
    text = _element_text(body)
    if not text:
        return None
    if len(text) > limit:
        return text[:limit].rstrip() + "…"
    return text


def _read_metadata(book: EpubBook) -> DocumentMetadata:
    metadata = _read_package_metadata(book)
    return DocumentMetadata(
        title=metadata.title,
        author=metadata.creator,
        language=metadata.language,
        identifier=metadata.identifier,
        publisher=metadata.publisher,
        description=metadata.description,
    )


def _archive_info(path: Path) -> dict[str, int]:
    with ZipFile(path, "r") as archive:
        return {item.filename: item.file_size for item in archive.infolist()}


def _container_opf_path(path: Path) -> str | None:
    try:
        with ZipFile(path, "r") as archive:
            container = ElementTree.fromstring(archive.read("META-INF/container.xml"))
    except (OSError, KeyError, ElementTree.ParseError):
        return None
    for element in container.iter():
        if local_name(element.tag) == "rootfile":
            full_path = element.attrib.get("full-path")
            if isinstance(full_path, str) and full_path.strip():
                return full_path.strip()
    return None


def _opf_root(path: Path, opf_path: str | None) -> ElementTree.Element | None:
    if opf_path is None:
        return None
    try:
        with ZipFile(path, "r") as archive:
            return ElementTree.fromstring(archive.read(opf_path))
    except (OSError, KeyError, ElementTree.ParseError):
        return None


def _read_opf_package_metadata(root: ElementTree.Element) -> EpubPackageMetadata:
    def values(name: str) -> list[str]:
        return [
            text
            for element in root.iter()
            if local_name(element.tag) == name and (text := _element_direct_text(element))
        ]

    opf_meta = _opf_metadata_from_root(root)
    return EpubPackageMetadata(
        title=_first(values("title")) or "Untitled",
        creator=_first(values("creator")),
        language=_first(values("language")) or "ja",
        identifier=_first(values("identifier")),
        publisher=_first(values("publisher")),
        description=_first(values("description")),
        contributors=values("contributor"),
        dates=values("date"),
        subjects=values("subject"),
        rights=values("rights"),
        sources=values("source"),
        coverages=values("coverage"),
        relations=values("relation"),
        types=values("type"),
        formats=values("format"),
        modified=_first_opf_meta(opf_meta, "dcterms:modified"),
        cover=_first_opf_meta(opf_meta, "cover"),
        series=_first_opf_meta(opf_meta, "calibre:series"),
        series_index=_first_opf_meta(opf_meta, "calibre:series_index"),
        collection=_first_opf_meta(opf_meta, "belongs-to-collection"),
        collection_type=_first_opf_meta(opf_meta, "collection-type"),
        group_position=_first_opf_meta(opf_meta, "group-position"),
        raw=_raw_opf_metadata(opf_meta),
    )


def _first(values: list[str]) -> str | None:
    return values[0] if values else None


def _element_direct_text(element: ElementTree.Element) -> str | None:
    if element.text is None:
        return None
    text = element.text.strip()
    return text or None


def _read_package_metadata(book: EpubBook) -> EpubPackageMetadata:
    opf_meta = _opf_metadata(book)
    return EpubPackageMetadata(
        title=_metadata_text(book, "title") or "Untitled",
        creator=_metadata_text(book, "creator"),
        language=_metadata_text(book, "language") or "ja",
        identifier=_metadata_text(book, "identifier"),
        publisher=_metadata_text(book, "publisher"),
        description=_metadata_text(book, "description"),
        contributors=_metadata_values(book, "contributor"),
        dates=_metadata_values(book, "date"),
        subjects=_metadata_values(book, "subject"),
        rights=_metadata_values(book, "rights"),
        sources=_metadata_values(book, "source"),
        coverages=_metadata_values(book, "coverage"),
        relations=_metadata_values(book, "relation"),
        types=_metadata_values(book, "type"),
        formats=_metadata_values(book, "format"),
        modified=_first_opf_meta(opf_meta, "dcterms:modified"),
        cover=_first_opf_meta(opf_meta, "cover"),
        series=_first_opf_meta(opf_meta, "calibre:series"),
        series_index=_first_opf_meta(opf_meta, "calibre:series_index"),
        collection=_first_opf_meta(opf_meta, "belongs-to-collection"),
        collection_type=_first_opf_meta(opf_meta, "collection-type"),
        group_position=_first_opf_meta(opf_meta, "group-position"),
        raw=_raw_metadata(book, opf_meta),
    )


def _metadata_text(book: EpubBook, name: str) -> str | None:
    values = _metadata_values(book, name)
    return values[0] if values else None


def _metadata_values(book: EpubBook, name: str) -> list[str]:
    entries = book.get_metadata("DC", name)
    values: list[str] = []
    for value, _attrs in entries:
        if not isinstance(value, str):
            continue
        text = value.strip()
        if text:
            values.append(text)
    return values


def _opf_metadata(book: EpubBook) -> dict[str, list[str]]:
    metadata: dict[str, list[str]] = defaultdict(list)
    for value, attrs in book.get_metadata("OPF", "meta"):
        key = _opf_meta_key(attrs)
        if key is None:
            continue
        text = _opf_meta_value(value, attrs)
        if text is not None:
            metadata[key].append(text)
    return dict(metadata)


def _opf_metadata_from_root(root: ElementTree.Element) -> dict[str, list[str]]:
    metadata: dict[str, list[str]] = defaultdict(list)
    for element in root.iter():
        if local_name(element.tag) != "meta":
            continue
        key = _opf_meta_key(element.attrib)
        if key is None:
            continue
        text = _opf_meta_value(element.text, element.attrib)
        if text is not None:
            metadata[key].append(text)
    return dict(metadata)


def _opf_meta_key(attrs: dict[str, str]) -> str | None:
    key = attrs.get("property") or attrs.get("name")
    if not isinstance(key, str):
        return None
    text = key.strip()
    return text or None


def _opf_meta_value(value: object, attrs: dict[str, str]) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    content = attrs.get("content")
    if isinstance(content, str) and content.strip():
        return content.strip()
    return None


def _first_opf_meta(metadata: dict[str, list[str]], name: str) -> str | None:
    values = metadata.get(name, [])
    return values[0] if values else None


def _raw_metadata(book: EpubBook, opf_meta: dict[str, list[str]]) -> dict[str, list[str]]:
    raw = _raw_opf_metadata(opf_meta)
    for namespace, namespace_values in getattr(book, "metadata", {}).items():
        if namespace in {"http://purl.org/dc/elements/1.1/", "http://www.idpf.org/2007/opf"}:
            continue
        if not isinstance(namespace_values, dict):
            continue
        for name, entries in namespace_values.items():
            values = _metadata_entry_values(entries)
            if values:
                raw[f"{namespace}:{name}"] = values
    return raw


def _raw_opf_metadata(opf_meta: dict[str, list[str]]) -> dict[str, list[str]]:
    raw: dict[str, list[str]] = {}
    known_opf = {
        "dcterms:modified",
        "cover",
        "calibre:series",
        "calibre:series_index",
        "belongs-to-collection",
        "collection-type",
        "group-position",
    }
    for name, values in opf_meta.items():
        if name not in known_opf and values:
            raw[f"OPF:meta:{name}"] = values
    return raw


def _metadata_entry_values(entries: object) -> list[str]:
    if not entries:
        return []
    values: list[str] = []
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, tuple) or not entry:
            continue
        value = entry[0]
        if isinstance(value, str) and value.strip():
            values.append(value.strip())
    return values


def _read_spine_items(book: EpubBook) -> list[EpubItem]:
    items: list[EpubItem] = []
    for item_id, _linear in book.spine:
        item = book.get_item_with_id(item_id)
        if (
            item is not None
            and _item_media_type(item) in DOCUMENT_MEDIA_TYPES
            and not _is_navigation_item(item)
        ):
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


def _read_manifest(
    book: EpubBook | None,
    *,
    opf_root: ElementTree.Element | None,
    opf_path: str | None,
    archive_info: dict[str, int],
) -> list[ManifestResource]:
    if opf_root is not None:
        return _read_manifest_from_opf(opf_root, opf_path=opf_path, archive_info=archive_info)

    resources: list[ManifestResource] = []
    if book is None:
        return resources
    spine_ids = _spine_ids_from_book(book)
    cover_id = _read_package_metadata(book).cover
    for item in book.get_items():
        media_type = _item_media_type(item)
        item_id = _item_id(item)
        href = item.get_name()
        properties = _item_properties(item)
        resources.append(
            _manifest_resource(
                item_id=item_id,
                href=href,
                opf_path=None,
                media_type=media_type,
                properties=properties,
                archive_info=archive_info,
                spine_ids=spine_ids,
                cover_id=cover_id,
            )
        )
    return resources


def _read_manifest_from_opf(
    root: ElementTree.Element, *, opf_path: str | None, archive_info: dict[str, int]
) -> list[ManifestResource]:
    spine_ids = _spine_ids_from_opf(root)
    cover_id = _read_opf_package_metadata(root).cover
    resources: list[ManifestResource] = []
    for element in root.iter():
        if local_name(element.tag) != "item":
            continue
        href = element.attrib.get("href", "").strip()
        if not href:
            continue
        properties = _split_properties(element.attrib.get("properties"))
        resources.append(
            _manifest_resource(
                item_id=_optional_attr(element, "id"),
                href=href,
                opf_path=opf_path,
                media_type=element.attrib.get("media-type", "").strip(),
                properties=properties,
                archive_info=archive_info,
                spine_ids=spine_ids,
                cover_id=cover_id,
            )
        )
    return resources


def _manifest_resource(
    *,
    item_id: str | None,
    href: str,
    opf_path: str | None,
    media_type: str,
    properties: list[str],
    archive_info: dict[str, int],
    spine_ids: set[str],
    cover_id: str | None,
) -> ManifestResource:
    resolved_path = _resolve_internal_path(opf_path, href)
    category = _resource_category(media_type, properties=properties)
    is_navigation = category in {"nav", "ncx"} or "nav" in properties
    is_image = category == "image"
    return ManifestResource(
        id=item_id,
        href=href,
        resolved_path=resolved_path,
        media_type=media_type,
        category=category,
        properties=properties,
        exists_in_archive=resolved_path in archive_info,
        is_spine_item=item_id in spine_ids if item_id is not None else False,
        is_navigation=is_navigation,
        is_stylesheet=category == "css",
        is_image=is_image,
        is_font=category == "font",
        is_script=category == "script",
        is_cover_candidate=is_image and (item_id == cover_id or "cover-image" in properties),
        image_role=_image_role(
            item_id=item_id,
            href=href,
            media_type=media_type,
            properties=properties,
            cover_id=cover_id,
        ),
        image_kind=_image_kind(
            item_id=item_id,
            href=href,
            media_type=media_type,
            properties=properties,
            cover_id=cover_id,
        ),
        manifest_id=item_id,
        byte_size=archive_info.get(resolved_path),
        preview_available=category == "image" and resolved_path in archive_info,
        referenced_by=[],
    )


def _resolve_internal_path(opf_path: str | None, href: str) -> str:
    if opf_path is None:
        return posixpath.normpath(href)
    base = posixpath.dirname(opf_path)
    return posixpath.normpath(posixpath.join(base, href))


def _image_role(
    *,
    item_id: str | None,
    href: str,
    media_type: str,
    properties: list[str],
    cover_id: str | None,
) -> ImageRole:
    if not _is_image_media_type(media_type):
        return "unknown"
    text = f"{item_id or ''} {href}".lower()
    if item_id == cover_id or "cover-image" in properties or "cover" in text:
        return "cover"
    if any(token in text for token in ["color", "colour", "カラー", "口絵", "illust"]):
        return "color_illustration"
    if any(token in text for token in ["character", "chara", "profile", "人物", "キャラ"]):
        return "character_page"
    if any(token in text for token in ["divider", "separator", "ornament", "line"]):
        return "divider"
    if any(token in text for token in ["publisher", "logo", "imprint"]):
        return "publisher_logo"
    if any(token in text for token in ["insert", "art", "挿絵", "挿し絵"]):
        return "insert_illustration"
    return "unknown"


def _image_kind(
    *,
    item_id: str | None,
    href: str,
    media_type: str,
    properties: list[str],
    cover_id: str | None,
) -> str:
    role = _image_role(
        item_id=item_id,
        href=href,
        media_type=media_type,
        properties=properties,
        cover_id=cover_id,
    )
    if role == "cover":
        return "cover"
    if role in {"color_illustration", "insert_illustration", "character_page"}:
        return "illustration"
    if role in {"divider", "publisher_logo"}:
        return "decorative"
    return "unknown"


def _is_image_media_type(media_type: str) -> bool:
    return media_type in IMAGE_MEDIA_TYPES or media_type.startswith("image/")


def _with_image_reference_data(
    path: Path, *, manifest: list[ManifestResource], spine: list[SpineResource]
) -> list[ManifestResource]:
    manifest_by_path = {item.resolved_path: item for item in manifest}
    spine_by_path = {
        item.resolved_path: item.index for item in spine if item.resolved_path is not None
    }
    references = _scan_image_references(path, manifest=manifest)
    updated: list[ManifestResource] = []
    for item in manifest:
        if item.category != "image":
            updated.append(item)
            continue
        referring_documents = sorted(references.get(item.resolved_path, set()))
        linked_spine_index = next(
            (
                spine_by_path.get(document_path)
                for document_path in referring_documents
                if document_path in spine_by_path
            ),
            None,
        )
        width, height = _image_dimensions(path, item)
        updated.append(
            replace(
                item,
                referenced_by=[
                    manifest_by_path[document_path].href
                    for document_path in referring_documents
                    if document_path in manifest_by_path
                ],
                linked_spine_index=linked_spine_index,
                width=width,
                height=height,
            )
        )
    return updated


def _scan_image_references(path: Path, *, manifest: list[ManifestResource]) -> dict[str, set[str]]:
    references: dict[str, set[str]] = defaultdict(set)
    for item in manifest:
        if item.category != "chapter" or not item.exists_in_archive:
            continue
        root = _archive_xml_root(path, item.resolved_path)
        if root is None:
            continue
        for image_href in _iter_image_hrefs(root):
            resolved = _resolve_internal_path(item.resolved_path, image_href)
            references[resolved].add(item.resolved_path)
    return references


def _iter_image_hrefs(root: ElementTree.Element) -> Iterable[str]:
    for element in root.iter():
        tag = local_name(element.tag)
        if tag == "img":
            href = element.attrib.get("src")
            if href:
                yield href
        if tag == "image":
            for key, value in element.attrib.items():
                if local_name(key) == "href" and value:
                    yield value


def _image_dimensions(path: Path, item: ManifestResource) -> tuple[int | None, int | None]:
    if item.media_type != "image/png" or not item.exists_in_archive:
        return None, None
    try:
        with ZipFile(path, "r") as archive:
            data = archive.read(item.resolved_path)[:24]
    except (OSError, KeyError):
        return None, None
    if len(data) >= 16 and data.startswith(b"\x89PNG\r\n\x1a\n"):
        return int.from_bytes(data[8:12], "big"), int.from_bytes(data[12:16], "big")
    return None, None


def _spine_ids_from_book(book: EpubBook) -> set[str]:
    return {str(item_id) for item_id, _linear in book.spine}


def _spine_ids_from_opf(root: ElementTree.Element) -> set[str]:
    return {
        itemref.attrib["idref"]
        for itemref in root.iter()
        if local_name(itemref.tag) == "itemref" and "idref" in itemref.attrib
    }


def _optional_attr(element: ElementTree.Element, name: str) -> str | None:
    value = element.attrib.get(name)
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _split_properties(value: str | None) -> list[str]:
    if value is None:
        return []
    return [item for item in value.split() if item]


def _read_spine_resources(
    book: EpubBook | None,
    *,
    manifest: list[ManifestResource],
    opf_root: ElementTree.Element | None,
) -> list[SpineResource]:
    if opf_root is not None:
        return _read_spine_resources_from_manifest(opf_root, manifest)

    resources: list[SpineResource] = []
    if book is None:
        return resources
    for order, (item_id, linear_value) in enumerate(book.spine):
        item = book.get_item_with_id(item_id)
        if item is None:
            continue
        media_type = _item_media_type(item)
        if media_type not in DOCUMENT_MEDIA_TYPES or _is_navigation_item(item):
            continue
        resources.append(
            SpineResource(
                idref=str(item_id),
                index=order,
                href=item.get_name(),
                resolved_path=item.get_name(),
                media_type=media_type,
                order=order,
                linear=linear_value != "no",
                exists_in_manifest=True,
                exists_in_archive=True,
                is_navigation=_is_navigation_item(item),
                properties=_item_properties(item),
            )
        )
    return resources


def _read_spine_resources_from_manifest(
    root: ElementTree.Element, manifest: list[ManifestResource]
) -> list[SpineResource]:
    by_id = {item.id: item for item in manifest if item.id is not None}
    resources: list[SpineResource] = []
    for order, itemref in enumerate(
        element for element in root.iter() if local_name(element.tag) == "itemref"
    ):
        item_id = itemref.attrib.get("idref")
        if item_id is None:
            continue
        item = by_id.get(item_id)
        if item is not None and item.is_navigation:
            continue
        resources.append(
            SpineResource(
                idref=item_id,
                index=order,
                href=None if item is None else item.href,
                resolved_path=None if item is None else item.resolved_path,
                media_type=None if item is None else item.media_type,
                order=order,
                linear=itemref.attrib.get("linear") != "no",
                exists_in_manifest=item is not None,
                exists_in_archive=False if item is None else item.exists_in_archive,
                is_navigation=False if item is None else item.is_navigation,
                page_spread=itemref.attrib.get("page-spread"),
                properties=_split_properties(itemref.attrib.get("properties")),
            )
        )
    return resources


def _spine_element(root: ElementTree.Element | None) -> ElementTree.Element | None:
    if root is None:
        return None
    for element in root.iter():
        if local_name(element.tag) == "spine":
            return element
    return None


def _spine_toc(root: ElementTree.Element | None) -> str | None:
    spine = _spine_element(root)
    return None if spine is None else _optional_attr(spine, "toc")


def _page_progression_direction(root: ElementTree.Element | None) -> str | None:
    spine = _spine_element(root)
    return None if spine is None else _optional_attr(spine, "page-progression-direction")


def _read_navigation(
    path: Path,
    *,
    manifest: list[ManifestResource],
    spine: list[SpineResource],
    opf_path: str | None,
) -> list[NavigationResource]:
    entries: list[NavigationResource] = []
    manifest_by_path = {item.resolved_path: item for item in manifest}
    spine_by_path = {
        item.resolved_path: item.index for item in spine if item.resolved_path is not None
    }
    order = 0
    for item in manifest:
        if item.category == "nav" and item.exists_in_archive:
            for entry in _read_nav_entries(path, item, manifest_by_path, spine_by_path):
                entries.append(_replace_navigation_order(entry, order))
                order += 1
        if item.category == "ncx" and item.exists_in_archive:
            for entry in _read_ncx_entries(path, item, manifest_by_path, spine_by_path):
                entries.append(_replace_navigation_order(entry, order))
                order += 1
    return entries


def _build_preservation_context(
    *,
    manifest: list[ManifestResource],
    spine: list[SpineResource],
    navigation: list[NavigationResource],
) -> TranslationPreservationContext:
    manifest_by_path = {item.resolved_path: item for item in manifest}
    nav_labels_by_path = _nav_labels_by_resolved_path(navigation)
    chapters: list[ChapterTranslationContext] = []
    for spine_item in spine:
        if spine_item.resolved_path is None or spine_item.href is None:
            continue
        manifest_item = manifest_by_path.get(spine_item.resolved_path)
        if manifest_item is None or manifest_item.category != "chapter":
            continue
        chapters.append(
            ChapterTranslationContext(
                manifest_id=manifest_item.id,
                href=manifest_item.href,
                resolved_path=manifest_item.resolved_path,
                spine_index=spine_item.index,
                nav_labels=nav_labels_by_path.get(spine_item.resolved_path, []),
            )
        )

    records = [_preservation_record(item) for item in manifest if item.category != "chapter"]
    return TranslationPreservationContext(chapters=chapters, records=records)


def _nav_labels_by_resolved_path(
    navigation: list[NavigationResource],
) -> dict[str, list[str]]:
    labels: dict[str, list[str]] = defaultdict(list)
    for item in _iter_navigation_entries(navigation):
        if item.resolved_path is not None and item.label not in labels[item.resolved_path]:
            labels[item.resolved_path].append(item.label)
    return dict(labels)


def _iter_navigation_entries(
    navigation: list[NavigationResource],
) -> Iterable[NavigationResource]:
    for item in navigation:
        yield item
        yield from _iter_navigation_entries(item.children)


def _preservation_record(item: ManifestResource) -> PreservationRecord:
    preservation_kind = _preservation_kind(item)
    is_image = item.category == "image"
    return PreservationRecord(
        resource_id=item.id,
        href=item.href,
        resolved_path=item.resolved_path,
        category=item.category,
        preservation_kind=preservation_kind,
        image_role=item.image_role if is_image else None,
        image_kind=item.image_kind if is_image else None,
        referenced_by=item.referenced_by,
        linked_spine_index=item.linked_spine_index,
        placeholder_kind="future_ocr_image_text" if is_image else None,
        future_ocr_placeholder=is_image,
    )


def _preservation_kind(item: ManifestResource) -> str:
    if item.category == "image":
        return "image"
    if item.category == "css":
        return "style"
    if item.category == "font":
        return "font"
    if item.category in {"nav", "ncx"}:
        return "navigation"
    return "supporting"


def _read_nav_entries(
    path: Path,
    item: ManifestResource,
    manifest_by_path: dict[str, ManifestResource],
    spine_by_path: dict[str, int],
) -> list[NavigationResource]:
    root = _archive_xml_root(path, item.resolved_path)
    if root is None:
        return []
    entries: list[NavigationResource] = []
    for nav in (element for element in root.iter() if local_name(element.tag) == "nav"):
        nav_type = _navigation_type(_epub_type(nav))
        entries.extend(
            _nav_list_entries(
                nav,
                source_type="nav",
                nav_type=nav_type,
                base_path=item.resolved_path,
                manifest_by_path=manifest_by_path,
                spine_by_path=spine_by_path,
                depth=0,
            )
        )
    return entries


def _nav_list_entries(
    parent: ElementTree.Element,
    *,
    source_type: str,
    nav_type: str,
    base_path: str,
    manifest_by_path: dict[str, ManifestResource],
    spine_by_path: dict[str, int],
    depth: int,
) -> list[NavigationResource]:
    ol = next((child for child in list(parent) if local_name(child.tag) == "ol"), None)
    if ol is None:
        return []
    entries: list[NavigationResource] = []
    for li in (child for child in list(ol) if local_name(child.tag) == "li"):
        label_element = next(
            (child for child in list(li) if local_name(child.tag) in {"a", "span"}), None
        )
        if label_element is None:
            continue
        href = label_element.attrib.get("href")
        label = _element_text(label_element)
        children = [
            child_entry
            for child in list(li)
            if local_name(child.tag) == "ol"
            for child_entry in _nav_entries_from_ol(
                child,
                source_type=source_type,
                nav_type=nav_type,
                base_path=base_path,
                manifest_by_path=manifest_by_path,
                spine_by_path=spine_by_path,
                depth=depth + 1,
            )
        ]
        entries.append(
            _navigation_resource(
                source_type=source_type,
                nav_type=nav_type,
                label=label,
                href=href,
                base_path=base_path,
                depth=depth,
                children=children,
                manifest_by_path=manifest_by_path,
                spine_by_path=spine_by_path,
            )
        )
    return entries


def _nav_entries_from_ol(
    ol: ElementTree.Element,
    *,
    source_type: str,
    nav_type: str,
    base_path: str,
    manifest_by_path: dict[str, ManifestResource],
    spine_by_path: dict[str, int],
    depth: int,
) -> list[NavigationResource]:
    wrapper = ElementTree.Element("wrapper")
    wrapper.append(ol)
    return _nav_list_entries(
        wrapper,
        source_type=source_type,
        nav_type=nav_type,
        base_path=base_path,
        manifest_by_path=manifest_by_path,
        spine_by_path=spine_by_path,
        depth=depth,
    )


def _read_ncx_entries(
    path: Path,
    item: ManifestResource,
    manifest_by_path: dict[str, ManifestResource],
    spine_by_path: dict[str, int],
) -> list[NavigationResource]:
    root = _archive_xml_root(path, item.resolved_path)
    if root is None:
        return []
    nav_map = next(
        (element for element in root.iter() if local_name(element.tag) == "navMap"), None
    )
    if nav_map is None:
        return []
    return [
        _ncx_nav_point(
            nav_point,
            base_path=item.resolved_path,
            depth=0,
            manifest_by_path=manifest_by_path,
            spine_by_path=spine_by_path,
        )
        for nav_point in list(nav_map)
        if local_name(nav_point.tag) == "navPoint"
    ]


def _ncx_nav_point(
    nav_point: ElementTree.Element,
    *,
    base_path: str,
    depth: int,
    manifest_by_path: dict[str, ManifestResource],
    spine_by_path: dict[str, int],
) -> NavigationResource:
    label = _ncx_label(nav_point)
    href = _ncx_content_src(nav_point)
    children = [
        _ncx_nav_point(
            child,
            base_path=base_path,
            depth=depth + 1,
            manifest_by_path=manifest_by_path,
            spine_by_path=spine_by_path,
        )
        for child in list(nav_point)
        if local_name(child.tag) == "navPoint"
    ]
    return _navigation_resource(
        source_type="ncx",
        nav_type="toc",
        label=label,
        href=href,
        base_path=base_path,
        depth=depth,
        children=children,
        manifest_by_path=manifest_by_path,
        spine_by_path=spine_by_path,
        play_order=_optional_int(nav_point.attrib.get("playOrder")),
    )


def _archive_xml_root(path: Path, resolved_path: str) -> ElementTree.Element | None:
    try:
        with ZipFile(path, "r") as archive:
            return ElementTree.fromstring(archive.read(resolved_path))
    except (OSError, KeyError, ElementTree.ParseError):
        return None


def _navigation_resource(
    *,
    source_type: str,
    nav_type: str,
    label: str,
    href: str | None,
    base_path: str,
    depth: int,
    children: list[NavigationResource],
    manifest_by_path: dict[str, ManifestResource],
    spine_by_path: dict[str, int],
    play_order: int | None = None,
) -> NavigationResource:
    resolved_path, fragment = _resolve_nav_href(base_path, href)
    manifest_item = manifest_by_path.get(resolved_path) if resolved_path is not None else None
    linked_spine_index = spine_by_path.get(resolved_path) if resolved_path is not None else None
    return NavigationResource(
        source_type=source_type,  # type: ignore[arg-type]
        nav_type=nav_type,  # type: ignore[arg-type]
        label=label,
        href=href,
        resolved_path=resolved_path,
        fragment=fragment,
        order=0,
        depth=depth,
        children=children,
        linked_manifest_id=None if manifest_item is None else manifest_item.id,
        linked_spine_index=linked_spine_index,
        play_order=play_order,
    )


def _replace_navigation_order(entry: NavigationResource, order: int) -> NavigationResource:
    return replace(entry, order=order)


def _resolve_nav_href(base_path: str, href: str | None) -> tuple[str | None, str | None]:
    if href is None:
        return None, None
    path_part, separator, fragment = href.partition("#")
    resolved = base_path if not path_part else _resolve_internal_path(base_path, path_part)
    return resolved, fragment if separator else None


def _epub_type(element: ElementTree.Element) -> str | None:
    for key, value in element.attrib.items():
        if local_name(key) == "type" and isinstance(value, str):
            return value.strip() or None
    return None


def _navigation_type(value: str | None) -> str:
    if value in {"toc", "landmarks", "page-list", "lot", "loa"}:
        return value
    return "unknown"


def _ncx_label(nav_point: ElementTree.Element) -> str:
    for element in nav_point.iter():
        if local_name(element.tag) == "text" and (text := _element_direct_text(element)):
            return text
    return "Untitled"


def _ncx_content_src(nav_point: ElementTree.Element) -> str | None:
    for element in list(nav_point):
        if local_name(element.tag) == "content":
            return _optional_attr(element, "src")
    return None


def _optional_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _resource_category(media_type: str, *, properties: list[str] | None = None) -> ResourceCategory:
    properties = properties or []
    if "nav" in properties:
        return "nav"
    if media_type in DOCUMENT_MEDIA_TYPES:
        return "chapter"
    if media_type == "text/css":
        return "css"
    if _is_image_media_type(media_type):
        return "image"
    if media_type == "application/x-dtbncx+xml":
        return "ncx"
    if media_type.startswith("font/") or media_type in {
        "application/font-woff",
        "application/vnd.ms-opentype",
    }:
        return "font"
    if media_type in {"application/javascript", "text/javascript"}:
        return "script"
    if media_type.startswith("audio/"):
        return "audio"
    if media_type.startswith("video/"):
        return "video"
    if media_type in {"application/oebps-package+xml", "application/epub+zip"}:
        return "package"
    if media_type:
        return "unknown"
    return "supporting"


def _is_navigation_item(item: EpubItem) -> bool:
    item_id = _item_id(item)
    item_name = item.get_name().lower()
    if item_id == "nav" or item_name.endswith("nav.xhtml") or item_name.endswith("nav.html"):
        return True
    properties = getattr(item, "properties", [])
    return isinstance(properties, list) and "nav" in properties


def _item_properties(item: EpubItem) -> list[str]:
    properties = getattr(item, "properties", [])
    if isinstance(properties, list):
        return [value for value in properties if isinstance(value, str)]
    return []


def _item_id(item: EpubItem) -> str | None:
    item_id = getattr(item, "id", None)
    return item_id if isinstance(item_id, str) else None


def _opf_path(book: EpubBook) -> str | None:
    package_path = getattr(book, "package_path", None)
    return package_path if isinstance(package_path, str) else None


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
