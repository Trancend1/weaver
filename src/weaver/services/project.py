"""Project initialization and inspection services."""

from __future__ import annotations

import os
import sqlite3
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path

from weaver.readers.epub import read_epub
from weaver.storage.db import (
    SCHEMA_VERSION,
    connect_readonly_database,
    initialize_database,
    transaction,
)
from weaver.storage.projects import create_project
from weaver.storage.segments import sync_document_segments


@dataclass(frozen=True)
class InitResult:
    """Result returned after creating a Weaver project."""

    project_name: str
    project_toml: Path
    database_path: Path
    chapter_count: int
    segment_count: int


@dataclass(frozen=True)
class InspectSummary:
    """Read-only project status summary."""

    project_name: str
    source_file: str
    provider: str
    model: str
    chapter_count: int
    segment_count: int
    pending_count: int
    translated_count: int
    failed_count: int
    stale_count: int
    glossary_candidate_count: int
    glossary_term_count: int
    output_dir: str


def initialize_project(source_epub: Path, *, cwd: Path | None = None) -> InitResult:
    """Create project state for a source EPUB.

    Args:
        source_epub: Input EPUB path.
        cwd: Working directory used for generated project paths.

    Returns:
        InitResult with created project locations and counts.
    """

    base_dir = cwd or Path.cwd()
    source_epub = source_epub.resolve()
    project_name = source_epub.stem
    project_dir = base_dir / ".weaver" / project_name
    output_dir = project_dir / "output"
    db_path = project_dir / "weaver.db"
    project_toml = project_dir / "project.toml"

    document = read_epub(source_epub)
    project_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    chapter_count = len(document.chapters)
    segment_count = sum(len(chapter.blocks) for chapter in document.chapters)

    with initialize_database(db_path) as connection, transaction(connection):
        project_id = create_project(
            connection,
            name=project_name,
            source_path=str(source_epub),
            source_lang=document.metadata.language,
            target_lang="en",
        )
        sync_document_segments(connection, project_id=project_id, document=document)

    _write_project_toml(
        project_toml,
        project_name=project_name,
        source_file=str(source_epub),
        project_dir=_posix_relative(project_dir, base_dir),
        database_path=_posix_relative(db_path, base_dir),
        output_dir=_posix_relative(output_dir, base_dir),
    )
    return InitResult(
        project_name=project_name,
        project_toml=project_toml,
        database_path=db_path,
        chapter_count=chapter_count,
        segment_count=segment_count,
    )


def inspect_project(project_toml: Path, *, cwd: Path | None = None) -> InspectSummary:
    """Read project status without mutating the database.

    Args:
        project_toml: Path to a Weaver project.toml file.
        cwd: Working directory used to resolve generated project paths.

    Returns:
        InspectSummary with project counts.
    """

    base_dir = cwd or Path.cwd()
    data = tomllib.loads(project_toml.read_text(encoding="utf-8"))
    project = data["project"]
    provider = data["provider"]
    db_path = _resolve_path(str(project["database_path"]), base_dir, project_toml.parent)

    with connect_readonly_database(db_path) as connection:
        counts = _read_counts(connection)

    return InspectSummary(
        project_name=str(project["name"]),
        source_file=str(project["source_file"]),
        provider=str(provider["type"]),
        model=str(provider["model"]),
        chapter_count=counts["chapters"],
        segment_count=counts["segments"],
        pending_count=counts["pending"],
        translated_count=counts["translated"],
        failed_count=counts["failed"],
        stale_count=counts["stale"],
        glossary_candidate_count=counts["glossary_candidates"],
        glossary_term_count=counts["glossary_terms"],
        output_dir=str(project["output_dir"]),
    )


def _write_project_toml(
    path: Path,
    *,
    project_name: str,
    source_file: str,
    project_dir: str,
    database_path: str,
    output_dir: str,
) -> None:
    content = f"""[project]
name = "{project_name}"
source_file = "{_escape_toml(source_file)}"
project_dir = "{project_dir}"
database_path = "{database_path}"
output_dir = "{output_dir}"
schema_version = {SCHEMA_VERSION}

[languages]
source = "ja"
target = "en"

[provider]
type = "deepseek"
model = "deepseek-chat"
base_url = "http://localhost:11434"

[translation]
quality = "balanced"
honorifics = "preserve"
context_window_segments = 5
timeout_seconds = 180
max_retries = 2

[glossary]
candidate_path = "{project_dir}/glossary_candidates.tsv"
approved_path = "{project_dir}/glossary.tsv"
require_review = true
max_terms_per_segment = 20

[output]
default_mode = "markdown"
epub_enabled = true

[qa]
detect_untranslated_japanese = true
detect_empty_output = true
detect_glossary_mismatch = true
minimum_length_ratio = 0.3

[logging]
level = "info"
raw_response_logging = false
"""
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        delete=False,
    ) as file:
        temp_path = Path(file.name)
        file.write(content)
    temp_path.replace(path)


def _read_counts(connection: sqlite3.Connection) -> dict[str, int]:
    status_counts = {
        str(row["status"]): int(row["count"])
        for row in connection.execute(
            "SELECT status, COUNT(*) AS count FROM segments GROUP BY status"
        ).fetchall()
    }
    return {
        "chapters": _count(connection, "chapters"),
        "segments": _count(connection, "segments"),
        "pending": status_counts.get("pending", 0),
        "translated": status_counts.get("translated", 0),
        "failed": status_counts.get("failed", 0),
        "stale": status_counts.get("stale", 0),
        "glossary_candidates": _count(connection, "glossary_candidates"),
        "glossary_terms": _count(connection, "glossary_terms"),
    }


def _count(connection: sqlite3.Connection, table_name: str) -> int:
    row = connection.execute(f"SELECT COUNT(*) AS count FROM {table_name}").fetchone()
    return int(row["count"])


def _resolve_path(path_value: str, cwd: Path, project_toml_dir: Path) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    cwd_path = cwd / path
    if cwd_path.exists():
        return cwd_path
    return project_toml_dir / path


def _posix_relative(path: Path, start: Path) -> str:
    return Path(os.path.relpath(path, start)).as_posix()


def _escape_toml(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
