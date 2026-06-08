"""Read-only EPUB source-vs-export fidelity checks."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from weaver.core.epub_structure import ParsedEpub
from weaver.readers.epub import parse_epub_structure


@dataclass(frozen=True)
class FidelityCheck:
    """One deterministic source-vs-export fidelity check result."""

    severity: str
    code: str
    message: str
    href: str | None = None
    scope: str | None = None


@dataclass(frozen=True)
class EpubExportFidelityReport:
    """EPUB export fidelity report."""

    source_path: Path
    exported_path: Path
    source_counts: dict[str, int]
    exported_counts: dict[str, int]
    passed_checks: list[FidelityCheck] = field(default_factory=list)
    warnings: list[FidelityCheck] = field(default_factory=list)
    critical_gaps: list[FidelityCheck] = field(default_factory=list)
    missing_resources: list[str] = field(default_factory=list)

    @property
    def warning_count(self) -> int:
        return len(self.warnings)

    @property
    def critical_count(self) -> int:
        return len(self.critical_gaps)


def compare_epub_export_fidelity(
    source_epub: Path, exported_epub: Path
) -> EpubExportFidelityReport:
    """Compare source and exported EPUB structures without mutating either file."""

    source = parse_epub_structure(source_epub)
    exported = parse_epub_structure(exported_epub)
    passed: list[FidelityCheck] = []
    warnings: list[FidelityCheck] = []
    critical: list[FidelityCheck] = []

    _compare_metadata(source, exported, passed, warnings)
    missing_resources = _missing_resource_hrefs(source, exported)
    if missing_resources:
        for href in missing_resources:
            critical.append(
                FidelityCheck(
                    severity="critical",
                    code="missing-resource",
                    message=f"Exported EPUB is missing source resource '{href}'.",
                    href=href,
                    scope="manifest",
                )
            )
    else:
        passed.append(
            FidelityCheck(
                severity="passed",
                code="manifest-resources-preserved",
                message="All source manifest resources are present in the exported EPUB.",
                scope="manifest",
            )
        )

    _compare_category_counts(source, exported, passed, warnings)
    _compare_spine(source, exported, passed, critical)
    _compare_navigation(source, exported, passed, warnings)
    _compare_images(source, exported, passed, critical)
    _compare_validation(source, exported, passed, warnings)

    return EpubExportFidelityReport(
        source_path=source_epub,
        exported_path=exported_epub,
        source_counts=_counts(source),
        exported_counts=_counts(exported),
        passed_checks=passed,
        warnings=warnings,
        critical_gaps=critical,
        missing_resources=missing_resources,
    )


def _counts(parsed: ParsedEpub) -> dict[str, int]:
    return {
        "manifest": len(parsed.manifest),
        "spine": len(parsed.spine),
        "navigation": len(parsed.navigation),
        "images": len(parsed.images),
        "css": _category_count(parsed, "css"),
        "fonts": _category_count(parsed, "font"),
        "supporting": len(
            [
                item
                for item in parsed.manifest
                if item.category not in {"chapter", "image", "css", "font"}
            ]
        ),
        "validation_issues": len(parsed.validation_issues),
    }


def _category_count(parsed: ParsedEpub, category: str) -> int:
    return len([item for item in parsed.manifest if item.category == category])


def _compare_metadata(
    source: ParsedEpub,
    exported: ParsedEpub,
    passed: list[FidelityCheck],
    warnings: list[FidelityCheck],
) -> None:
    fields = ["title", "language", "identifier"]
    changed = [
        field
        for field in fields
        if getattr(source.metadata, field)
        and getattr(source.metadata, field) != getattr(exported.metadata, field)
    ]
    if changed:
        warnings.append(
            FidelityCheck(
                severity="warning",
                code="metadata-changed",
                message=f"Exported EPUB metadata changed fields: {', '.join(changed)}.",
                scope="metadata",
            )
        )
    else:
        passed.append(
            FidelityCheck(
                severity="passed",
                code="metadata-preserved",
                message="Core source metadata is present in the exported EPUB.",
                scope="metadata",
            )
        )


def _missing_resource_hrefs(source: ParsedEpub, exported: ParsedEpub) -> list[str]:
    exported_by_href = {item.href: item for item in exported.manifest}
    missing: list[str] = []
    for item in source.manifest:
        exported_item = exported_by_href.get(item.href)
        if exported_item is None or not exported_item.exists_in_archive:
            missing.append(item.href)
    return sorted(missing)


def _compare_category_counts(
    source: ParsedEpub,
    exported: ParsedEpub,
    passed: list[FidelityCheck],
    warnings: list[FidelityCheck],
) -> None:
    for category in ["css", "font", "image", "nav", "ncx"]:
        source_count = _category_count(source, category)
        exported_count = _category_count(exported, category)
        if source_count == exported_count:
            passed.append(
                FidelityCheck(
                    severity="passed",
                    code=f"{category}-count-preserved",
                    message=f"{category} resource count is preserved.",
                    scope="manifest",
                )
            )
        else:
            warnings.append(
                FidelityCheck(
                    severity="warning",
                    code=f"{category}-count-changed",
                    message=(
                        f"{category} resource count changed from {source_count} "
                        f"to {exported_count}."
                    ),
                    scope="manifest",
                )
            )


def _compare_spine(
    source: ParsedEpub,
    exported: ParsedEpub,
    passed: list[FidelityCheck],
    critical: list[FidelityCheck],
) -> None:
    source_order = [item.href for item in source.spine]
    exported_order = [item.href for item in exported.spine]
    if source_order == exported_order:
        passed.append(
            FidelityCheck(
                severity="passed",
                code="spine-order-preserved",
                message="Source spine reading order is preserved.",
                scope="spine",
            )
        )
    else:
        critical.append(
            FidelityCheck(
                severity="critical",
                code="spine-order-changed",
                message="Exported EPUB spine reading order differs from source.",
                scope="spine",
            )
        )


def _compare_navigation(
    source: ParsedEpub,
    exported: ParsedEpub,
    passed: list[FidelityCheck],
    warnings: list[FidelityCheck],
) -> None:
    source_has_nav = any(item.category in {"nav", "ncx"} for item in source.manifest)
    exported_has_nav = any(item.category in {"nav", "ncx"} for item in exported.manifest)
    if source_has_nav == exported_has_nav:
        passed.append(
            FidelityCheck(
                severity="passed",
                code="navigation-presence-preserved",
                message="NAV/NCX presence is preserved.",
                scope="navigation",
            )
        )
    else:
        warnings.append(
            FidelityCheck(
                severity="warning",
                code="navigation-presence-changed",
                message="NAV/NCX presence changed in exported EPUB.",
                scope="navigation",
            )
        )


def _compare_images(
    source: ParsedEpub,
    exported: ParsedEpub,
    passed: list[FidelityCheck],
    critical: list[FidelityCheck],
) -> None:
    exported_images_by_href = {item.href: item for item in exported.images}
    missing_images = sorted(
        item.href
        for item in source.images
        if item.href not in exported_images_by_href
        or not exported_images_by_href[item.href].exists_in_archive
    )
    if missing_images:
        for href in missing_images:
            critical.append(
                FidelityCheck(
                    severity="critical",
                    code="missing-image-resource",
                    message=f"Exported EPUB is missing image resource '{href}'.",
                    href=href,
                    scope="image",
                )
            )
    else:
        passed.append(
            FidelityCheck(
                severity="passed",
                code="image-resources-preserved",
                message="All source image resources are present in exported EPUB.",
                scope="image",
            )
        )


def _compare_validation(
    source: ParsedEpub,
    exported: ParsedEpub,
    passed: list[FidelityCheck],
    warnings: list[FidelityCheck],
) -> None:
    if len(exported.validation_issues) <= len(source.validation_issues):
        passed.append(
            FidelityCheck(
                severity="passed",
                code="validation-issue-count-not-increased",
                message="Exported EPUB did not add structural validation issues.",
                scope="validation",
            )
        )
    else:
        warnings.append(
            FidelityCheck(
                severity="warning",
                code="validation-issue-count-increased",
                message="Exported EPUB has more validation issues than source.",
                scope="validation",
            )
        )


def report_to_dict(report: EpubExportFidelityReport) -> dict[str, Any]:
    """Serialize an :class:`EpubExportFidelityReport` to a JSON-safe dict."""
    return {
        "source_path": str(report.source_path),
        "exported_path": str(report.exported_path),
        "source_counts": dict(report.source_counts),
        "exported_counts": dict(report.exported_counts),
        "passed_checks": [_check_to_dict(c) for c in report.passed_checks],
        "warnings": [_check_to_dict(c) for c in report.warnings],
        "critical_gaps": [_check_to_dict(c) for c in report.critical_gaps],
        "missing_resources": list(report.missing_resources),
        "warning_count": report.warning_count,
        "critical_count": report.critical_count,
    }


def _check_to_dict(check: FidelityCheck) -> dict[str, Any]:
    return {
        "severity": check.severity,
        "code": check.code,
        "message": check.message,
        "href": check.href,
        "scope": check.scope,
    }
