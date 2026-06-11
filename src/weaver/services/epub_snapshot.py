"""EPUB preservation snapshot service (Sprint J2 — ADR 010-adjacent).

Persists Phase F's :class:`ParsedEpub` into the v7 snapshot tables keyed by
``volume_id``. Pure storage; never spawns workers, never re-parses on read.
The reparse-as-Job wiring lives in Sprint J3 (``services/epub_snapshot_job``).

Stale detection compares two values that the snapshot row carries verbatim:

- ``source_hash`` — SHA-256 of the source EPUB bytes the snapshot was built
  from.
- ``parser_version`` — :data:`weaver.readers.epub.PARSER_VERSION` at the time
  the snapshot was written. Bumping the constant flags every existing
  snapshot stale.

Volume-delete cleanup is wired in :mod:`weaver.storage.volumes` (Sprint H3).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Mapping
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from weaver.core.epub_structure import (
    ChapterTranslationContext,
    EpubPackageMetadata,
    ManifestResource,
    NavigationResource,
    ParsedEpub,
    PreservationRecord,
    SpineResource,
    TranslationPreservationContext,
    ValidationIssue,
)
from weaver.errors import WeaverError
from weaver.readers.epub import PARSER_VERSION
from weaver.storage.db import connect_database, connect_readonly_database, transaction


@dataclass(frozen=True)
class SnapshotStatus:
    """Lightweight metadata for inspect/list endpoints (no payload).

    ``state`` is one of ``missing | fresh | stale``. Callers can use this to
    decide whether to schedule a reparse without paying the JSON-decode cost
    of the full snapshot.
    """

    volume_id: int
    state: str
    source_hash: str | None
    parser_version: int | None
    created_at: str | None
    updated_at: str | None

    @property
    def is_fresh(self) -> bool:
        return self.state == "fresh"

    @property
    def is_stale(self) -> bool:
        return self.state == "stale"


def compute_source_hash(path: Path) -> str:
    """Return the SHA-256 hex digest of the source EPUB bytes."""
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(64 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def store_snapshot(
    db_path: Path,
    *,
    volume_id: int,
    parsed: ParsedEpub,
    source_hash: str,
    parser_version: int = PARSER_VERSION,
) -> None:
    """Persist a fresh ParsedEpub against ``volume_id``.

    Existing rows for the same volume are replaced atomically inside one
    transaction so a partial write can never leave the snapshot tables in a
    mixed-version state.
    """
    now = datetime.now(UTC).isoformat()
    metadata_json = json.dumps(asdict(parsed.metadata), ensure_ascii=False)
    preservation_json = json.dumps(asdict(parsed.preservation_context), ensure_ascii=False)
    package_path = str(parsed.package_path)

    with closing(connect_database(db_path)) as connection, transaction(connection):
        existing = connection.execute(
            "SELECT created_at FROM epub_snapshots WHERE volume_id = ?",
            (volume_id,),
        ).fetchone()
        created_at = str(existing["created_at"]) if existing else now
        _delete_snapshot_rows(connection, volume_id)
        connection.execute(
            """
                INSERT INTO epub_snapshots (
                    volume_id, source_hash, parser_version, package_path,
                    opf_path, spine_toc, page_progression_direction,
                    metadata_json, preservation_context_json,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
            (
                volume_id,
                source_hash,
                parser_version,
                package_path,
                parsed.opf_path,
                parsed.spine_toc,
                parsed.page_progression_direction,
                metadata_json,
                preservation_json,
                created_at,
                now,
            ),
        )
        _bulk_insert(
            connection,
            "epub_snapshot_manifest",
            volume_id,
            [asdict(item) for item in parsed.manifest],
        )
        _bulk_insert(
            connection,
            "epub_snapshot_spine",
            volume_id,
            [asdict(item) for item in parsed.spine],
        )
        _bulk_insert(
            connection,
            "epub_snapshot_navigation",
            volume_id,
            [_nav_to_dict(node) for node in parsed.navigation],
        )
        _bulk_insert(
            connection,
            "epub_snapshot_images",
            volume_id,
            [asdict(item) for item in parsed.images],
        )
        _bulk_insert(
            connection,
            "epub_snapshot_validation",
            volume_id,
            [asdict(issue) for issue in parsed.validation_issues],
        )


def read_snapshot(db_path: Path, volume_id: int) -> ParsedEpub | None:
    """Reconstruct a :class:`ParsedEpub` from persisted rows. ``None`` if absent.

    Pure read: opens the database read-only (Q9 hardening — a snapshot read
    must never trigger migrations or any other write path).
    """
    with closing(connect_readonly_database(db_path)) as connection:
        header = connection.execute(
            """
            SELECT package_path, opf_path, spine_toc,
                   page_progression_direction,
                   metadata_json, preservation_context_json
            FROM epub_snapshots WHERE volume_id = ?
            """,
            (volume_id,),
        ).fetchone()
        if header is None:
            return None
        manifest = _read_list(connection, "epub_snapshot_manifest", volume_id)
        spine = _read_list(connection, "epub_snapshot_spine", volume_id)
        nav_rows = _read_list(connection, "epub_snapshot_navigation", volume_id)
        images = _read_list(connection, "epub_snapshot_images", volume_id)
        validation = _read_list(connection, "epub_snapshot_validation", volume_id)

    metadata = _build_metadata(json.loads(str(header["metadata_json"])))
    preservation = _build_preservation_context(json.loads(str(header["preservation_context_json"])))
    parsed_manifest = [_build_manifest_resource(payload) for payload in manifest]
    parsed_images = [_build_manifest_resource(payload) for payload in images]
    parsed_spine = [_build_spine_resource(payload) for payload in spine]
    parsed_nav = [_build_nav_resource(payload) for payload in nav_rows]
    parsed_validation = [_build_validation_issue(payload) for payload in validation]
    package_path_str = str(header["package_path"])
    opf_path = str(header["opf_path"]) if header["opf_path"] is not None else None
    spine_toc = str(header["spine_toc"]) if header["spine_toc"] is not None else None
    ppd = (
        str(header["page_progression_direction"])
        if header["page_progression_direction"] is not None
        else None
    )

    return ParsedEpub(
        package_path=Path(package_path_str),
        opf_path=opf_path,
        metadata=metadata,
        manifest=parsed_manifest,
        spine=parsed_spine,
        navigation=parsed_nav,
        resources=parsed_manifest,
        images=parsed_images,
        validation_issues=parsed_validation,
        spine_toc=spine_toc,
        page_progression_direction=ppd,
        preservation_context=preservation,
    )


def snapshot_status(
    db_path: Path,
    *,
    volume_id: int,
    expected_source_hash: str,
    expected_parser_version: int = PARSER_VERSION,
) -> SnapshotStatus:
    """Classify the persisted snapshot for ``volume_id`` as missing/fresh/stale."""
    with closing(connect_readonly_database(db_path)) as connection:
        row = connection.execute(
            """
            SELECT source_hash, parser_version, created_at, updated_at
            FROM epub_snapshots WHERE volume_id = ?
            """,
            (volume_id,),
        ).fetchone()
    if row is None:
        return SnapshotStatus(
            volume_id=volume_id,
            state="missing",
            source_hash=None,
            parser_version=None,
            created_at=None,
            updated_at=None,
        )
    persisted_hash = str(row["source_hash"])
    persisted_parser = int(row["parser_version"])
    is_fresh = (
        persisted_hash == expected_source_hash and persisted_parser == expected_parser_version
    )
    return SnapshotStatus(
        volume_id=volume_id,
        state="fresh" if is_fresh else "stale",
        source_hash=persisted_hash,
        parser_version=persisted_parser,
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def snapshot_info(db_path: Path, volume_id: int) -> SnapshotStatus | None:
    """Return the persisted snapshot row's metadata without any freshness check.

    Hash-free by design (Q9 / Gate B1 extended): render paths must never hash
    the source file, so this reader reports only what the row itself says —
    ``state`` is ``"recorded"`` when a snapshot exists. Freshness classification
    (fresh/stale) stays in :func:`snapshot_status`, which is reserved for
    explicit user actions (snapshot-status button, reparse flow).
    """
    with closing(connect_readonly_database(db_path)) as connection:
        row = connection.execute(
            """
            SELECT source_hash, parser_version, created_at, updated_at
            FROM epub_snapshots WHERE volume_id = ?
            """,
            (volume_id,),
        ).fetchone()
    if row is None:
        return None
    return SnapshotStatus(
        volume_id=volume_id,
        state="recorded",
        source_hash=str(row["source_hash"]),
        parser_version=int(row["parser_version"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def delete_snapshot(connection: sqlite3.Connection, volume_id: int) -> None:
    """Remove every snapshot row for ``volume_id`` (volume-delete hook).

    Caller-managed connection so the volume-delete service in
    :mod:`weaver.storage.volumes` can fold this into its existing transaction.
    """
    _delete_snapshot_rows(connection, volume_id)


# ---------------------------------------------------------------------------
# internals
# ---------------------------------------------------------------------------


def _delete_snapshot_rows(connection: sqlite3.Connection, volume_id: int) -> None:
    for table in (
        "epub_snapshot_validation",
        "epub_snapshot_images",
        "epub_snapshot_navigation",
        "epub_snapshot_spine",
        "epub_snapshot_manifest",
        "epub_snapshots",
    ):
        connection.execute(f"DELETE FROM {table} WHERE volume_id = ?", (volume_id,))


def _bulk_insert(
    connection: sqlite3.Connection,
    table: str,
    volume_id: int,
    rows: list[Mapping[str, Any]],
) -> None:
    if not rows:
        return
    connection.executemany(
        f"INSERT INTO {table} (volume_id, position, data_json) VALUES (?, ?, ?)",
        [
            (volume_id, index, json.dumps(payload, ensure_ascii=False))
            for index, payload in enumerate(rows)
        ],
    )


def _read_list(
    connection: sqlite3.Connection, table: str, volume_id: int
) -> list[Mapping[str, Any]]:
    rows = connection.execute(
        f"SELECT data_json FROM {table} WHERE volume_id = ? ORDER BY position",
        (volume_id,),
    ).fetchall()
    return [json.loads(str(row["data_json"])) for row in rows]


def _nav_to_dict(node: NavigationResource) -> Mapping[str, Any]:
    payload = asdict(node)
    payload["children"] = [_nav_to_dict(child) for child in node.children]
    return payload


def _build_metadata(payload: Mapping[str, Any]) -> EpubPackageMetadata:
    raw = payload.get("raw", {}) or {}
    return EpubPackageMetadata(
        title=str(payload.get("title", "")),
        creator=_str_or_none(payload.get("creator")),
        language=str(payload.get("language", "")),
        publisher=_str_or_none(payload.get("publisher")),
        identifier=_str_or_none(payload.get("identifier")),
        description=_str_or_none(payload.get("description")),
        contributors=list(payload.get("contributors") or []),
        dates=list(payload.get("dates") or []),
        subjects=list(payload.get("subjects") or []),
        rights=list(payload.get("rights") or []),
        sources=list(payload.get("sources") or []),
        coverages=list(payload.get("coverages") or []),
        relations=list(payload.get("relations") or []),
        types=list(payload.get("types") or []),
        formats=list(payload.get("formats") or []),
        modified=_str_or_none(payload.get("modified")),
        cover=_str_or_none(payload.get("cover")),
        series=_str_or_none(payload.get("series")),
        series_index=_str_or_none(payload.get("series_index")),
        collection=_str_or_none(payload.get("collection")),
        collection_type=_str_or_none(payload.get("collection_type")),
        group_position=_str_or_none(payload.get("group_position")),
        raw={str(k): list(v or []) for k, v in raw.items()},
    )


def _build_manifest_resource(payload: Mapping[str, Any]) -> ManifestResource:
    return ManifestResource(
        id=_str_or_none(payload.get("id")),
        href=str(payload.get("href", "")),
        resolved_path=str(payload.get("resolved_path", "")),
        media_type=str(payload.get("media_type", "")),
        category=str(payload.get("category", "unknown")),  # type: ignore[arg-type]
        properties=list(payload.get("properties") or []),
        exists_in_archive=bool(payload.get("exists_in_archive", True)),
        is_spine_item=bool(payload.get("is_spine_item", False)),
        is_navigation=bool(payload.get("is_navigation", False)),
        is_stylesheet=bool(payload.get("is_stylesheet", False)),
        is_image=bool(payload.get("is_image", False)),
        is_font=bool(payload.get("is_font", False)),
        is_script=bool(payload.get("is_script", False)),
        is_cover_candidate=bool(payload.get("is_cover_candidate", False)),
        referenced_by=list(payload.get("referenced_by") or []),
        image_role=str(payload.get("image_role", "unknown")),  # type: ignore[arg-type]
        image_kind=str(payload.get("image_kind", "unknown")),
        manifest_id=_str_or_none(payload.get("manifest_id")),
        width=_int_or_none(payload.get("width")),
        height=_int_or_none(payload.get("height")),
        byte_size=_int_or_none(payload.get("byte_size")),
        linked_spine_index=_int_or_none(payload.get("linked_spine_index")),
        preview_available=bool(payload.get("preview_available", False)),
    )


def _build_spine_resource(payload: Mapping[str, Any]) -> SpineResource:
    return SpineResource(
        idref=str(payload.get("idref", "")),
        index=int(payload.get("index", 0) or 0),
        href=_str_or_none(payload.get("href")),
        resolved_path=_str_or_none(payload.get("resolved_path")),
        media_type=_str_or_none(payload.get("media_type")),
        order=int(payload.get("order", 0) or 0),
        linear=bool(payload.get("linear", True)),
        exists_in_manifest=bool(payload.get("exists_in_manifest", True)),
        exists_in_archive=bool(payload.get("exists_in_archive", True)),
        is_navigation=bool(payload.get("is_navigation", False)),
        page_spread=_str_or_none(payload.get("page_spread")),
        properties=list(payload.get("properties") or []),
    )


def _build_nav_resource(payload: Mapping[str, Any]) -> NavigationResource:
    children_payload = payload.get("children") or []
    children = [_build_nav_resource(child) for child in children_payload if isinstance(child, dict)]
    return NavigationResource(
        source_type=str(payload.get("source_type", "nav")),  # type: ignore[arg-type]
        nav_type=str(payload.get("nav_type", "toc")),  # type: ignore[arg-type]
        label=str(payload.get("label", "")),
        href=_str_or_none(payload.get("href")),
        resolved_path=_str_or_none(payload.get("resolved_path")),
        fragment=_str_or_none(payload.get("fragment")),
        order=int(payload.get("order", 0) or 0),
        depth=int(payload.get("depth", 0) or 0),
        children=children,
        linked_manifest_id=_str_or_none(payload.get("linked_manifest_id")),
        linked_spine_index=_int_or_none(payload.get("linked_spine_index")),
        play_order=_int_or_none(payload.get("play_order")),
    )


def _build_validation_issue(payload: Mapping[str, Any]) -> ValidationIssue:
    return ValidationIssue(
        severity=str(payload.get("severity", "warning")),  # type: ignore[arg-type]
        code=str(payload.get("code", "")),
        message=str(payload.get("message", "")),
        href=_str_or_none(payload.get("href")),
        path=_str_or_none(payload.get("path")),
        resource_id=_str_or_none(payload.get("resource_id")),
        scope=_str_or_none(payload.get("scope")),
    )


def _build_preservation_context(payload: Mapping[str, Any]) -> TranslationPreservationContext:
    chapters_payload = payload.get("chapters") or []
    records_payload = payload.get("records") or []
    chapters = [
        ChapterTranslationContext(
            manifest_id=_str_or_none(item.get("manifest_id")),
            href=str(item.get("href", "")),
            resolved_path=str(item.get("resolved_path", "")),
            spine_index=int(item.get("spine_index", 0) or 0),
            nav_labels=list(item.get("nav_labels") or []),
            segment_source=str(item.get("segment_source", "document_ir")),
            translatable=bool(item.get("translatable", True)),
        )
        for item in chapters_payload
        if isinstance(item, dict)
    ]
    records = [
        PreservationRecord(
            resource_id=_str_or_none(item.get("resource_id")),
            href=str(item.get("href", "")),
            resolved_path=str(item.get("resolved_path", "")),
            category=str(item.get("category", "unknown")),  # type: ignore[arg-type]
            preservation_kind=str(item.get("preservation_kind", "")),
            translatable=bool(item.get("translatable", False)),
            image_role=item.get("image_role"),  # type: ignore[arg-type]
            image_kind=_str_or_none(item.get("image_kind")),
            referenced_by=list(item.get("referenced_by") or []),
            linked_spine_index=_int_or_none(item.get("linked_spine_index")),
            placeholder_kind=_str_or_none(item.get("placeholder_kind")),
            future_ocr_placeholder=bool(item.get("future_ocr_placeholder", False)),
        )
        for item in records_payload
        if isinstance(item, dict)
    ]
    return TranslationPreservationContext(chapters=chapters, records=records)


def _str_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _int_or_none(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


__all__ = [
    "PARSER_VERSION",
    "SnapshotStatus",
    "WeaverError",
    "compute_source_hash",
    "delete_snapshot",
    "read_snapshot",
    "snapshot_status",
    "store_snapshot",
]
