"""Markdown export service."""

from __future__ import annotations

import re
import sqlite3
import tomllib
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from weaver.core.ir import BlockIR, ChapterIR
from weaver.errors import ConfigError
from weaver.readers.epub import read_epub
from weaver.storage.db import connect_readonly_database


@dataclass(frozen=True)
class MarkdownExportResult:
    """Markdown export result."""

    output_dir: Path
    index_path: Path
    chapter_paths: tuple[Path, ...]


@dataclass(frozen=True)
class SegmentExportState:
    """Stored segment state needed by the Markdown renderer."""

    status: str
    translation: str | None


def export_markdown_project(
    project_toml: Path, *, cwd: Path | None = None, translation_only: bool = False
) -> MarkdownExportResult:
    """Export a Weaver project to per-chapter Markdown review files."""

    base_dir = cwd or Path.cwd()
    data = tomllib.loads(project_toml.read_text(encoding="utf-8"))
    project = data["project"]
    db_path = _resolve_path(str(project["database_path"]), base_dir, project_toml.parent)
    source_path = _resolve_path(str(project["source_file"]), base_dir, project_toml.parent)
    output_root = _resolve_path(str(project["output_dir"]), base_dir, project_toml.parent)
    output_dir = output_root / "markdown"

    document = read_epub(source_path)
    with closing(connect_readonly_database(db_path)) as connection:
        states = _load_segment_states(connection)

    output_dir.mkdir(parents=True, exist_ok=True)
    chapter_paths: list[Path] = []
    for index, chapter in enumerate(document.chapters, start=1):
        chapter_path = output_dir / f"chapter-{index:03d}.md"
        chapter_path.write_text(
            _render_chapter(chapter, states=states, translation_only=translation_only),
            encoding="utf-8",
        )
        chapter_paths.append(chapter_path)

    index_path = output_dir / "review.md"
    index_path.write_text(
        _render_index(project_name=str(project["name"]), chapter_paths=chapter_paths),
        encoding="utf-8",
    )
    return MarkdownExportResult(
        output_dir=output_dir,
        index_path=index_path,
        chapter_paths=tuple(chapter_paths),
    )


def _render_index(*, project_name: str, chapter_paths: list[Path]) -> str:
    lines = [f"# {project_name} Review", ""]
    for path in chapter_paths:
        title = path.stem.replace("-", " ").title()
        lines.append(f"- [{title}]({path.name})")
    lines.append("")
    return "\n".join(lines)


def _render_chapter(
    chapter: ChapterIR,
    *,
    states: dict[str, SegmentExportState],
    translation_only: bool,
) -> str:
    title = chapter.title or f"Chapter {chapter.order + 1}"
    lines = [f"# {_clean_heading(title)}", ""]
    for block in chapter.blocks:
        rendered = _render_block(
            block, state=states.get(block.id), translation_only=translation_only
        )
        lines.extend(rendered)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _render_block(
    block: BlockIR,
    *,
    state: SegmentExportState | None,
    translation_only: bool,
) -> list[str]:
    translation = _translation_or_marker(block, state)
    if block.kind == "heading":
        heading = translation if not translation.startswith("[") else block.source_text
        if translation_only:
            return [f"## {_clean_heading(heading)}"]
        return [
            f"## {_clean_heading(heading)}",
            "",
            "## Source",
            _blockquote(block.source_text),
            "",
            "## Translation",
            translation,
        ]

    if translation_only:
        return [translation]
    return [
        "## Source",
        _blockquote(block.source_text),
        "",
        "## Translation",
        translation,
    ]


def _translation_or_marker(block: BlockIR, state: SegmentExportState | None) -> str:
    if state is None:
        return f"[MISSING: {block.id}]"
    if state.status == "failed":
        return f"[FAILED: {block.id}]"
    if state.status == "stale":
        return f"[STALE: {block.id}]"
    if state.translation:
        return state.translation
    return f"[MISSING: {block.id}]"


def _blockquote(text: str) -> str:
    return "\n".join(f"> {line}" if line else ">" for line in text.splitlines())


def _clean_heading(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    return cleaned.replace("#", "").strip() or "Untitled"


def _load_segment_states(connection: sqlite3.Connection) -> dict[str, SegmentExportState]:
    rows = connection.execute(
        """
        WITH latest AS (
          SELECT segment_id, MAX(attempt) AS attempt
          FROM translations
          GROUP BY segment_id
        )
        SELECT s.id, s.status, t.text
        FROM segments s
        LEFT JOIN latest l ON l.segment_id = s.id
        LEFT JOIN translations t
          ON t.segment_id = l.segment_id
         AND t.attempt = l.attempt
         AND t.source_hash = s.source_hash
        """
    ).fetchall()
    return {
        str(row["id"]): SegmentExportState(
            status=str(row["status"]),
            translation=None if row["text"] is None else str(row["text"]),
        )
        for row in rows
    }


def _resolve_path(path_value: str, cwd: Path, project_toml_dir: Path) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    cwd_path = cwd / path
    if cwd_path.exists():
        return cwd_path
    project_relative = project_toml_dir / path
    if project_relative.exists():
        return project_relative
    if path_value.startswith(".weaver/") or path_value.startswith(".weaver\\"):
        return cwd_path
    if "database_path" in path_value:
        raise ConfigError(
            "Could not resolve project path. "
            "Likely cause: project.toml was moved without its .weaver directory. "
            "Next command: run `weaver inspect <project.toml>` from the project root."
        )
    return cwd_path
