"""Read-only per-chapter glossary term coverage diff."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from weaver.core.config import load_project_config
from weaver.errors import ConfigError
from weaver.storage.db import connect_readonly_database
from weaver.storage.glossary import list_glossary_terms
from weaver.storage.projects import get_project


@dataclass(frozen=True)
class GlossaryDiffResult:
    """Coverage diff of approved glossary terms between two chapters."""

    chapter_a: int
    chapter_b: int
    only_in_a: tuple[str, ...]
    only_in_b: tuple[str, ...]
    in_both: tuple[str, ...]


def glossary_diff(
    project_toml: Path,
    chapter_a: int,
    chapter_b: int,
    *,
    cwd: Path | None = None,
) -> GlossaryDiffResult:
    """Return approved glossary term coverage diff between two chapters.

    Args:
        project_toml: Path to a Weaver project.toml file.
        chapter_a: First chapter number (1-indexed).
        chapter_b: Second chapter number (1-indexed).
        cwd: Working directory used to resolve project paths.

    Returns:
        GlossaryDiffResult with sets of term sources partitioned by chapter coverage.

    Raises:
        ConfigError: When chapter index is out of range or project not initialised.
    """
    base_dir = cwd or Path.cwd()
    data = load_project_config(project_toml)
    project = data["project"]
    db_path = _resolve_path(str(project["database_path"]), base_dir, project_toml.parent)

    with closing(connect_readonly_database(db_path)) as connection:
        project_row = connection.execute("SELECT id FROM projects ORDER BY id LIMIT 1").fetchone()
        if project_row is None:
            raise ConfigError(
                "Project database is empty. "
                "Likely cause: database was not initialised by `weaver init`. "
                "Next command: run `weaver init <input.epub>`."
            )
        project_record = get_project(connection, int(project_row["id"]))

        terms = list_glossary_terms(connection, project_id=project_record.id)

        chapter_count = connection.execute(
            "SELECT COUNT(*) FROM chapters WHERE project_id = ?",
            (project_record.id,),
        ).fetchone()[0]

        for idx, _label in ((chapter_a, "chapter_a"), (chapter_b, "chapter_b")):
            if idx < 1 or idx > chapter_count:
                raise ConfigError(
                    f"Chapter {idx} is out of range. "
                    f"Likely cause: project has {chapter_count} chapter(s). "
                    "Next command: run `weaver inspect <project.toml>` to see chapter count."
                )

        text_a = _chapter_source_text(connection, project_record.id, chapter_a)
        text_b = _chapter_source_text(connection, project_record.id, chapter_b)

    in_a = frozenset(t.source for t in terms if t.source in text_a)
    in_b = frozenset(t.source for t in terms if t.source in text_b)

    return GlossaryDiffResult(
        chapter_a=chapter_a,
        chapter_b=chapter_b,
        only_in_a=tuple(sorted(in_a - in_b)),
        only_in_b=tuple(sorted(in_b - in_a)),
        in_both=tuple(sorted(in_a & in_b)),
    )


def _resolve_path(path_value: str, cwd: Path, project_toml_dir: Path) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    cwd_path = cwd / path
    if cwd_path.exists():
        return cwd_path
    return project_toml_dir / path


def _chapter_source_text(
    connection: sqlite3.Connection,
    project_id: int,
    chapter_index: int,
) -> str:
    rows = connection.execute(
        """
        SELECT s.source_text
        FROM segments s
        JOIN chapters c ON c.id = s.chapter_id
        WHERE c.project_id = ?
          AND c.spine_order = ?
        ORDER BY s.block_order
        """,
        (project_id, chapter_index - 1),
    ).fetchall()
    return " ".join(str(row["source_text"]) for row in rows)
