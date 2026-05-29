"""Read-only Novel -> Volume -> Chapter tree for the cockpit project page.

Builds a display model from the project database: each volume with its chapters
and per-chapter segment/translation counts. Read-only; never mutates state.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from weaver.core.config import load_project_config
from weaver.storage.db import connect_readonly_database
from weaver.storage.volumes import VolumeRecord, list_volumes


@dataclass(frozen=True)
class ChapterView:
    """One chapter row with counts for the tree."""

    id: str
    title: str | None
    segment_count: int
    translated_count: int


@dataclass(frozen=True)
class VolumeView:
    """One volume with its chapters."""

    id: int
    title: str
    source_format: str
    volume_order: int
    chapter_count: int
    segment_count: int
    chapters: list[ChapterView]


@dataclass(frozen=True)
class NovelTree:
    """A novel's volumes in reading order."""

    project_name: str
    volumes: list[VolumeView]


def project_tree(project_toml: Path, *, cwd: Path | None = None) -> NovelTree:
    """Build the Novel -> Volume -> Chapter tree for one project.

    Args:
        project_toml: Path to the project's ``project.toml``.
        cwd: Working directory used to resolve project-relative paths.

    Returns:
        A NovelTree with each volume's chapters and counts.
    """

    base_dir = cwd or Path.cwd()
    data = load_project_config(project_toml)
    project_name = str(data["project"]["name"])
    db_path = _resolve_path(str(data["project"]["database_path"]), base_dir, project_toml.parent)

    with closing(connect_readonly_database(db_path)) as connection:
        project_id = _single_project_id(connection)
        volumes = [
            _volume_view(connection, volume) for volume in list_volumes(connection, project_id)
        ]
    return NovelTree(project_name=project_name, volumes=volumes)


def _volume_view(connection: sqlite3.Connection, volume: VolumeRecord) -> VolumeView:
    rows = connection.execute(
        """
        SELECT c.id AS id,
               c.title AS title,
               COUNT(s.id) AS segment_count,
               SUM(CASE WHEN s.status = 'translated' THEN 1 ELSE 0 END) AS translated_count
        FROM chapters c
        LEFT JOIN segments s ON s.chapter_id = c.id
        WHERE c.volume_id = ?
        GROUP BY c.id
        ORDER BY c.spine_order
        """,
        (volume.id,),
    ).fetchall()
    chapters = [
        ChapterView(
            id=str(row["id"]),
            title=row["title"],
            segment_count=int(row["segment_count"]),
            translated_count=int(row["translated_count"] or 0),
        )
        for row in rows
    ]
    return VolumeView(
        id=volume.id,
        title=volume.title,
        source_format=volume.source_format,
        volume_order=volume.volume_order,
        chapter_count=len(chapters),
        segment_count=sum(chapter.segment_count for chapter in chapters),
        chapters=chapters,
    )


def _single_project_id(connection: sqlite3.Connection) -> int:
    row = connection.execute("SELECT id FROM projects ORDER BY id LIMIT 1").fetchone()
    return int(row["id"]) if row is not None else 0


def _resolve_path(path_value: str, cwd: Path, project_toml_dir: Path) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    cwd_path = cwd / path
    if cwd_path.exists():
        return cwd_path
    return project_toml_dir / path
