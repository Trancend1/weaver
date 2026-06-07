"""Phase F EPUB package structure contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

ResourceCategory = Literal[
    "chapter",
    "nav",
    "ncx",
    "image",
    "css",
    "font",
    "audio",
    "video",
    "script",
    "package",
    "unknown",
    "supporting",
]

ValidationSeverity = Literal["error", "warning", "info"]
NavigationSourceType = Literal["nav", "ncx"]
NavigationType = Literal["toc", "landmarks", "page-list", "lot", "loa", "unknown"]
ImageRole = Literal[
    "cover",
    "color_illustration",
    "insert_illustration",
    "character_page",
    "divider",
    "publisher_logo",
    "unknown",
]


@dataclass(frozen=True)
class EpubPackageMetadata:
    """Normalized OPF metadata needed by Phase F."""

    title: str
    creator: str | None
    language: str
    publisher: str | None
    identifier: str | None
    description: str | None
    contributors: list[str] = field(default_factory=list)
    dates: list[str] = field(default_factory=list)
    subjects: list[str] = field(default_factory=list)
    rights: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    coverages: list[str] = field(default_factory=list)
    relations: list[str] = field(default_factory=list)
    types: list[str] = field(default_factory=list)
    formats: list[str] = field(default_factory=list)
    modified: str | None = None
    cover: str | None = None
    series: str | None = None
    series_index: str | None = None
    collection: str | None = None
    collection_type: str | None = None
    group_position: str | None = None
    raw: dict[str, list[str]] = field(default_factory=dict)


@dataclass(frozen=True)
class ManifestResource:
    """Manifest item/resource discovered in the EPUB package."""

    id: str | None
    href: str
    resolved_path: str
    media_type: str
    category: ResourceCategory
    properties: list[str] = field(default_factory=list)
    exists_in_archive: bool = True
    is_spine_item: bool = False
    is_navigation: bool = False
    is_stylesheet: bool = False
    is_image: bool = False
    is_font: bool = False
    is_script: bool = False
    is_cover_candidate: bool = False
    referenced_by: list[str] = field(default_factory=list)
    image_role: ImageRole = "unknown"
    image_kind: str = "unknown"
    manifest_id: str | None = None
    width: int | None = None
    height: int | None = None
    byte_size: int | None = None
    linked_spine_index: int | None = None
    preview_available: bool = False


@dataclass(frozen=True)
class SpineResource:
    """Reading-order item referenced by the EPUB spine."""

    idref: str
    index: int
    href: str | None
    resolved_path: str | None
    media_type: str | None
    order: int
    linear: bool
    exists_in_manifest: bool = True
    exists_in_archive: bool = True
    is_navigation: bool = False
    page_spread: str | None = None
    properties: list[str] = field(default_factory=list)

    @property
    def item_id(self) -> str:
        """Backward-compatible alias for the spine idref."""

        return self.idref

    @property
    def is_non_linear(self) -> bool:
        """Return whether this spine item is explicitly non-linear."""

        return not self.linear


@dataclass(frozen=True)
class NavigationResource:
    """Navigation entry placeholder for NAV/NCX extraction."""

    source_type: NavigationSourceType
    nav_type: NavigationType
    label: str
    href: str | None
    resolved_path: str | None
    fragment: str | None
    order: int
    depth: int = 0
    children: list[NavigationResource] = field(default_factory=list)
    linked_manifest_id: str | None = None
    linked_spine_index: int | None = None
    play_order: int | None = None


@dataclass(frozen=True)
class ChapterTranslationContext:
    """Spine-backed XHTML context for future translation preservation."""

    manifest_id: str | None
    href: str
    resolved_path: str
    spine_index: int
    nav_labels: list[str] = field(default_factory=list)
    segment_source: str = "document_ir"
    translatable: bool = True


@dataclass(frozen=True)
class PreservationRecord:
    """Non-text or structural EPUB resource to preserve during future export."""

    resource_id: str | None
    href: str
    resolved_path: str
    category: ResourceCategory
    preservation_kind: str
    translatable: bool = False
    image_role: ImageRole | None = None
    image_kind: str | None = None
    referenced_by: list[str] = field(default_factory=list)
    linked_spine_index: int | None = None
    placeholder_kind: str | None = None
    future_ocr_placeholder: bool = False


@dataclass(frozen=True)
class TranslationPreservationContext:
    """Derived context for keeping EPUB structure separate from text segments."""

    chapters: list[ChapterTranslationContext] = field(default_factory=list)
    records: list[PreservationRecord] = field(default_factory=list)


@dataclass(frozen=True)
class ValidationIssue:
    """Deterministic EPUB structure issue."""

    severity: ValidationSeverity
    code: str
    message: str
    href: str | None = None
    path: str | None = None
    resource_id: str | None = None
    scope: str | None = None


@dataclass(frozen=True)
class ParsedEpub:
    """Additive Phase F structure view of an EPUB package.

    This contract intentionally lives beside ``DocumentIR``. Import,
    translation, and export continue to use ``DocumentIR`` until later Phase F
    stages explicitly integrate the richer package model.
    """

    package_path: Path
    opf_path: str | None
    metadata: EpubPackageMetadata
    manifest: list[ManifestResource]
    spine: list[SpineResource]
    navigation: list[NavigationResource]
    resources: list[ManifestResource]
    images: list[ManifestResource]
    validation_issues: list[ValidationIssue]
    spine_toc: str | None = None
    page_progression_direction: str | None = None
    preservation_context: TranslationPreservationContext = field(
        default_factory=TranslationPreservationContext
    )
