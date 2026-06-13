"""Direct unit tests for validate_epub_structure."""

from __future__ import annotations

from weaver.core.epub_structure import (
    ManifestResource,
    NavigationResource,
    SpineResource,
    ValidationIssue,
)
from weaver.readers.epub_validation import validate_epub_structure

COMMON_MANIFEST = [
    ManifestResource(
        id="ch01",
        href="text/chapter01.xhtml",
        resolved_path="EPUB/text/chapter01.xhtml",
        media_type="application/xhtml+xml",
        category="chapter",
    ),
    ManifestResource(
        id="img01",
        href="images/cover.jpg",
        resolved_path="EPUB/images/cover.jpg",
        media_type="image/jpeg",
        category="image",
    ),
    ManifestResource(
        id="img02",
        href="images/illustration.webp",
        resolved_path="EPUB/images/illustration.webp",
        media_type="image/webp",
        category="image",
    ),
]

COMMON_SPINE = [
    SpineResource(
        idref="ch01",
        index=0,
        href="text/chapter01.xhtml",
        resolved_path="EPUB/text/chapter01.xhtml",
        media_type="application/xhtml+xml",
        order=1,
        linear=True,
    ),
]

COMMON_NAV = [
    NavigationResource(
        source_type="nav",
        nav_type="toc",
        label="Chapter 1",
        href="text/chapter01.xhtml",
        resolved_path="EPUB/text/chapter01.xhtml",
        fragment=None,
        order=1,
        linked_manifest_id="ch01",
        linked_spine_index=0,
    ),
]


def _codes(issues: list[ValidationIssue]) -> set[str]:
    return {i.code for i in issues}


# ---------------------------------------------------------------------------
# Baseline
# ---------------------------------------------------------------------------


def test_validate_empty_baseline() -> None:
    """Empty inputs produce empty-spine and empty-toc (no surprises)."""
    issues = validate_epub_structure(
        manifest=[],
        spine=[],
        navigation=[],
        image_reference_paths=[],
    )
    assert _codes(issues) == {"empty-spine", "empty-toc"}


def test_validate_no_issues() -> None:
    """Happy path with valid data produces no issues."""
    issues = validate_epub_structure(
        manifest=COMMON_MANIFEST,
        spine=COMMON_SPINE,
        navigation=COMMON_NAV,
        image_reference_paths=[],
    )
    assert issues == []


# ---------------------------------------------------------------------------
# Metadata flags
# ---------------------------------------------------------------------------


def test_validate_missing_title() -> None:
    """metadata_title_missing=True emits a missing-title warning."""
    issues = validate_epub_structure(
        manifest=COMMON_MANIFEST,
        spine=COMMON_SPINE,
        navigation=COMMON_NAV,
        image_reference_paths=[],
        metadata_title_missing=True,
    )
    codes = _codes(issues)
    assert "missing-title" in codes
    assert issues[0].severity == "warning"
    assert issues[0].scope == "metadata"


def test_validate_missing_language() -> None:
    """metadata_language_missing=True emits a missing-language warning."""
    issues = validate_epub_structure(
        manifest=COMMON_MANIFEST,
        spine=COMMON_SPINE,
        navigation=COMMON_NAV,
        image_reference_paths=[],
        metadata_language_missing=True,
    )
    codes = _codes(issues)
    assert "missing-language" in codes
    assert issues[0].severity == "warning"
    assert issues[0].scope == "metadata"


def test_validate_both_metadata_missing() -> None:
    """Both metadata flags produce two separate issues."""
    issues = validate_epub_structure(
        manifest=COMMON_MANIFEST,
        spine=COMMON_SPINE,
        navigation=COMMON_NAV,
        image_reference_paths=[],
        metadata_title_missing=True,
        metadata_language_missing=True,
    )
    assert len(issues) == 2
    assert _codes(issues) == {"missing-title", "missing-language"}


# ---------------------------------------------------------------------------
# Manifest issues
# ---------------------------------------------------------------------------


def test_validate_missing_manifest_resource() -> None:
    """A manifest item missing from archive emits missing-manifest-resource."""
    manifest = [
        ManifestResource(
            id="missing",
            href="text/gone.xhtml",
            resolved_path="EPUB/text/gone.xhtml",
            media_type="application/xhtml+xml",
            category="chapter",
            exists_in_archive=False,
        ),
    ]
    issues = validate_epub_structure(
        manifest=manifest,
        spine=[],
        navigation=[],
        image_reference_paths=[],
    )
    codes = _codes(issues)
    assert "missing-manifest-resource" in codes
    assert issues[0].severity == "error"
    assert issues[0].scope == "manifest"


def test_validate_missing_image_resource() -> None:
    """A manifest image missing from archive emits missing-image-resource too."""
    manifest = [
        ManifestResource(
            id="cover",
            href="images/cover.jpg",
            resolved_path="EPUB/images/cover.jpg",
            media_type="image/jpeg",
            category="image",
            exists_in_archive=False,
        ),
    ]
    issues = validate_epub_structure(
        manifest=manifest,
        spine=[],
        navigation=[],
        image_reference_paths=[],
    )
    codes = _codes(issues)
    assert "missing-manifest-resource" in codes
    assert "missing-image-resource" in codes
    image_issue = next(i for i in issues if i.code == "missing-image-resource")
    assert image_issue.severity == "error"
    assert image_issue.scope == "image"


def test_validate_unsupported_image_media_type() -> None:
    """An image with unsupported media type emits unsupported-image-media-type."""
    manifest = [
        ManifestResource(
            id="bmp",
            href="images/old.bmp",
            resolved_path="EPUB/images/old.bmp",
            media_type="image/bmp",
            category="image",
        ),
    ]
    issues = validate_epub_structure(
        manifest=manifest,
        spine=[],
        navigation=[],
        image_reference_paths=[],
    )
    codes = _codes(issues)
    assert "unsupported-image-media-type" in codes
    # first issue may be empty-spine; find the image one
    image_issue = next(i for i in issues if i.code == "unsupported-image-media-type")
    assert image_issue.severity == "warning"
    assert image_issue.scope == "image"


# ---------------------------------------------------------------------------
# Image reference issues
# ---------------------------------------------------------------------------


def test_validate_image_reference_missing_manifest() -> None:
    """An image reference path not in the manifest emits warning."""
    manifest = [
        ManifestResource(
            id="img01",
            href="images/cover.jpg",
            resolved_path="EPUB/images/cover.jpg",
            media_type="image/jpeg",
            category="image",
        ),
    ]
    issues = validate_epub_structure(
        manifest=manifest,
        spine=[],
        navigation=[],
        image_reference_paths=["images/not_in_manifest.png"],
    )
    codes = _codes(issues)
    assert "image-reference-missing-manifest" in codes
    ref_issue = next(i for i in issues if i.code == "image-reference-missing-manifest")
    assert ref_issue.severity == "warning"
    assert ref_issue.scope == "image"


def test_validate_image_reference_resolves_ok() -> None:
    """An image reference that appears in the manifest produces no issue."""
    issues = validate_epub_structure(
        manifest=COMMON_MANIFEST,
        spine=[],
        navigation=[],
        image_reference_paths=["EPUB/images/cover.jpg"],
    )
    assert "image-reference-missing-manifest" not in _codes(issues)


# ---------------------------------------------------------------------------
# Spine issues
# ---------------------------------------------------------------------------


def test_validate_empty_spine() -> None:
    """Empty spine emits empty-spine error."""
    issues = validate_epub_structure(
        manifest=COMMON_MANIFEST,
        spine=[],
        navigation=[],
        image_reference_paths=[],
    )
    codes = _codes(issues)
    assert "empty-spine" in codes
    spine_issue = next(i for i in issues if i.code == "empty-spine")
    assert spine_issue.severity == "error"
    assert spine_issue.scope == "spine"


def test_validate_spine_idref_missing_manifest() -> None:
    """Spine idref not in manifest emits spine-idref-missing-manifest."""
    spine = [
        SpineResource(
            idref="ghost",
            index=0,
            href="text/ghost.xhtml",
            resolved_path="EPUB/text/ghost.xhtml",
            media_type="application/xhtml+xml",
            order=1,
            linear=True,
            exists_in_manifest=False,
        ),
    ]
    issues = validate_epub_structure(
        manifest=COMMON_MANIFEST,
        spine=spine,
        navigation=[],
        image_reference_paths=[],
    )
    codes = _codes(issues)
    assert "spine-idref-missing-manifest" in codes
    spine_issue = next(i for i in issues if i.code == "spine-idref-missing-manifest")
    assert spine_issue.severity == "error"
    assert spine_issue.scope == "spine"


def test_validate_spine_resource_missing_archive() -> None:
    """Spine resource in manifest but missing from archive."""
    spine = [
        SpineResource(
            idref="ch01",
            index=0,
            href="text/chapter01.xhtml",
            resolved_path="EPUB/text/chapter01.xhtml",
            media_type="application/xhtml+xml",
            order=1,
            linear=True,
            exists_in_manifest=True,
            exists_in_archive=False,
        ),
    ]
    issues = validate_epub_structure(
        manifest=COMMON_MANIFEST,
        spine=spine,
        navigation=[],
        image_reference_paths=[],
    )
    codes = _codes(issues)
    assert "spine-resource-missing-archive" in codes
    spine_issue = next(i for i in issues if i.code == "spine-resource-missing-archive")
    assert spine_issue.severity == "error"
    assert spine_issue.scope == "spine"


def test_validate_duplicate_spine_idref() -> None:
    """Duplicate spine idrefs emit duplicate-spine-idref warning."""
    spine = [
        SpineResource(
            idref="ch01",
            index=0,
            href="text/chapter01.xhtml",
            resolved_path="EPUB/text/chapter01.xhtml",
            media_type="application/xhtml+xml",
            order=1,
            linear=True,
        ),
        SpineResource(
            idref="ch01",
            index=1,
            href="text/chapter01.xhtml",
            resolved_path="EPUB/text/chapter01.xhtml",
            media_type="application/xhtml+xml",
            order=2,
            linear=True,
        ),
    ]
    issues = validate_epub_structure(
        manifest=COMMON_MANIFEST,
        spine=spine,
        navigation=[],
        image_reference_paths=[],
    )
    assert "duplicate-spine-idref" in _codes(issues)
    assert issues[0].severity == "warning"
    assert issues[0].scope == "spine"


def test_validate_non_linear_spine_item() -> None:
    """Non-linear spine item emits info-level issue."""
    spine = [
        SpineResource(
            idref="ch01",
            index=0,
            href="text/chapter01.xhtml",
            resolved_path="EPUB/text/chapter01.xhtml",
            media_type="application/xhtml+xml",
            order=1,
            linear=False,
        ),
    ]
    issues = validate_epub_structure(
        manifest=COMMON_MANIFEST,
        spine=spine,
        navigation=[],
        image_reference_paths=[],
    )
    assert "non-linear-spine-item" in _codes(issues)
    assert issues[0].severity == "info"
    assert issues[0].scope == "spine"


# ---------------------------------------------------------------------------
# Navigation issues
# ---------------------------------------------------------------------------


def test_validate_empty_navigation() -> None:
    """Empty navigation emits empty-toc warning."""
    issues = validate_epub_structure(
        manifest=COMMON_MANIFEST,
        spine=COMMON_SPINE,
        navigation=[],
        image_reference_paths=[],
    )
    assert _codes(issues) == {"empty-toc"}
    assert issues[0].severity == "warning"
    assert issues[0].scope == "navigation"


def test_validate_nav_href_missing_manifest() -> None:
    """Nav href not resolving to manifest emits nav-href-missing-resource + outside-spine."""
    nav = [
        NavigationResource(
            source_type="nav",
            nav_type="toc",
            label="Ghost Chapter",
            href="text/ghost.xhtml",
            resolved_path="EPUB/text/ghost.xhtml",
            fragment=None,
            order=1,
            linked_manifest_id=None,
            linked_spine_index=None,
        ),
    ]
    issues = validate_epub_structure(
        manifest=COMMON_MANIFEST,
        spine=COMMON_SPINE,
        navigation=nav,
        image_reference_paths=[],
    )
    codes = _codes(issues)
    assert "nav-href-missing-resource" in codes
    assert "nav-href-outside-spine" in codes


def test_validate_nav_href_outside_spine() -> None:
    """Nav href with manifest entry but outside spine emits outside-spine."""
    nav = [
        NavigationResource(
            source_type="nav",
            nav_type="toc",
            label="Image Only",
            href="images/cover.jpg",
            resolved_path="EPUB/images/cover.jpg",
            fragment=None,
            order=1,
            linked_manifest_id="img01",
            linked_spine_index=None,
        ),
    ]
    issues = validate_epub_structure(
        manifest=COMMON_MANIFEST,
        spine=COMMON_SPINE,
        navigation=nav,
        image_reference_paths=[],
    )
    assert _codes(issues) == {"nav-href-outside-spine"}
    assert issues[0].severity == "warning"
    assert issues[0].scope == "navigation"


def test_validate_duplicate_nav_href() -> None:
    """Duplicate nav href emits duplicate-nav-href info."""
    nav = [
        NavigationResource(
            source_type="nav",
            nav_type="toc",
            label="Chapter 1",
            href="text/chapter01.xhtml",
            resolved_path="EPUB/text/chapter01.xhtml",
            fragment=None,
            order=1,
            linked_manifest_id="ch01",
            linked_spine_index=0,
        ),
        NavigationResource(
            source_type="nav",
            nav_type="toc",
            label="Chapter 1 Again",
            href="text/chapter01.xhtml",
            resolved_path="EPUB/text/chapter01.xhtml",
            fragment=None,
            order=2,
            linked_manifest_id="ch01",
            linked_spine_index=0,
        ),
    ]
    issues = validate_epub_structure(
        manifest=COMMON_MANIFEST,
        spine=COMMON_SPINE,
        navigation=nav,
        image_reference_paths=[],
    )
    assert "duplicate-nav-href" in _codes(issues)


def test_validate_nested_nav_entry() -> None:
    """Nested navigation children are walked and validated."""
    nav = [
        NavigationResource(
            source_type="ncx",
            nav_type="toc",
            label="Parent",
            href="text/parent.xhtml",
            resolved_path="EPUB/text/parent.xhtml",
            fragment=None,
            order=1,
            linked_manifest_id=None,
            linked_spine_index=None,
            children=[
                NavigationResource(
                    source_type="ncx",
                    nav_type="toc",
                    label="Child",
                    href="text/child.xhtml",
                    resolved_path="EPUB/text/child.xhtml",
                    fragment=None,
                    order=2,
                    linked_manifest_id=None,
                    linked_spine_index=None,
                ),
            ],
        ),
    ]
    issues = validate_epub_structure(
        manifest=COMMON_MANIFEST,
        spine=COMMON_SPINE,
        navigation=nav,
        image_reference_paths=[],
    )
    codes = _codes(issues)
    assert "nav-href-missing-resource" in codes
    assert "nav-href-outside-spine" in codes


# ---------------------------------------------------------------------------
# Combined issues
# ---------------------------------------------------------------------------


def test_validate_accumulates_all_issue_classes() -> None:
    """Multiple problem areas produce issues from each category."""
    manifest = [
        ManifestResource(
            id="bmp",
            href="images/old.bmp",
            resolved_path="EPUB/images/old.bmp",
            media_type="image/bmp",
            category="image",
        ),
    ]
    spine = [
        SpineResource(
            idref="ghost",
            index=0,
            href="text/ghost.xhtml",
            resolved_path="EPUB/text/ghost.xhtml",
            media_type="application/xhtml+xml",
            order=1,
            linear=True,
            exists_in_manifest=False,
        ),
    ]
    issues = validate_epub_structure(
        manifest=manifest,
        spine=spine,
        navigation=[],
        image_reference_paths=["EPUB/images/missing.png"],
        metadata_title_missing=True,
        metadata_language_missing=False,
    )
    codes = _codes(issues)
    assert "missing-title" in codes
    assert "unsupported-image-media-type" in codes
    assert "spine-idref-missing-manifest" in codes
    assert "empty-toc" in codes
    assert "image-reference-missing-manifest" in codes
