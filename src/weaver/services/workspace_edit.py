"""Write service for cockpit workspace translation edits (Sprint 3B).

Persists a manually edited translation for one segment, scoped to its chapter:
the segment must belong to the named chapter or the edit is rejected. The source
text and source hash are never mutated; only a new translation attempt is
recorded and the segment status is set to ``manual``.

Framework-agnostic: no web types here. The FastAPI router adapts the result and
maps the exception types to HTTP status codes. Autosave and revision history are
later stages and live elsewhere.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from weaver.core.segment import normalize_japanese_text
from weaver.errors import ChapterNotFoundError, SegmentNotFoundError
from weaver.services.project_paths import resolve_database_path
from weaver.storage.db import connect_database, transaction
from weaver.storage.segments import SegmentRecord, get_segment, update_segment_status
from weaver.storage.translation_memory import save_translation_memory
from weaver.storage.translations import record_translation

MANUAL_PROVIDER_NAME = "manual"
MANUAL_PROVIDER_MODEL = "manual"


@dataclass(frozen=True)
class SegmentEditResult:
    """Outcome of a workspace translation save."""

    segment_id: str
    status: str
    translated_text: str
    saved_at: str


def save_segment_translation(
    project_toml: Path,
    chapter_id: str,
    segment_id: str,
    translated_text: str,
    *,
    cwd: Path | None = None,
) -> SegmentEditResult:
    """Persist a manual translation for one segment within a chapter.

    Args:
        project_toml: Path to the project's ``project.toml``.
        chapter_id: Chapter the segment must belong to.
        segment_id: Target segment id.
        translated_text: User-edited translation text.
        cwd: Working directory used to resolve project-relative paths.

    Returns:
        SegmentEditResult with the stored text, ``manual`` status, and save time.

    Raises:
        ChapterNotFoundError: If the chapter id does not exist in the project.
        SegmentNotFoundError: If the segment does not exist or is not in the chapter.
        ValueError: If ``translated_text`` is empty after stripping whitespace.
    """

    cleaned = translated_text.strip()
    if not cleaned:
        raise ValueError(
            "Translation cannot be empty. "
            "Likely cause: the save request carried no translation text. "
            "Next command: send a non-empty `translated_text` value."
        )

    db_path = resolve_database_path(project_toml, cwd=cwd)
    with closing(connect_database(db_path)) as connection:
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

        with transaction(connection):
            attempt = record_translation(
                connection,
                segment_id=segment.id,
                text=cleaned,
                source_hash=segment.source_hash,
                provider=MANUAL_PROVIDER_NAME,
                model=MANUAL_PROVIDER_MODEL,
            )
            update_segment_status(connection, segment_id=segment.id, status="manual")
            _remember_manual_translation(connection, segment=segment, target_text=cleaned)

        saved_at = _translation_saved_at(connection, segment_id=segment.id, attempt=attempt)

    return SegmentEditResult(
        segment_id=segment.id,
        status="manual",
        translated_text=cleaned,
        saved_at=saved_at,
    )


def _chapter_exists(connection: sqlite3.Connection, chapter_id: str) -> bool:
    row = connection.execute("SELECT 1 FROM chapters WHERE id = ?", (chapter_id,)).fetchone()
    return row is not None


def _remember_manual_translation(
    connection: sqlite3.Connection, *, segment: SegmentRecord, target_text: str
) -> None:
    """Store a manual edit in translation memory (manual is the source of truth).

    Manual saves upsert unconditionally so the latest manual edit wins; a later
    provider translation never overwrites it (``protect_manual`` on that path).
    """

    project_row = connection.execute("SELECT id FROM projects ORDER BY id LIMIT 1").fetchone()
    if project_row is None:  # pragma: no cover - an initialized project always has a row
        return
    save_translation_memory(
        connection,
        project_id=int(project_row["id"]),
        source_text=normalize_japanese_text(segment.source_text),
        source_hash=segment.source_hash,
        target_text=target_text,
        provider=MANUAL_PROVIDER_NAME,
        model=MANUAL_PROVIDER_MODEL,
    )


def _translation_saved_at(connection: sqlite3.Connection, *, segment_id: str, attempt: int) -> str:
    row = connection.execute(
        "SELECT created_at FROM translations WHERE segment_id = ? AND attempt = ?",
        (segment_id, attempt),
    ).fetchone()
    return str(row["created_at"])
