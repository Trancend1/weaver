"""Read-only EPUB structure preview service.

Serializes a :class:`ParsedEpub` into a JSON/UI-friendly inspection payload for
translators to eyeball an EPUB before import. It is strictly read-only: no
SQLite writes, no image bytes, no translation, and no persistence of the parsed
package.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from weaver.core.epub_structure import (
    ManifestResource,
    NavigationResource,
    ParsedEpub,
    ValidationIssue,
)
from weaver.readers.epub import parse_epub_structure, read_chapter_excerpt

# Bound chapter-excerpt I/O so a pathological EPUB cannot make a preview expensive.
_MAX_EXCERPTS = 40

# Fixed display order for grouped validation; unknown scopes follow, sorted.
_SCOPE_ORDER = ("metadata", "manifest", "spine", "navigation", "image")


def preview_epub_structure(path: Path) -> dict[str, Any]:
    """Return a JSON/UI friendly preview for an EPUB without persisting state."""

    parsed = parse_epub_structure(path)
    return _preview_dict(parsed)


def serialize_parsed_epub(
    parsed: ParsedEpub,
    *,
    project_name: str | None = None,
    volume_id: int | None = None,
    include_excerpts: bool = True,
) -> dict[str, Any]:
    """Serialize an already-parsed :class:`ParsedEpub` for the preview UI.

    Sprint J4 reuses this from the persisted-snapshot path so the EPUB-structure
    page renders the same shape whether the source was an on-demand parse
    (preview upload) or a stored snapshot row.

    ``include_excerpts=False`` skips the chapter-excerpt extraction, which
    re-opens the source archive — render paths fed by the persisted snapshot
    must stay archive-free (Q9 / no reparse on render).
    """

    return _preview_dict(
        parsed,
        project_name=project_name,
        volume_id=volume_id,
        include_excerpts=include_excerpts,
    )


def _preview_dict(
    parsed: ParsedEpub,
    *,
    project_name: str | None = None,
    volume_id: int | None = None,
    include_excerpts: bool = True,
) -> dict[str, Any]:
    severity_counts = _severity_counts(parsed.validation_issues)
    return {
        "source_path": str(parsed.package_path),
        "opf_path": parsed.opf_path,
        "page_progression_direction": parsed.page_progression_direction,
        "spine_toc": parsed.spine_toc,
        "metadata": {
            "title": parsed.metadata.title,
            "creator": parsed.metadata.creator,
            "language": parsed.metadata.language,
            "publisher": parsed.metadata.publisher,
            "identifier": parsed.metadata.identifier,
            "description": parsed.metadata.description,
            "series": parsed.metadata.series,
            "series_index": parsed.metadata.series_index,
        },
        "counts": {
            "manifest": len(parsed.manifest),
            "resources": len(parsed.resources),
            "spine": len(parsed.spine),
            "navigation": len(parsed.navigation),
            "images": len(parsed.images),
            "validation_issues": len(parsed.validation_issues),
        },
        "severity_counts": severity_counts,
        "readiness": _readiness(severity_counts),
        "is_safe_to_preview": True,
        "is_safe_to_translate": severity_counts["error"] == 0,
        "resources_by_category": _resources_by_category(parsed.manifest),
        "spine": [
            {
                "idref": item.idref,
                "index": item.index,
                "href": item.href,
                "media_type": item.media_type,
                "linear": item.linear,
                "page_spread": item.page_spread,
                "is_navigation": item.is_navigation,
                "exists_in_manifest": item.exists_in_manifest,
                "exists_in_archive": item.exists_in_archive,
            }
            for item in parsed.spine
        ],
        "navigation": [_navigation_dict(item) for item in parsed.navigation],
        "images": [
            _image_dict(item, project_name=project_name, volume_id=volume_id)
            for item in parsed.images
        ],
        "excerpts": _excerpts(parsed) if include_excerpts else [],
        "validation_issues": [_issue_dict(issue) for issue in parsed.validation_issues],
        "validation_by_scope": _validation_by_scope(parsed.validation_issues),
    }


def _severity_counts(issues: list[ValidationIssue]) -> dict[str, int]:
    counts = {"error": 0, "warning": 0, "info": 0}
    for issue in issues:
        if issue.severity in counts:
            counts[issue.severity] += 1
    return counts


def _readiness(severity_counts: dict[str, int]) -> str:
    if severity_counts["error"]:
        return "errors"
    if severity_counts["warning"]:
        return "warnings"
    return "safe"


def _excerpts(parsed: ParsedEpub) -> list[dict[str, Any]]:
    excerpts: list[dict[str, Any]] = []
    for chapter in parsed.preservation_context.chapters[:_MAX_EXCERPTS]:
        text = read_chapter_excerpt(parsed.package_path, chapter.resolved_path)
        if text is None:
            continue
        excerpts.append(
            {
                "spine_index": chapter.spine_index,
                "href": chapter.href,
                "label": chapter.nav_labels[0] if chapter.nav_labels else None,
                "text": text,
            }
        )
    return excerpts


def _resources_by_category(manifest: list[ManifestResource]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in manifest:
        counts[item.category] = counts.get(item.category, 0) + 1
    return dict(sorted(counts.items()))


def _navigation_dict(item: NavigationResource) -> dict[str, Any]:
    return {
        "source_type": item.source_type,
        "nav_type": item.nav_type,
        "label": item.label,
        "href": item.href,
        "fragment": item.fragment,
        "depth": item.depth,
        "linked_manifest_id": item.linked_manifest_id,
        "linked_spine_index": item.linked_spine_index,
        "children": [_navigation_dict(child) for child in item.children],
    }


def _image_dict(
    item: ManifestResource,
    *,
    project_name: str | None = None,
    volume_id: int | None = None,
) -> dict[str, Any]:
    preview_url = None
    if (
        project_name is not None
        and volume_id is not None
        and item.manifest_id
        and item.preview_available
    ):
        preview_url = (
            f"/projects/{project_name}/volumes/{volume_id}/images/{item.manifest_id}/preview"
        )
    return {
        "manifest_id": item.manifest_id,
        "href": item.href,
        "media_type": item.media_type,
        "image_role": item.image_role,
        "image_kind": item.image_kind,
        "width": item.width,
        "height": item.height,
        "byte_size": item.byte_size,
        "linked_spine_index": item.linked_spine_index,
        "referenced_by": item.referenced_by,
        "preview_available": item.preview_available,
        "preview_url": preview_url,
    }


def _issue_dict(issue: ValidationIssue) -> dict[str, Any]:
    return {
        "severity": issue.severity,
        "code": issue.code,
        "message": issue.message,
        "href": issue.href,
        "path": issue.path,
        "resource_id": issue.resource_id,
        "scope": issue.scope,
    }


def _validation_by_scope(issues: list[ValidationIssue]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for issue in issues:
        groups.setdefault(issue.scope or "other", []).append(_issue_dict(issue))
    ordered: dict[str, list[dict[str, Any]]] = {
        scope: groups[scope] for scope in _SCOPE_ORDER if scope in groups
    }
    for scope in sorted(groups):
        ordered.setdefault(scope, groups[scope])
    return ordered
