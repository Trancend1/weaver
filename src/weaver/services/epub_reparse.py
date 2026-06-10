"""High-level EPUB reparse service (Sprint J3 — ADR 010-adjacent).

Glues :func:`weaver.readers.epub.parse_epub_structure` to the Sprint J2
preservation-snapshot service. The reparse runs synchronously inside the
caller's worker thread; the FastAPI factory wraps it as a persistent
:class:`weaver.api.jobs.ParseJob` so progress and terminal state survive a
process restart (cold-start recovery from Sprint I3 applies unchanged).

The service deliberately keeps no thread state: callers (CLI / UI / job
runner) build the closure they need and the snapshot row is the durable
result. Translation, import, and export behavior are unchanged — Phase F's
``ParsedEpub`` is still strictly additive (CLAUDE.md §2.5 Phase F).
"""

from __future__ import annotations

from contextlib import closing
from pathlib import Path

from weaver.errors import VolumeNotFoundError, WeaverError
from weaver.readers.epub import PARSER_VERSION, parse_epub_structure
from weaver.services.epub_snapshot import (
    SnapshotStatus,
    compute_source_hash,
    snapshot_status,
    store_snapshot,
)
from weaver.services.project_paths import resolve_database_path
from weaver.storage.db import connect_database, connect_readonly_database
from weaver.storage.volumes import get_volume


def reparse_volume(
    project_toml: Path, volume_id: int, *, cwd: Path | None = None
) -> SnapshotStatus:
    """Parse a volume's source EPUB and persist it as a fresh snapshot.

    Synchronous. Idempotent: re-running over a fresh snapshot rewrites it but
    keeps ``created_at`` so callers can see the row's age via
    :class:`SnapshotStatus`.

    Returns:
        :class:`SnapshotStatus` reporting ``state='fresh'`` on success.

    Raises:
        VolumeNotFoundError: ``volume_id`` does not exist in this project.
        EpubReadError: The source EPUB cannot be parsed.
        WeaverError: Source path is unresolvable.
    """
    db_path = resolve_database_path(project_toml, cwd=cwd)
    with closing(connect_database(db_path)) as connection:
        try:
            volume = get_volume(connection, volume_id)
        except LookupError as exc:
            raise VolumeNotFoundError(
                f"No volume with id {volume_id} in {project_toml}. "
                "Likely cause: volume was deleted or never created. "
                "Next command: list volumes via `GET /projects/{name}/tree`."
            ) from exc

    epub_path = _resolve_source_path(volume.source_path, project_toml=project_toml, cwd=cwd)
    if not epub_path.is_file():
        raise WeaverError(
            f"Source EPUB for volume {volume_id} is missing at {epub_path}. "
            "Likely cause: the imported file was moved or deleted. "
            "Next command: re-import the volume or restore the source."
        )
    parsed = parse_epub_structure(epub_path)
    source_hash = compute_source_hash(epub_path)
    store_snapshot(
        db_path,
        volume_id=volume_id,
        parsed=parsed,
        source_hash=source_hash,
        parser_version=PARSER_VERSION,
    )
    return snapshot_status(
        db_path,
        volume_id=volume_id,
        expected_source_hash=source_hash,
        expected_parser_version=PARSER_VERSION,
    )


def status_for_volume(
    project_toml: Path, volume_id: int, *, cwd: Path | None = None
) -> SnapshotStatus:
    """Return :class:`SnapshotStatus` for a volume without re-parsing."""
    db_path = resolve_database_path(project_toml, cwd=cwd)
    with closing(connect_readonly_database(db_path)) as connection:
        try:
            volume = get_volume(connection, volume_id)
        except LookupError as exc:
            raise VolumeNotFoundError(
                f"No volume with id {volume_id} in {project_toml}. "
                "Likely cause: volume was deleted or never created. "
                "Next command: list volumes via `GET /projects/{name}/tree`."
            ) from exc

    epub_path = _resolve_source_path(volume.source_path, project_toml=project_toml, cwd=cwd)
    if not epub_path.is_file():
        # Snapshot may still exist; report whatever the row says compared
        # against an empty hash so the result is "stale" or "missing".
        return snapshot_status(
            db_path,
            volume_id=volume_id,
            expected_source_hash="",
            expected_parser_version=PARSER_VERSION,
        )
    source_hash = compute_source_hash(epub_path)
    return snapshot_status(
        db_path,
        volume_id=volume_id,
        expected_source_hash=source_hash,
        expected_parser_version=PARSER_VERSION,
    )


def _resolve_source_path(raw: str, *, project_toml: Path, cwd: Path | None) -> Path:
    candidate = Path(raw)
    if candidate.is_absolute():
        return candidate
    base = cwd or Path.cwd()
    cwd_candidate = base / candidate
    if cwd_candidate.exists():
        return cwd_candidate
    return project_toml.parent / candidate
