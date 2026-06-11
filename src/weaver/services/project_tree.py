"""Read-only Project -> Volume -> Chapter tree for the cockpit project page.

Builds a display model from the project database: each volume with its chapters
and per-chapter segment/translation counts. Read-only; never mutates state.
Volume lifecycle status is derived live (Sprint H2) — see
``services/volume_lifecycle.py``.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from weaver.api.jobs import JobRegistry
from weaver.core.config import load_project_config
from weaver.services.project_paths import resolve_database_path
from weaver.services.volume_lifecycle import VolumeStatus, derive_volume_status
from weaver.storage.db import connect_readonly_database
from weaver.storage.projects import get_first_project_id
from weaver.storage.volumes import VolumeRecord, list_volumes


@dataclass(frozen=True)
class ChapterView:
    """One chapter row with counts for the tree.

    ``translated_count`` counts only auto-``translated`` segments (kept for the
    JSON API). ``done_count`` also counts ``manual`` edits, so the tree can show
    an honest "finished" progress that doesn't drop when a segment is hand-edited.
    """

    id: str
    title: str | None
    segment_count: int
    translated_count: int
    done_count: int


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
    status: VolumeStatus
    status_label: str


@dataclass(frozen=True)
class NovelTree:
    """A project's volumes in reading order."""

    project_name: str
    volumes: list[VolumeView]


def project_tree(
    project_toml: Path,
    *,
    cwd: Path | None = None,
    jobs: JobRegistry | None = None,
) -> NovelTree:
    """Build the Project -> Volume -> Chapter tree for one project.

    Args:
        project_toml: Path to the project's ``project.toml``.
        cwd: Working directory used to resolve project-relative paths.
        jobs: Optional in-memory JobRegistry. When provided, volumes whose
            chapters have a running translate job are reported with the
            ``translating`` status overlay (Sprint H2).

    Returns:
        A NovelTree with each volume's chapters and counts.
    """

    data = load_project_config(project_toml)
    project_name = str(data["project"]["name"])
    db_path = resolve_database_path(project_toml, cwd=cwd)

    with closing(connect_readonly_database(db_path)) as connection:
        project_id = _single_project_id(connection)
        volumes = [
            _volume_view(connection, volume, project_name=project_name, jobs=jobs)
            for volume in list_volumes(connection, project_id)
        ]
    return NovelTree(project_name=project_name, volumes=volumes)


def _volume_view(
    connection: sqlite3.Connection,
    volume: VolumeRecord,
    *,
    project_name: str,
    jobs: JobRegistry | None,
) -> VolumeView:
    rows = connection.execute(
        """
        SELECT c.id AS id,
               c.title AS title,
               COUNT(s.id) AS segment_count,
               SUM(CASE WHEN s.status = 'translated' THEN 1 ELSE 0 END) AS translated_count,
               SUM(CASE WHEN s.status IN ('translated', 'manual') THEN 1 ELSE 0 END) AS done_count
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
            done_count=int(row["done_count"] or 0),
        )
        for row in rows
    ]
    segment_count = sum(chapter.segment_count for chapter in chapters)
    done_count = sum(chapter.done_count for chapter in chapters)
    status_view = derive_volume_status(
        segment_count=segment_count,
        done_count=done_count,
        chapter_ids=[chapter.id for chapter in chapters],
        project_name=project_name,
        jobs=jobs,
    )
    return VolumeView(
        id=volume.id,
        title=volume.title,
        source_format=volume.source_format,
        volume_order=volume.volume_order,
        chapter_count=len(chapters),
        segment_count=segment_count,
        chapters=chapters,
        status=status_view.status,
        status_label=status_view.label,
    )


def _single_project_id(connection: sqlite3.Connection) -> int:
    return get_first_project_id(connection) or 0
