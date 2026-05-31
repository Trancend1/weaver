"""Character database management service (Sprint 5B).

Project-scoped CRUD over the ``characters`` table, keyed by Japanese name. Used
by the FastAPI cockpit; prompt injection of character context lands in 5C.

Framework-agnostic: no web types. The FastAPI router adapts results and maps the
raised exceptions to HTTP status codes.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from weaver.errors import CharacterNotFoundError, ConfigError
from weaver.services.project_paths import resolve_database_path
from weaver.storage.characters import (
    CharacterRecord,
    delete_character,
    get_character,
    list_characters,
    upsert_character,
)
from weaver.storage.db import connect_database, connect_readonly_database, transaction
from weaver.storage.projects import ProjectRecord, get_project


def list_all(project_toml: Path, *, cwd: Path | None = None) -> tuple[CharacterRecord, ...]:
    """Return all characters for a project (read-only, insertion order)."""

    db_path = resolve_database_path(project_toml, cwd=cwd)
    with closing(connect_readonly_database(db_path)) as connection:
        project = _load_single_project(connection)
        return tuple(list_characters(connection, project_id=project.id))


def add_character(
    project_toml: Path,
    *,
    jp_name: str,
    en_name: str,
    gender: str | None = None,
    role: str | None = None,
    notes: str | None = None,
    cwd: Path | None = None,
) -> CharacterRecord:
    """Add or upsert one character (keyed by ``jp_name`` within the project).

    Raises:
        ValueError: If ``jp_name`` or ``en_name`` is empty after stripping.
    """

    clean_jp = jp_name.strip()
    clean_en = en_name.strip()
    _require(clean_jp, "jp_name")
    _require(clean_en, "en_name")

    db_path = resolve_database_path(project_toml, cwd=cwd)
    with closing(connect_database(db_path)) as connection:
        project = _load_single_project(connection)
        with transaction(connection):
            return upsert_character(
                connection,
                project_id=project.id,
                jp_name=clean_jp,
                en_name=clean_en,
                gender=_clean_optional(gender),
                role=_clean_optional(role),
                notes=_clean_optional(notes),
            )


def update_character(
    project_toml: Path,
    *,
    jp_name: str,
    en_name: str,
    gender: str | None = None,
    role: str | None = None,
    notes: str | None = None,
    cwd: Path | None = None,
) -> CharacterRecord:
    """Update an existing character identified by ``jp_name``.

    Raises:
        CharacterNotFoundError: If no character with that Japanese name exists.
        ValueError: If ``en_name`` is empty after stripping.
    """

    clean_en = en_name.strip()
    _require(clean_en, "en_name")

    db_path = resolve_database_path(project_toml, cwd=cwd)
    with closing(connect_database(db_path)) as connection:
        project = _load_single_project(connection)
        if get_character(connection, project_id=project.id, jp_name=jp_name) is None:
            raise _not_found(jp_name)
        with transaction(connection):
            return upsert_character(
                connection,
                project_id=project.id,
                jp_name=jp_name,
                en_name=clean_en,
                gender=_clean_optional(gender),
                role=_clean_optional(role),
                notes=_clean_optional(notes),
            )


def delete(project_toml: Path, *, jp_name: str, cwd: Path | None = None) -> None:
    """Delete one character identified by ``jp_name``.

    Raises:
        CharacterNotFoundError: If no character with that Japanese name exists.
    """

    db_path = resolve_database_path(project_toml, cwd=cwd)
    with closing(connect_database(db_path)) as connection:
        project = _load_single_project(connection)
        with transaction(connection):
            if not delete_character(connection, project_id=project.id, jp_name=jp_name):
                raise _not_found(jp_name)


def _require(value: str, field: str) -> None:
    if not value:
        raise ValueError(
            f"Character `{field}` cannot be empty. "
            f"Likely cause: the request carried no `{field}` value. "
            f"Next command: resend with a non-empty `{field}`."
        )


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _not_found(jp_name: str) -> CharacterNotFoundError:
    return CharacterNotFoundError(
        f"Character '{jp_name}' was not found in this project. "
        "Likely cause: the Japanese name is wrong or was already deleted. "
        "Next command: list characters (GET /projects/<name>/characters) to see names."
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
