"""Read-only translation revision history for one segment (Sprint 3C).

Every manual save records a new row in ``translations`` keyed by
``(segment_id, attempt)``; this service exposes that history. The latest attempt
is the current translation — read behavior elsewhere is unchanged.

Framework-agnostic: no web types. The FastAPI router adapts the result and maps
the exception types to HTTP status codes.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from weaver.errors import ChapterNotFoundError, SegmentNotFoundError
from weaver.services.project_paths import resolve_database_path
from weaver.storage.db import connect_readonly_database
from weaver.storage.segments import get_segment
from weaver.storage.translations import TranslationAttempt, list_translation_attempts


@dataclass(frozen=True)
class SegmentHistory:
    """A segment's current translation plus its full attempt history."""

    segment_id: str
    chapter_id: str
    status: str
    current_translation: str | None
    attempts: list[TranslationAttempt]


def segment_translation_history(
    project_toml: Path,
    chapter_id: str,
    segment_id: str,
    *,
    cwd: Path | None = None,
) -> SegmentHistory:
    """Return the revision history for one segment within a chapter.

    Args:
        project_toml: Path to the project's ``project.toml``.
        chapter_id: Chapter the segment must belong to.
        segment_id: Target segment id.
        cwd: Working directory used to resolve project-relative paths.

    Returns:
        SegmentHistory with the current translation (latest attempt, or ``None``)
        and all attempts oldest-first.

    Raises:
        ChapterNotFoundError: If the chapter id does not exist in the project.
        SegmentNotFoundError: If the segment does not exist or is not in the chapter.
    """

    db_path = resolve_database_path(project_toml, cwd=cwd)
    with closing(connect_readonly_database(db_path)) as connection:
        if not _chapter_exists(connection, chapter_id):
            raise ChapterNotFoundError(
                f"Chapter '{chapter_id}' was not found in this project. "
                "Likely cause: the chapter id is wrong or its volume was removed. "
                "Next command: open the project tree (GET /projects/<name>/tree) "
                "to list chapter ids."
            )

        segment = get_segment(connection, segment_id)
        if segment is None or segment.chapter_id != chapter_id:
            raise SegmentNotFoundError(
                f"Segment '{segment_id}' was not found in chapter '{chapter_id}'. "
                "Likely cause: the segment id is wrong or belongs to another chapter. "
                "Next command: open the chapter workspace "
                "(GET /projects/<name>/chapters/<chapter_id>/workspace) to list segment ids."
            )

        attempts = list_translation_attempts(connection, segment_id=segment_id)

    current_translation = attempts[-1].text if attempts else None
    return SegmentHistory(
        segment_id=segment_id,
        chapter_id=chapter_id,
        status=segment.status,
        current_translation=current_translation,
        attempts=attempts,
    )


def _chapter_exists(connection: sqlite3.Connection, chapter_id: str) -> bool:
    row = connection.execute("SELECT 1 FROM chapters WHERE id = ?", (chapter_id,)).fetchone()
    return row is not None
