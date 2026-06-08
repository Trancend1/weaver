"""Volume-scoped lifecycle services (Sprint H3).

Today this module hosts one operation: :func:`delete_volume_from_project`, the
service-layer wrapper that opens a transaction and clears every row a single
volume owns (qa_warnings, translations, segments, chapters, volume). Future
sprints (J snapshot, K export fidelity, L candidate review) will add their
volume-scoped lifecycle operations here so the cockpit never reaches into
SQLite directly.

Project-scoped data (glossary, characters, translation memory) is **not**
touched — those live at the project level. Use :func:`weaver.services.project.
delete_project` to remove a whole project.
"""

from __future__ import annotations

from contextlib import closing
from pathlib import Path

from weaver.errors import VolumeNotFoundError, WeaverError
from weaver.services.logging_setup import log_runtime_event
from weaver.services.project_paths import resolve_database_path
from weaver.storage.db import connect_database, transaction
from weaver.storage.volumes import delete_volume, get_volume


def delete_volume_from_project(
    project_toml: Path, volume_id: int, *, cwd: Path | None = None
) -> str:
    """Permanently delete one volume and every row that depends on it.

    Args:
        project_toml: Path to the owning project's ``project.toml``.
        volume_id: Volume row id.
        cwd: Working directory used to resolve the project database path.

    Returns:
        The deleted volume's title (so callers can build a confirmation line).

    Raises:
        VolumeNotFoundError: The volume does not exist in this project.
        WeaverError: Any other database failure (re-raised by the storage layer).
    """
    db_path = resolve_database_path(project_toml, cwd=cwd)
    with closing(connect_database(db_path)) as connection:
        try:
            volume = get_volume(connection, volume_id)
        except LookupError as exc:
            raise VolumeNotFoundError(
                f"No volume with id {volume_id} in {project_toml}. "
                "Likely cause: the volume was already deleted or never existed. "
                "Next command: list volumes via `GET /projects/{name}/tree`."
            ) from exc
        with transaction(connection):
            delete_volume(connection, volume_id)
        try:
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except Exception as exc:  # noqa: BLE001 — non-fatal best-effort
            raise WeaverError(
                "Volume deleted but WAL checkpoint failed. "
                "Likely cause: another writer holds the database. "
                "Next command: retry once no other Weaver process is running."
            ) from exc
    log_runtime_event(
        "volume.deleted",
        project=project_toml.parent.name,
        volume_id=volume_id,
        title=volume.title,
    )
    return volume.title
