"""Preview service for ``weaver preview``.

Read-only display of source + translation pairs inline, with optional
segment-level or chapter-level filtering.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from weaver.core.config import load_project_config
from weaver.errors import ConfigError, SegmentNotFoundError
from weaver.readers.epub import read_epub
from weaver.storage.db import connect_readonly_database


@dataclass(frozen=True)
class PreviewBlock:
    """One source + translation pair for display."""

    segment_id: str
    chapter_index: int
    chapter_title: str
    source_text: str
    translation: str | None
    status: str


def preview_project(
    project_toml: Path,
    *,
    cwd: Path | None = None,
    segment_id: str | None = None,
    chapter: int | None = None,
) -> list[PreviewBlock]:
    """Load segments for preview, optionally filtering by segment or chapter.

    Args:
        project_toml: Weaver project file.
        cwd: Working directory used to resolve relative project paths.
        segment_id: Show only this segment (exact match).
        chapter: Show only segments from this chapter (1-indexed).

    Returns:
        Ordered list of PreviewBlock instances.

    Raises:
        SegmentNotFoundError: When ``segment_id`` does not exist.
        ConfigError: When ``chapter`` is out of range.
    """

    base_dir = cwd or Path.cwd()
    data = load_project_config(project_toml)
    project_config = data["project"]
    db_path = _resolve_path(str(project_config["database_path"]), base_dir, project_toml.parent)
    source_path = _resolve_path(str(project_config["source_file"]), base_dir, project_toml.parent)

    document = read_epub(source_path)

    with closing(connect_readonly_database(db_path)) as connection:
        translations = _load_translations(connection)
        statuses = _load_statuses(connection)

    blocks: list[PreviewBlock] = []
    for ch_index, ch in enumerate(document.chapters, start=1):
        if chapter is not None and ch_index != chapter:
            continue
        ch_title = ch.title or f"Chapter {ch_index}"
        for block in ch.blocks:
            if segment_id is not None and block.id != segment_id:
                continue
            blocks.append(
                PreviewBlock(
                    segment_id=block.id,
                    chapter_index=ch_index,
                    chapter_title=ch_title,
                    source_text=block.source_text,
                    translation=translations.get(block.id),
                    status=statuses.get(block.id, "pending"),
                )
            )

    if segment_id is not None and not blocks:
        raise SegmentNotFoundError(
            f"Segment `{segment_id}` not found. "
            "Likely cause: segment id is incorrect or does not exist in this project. "
            "Next command: run `weaver inspect <project.toml>` for segment ids."
        )
    if chapter is not None and not blocks:
        raise ConfigError(
            f"Chapter {chapter} is out of range. "
            f"Likely cause: this project has {len(document.chapters)} chapters. "
            "Next command: run `weaver inspect <project.toml>` to see chapter count."
        )

    return blocks


def _load_translations(connection: sqlite3.Connection) -> dict[str, str]:
    rows = connection.execute(
        """
        WITH latest AS (
          SELECT segment_id, MAX(attempt) AS attempt
          FROM translations
          GROUP BY segment_id
        )
        SELECT s.id, t.text
        FROM segments s
        JOIN latest l ON l.segment_id = s.id
        JOIN translations t
          ON t.segment_id = l.segment_id
         AND t.attempt = l.attempt
         AND t.source_hash = s.source_hash
        WHERE s.status IN ('translated', 'manual')
        """
    ).fetchall()
    return {str(row["id"]): str(row["text"]) for row in rows}


def _load_statuses(connection: sqlite3.Connection) -> dict[str, str]:
    rows = connection.execute("SELECT id, status FROM segments").fetchall()
    return {str(row["id"]): str(row["status"]) for row in rows}


def _resolve_path(path_value: str, cwd: Path, project_toml_dir: Path) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    cwd_path = cwd / path
    if cwd_path.exists():
        return cwd_path
    return project_toml_dir / path
