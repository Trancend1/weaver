"""Translation memory read/management service (Sprint 6B).

Project-scoped read overview + entry deletion over the ``translation_memory``
table. Framework-agnostic: no web types. The FastAPI router adapts results and
maps the raised exceptions to HTTP status codes.

Deleting an entry removes only its ``translation_memory`` row — translation
attempt history, manual edits, glossary, and character data are never touched.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from weaver.errors import ConfigError, TranslationMemoryNotFoundError
from weaver.services.project_paths import resolve_database_path
from weaver.services.translation import MEMORY_PROVIDER
from weaver.storage.db import connect_database, connect_readonly_database, transaction
from weaver.storage.projects import ProjectRecord, get_project
from weaver.storage.translation_memory import (
    TranslationMemoryRecord,
    count_memory_reuses,
    delete_translation_memory,
    list_translation_memory,
)


@dataclass(frozen=True)
class MemoryOverview:
    """A project's translation-memory entries plus reuse statistics."""

    total_entries: int
    exact_hits: int
    reused_from_memory: int
    entries: tuple[TranslationMemoryRecord, ...]


def get_memory_overview(project_toml: Path, *, cwd: Path | None = None) -> MemoryOverview:
    """Return all translation-memory entries and reuse statistics (read-only).

    ``exact_hits`` and ``reused_from_memory`` are both the count of translation
    attempts served from memory (exact match is the only match type today).
    """

    db_path = resolve_database_path(project_toml, cwd=cwd)
    with closing(connect_readonly_database(db_path)) as connection:
        project = _load_single_project(connection)
        entries = tuple(list_translation_memory(connection, project_id=project.id))
        reuses = count_memory_reuses(
            connection, project_id=project.id, provider_marker=MEMORY_PROVIDER
        )
    return MemoryOverview(
        total_entries=len(entries),
        exact_hits=reuses,
        reused_from_memory=reuses,
        entries=entries,
    )


def delete_entry(project_toml: Path, *, source_hash: str, cwd: Path | None = None) -> None:
    """Delete one translation-memory entry identified by ``source_hash``.

    Removes only the ``translation_memory`` row; never touches translation
    history, manual edits, glossary, or character data.

    Raises:
        TranslationMemoryNotFoundError: If no entry with that source hash exists.
    """

    db_path = resolve_database_path(project_toml, cwd=cwd)
    with closing(connect_database(db_path)) as connection:
        project = _load_single_project(connection)
        with transaction(connection):
            if not delete_translation_memory(
                connection, project_id=project.id, source_hash=source_hash
            ):
                raise _not_found(source_hash)


def _not_found(source_hash: str) -> TranslationMemoryNotFoundError:
    return TranslationMemoryNotFoundError(
        f"Translation memory entry '{source_hash}' was not found in this project. "
        "Likely cause: the source hash is wrong or was already deleted. "
        "Next command: list entries (GET /projects/<name>/memory) to see source hashes."
    )


def _load_single_project(connection: sqlite3.Connection) -> ProjectRecord:
    row = connection.execute("SELECT id FROM projects ORDER BY id LIMIT 1").fetchone()
    if row is None:
        raise ConfigError(
            "Project database has no project row. "
            "Likely cause: database was not initialized by `weaver init`. "
            "Next command: run `weaver init <input.epub>`."
        )
    return get_project(connection, int(row["id"]))
