"""Read-only reading preview for translated content.

Builds a rendered view of a volume or chapter using the same publishable rule as
export so *preview == export*. Produces ordered blocks with resolved text,
source fallback, and status — all in memory, no disk writes.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from weaver.errors import ChapterNotFoundError, VolumeNotFoundError
from weaver.renderers.rendered_document import block_to_html
from weaver.services.project_paths import resolve_database_path
from weaver.storage.db import connect_readonly_database
from weaver.storage.segments import get_chapter, list_chapter_ids_for_volume, list_chapter_segments
from weaver.storage.translations import ExportSegmentState, list_export_segment_states
from weaver.storage.volumes import get_volume


@dataclass(frozen=True)
class ReadingBlock:
    """One display block with its resolution status."""

    segment_id: str
    kind: str
    resolved_text: str
    source_text: str
    status: str
    is_fallback: bool

    @property
    def html(self) -> str:
        return block_to_html(self.kind, self.resolved_text)


@dataclass(frozen=True)
class ReadingChapter:
    """One chapter's resolved blocks in reading order."""

    chapter_id: str
    title: str | None
    blocks: list[ReadingBlock]


def _chapter_blocks(
    connection: sqlite3.Connection,
    chapter_id: str,
    state_map: dict[str, ExportSegmentState] | None = None,
) -> list[ReadingBlock]:
    segments = list_chapter_segments(connection, chapter_id=chapter_id)
    if not segments:
        if get_chapter(connection, chapter_id) is None:
            raise ChapterNotFoundError(
                f"Chapter '{chapter_id}' not found. "
                "Likely cause: the chapter id is wrong or its volume was removed."
            )
        return []

    if state_map is None:
        states = list_export_segment_states(connection, chapter_ids=[chapter_id])
        state_map = {s.id: s for s in states}

    blocks: list[ReadingBlock] = []
    for seg in segments:
        state = state_map.get(seg.id)
        publishable = state.publishable_text if state else None
        is_fallback = publishable is None
        blocks.append(
            ReadingBlock(
                segment_id=seg.id,
                kind=seg.kind,
                resolved_text=publishable if publishable is not None else seg.source_text,
                source_text=seg.source_text,
                status=seg.status,
                is_fallback=is_fallback,
            )
        )
    return blocks


def reading_preview_for_chapter(
    project_toml: Path,
    chapter_id: str,
    *,
    cwd: Path | None = None,
) -> ReadingChapter:
    """Return a read-only reading preview for one chapter.

    Args:
        project_toml: Path to the project's ``project.toml``.
        chapter_id: Chapter id to preview.
        cwd: Working directory used to resolve project-relative paths.

    Returns:
        A ReadingChapter with blocks ordered by block_order.

    Raises:
        ChapterNotFoundError: If the chapter does not exist.
    """

    db_path = resolve_database_path(project_toml, cwd=cwd)
    with closing(connect_readonly_database(db_path)) as connection:
        chapter = get_chapter(connection, chapter_id)
        if chapter is None:
            raise ChapterNotFoundError(
                f"Chapter '{chapter_id}' not found. "
                "Likely cause: the chapter id is wrong or its volume was removed."
            )
        blocks = _chapter_blocks(connection, chapter_id)

    return ReadingChapter(chapter_id=chapter_id, title=chapter.title, blocks=blocks)


def reading_preview_for_volume(
    project_toml: Path,
    volume_id: int,
    *,
    cwd: Path | None = None,
) -> list[ReadingChapter]:
    """Return a read-only reading preview for every chapter in a volume.

    Chapters are ordered by spine_order. Each block uses the export publishable
    rule (``translated`` / ``manual`` + hash match → translation, else source
    fallback).

    Args:
        project_toml: Path to the project's ``project.toml``.
        volume_id: Volume id to preview.
        cwd: Working directory used to resolve project-relative paths.

    Returns:
        List of ReadingChapter instances in reading order.

    Raises:
        VolumeNotFoundError: If the volume does not exist.
    """

    db_path = resolve_database_path(project_toml, cwd=cwd)
    with closing(connect_readonly_database(db_path)) as connection:
        try:
            get_volume(connection, volume_id)
        except LookupError as exc:
            raise VolumeNotFoundError(
                f"Volume {volume_id} not found. "
                "Likely cause: the volume was deleted or the id is incorrect."
            ) from exc

        chapter_ids = list_chapter_ids_for_volume(connection, volume_id)
        if not chapter_ids:
            return []

        states = list_export_segment_states(connection, chapter_ids=chapter_ids)
        state_map = {s.id: s for s in states}

        chapters: list[ReadingChapter] = []
        for ch_id in chapter_ids:
            chapter = get_chapter(connection, ch_id)
            blocks = _chapter_blocks(connection, ch_id, state_map=state_map)
            chapters.append(
                ReadingChapter(
                    chapter_id=ch_id,
                    title=chapter.title if chapter else None,
                    blocks=blocks,
                )
            )

    return chapters
