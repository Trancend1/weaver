"""Deterministic validation for parsed EPUB package structure."""

from __future__ import annotations

from collections.abc import Iterable

from weaver.core.epub_structure import (
    ManifestResource,
    NavigationResource,
    SpineResource,
    ValidationIssue,
)


def validate_epub_structure(
    *,
    manifest: list[ManifestResource],
    spine: list[SpineResource],
    navigation: list[NavigationResource],
    image_reference_paths: Iterable[str],
    metadata_title_missing: bool = False,
    metadata_language_missing: bool = False,
) -> list[ValidationIssue]:
    """Return stable, non-fatal validation issues for ParsedEpub."""

    issues: list[ValidationIssue] = []
    if metadata_title_missing:
        issues.append(
            ValidationIssue(
                severity="warning",
                code="missing-title",
                message="OPF metadata does not declare dc:title.",
                scope="metadata",
            )
        )
    if metadata_language_missing:
        issues.append(
            ValidationIssue(
                severity="warning",
                code="missing-language",
                message="OPF metadata does not declare dc:language.",
                scope="metadata",
            )
        )

    issues.extend(_manifest_issues(manifest))
    issues.extend(_image_reference_issues(manifest, image_reference_paths))
    issues.extend(_spine_issues(spine))
    issues.extend(_navigation_issues(navigation))
    return issues


def _manifest_issues(manifest: list[ManifestResource]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for item in manifest:
        if not item.exists_in_archive:
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="missing-manifest-resource",
                    message=f"Manifest resource '{item.href}' is missing from the EPUB archive.",
                    href=item.href,
                    path=item.resolved_path,
                    resource_id=item.id,
                    scope="manifest",
                )
            )
        if item.category == "image" and not item.exists_in_archive:
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="missing-image-resource",
                    message=f"Image resource '{item.href}' is missing from the EPUB archive.",
                    href=item.href,
                    path=item.resolved_path,
                    resource_id=item.id,
                    scope="image",
                )
            )
        if item.category == "image" and item.media_type not in {
            "image/jpeg",
            "image/png",
            "image/webp",
            "image/svg+xml",
        }:
            issues.append(
                ValidationIssue(
                    severity="warning",
                    code="unsupported-image-media-type",
                    message=(
                        f"Image resource '{item.href}' uses unsupported media type "
                        f"'{item.media_type}'."
                    ),
                    href=item.href,
                    path=item.resolved_path,
                    resource_id=item.id,
                    scope="image",
                )
            )
    return issues


def _image_reference_issues(
    manifest: list[ManifestResource], image_reference_paths: Iterable[str]
) -> list[ValidationIssue]:
    manifest_paths = {item.resolved_path for item in manifest}
    manifest_href_by_path = {item.resolved_path: item.href for item in manifest}
    issues: list[ValidationIssue] = []
    for resolved_path in sorted(set(image_reference_paths)):
        if resolved_path not in manifest_paths:
            issues.append(
                ValidationIssue(
                    severity="warning",
                    code="image-reference-missing-manifest",
                    message=(
                        f"Image reference '{resolved_path}' does not resolve to a manifest item."
                    ),
                    href=_href_from_resolved_path(resolved_path, manifest_href_by_path),
                    path=resolved_path,
                    scope="image",
                )
            )
    return issues


def _spine_issues(spine: list[SpineResource]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if not spine:
        issues.append(
            ValidationIssue(
                severity="error",
                code="empty-spine",
                message="EPUB spine does not contain any reading-order items.",
                scope="spine",
            )
        )
        return issues

    seen_spine_ids: set[str] = set()
    duplicate_spine_ids: set[str] = set()
    for item in spine:
        if not item.exists_in_manifest:
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="spine-idref-missing-manifest",
                    message=f"Spine idref '{item.idref}' does not exist in the manifest.",
                    href=item.idref,
                    resource_id=item.idref,
                    scope="spine",
                )
            )
        if item.exists_in_manifest and not item.exists_in_archive:
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="spine-resource-missing-archive",
                    message=f"Spine resource '{item.href}' is missing from the EPUB archive.",
                    href=item.href,
                    path=item.resolved_path,
                    resource_id=item.idref,
                    scope="spine",
                )
            )
        if item.idref in seen_spine_ids and item.idref not in duplicate_spine_ids:
            duplicate_spine_ids.add(item.idref)
            issues.append(
                ValidationIssue(
                    severity="warning",
                    code="duplicate-spine-idref",
                    message=f"Spine idref '{item.idref}' appears multiple times.",
                    href=item.idref,
                    resource_id=item.idref,
                    scope="spine",
                )
            )
        seen_spine_ids.add(item.idref)
        if item.is_non_linear:
            issues.append(
                ValidationIssue(
                    severity="info",
                    code="non-linear-spine-item",
                    message=f"Spine item '{item.idref}' is marked non-linear.",
                    href=item.href or item.idref,
                    path=item.resolved_path,
                    resource_id=item.idref,
                    scope="spine",
                )
            )
    return issues


def _navigation_issues(navigation: list[NavigationResource]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    toc_entries = [item for item in navigation if item.nav_type == "toc"]
    if not toc_entries:
        issues.append(
            ValidationIssue(
                severity="warning",
                code="empty-toc",
                message="EPUB navigation does not contain any TOC entries.",
                scope="navigation",
            )
        )

    seen_nav_hrefs: set[tuple[str, str]] = set()
    duplicate_nav_hrefs: set[tuple[str, str]] = set()
    for item in _walk_navigation(navigation):
        if item.resolved_path is None:
            continue
        if item.linked_manifest_id is None:
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="nav-href-missing-resource",
                    message=f"Navigation href '{item.href}' does not resolve to a manifest item.",
                    href=item.href,
                    path=item.resolved_path,
                    scope="navigation",
                )
            )
        if item.linked_spine_index is None:
            issues.append(
                ValidationIssue(
                    severity="warning",
                    code="nav-href-outside-spine",
                    message=f"Navigation href '{item.href}' does not point to a spine item.",
                    href=item.href,
                    path=item.resolved_path,
                    resource_id=item.linked_manifest_id,
                    scope="navigation",
                )
            )
        if item.href is not None:
            nav_key = (item.source_type, item.href)
            if nav_key in seen_nav_hrefs and nav_key not in duplicate_nav_hrefs:
                duplicate_nav_hrefs.add(nav_key)
                issues.append(
                    ValidationIssue(
                        severity="info",
                        code="duplicate-nav-href",
                        message=f"Navigation href '{item.href}' appears multiple times.",
                        href=item.href,
                        path=item.resolved_path,
                        resource_id=item.linked_manifest_id,
                        scope="navigation",
                    )
                )
            seen_nav_hrefs.add(nav_key)
    return issues


def _walk_navigation(entries: list[NavigationResource]) -> Iterable[NavigationResource]:
    for entry in entries:
        yield entry
        yield from _walk_navigation(entry.children)


def _href_from_resolved_path(resolved_path: str, manifest_href_by_path: dict[str, str]) -> str:
    if resolved_path in manifest_href_by_path:
        return manifest_href_by_path[resolved_path]
    if "/" in resolved_path:
        return resolved_path.split("/", maxsplit=1)[1]
    return resolved_path
