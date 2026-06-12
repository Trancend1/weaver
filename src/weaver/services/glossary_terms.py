"""Direct glossary term management service (Sprint 5A).

Manages approved entries in the project's ``glossary_terms`` table directly:
list, add, update, delete. This is the same table the candidate review flow
(``services/glossary_review.py``) writes to — there is no second store. Manual
entry here and reviewed candidates coexist as one project-scoped glossary that
``services/translation.build_context`` injects into the prompt.

Framework-agnostic: no web types. The FastAPI router adapts results and maps the
raised exceptions to HTTP status codes.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from weaver.errors import ConfigError, GlossaryTermNotFoundError
from weaver.providers.types import GlossaryTerm
from weaver.services.project_paths import resolve_database_path
from weaver.storage.db import connect_database, connect_readonly_database, transaction
from weaver.storage.glossary import (
    count_glossary_terms,
    delete_glossary_term,
    get_glossary_term,
    list_glossary_terms,
    upsert_glossary_term,
)
from weaver.storage.projects import ProjectRecord, get_project

DEFAULT_TERMS_PAGE = 20


@dataclass(frozen=True)
class TermsPage:
    """One page of approved glossary terms plus the (filtered) total.

    ``total`` reflects the current ``find`` filter so pagination is correct.
    """

    items: tuple[GlossaryTerm, ...]
    total: int
    offset: int
    limit: int
    find: str | None = None


def list_terms(project_toml: Path, *, cwd: Path | None = None) -> tuple[GlossaryTerm, ...]:
    """Return all approved glossary terms for a project (read-only, id order)."""

    db_path = resolve_database_path(project_toml, cwd=cwd)
    with closing(connect_readonly_database(db_path)) as connection:
        project = _load_single_project(connection)
        return tuple(list_glossary_terms(connection, project_id=project.id))


def list_terms_page(
    project_toml: Path,
    *,
    cwd: Path | None = None,
    offset: int = 0,
    limit: int = DEFAULT_TERMS_PAGE,
    find: str | None = None,
) -> TermsPage:
    """Return one page of approved glossary terms plus the filtered total.

    Read-only counterpart to :func:`list_terms` for the paginated/searchable web
    admin table. When ``find`` is set, only terms whose JP source or EN target
    contains it (case-insensitive) are returned and counted.
    """

    offset = max(offset, 0)
    limit = max(limit, 1)
    needle = (find or "").strip() or None
    db_path = resolve_database_path(project_toml, cwd=cwd)
    with closing(connect_readonly_database(db_path)) as connection:
        project = _load_single_project(connection)
        items = list_glossary_terms(
            connection, project_id=project.id, find=needle, offset=offset, limit=limit
        )
        total = count_glossary_terms(connection, project_id=project.id, find=needle)
    return TermsPage(items=tuple(items), total=total, offset=offset, limit=limit, find=needle)


def add_term(
    project_toml: Path,
    *,
    source: str,
    target: str,
    category: str | None = None,
    notes: str | None = None,
    case_sensitive: bool = False,
    cwd: Path | None = None,
) -> GlossaryTerm:
    """Add or upsert one glossary term.

    Args:
        project_toml: Path to the project's ``project.toml``.
        source: Japanese source term (must be non-empty after stripping).
        target: English target term (must be non-empty after stripping).
        category: Optional category label.
        notes: Optional translator notes.
        case_sensitive: Whether source matching is case-sensitive.
        cwd: Working directory used to resolve project-relative paths.

    Returns:
        The stored :class:`GlossaryTerm`.

    Raises:
        ValueError: If ``source`` or ``target`` is empty after stripping. An
            existing term with the same source is upserted (not duplicated).
    """

    clean_source = source.strip()
    clean_target = target.strip()
    _require(clean_source, "source")
    _require(clean_target, "target")

    db_path = resolve_database_path(project_toml, cwd=cwd)
    with closing(connect_database(db_path)) as connection:
        project = _load_single_project(connection)
        with transaction(connection):
            return upsert_glossary_term(
                connection,
                project_id=project.id,
                source=clean_source,
                target=clean_target,
                category=_clean_optional(category),
                notes=_clean_optional(notes),
                case_sensitive=case_sensitive,
            )


def update_term(
    project_toml: Path,
    *,
    source: str,
    target: str,
    category: str | None = None,
    notes: str | None = None,
    case_sensitive: bool = False,
    cwd: Path | None = None,
) -> GlossaryTerm:
    """Update an existing glossary term identified by ``source``.

    Raises:
        GlossaryTermNotFoundError: If no term with that source exists.
        ValueError: If ``target`` is empty after stripping.
    """

    clean_target = target.strip()
    _require(clean_target, "target")

    db_path = resolve_database_path(project_toml, cwd=cwd)
    with closing(connect_database(db_path)) as connection:
        project = _load_single_project(connection)
        if get_glossary_term(connection, project_id=project.id, source=source) is None:
            raise _not_found(source)
        with transaction(connection):
            return upsert_glossary_term(
                connection,
                project_id=project.id,
                source=source,
                target=clean_target,
                category=_clean_optional(category),
                notes=_clean_optional(notes),
                case_sensitive=case_sensitive,
            )


def delete_term(project_toml: Path, *, source: str, cwd: Path | None = None) -> None:
    """Delete one glossary term identified by ``source``.

    Raises:
        GlossaryTermNotFoundError: If no term with that source exists.
    """

    db_path = resolve_database_path(project_toml, cwd=cwd)
    with closing(connect_database(db_path)) as connection:
        project = _load_single_project(connection)
        with transaction(connection):
            if not delete_glossary_term(connection, project_id=project.id, source=source):
                raise _not_found(source)


def _require(value: str, field: str) -> None:
    if not value:
        raise ValueError(
            f"Glossary term `{field}` cannot be empty. "
            f"Likely cause: the request carried no `{field}` value. "
            f"Next command: resend with a non-empty `{field}`."
        )


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _not_found(source: str) -> GlossaryTermNotFoundError:
    return GlossaryTermNotFoundError(
        f"Glossary term '{source}' was not found in this project. "
        "Likely cause: the source term is wrong or was already deleted. "
        "Next command: list terms (GET /projects/<name>/glossary) to see sources."
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
