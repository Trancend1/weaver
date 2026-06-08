"""Translation candidate repository functions (Sprint L).

One row per AI-generated candidate translation. Every row carries a full
provenance record (provider, model, prompt_version, source segments, timestamps).
Status transitions: pending -> approved / rejected / superseded / failed.
Approved candidates are applied via ``candidate_apply.py`` which copies the
candidate text into the ``translations`` table (creating a normal history entry).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

CandidateStatus = Literal[
    "pending",
    "approved",
    "rejected",
    "applied",
    "superseded",
    "failed",
]


@dataclass(frozen=True)
class CandidateRecord:
    """One stored translation candidate row."""

    id: str
    project_id: int
    volume_id: int | None
    chapter_id: str
    segment_id: str
    source_text: str
    candidate_text: str
    provider: str
    model: str
    status: str
    provenance_json: str
    created_at: str
    updated_at: str


def insert_candidate(
    connection: sqlite3.Connection,
    *,
    project_id: int,
    volume_id: int | None,
    chapter_id: str,
    segment_id: str,
    source_text: str,
    candidate_text: str,
    provider: str,
    model: str,
    provenance_json: str,
) -> CandidateRecord:
    """Insert one translation candidate and return its record.

    Args:
        connection: Open writable SQLite connection.
        project_id: Owning project id.
        volume_id: Owning volume id, if known.
        chapter_id: Chapter the segment belongs to.
        segment_id: Target segment id.
        source_text: Source text the candidate was generated from.
        candidate_text: AI-generated candidate translation.
        provider: Provider name.
        model: Provider model name.
        provenance_json: JSON blob with full provenance (prompt_version, context, etc).

    Returns:
        The inserted CandidateRecord.
    """

    now = datetime.now(UTC).isoformat()
    candidate_id = uuid4().hex
    connection.execute(
        """
        INSERT INTO translation_candidates (
          id, project_id, volume_id, chapter_id, segment_id,
          source_text, candidate_text, provider, model, status,
          provenance_json, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)
        """,
        (
            candidate_id,
            project_id,
            volume_id,
            chapter_id,
            segment_id,
            source_text,
            candidate_text,
            provider,
            model,
            provenance_json,
            now,
            now,
        ),
    )
    return get_candidate(connection, candidate_id=candidate_id)


def get_candidate(connection: sqlite3.Connection, *, candidate_id: str) -> CandidateRecord:
    """Load one candidate by id.

    Args:
        connection: Open SQLite connection.
        candidate_id: Candidate id.

    Returns:
        CandidateRecord.

    Raises:
        LookupError: If the candidate does not exist.
    """

    row = connection.execute(
        "SELECT * FROM translation_candidates WHERE id = ?",
        (candidate_id,),
    ).fetchone()
    if row is None:
        raise LookupError(f"Translation candidate not found: {candidate_id}")
    return _candidate_from_row(row)


def list_candidates_for_segment(
    connection: sqlite3.Connection,
    *,
    segment_id: str,
    status: str | None = None,
) -> list[CandidateRecord]:
    """List all candidates for a segment, newest first.

    Args:
        connection: Open SQLite connection.
        segment_id: Segment id to filter by.
        status: Optional status filter.

    Returns:
        List of CandidateRecord ordered by created_at descending.
    """

    if status is not None:
        rows = connection.execute(
            """
            SELECT * FROM translation_candidates
            WHERE segment_id = ? AND status = ?
            ORDER BY created_at DESC
            """,
            (segment_id, status),
        ).fetchall()
    else:
        rows = connection.execute(
            """
            SELECT * FROM translation_candidates
            WHERE segment_id = ?
            ORDER BY created_at DESC
            """,
            (segment_id,),
        ).fetchall()
    return [_candidate_from_row(row) for row in rows]


def list_candidates_for_chapter(
    connection: sqlite3.Connection,
    *,
    chapter_id: str,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[CandidateRecord]:
    """List candidates for a chapter, paged.

    Args:
        connection: Open SQLite connection.
        chapter_id: Chapter id to filter by.
        status: Optional status filter.
        limit: Page size.
        offset: Page offset.

    Returns:
        List of CandidateRecord ordered by created_at descending.
    """

    if status is not None:
        rows = connection.execute(
            """
            SELECT * FROM translation_candidates
            WHERE chapter_id = ? AND status = ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (chapter_id, status, limit, offset),
        ).fetchall()
    else:
        rows = connection.execute(
            """
            SELECT * FROM translation_candidates
            WHERE chapter_id = ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (chapter_id, limit, offset),
        ).fetchall()
    return [_candidate_from_row(row) for row in rows]


def list_candidates_for_project(
    connection: sqlite3.Connection,
    *,
    project_id: int,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[CandidateRecord]:
    """List candidates for a project, paged.

    Args:
        connection: Open SQLite connection.
        project_id: Project id to filter by.
        status: Optional status filter.
        limit: Page size.
        offset: Page offset.

    Returns:
        List of CandidateRecord ordered by created_at descending.
    """

    if status is not None:
        rows = connection.execute(
            """
            SELECT * FROM translation_candidates
            WHERE project_id = ? AND status = ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (project_id, status, limit, offset),
        ).fetchall()
    else:
        rows = connection.execute(
            """
            SELECT * FROM translation_candidates
            WHERE project_id = ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (project_id, limit, offset),
        ).fetchall()
    return [_candidate_from_row(row) for row in rows]


def count_candidates_for_project(
    connection: sqlite3.Connection,
    *,
    project_id: int,
    status: str | None = None,
) -> int:
    """Count candidates for a project, optionally filtered by status."""

    if status is not None:
        row = connection.execute(
            "SELECT COUNT(*) AS count FROM translation_candidates "
            "WHERE project_id = ? AND status = ?",
            (project_id, status),
        ).fetchone()
    else:
        row = connection.execute(
            "SELECT COUNT(*) AS count FROM translation_candidates WHERE project_id = ?",
            (project_id,),
        ).fetchone()
    return int(row["count"])


def update_candidate_status(
    connection: sqlite3.Connection,
    *,
    candidate_id: str,
    status: str,
) -> CandidateRecord:
    """Update a candidate's status and updated_at timestamp.

    Args:
        connection: Open writable SQLite connection.
        candidate_id: Candidate id to update.
        status: New status value.

    Returns:
        Updated CandidateRecord.
    """

    now = datetime.now(UTC).isoformat()
    connection.execute(
        """
        UPDATE translation_candidates
        SET status = ?, updated_at = ?
        WHERE id = ?
        """,
        (status, now, candidate_id),
    )
    return get_candidate(connection, candidate_id=candidate_id)


def supersede_candidates_for_segment(
    connection: sqlite3.Connection,
    *,
    segment_id: str,
    exclude_id: str | None = None,
) -> int:
    """Mark all pending/approved candidates for a segment as superseded.

    Called when a new candidate is generated for the same segment or when an
    existing candidate is applied. The ``exclude_id`` is preserved unchanged.

    Args:
        connection: Open writable SQLite connection.
        segment_id: Segment id whose candidates are superseded.
        exclude_id: Optional candidate id to exclude from superseding.

    Returns:
        Number of rows updated.
    """

    now = datetime.now(UTC).isoformat()
    if exclude_id is not None:
        cursor = connection.execute(
            """
            UPDATE translation_candidates
            SET status = 'superseded', updated_at = ?
            WHERE segment_id = ?
              AND id != ?
              AND status IN ('pending', 'approved')
            """,
            (now, segment_id, exclude_id),
        )
    else:
        cursor = connection.execute(
            """
            UPDATE translation_candidates
            SET status = 'superseded', updated_at = ?
            WHERE segment_id = ?
              AND status IN ('pending', 'approved')
            """,
            (now, segment_id),
        )
    return cursor.rowcount


def _candidate_from_row(row: sqlite3.Row) -> CandidateRecord:
    return CandidateRecord(
        id=str(row["id"]),
        project_id=int(row["project_id"]),
        volume_id=None if row["volume_id"] is None else int(row["volume_id"]),
        chapter_id=str(row["chapter_id"]),
        segment_id=str(row["segment_id"]),
        source_text=str(row["source_text"]),
        candidate_text=str(row["candidate_text"]),
        provider=str(row["provider"]),
        model=str(row["model"]),
        status=str(row["status"]),
        provenance_json=str(row["provenance_json"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )
