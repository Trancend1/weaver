"""Import an additional source file as a Volume in an existing novel.

A novel (project) can hold several volumes. This service adds one volume from a
source file to a project that already exists on disk, reusing the same reader,
segment-sync, and glossary-extraction pipeline as ``initialize_project``.

Stage 1a wires the EPUB reader only; TXT/HTML land in a later stage.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from weaver.core.config import load_project_config
from weaver.errors import WeaverError
from weaver.readers.epub import read_epub
from weaver.services.glossary import extract_and_store_project_glossary
from weaver.storage.db import connect_database, transaction
from weaver.storage.segments import sync_document_segments
from weaver.storage.volumes import create_volume

_EPUB_SUFFIX = ".epub"
_PENDING_FORMATS = {".txt", ".html", ".htm"}


@dataclass(frozen=True)
class VolumeResult:
    """Result returned after importing a volume into a novel."""

    volume_id: int
    volume_title: str
    chapter_count: int
    segment_count: int
    glossary_candidate_count: int


def import_volume(
    project_toml: Path,
    source_path: Path,
    *,
    cwd: Path | None = None,
) -> VolumeResult:
    """Import a source file as a new volume in an existing novel.

    Args:
        project_toml: Path to the target project's ``project.toml``.
        source_path: Path to the source file to import (EPUB in stage 1a).
        cwd: Working directory used to resolve project-relative paths.

    Returns:
        VolumeResult with the new volume's id, title, and counts.

    Raises:
        WeaverError: If the source format is unsupported or the project cannot
            be opened.
    """

    base_dir = cwd or Path.cwd()
    source_path = source_path.resolve()
    _reject_unsupported_format(source_path)

    data = load_project_config(project_toml)
    db_path = _resolve_path(str(data["project"]["database_path"]), base_dir, project_toml.parent)
    candidate_path = _resolve_path(
        str(data["glossary"]["candidate_path"]), base_dir, project_toml.parent
    )

    document = read_epub(source_path)
    chapter_count = len(document.chapters)
    segment_count = sum(len(chapter.blocks) for chapter in document.chapters)
    volume_title = document.metadata.title or source_path.stem

    with closing(connect_database(db_path)) as connection:
        with transaction(connection):
            project_id = _single_project_id(connection, project_toml)
            volume_id = create_volume(
                connection,
                project_id=project_id,
                title=volume_title,
                source_path=str(source_path),
                source_format="epub",
            )
            sync_document_segments(
                connection,
                project_id=project_id,
                volume_id=volume_id,
                document=document,
            )
            glossary_result = extract_and_store_project_glossary(
                connection=connection,
                project_id=project_id,
                document=document,
                candidate_path=candidate_path,
            )
            _set_source_path_if_empty(
                connection, project_id=project_id, source_path=str(source_path)
            )
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    return VolumeResult(
        volume_id=volume_id,
        volume_title=volume_title,
        chapter_count=chapter_count,
        segment_count=segment_count,
        glossary_candidate_count=glossary_result.candidate_count,
    )


def _reject_unsupported_format(source_path: Path) -> None:
    suffix = source_path.suffix.lower()
    if suffix == _EPUB_SUFFIX:
        return
    if suffix in _PENDING_FORMATS:
        raise WeaverError(
            f"Importing `{suffix}` sources is not available yet: {source_path.name}. "
            "Likely cause: TXT/HTML readers land in a later Sprint 1 stage. "
            "Next command: import an .epub volume for now."
        )
    raise WeaverError(
        f"Unsupported source format `{suffix}`: {source_path.name}. "
        "Likely cause: only .epub is supported in this build. "
        "Next command: import an .epub file."
    )


def _single_project_id(connection: sqlite3.Connection, project_toml: Path) -> int:
    row = connection.execute("SELECT id FROM projects ORDER BY id LIMIT 1").fetchone()
    if row is None:
        raise WeaverError(
            f"No novel found in {project_toml}. "
            "Likely cause: the project database has no project row. "
            "Next command: recreate the project with `weaver init <input.epub>`."
        )
    return int(row["id"])


def _set_source_path_if_empty(
    connection: sqlite3.Connection, *, project_id: int, source_path: str
) -> None:
    connection.execute(
        "UPDATE projects SET source_path = ? WHERE id = ? AND source_path = ''",
        (source_path, project_id),
    )


def _resolve_path(path_value: str, cwd: Path, project_toml_dir: Path) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    cwd_path = cwd / path
    if cwd_path.exists():
        return cwd_path
    return project_toml_dir / path
