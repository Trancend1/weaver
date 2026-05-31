"""Glossary repository functions."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Literal

from weaver.providers.types import GlossaryTerm

GlossaryCandidateStatus = Literal["pending", "approved", "rejected", "edited"]


@dataclass(frozen=True)
class GlossaryCandidateRecord:
    """Stored glossary candidate row."""

    id: int
    project_id: int
    source: str
    target: str | None
    category: str | None
    notes: str | None
    status: str
    frequency: int


def list_glossary_terms(connection: sqlite3.Connection, *, project_id: int) -> list[GlossaryTerm]:
    """Load approved glossary terms for a project.

    Args:
        connection: Open SQLite connection.
        project_id: Project row id.

    Returns:
        Glossary terms in stable id order. Empty list when no terms are
        approved yet (the glossary review workflow ships in Phase 5).
    """

    rows = connection.execute(
        """
        SELECT source, target, category, notes, case_sensitive
        FROM glossary_terms
        WHERE project_id = ?
        ORDER BY id
        """,
        (project_id,),
    ).fetchall()
    return [
        GlossaryTerm(
            source=str(row["source"]),
            target=str(row["target"]),
            category=_optional_str(row["category"]),
            notes=_optional_str(row["notes"]),
            case_sensitive=bool(row["case_sensitive"]),
        )
        for row in rows
    ]


def get_glossary_term(
    connection: sqlite3.Connection, *, project_id: int, source: str
) -> GlossaryTerm | None:
    """Load one approved glossary term by its source, or None if absent."""

    row = connection.execute(
        """
        SELECT source, target, category, notes, case_sensitive
        FROM glossary_terms
        WHERE project_id = ? AND source = ?
        """,
        (project_id, source),
    ).fetchone()
    if row is None:
        return None
    return GlossaryTerm(
        source=str(row["source"]),
        target=str(row["target"]),
        category=_optional_str(row["category"]),
        notes=_optional_str(row["notes"]),
        case_sensitive=bool(row["case_sensitive"]),
    )


def upsert_glossary_term(
    connection: sqlite3.Connection,
    *,
    project_id: int,
    source: str,
    target: str,
    category: str | None = None,
    notes: str | None = None,
    case_sensitive: bool = False,
) -> GlossaryTerm:
    """Insert or update one approved glossary term.

    Writes directly to the same ``glossary_terms`` table the candidate review
    flow populates (UNIQUE(project_id, source) → upsert, never a duplicate row).
    """

    connection.execute(
        """
        INSERT INTO glossary_terms (
          project_id,
          source,
          target,
          category,
          notes,
          case_sensitive
        )
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(project_id, source) DO UPDATE SET
          target = excluded.target,
          category = excluded.category,
          notes = excluded.notes,
          case_sensitive = excluded.case_sensitive
        """,
        (project_id, source, target, category, notes, 1 if case_sensitive else 0),
    )
    stored = get_glossary_term(connection, project_id=project_id, source=source)
    if stored is None:  # pragma: no cover - upsert always yields a row
        raise RuntimeError("Glossary term upsert did not persist a row")
    return stored


def delete_glossary_term(
    connection: sqlite3.Connection, *, project_id: int, source: str
) -> bool:
    """Delete one approved glossary term; return whether a row was removed."""

    cursor = connection.execute(
        "DELETE FROM glossary_terms WHERE project_id = ? AND source = ?",
        (project_id, source),
    )
    return cursor.rowcount > 0


def insert_glossary_candidate(
    connection: sqlite3.Connection,
    *,
    project_id: int,
    source: str,
    target: str | None,
    category: str | None,
    notes: str | None,
    status: GlossaryCandidateStatus,
    frequency: int,
) -> int:
    """Insert one glossary candidate and return its row id."""

    cursor = connection.execute(
        """
        INSERT INTO glossary_candidates (
          project_id,
          source,
          target,
          category,
          notes,
          status,
          frequency
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (project_id, source, target, category, notes, status, frequency),
    )
    if cursor.lastrowid is None:
        raise RuntimeError("Glossary candidate insert did not return a row id")
    return int(cursor.lastrowid)


def list_glossary_candidates(
    connection: sqlite3.Connection, *, project_id: int
) -> list[GlossaryCandidateRecord]:
    """List glossary candidates in stable review order."""

    rows = connection.execute(
        """
        SELECT id, project_id, source, target, category, notes, status, frequency
        FROM glossary_candidates
        WHERE project_id = ?
        ORDER BY frequency DESC, source, id
        """,
        (project_id,),
    ).fetchall()
    return [_candidate_from_row(row) for row in rows]


def list_pending_glossary_candidates(
    connection: sqlite3.Connection,
    *,
    project_id: int,
    offset: int = 0,
    limit: int = 20,
    find: str | None = None,
) -> list[GlossaryCandidateRecord]:
    """List pending candidates in review order, paginated.

    Order matches `get_pending_glossary_candidate` (frequency desc, source, id)
    so browser pagination and the CLI loop agree on sequence. When `find` is
    given, only candidates whose source contains it (case-insensitive) are
    returned.
    """

    needle = (find or "").strip()
    if needle:
        rows = connection.execute(
            """
            SELECT id, project_id, source, target, category, notes, status, frequency
            FROM glossary_candidates
            WHERE project_id = ? AND status = 'pending' AND source LIKE ?
            ORDER BY frequency DESC, source, id
            LIMIT ? OFFSET ?
            """,
            (project_id, f"%{needle}%", limit, offset),
        ).fetchall()
    else:
        rows = connection.execute(
            """
            SELECT id, project_id, source, target, category, notes, status, frequency
            FROM glossary_candidates
            WHERE project_id = ? AND status = 'pending'
            ORDER BY frequency DESC, source, id
            LIMIT ? OFFSET ?
            """,
            (project_id, limit, offset),
        ).fetchall()
    return [_candidate_from_row(row) for row in rows]


def count_pending_glossary_candidates(
    connection: sqlite3.Connection, *, project_id: int, find: str | None = None
) -> int:
    """Count pending candidates, optionally filtered by a source substring."""

    needle = (find or "").strip()
    if needle:
        row = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM glossary_candidates
            WHERE project_id = ? AND status = 'pending' AND source LIKE ?
            """,
            (project_id, f"%{needle}%"),
        ).fetchone()
    else:
        row = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM glossary_candidates
            WHERE project_id = ? AND status = 'pending'
            """,
            (project_id,),
        ).fetchone()
    return int(row["count"])


def get_pending_glossary_candidate(
    connection: sqlite3.Connection, *, project_id: int
) -> GlossaryCandidateRecord | None:
    """Return the next pending glossary candidate for interactive review."""

    row = connection.execute(
        """
        SELECT id, project_id, source, target, category, notes, status, frequency
        FROM glossary_candidates
        WHERE project_id = ? AND status = 'pending'
        ORDER BY frequency DESC, source, id
        LIMIT 1
        """,
        (project_id,),
    ).fetchone()
    if row is None:
        return None
    return _candidate_from_row(row)


def approve_glossary_candidate(
    connection: sqlite3.Connection, *, candidate_id: int
) -> GlossaryCandidateRecord:
    """Approve a candidate and copy it to approved glossary terms."""

    candidate = get_glossary_candidate(connection, candidate_id=candidate_id)
    target = candidate.target or candidate.source
    connection.execute(
        "UPDATE glossary_candidates SET status = 'approved', target = ? WHERE id = ?",
        (target, candidate_id),
    )
    _upsert_term(connection, candidate=candidate, target=target, notes=candidate.notes)
    return get_glossary_candidate(connection, candidate_id=candidate_id)


def edit_glossary_candidate(
    connection: sqlite3.Connection,
    *,
    candidate_id: int,
    target: str,
    notes: str | None,
) -> GlossaryCandidateRecord:
    """Edit and approve a candidate with translator-provided wording."""

    candidate = get_glossary_candidate(connection, candidate_id=candidate_id)
    clean_target = target.strip() or candidate.source
    connection.execute(
        """
        UPDATE glossary_candidates
        SET status = 'edited', target = ?, notes = ?
        WHERE id = ?
        """,
        (clean_target, notes, candidate_id),
    )
    _upsert_term(connection, candidate=candidate, target=clean_target, notes=notes)
    return get_glossary_candidate(connection, candidate_id=candidate_id)


def reject_glossary_candidate(
    connection: sqlite3.Connection, *, candidate_id: int
) -> GlossaryCandidateRecord:
    """Reject a candidate and remove its approved glossary term."""

    candidate = get_glossary_candidate(connection, candidate_id=candidate_id)
    connection.execute(
        "UPDATE glossary_candidates SET status = 'rejected' WHERE id = ?",
        (candidate_id,),
    )
    connection.execute(
        "DELETE FROM glossary_terms WHERE project_id = ? AND source = ?",
        (candidate.project_id, candidate.source),
    )
    return get_glossary_candidate(connection, candidate_id=candidate_id)


def restore_glossary_candidate(
    connection: sqlite3.Connection, *, candidate: GlossaryCandidateRecord
) -> None:
    """Restore one candidate snapshot for same-session undo."""

    connection.execute(
        """
        UPDATE glossary_candidates
        SET target = ?, category = ?, notes = ?, status = ?, frequency = ?
        WHERE id = ?
        """,
        (
            candidate.target,
            candidate.category,
            candidate.notes,
            candidate.status,
            candidate.frequency,
            candidate.id,
        ),
    )
    connection.execute(
        "DELETE FROM glossary_terms WHERE project_id = ? AND source = ?",
        (candidate.project_id, candidate.source),
    )
    if candidate.status in {"approved", "edited"}:
        _upsert_term(
            connection,
            candidate=candidate,
            target=candidate.target or candidate.source,
            notes=candidate.notes,
        )


def get_glossary_candidate(
    connection: sqlite3.Connection, *, candidate_id: int
) -> GlossaryCandidateRecord:
    """Load one glossary candidate by id."""

    row = connection.execute(
        """
        SELECT id, project_id, source, target, category, notes, status, frequency
        FROM glossary_candidates
        WHERE id = ?
        """,
        (candidate_id,),
    ).fetchone()
    if row is None:
        raise LookupError(f"Glossary candidate not found: {candidate_id}")
    return _candidate_from_row(row)


def count_glossary_candidates_by_status(
    connection: sqlite3.Connection, *, project_id: int
) -> dict[str, int]:
    """Return glossary candidate status counts."""

    return {
        str(row["status"]): int(row["count"])
        for row in connection.execute(
            """
            SELECT status, COUNT(*) AS count
            FROM glossary_candidates
            WHERE project_id = ?
            GROUP BY status
            """,
            (project_id,),
        ).fetchall()
    }


def list_glossary_conflicts(
    connection: sqlite3.Connection, *, project_id: int
) -> list[tuple[str, tuple[str, ...]]]:
    """List approved/edited candidate conflicts by source term."""

    rows = connection.execute(
        """
        SELECT source, target
        FROM glossary_candidates
        WHERE project_id = ?
          AND status IN ('approved', 'edited')
          AND target IS NOT NULL
          AND target != ''
        ORDER BY source, target
        """,
        (project_id,),
    ).fetchall()
    targets_by_source: dict[str, set[str]] = {}
    for row in rows:
        targets_by_source.setdefault(str(row["source"]), set()).add(str(row["target"]))
    return [
        (source, tuple(sorted(targets)))
        for source, targets in sorted(targets_by_source.items())
        if len(targets) > 1
    ]


def _upsert_term(
    connection: sqlite3.Connection,
    *,
    candidate: GlossaryCandidateRecord,
    target: str,
    notes: str | None,
) -> None:
    upsert_glossary_term(
        connection,
        project_id=candidate.project_id,
        source=candidate.source,
        target=target,
        category=candidate.category,
        notes=notes,
        case_sensitive=False,
    )


def _candidate_from_row(row: sqlite3.Row) -> GlossaryCandidateRecord:
    return GlossaryCandidateRecord(
        id=int(row["id"]),
        project_id=int(row["project_id"]),
        source=str(row["source"]),
        target=_optional_str(row["target"]),
        category=_optional_str(row["category"]),
        notes=_optional_str(row["notes"]),
        status=str(row["status"]),
        frequency=int(row["frequency"]),
    )


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)
