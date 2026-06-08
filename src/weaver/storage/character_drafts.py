"""Character page draft repository functions (Sprint L).

One row per XHTML/text-only character page extraction. Drafts are generated from
parsed EPUB character pages that contain actual text content (headings, name
lists, descriptions, aliases). No OCR, no image processing.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

DraftStatus = Literal[
    "draft",
    "approved",
    "rejected",
]


@dataclass(frozen=True)
class CharacterDraftRecord:
    """One stored character page draft row."""

    id: str
    project_id: int
    volume_id: int | None
    chapter_id: str
    segment_id: str | None
    source_text: str
    draft_text: str
    heading: str | None
    page_identifier: str | None
    status: str
    provenance_json: str
    created_at: str
    updated_at: str


def insert_draft(
    connection: sqlite3.Connection,
    *,
    project_id: int,
    volume_id: int | None,
    chapter_id: str,
    segment_id: str | None,
    source_text: str,
    draft_text: str,
    heading: str | None,
    page_identifier: str | None,
    provenance_json: str,
) -> CharacterDraftRecord:
    """Insert one character page draft and return its record.

    Args:
        connection: Open writable SQLite connection.
        project_id: Owning project id.
        volume_id: Owning volume id, if known.
        chapter_id: Chapter the segment/character page belongs to.
        segment_id: Optional segment id that contains the character reference.
        source_text: Raw XHTML text content of the character page.
        draft_text: AI-generated draft text (character description/notes).
        heading: Page heading extracted from XHTML.
        page_identifier: Unique identifier for the character page (e.g. href).
        provenance_json: JSON blob with full provenance.

    Returns:
        The inserted CharacterDraftRecord.
    """

    now = datetime.now(UTC).isoformat()
    draft_id = uuid4().hex
    connection.execute(
        """
        INSERT INTO character_page_drafts (
          id, project_id, volume_id, chapter_id, segment_id,
          source_text, draft_text, heading, page_identifier, status,
          provenance_json, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'draft', ?, ?, ?)
        """,
        (
            draft_id,
            project_id,
            volume_id,
            chapter_id,
            segment_id,
            source_text,
            draft_text,
            heading,
            page_identifier,
            provenance_json,
            now,
            now,
        ),
    )
    return get_draft(connection, draft_id=draft_id)


def get_draft(connection: sqlite3.Connection, *, draft_id: str) -> CharacterDraftRecord:
    """Load one draft by id.

    Args:
        connection: Open SQLite connection.
        draft_id: Draft id.

    Returns:
        CharacterDraftRecord.

    Raises:
        LookupError: If the draft does not exist.
    """

    row = connection.execute(
        "SELECT * FROM character_page_drafts WHERE id = ?",
        (draft_id,),
    ).fetchone()
    if row is None:
        raise LookupError(f"Character page draft not found: {draft_id}")
    return _draft_from_row(row)


def list_drafts_for_project(
    connection: sqlite3.Connection,
    *,
    project_id: int,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[CharacterDraftRecord]:
    """List drafts for a project, paged.

    Args:
        connection: Open SQLite connection.
        project_id: Project id to filter by.
        status: Optional status filter.
        limit: Page size.
        offset: Page offset.

    Returns:
        List of CharacterDraftRecord ordered by created_at descending.
    """

    if status is not None:
        rows = connection.execute(
            """
            SELECT * FROM character_page_drafts
            WHERE project_id = ? AND status = ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (project_id, status, limit, offset),
        ).fetchall()
    else:
        rows = connection.execute(
            """
            SELECT * FROM character_page_drafts
            WHERE project_id = ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (project_id, limit, offset),
        ).fetchall()
    return [_draft_from_row(row) for row in rows]


def update_draft_status(
    connection: sqlite3.Connection,
    *,
    draft_id: str,
    status: str,
) -> CharacterDraftRecord:
    """Update a draft's status and updated_at timestamp.

    Args:
        connection: Open writable SQLite connection.
        draft_id: Draft id to update.
        status: New status value.

    Returns:
        Updated CharacterDraftRecord.
    """

    now = datetime.now(UTC).isoformat()
    connection.execute(
        """
        UPDATE character_page_drafts
        SET status = ?, updated_at = ?
        WHERE id = ?
        """,
        (status, now, draft_id),
    )
    return get_draft(connection, draft_id=draft_id)


def _draft_from_row(row: sqlite3.Row) -> CharacterDraftRecord:
    return CharacterDraftRecord(
        id=str(row["id"]),
        project_id=int(row["project_id"]),
        volume_id=None if row["volume_id"] is None else int(row["volume_id"]),
        chapter_id=str(row["chapter_id"]),
        segment_id=None if row["segment_id"] is None else str(row["segment_id"]),
        source_text=str(row["source_text"]),
        draft_text=str(row["draft_text"]),
        heading=None if row["heading"] is None else str(row["heading"]),
        page_identifier=None if row["page_identifier"] is None else str(row["page_identifier"]),
        status=str(row["status"]),
        provenance_json=str(row["provenance_json"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )
