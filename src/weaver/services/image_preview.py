"""Safe EPUB image preview byte access (Sprint M / ADR 012).

Reads image bytes only from persisted EPUB snapshot metadata plus the original
volume EPUB. It never mutates, recompresses, or writes image data.
"""

from __future__ import annotations

import posixpath
from dataclasses import dataclass
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from weaver.core.epub_structure import ManifestResource
from weaver.errors import WeaverError
from weaver.services.epub_snapshot import read_snapshot
from weaver.storage.db import connect_database
from weaver.storage.volumes import get_volume

ALLOWED_IMAGE_MIME_TYPES = frozenset(
    {
        "image/jpeg",
        "image/png",
        "image/gif",
        "image/webp",
    }
)
MAX_IMAGE_PREVIEW_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True)
class ImagePreviewResult:
    """Read-only image preview bytes and response metadata."""

    data: bytes
    media_type: str
    byte_size: int
    archive_path: str
    etag: str


def read_image_preview(
    db_path: Path,
    *,
    volume_id: int,
    manifest_id: str,
    max_bytes: int = MAX_IMAGE_PREVIEW_BYTES,
) -> ImagePreviewResult:
    """Read one manifest-backed image from a volume's source EPUB.

    Args:
        db_path: Project database path.
        volume_id: Volume whose snapshot/image inventory authorizes access.
        manifest_id: Image manifest id. Raw archive paths are intentionally not accepted.
        max_bytes: Upper byte cap enforced before and after reading.

    Raises:
        WeaverError: The snapshot, manifest image, MIME type, path, or size is unsafe.
    """

    parsed = read_snapshot(db_path, volume_id)
    if parsed is None:
        raise WeaverError(
            "Image preview unavailable: EPUB snapshot is missing. "
            "Likely cause: the volume has not been reparsed. "
            "Next command: run Reparse EPUB, then try preview again."
        )
    image = _find_image(parsed.images, manifest_id)
    _validate_image_metadata(image, max_bytes=max_bytes)
    archive_path = _safe_archive_path(image.resolved_path)
    source_path = _volume_source_path(db_path, volume_id)

    try:
        with ZipFile(source_path) as archive:
            info = archive.getinfo(archive_path)
            if info.file_size > max_bytes:
                raise WeaverError(
                    "Image preview rejected: image exceeds the byte-size cap. "
                    "Likely cause: the EPUB contains a large image resource. "
                    "Next command: inspect metadata only; do not preview this image."
                )
            data = archive.read(info)
    except KeyError as exc:
        raise WeaverError(
            "Image preview rejected: manifest image is missing from the EPUB archive. "
            "Likely cause: stale or invalid EPUB snapshot metadata. "
            "Next command: reparse the EPUB and retry."
        ) from exc
    except BadZipFile as exc:
        raise WeaverError(
            "Image preview rejected: source EPUB cannot be opened as a ZIP archive. "
            "Likely cause: the source file changed or is corrupt. "
            "Next command: re-import or reparse the volume."
        ) from exc
    if len(data) > max_bytes:
        raise WeaverError(
            "Image preview rejected: image exceeds the byte-size cap. "
            "Likely cause: the EPUB contains a large image resource. "
            "Next command: inspect metadata only; do not preview this image."
        )
    return ImagePreviewResult(
        data=data,
        media_type=image.media_type,
        byte_size=len(data),
        archive_path=archive_path,
        etag=f'W/"{volume_id}-{manifest_id}-{len(data)}"',
    )


def _find_image(images: list[ManifestResource], manifest_id: str) -> ManifestResource:
    for image in images:
        if image.manifest_id == manifest_id or image.id == manifest_id:
            return image
    raise WeaverError(
        "Image preview rejected: manifest image was not found in the persisted snapshot. "
        "Likely cause: missing, stale, or tampered image reference. "
        "Next command: choose an image from the structure page inventory."
    )


def _validate_image_metadata(image: ManifestResource, *, max_bytes: int) -> None:
    if not image.exists_in_archive or not image.preview_available:
        raise WeaverError(
            "Image preview rejected: image is not available in the EPUB archive. "
            "Likely cause: the manifest points at a missing resource. "
            "Next command: reparse the EPUB and inspect validation issues."
        )
    if image.media_type not in ALLOWED_IMAGE_MIME_TYPES:
        raise WeaverError(
            "Image preview rejected: unsupported image MIME type. "
            "Likely cause: only JPEG, PNG, GIF, and WebP are previewable. "
            "Next command: inspect metadata only; do not preview this image."
        )
    if image.byte_size is not None and image.byte_size > max_bytes:
        raise WeaverError(
            "Image preview rejected: image exceeds the byte-size cap. "
            "Likely cause: the EPUB contains a large image resource. "
            "Next command: inspect metadata only; do not preview this image."
        )


def _safe_archive_path(path_value: str) -> str:
    path = path_value.replace("\\", "/")
    normalized = posixpath.normpath(path)
    if normalized.startswith("../") or normalized == ".." or normalized.startswith("/"):
        raise WeaverError(
            "Image preview rejected: image path escapes the EPUB archive sandbox. "
            "Likely cause: path traversal in manifest metadata. "
            "Next command: reject this EPUB or inspect validation issues."
        )
    return normalized


def _volume_source_path(db_path: Path, volume_id: int) -> Path:
    with connect_database(db_path) as connection:
        try:
            volume = get_volume(connection, volume_id)
        except LookupError as exc:
            raise WeaverError(
                f"Image preview rejected: volume {volume_id} was not found. "
                "Likely cause: deleted or stale volume link. "
                "Next command: refresh the project tree."
            ) from exc
    return Path(volume.source_path)


__all__ = [
    "ALLOWED_IMAGE_MIME_TYPES",
    "MAX_IMAGE_PREVIEW_BYTES",
    "ImagePreviewResult",
    "read_image_preview",
]
