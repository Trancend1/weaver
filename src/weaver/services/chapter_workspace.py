"""Read-only translation workspace view for one chapter.

Builds the JP/EN two-column workspace payload for the cockpit: chapter
identity, its source segments in block order, and the latest translation text
per segment (or ``None`` when untranslated). Read-only; never mutates state.

This is the Sprint 3A read layer. Editing, auto-save, and revisions arrive in
later stages and live elsewhere.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from weaver.core.config import load_project_config
from weaver.errors import ChapterNotFoundError
from weaver.services.project_paths import resolve_database_path
from weaver.storage.db import connect_readonly_database


@dataclass(frozen=True)
class WorkspaceSegment:
    """One source segment paired with its latest translation and review state."""

    id: str
    block_order: int
    kind: str
    source_text: str
    status: str
    translated_text: str | None
    review_status: str


@dataclass(frozen=True)
class ChapterWorkspace:
    """A chapter's source segments and translations for the workspace view."""

    project_name: str
    volume_id: int
    volume_title: str
    chapter_id: str
    chapter_title: str | None
    segment_count: int
    translated_count: int
    segments: list[WorkspaceSegment]


def chapter_workspace(
    project_toml: Path, chapter_id: str, *, cwd: Path | None = None
) -> ChapterWorkspace:
    """Build the read-only workspace view for one chapter.

    Args:
        project_toml: Path to the project's ``project.toml``.
        chapter_id: Chapter id to load.
        cwd: Working directory used to resolve project-relative paths.

    Returns:
        A ChapterWorkspace with each segment and its latest translation.

    Raises:
        ChapterNotFoundError: If the chapter id does not exist in the project.
    """

    data = load_project_config(project_toml)
    project_name = str(data["project"]["name"])
    db_path = resolve_database_path(project_toml, cwd=cwd)

    with closing(connect_readonly_database(db_path)) as connection:
        chapter = _chapter_row(connection, chapter_id)
        if chapter is None:
            raise ChapterNotFoundError(
                f"Chapter '{chapter_id}' was not found in project '{project_name}'. "
                "Likely cause: the chapter id is wrong or its volume was removed. "
                "Next command: open the project tree (GET /projects/<name>/tree) "
                "to list chapter ids."
            )
        segments = _workspace_segments(connection, chapter_id)

    translated_count = sum(1 for segment in segments if segment.status == "translated")
    return ChapterWorkspace(
        project_name=project_name,
        volume_id=int(chapter["volume_id"]),
        volume_title=str(chapter["volume_title"]),
        chapter_id=chapter_id,
        chapter_title=chapter["chapter_title"],
        segment_count=len(segments),
        translated_count=translated_count,
        segments=segments,
    )


def _chapter_row(connection: sqlite3.Connection, chapter_id: str) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT c.id AS id,
               c.title AS chapter_title,
               c.volume_id AS volume_id,
               v.title AS volume_title
        FROM chapters c
        JOIN volumes v ON v.id = c.volume_id
        WHERE c.id = ?
        """,
        (chapter_id,),
    ).fetchone()


def _workspace_segments(connection: sqlite3.Connection, chapter_id: str) -> list[WorkspaceSegment]:
    review_col = _review_status_column_sql(connection)
    rows = connection.execute(
        f"""
        SELECT s.id AS id,
               s.block_order AS block_order,
               s.kind AS kind,
               s.source_text AS source_text,
               s.status AS status,
               {review_col},
               (
                 SELECT t.text
                 FROM translations t
                 WHERE t.segment_id = s.id
                 ORDER BY t.attempt DESC
                 LIMIT 1
               ) AS translated_text
        FROM segments s
        WHERE s.chapter_id = ?
        ORDER BY s.block_order
        """,
        (chapter_id,),
    ).fetchall()
    return [
        WorkspaceSegment(
            id=str(row["id"]),
            block_order=int(row["block_order"]),
            kind=str(row["kind"]),
            source_text=str(row["source_text"]),
            status=str(row["status"]),
            translated_text=(
                None if row["translated_text"] is None else str(row["translated_text"])
            ),
            review_status=str(row["review_status"]),
        )
        for row in rows
    ]


def _review_status_column_sql(connection: sqlite3.Connection) -> str:
    columns = {
        str(row["name"]) for row in connection.execute("PRAGMA table_info(segments)").fetchall()
    }
    if "review_status" in columns:
        return "COALESCE(s.review_status, 'not_reviewed') AS review_status"
    return "'not_reviewed' AS review_status"
