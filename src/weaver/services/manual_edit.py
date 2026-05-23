"""Phase 7 manual segment override service."""

from __future__ import annotations

import subprocess
import tempfile
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from weaver.core.config import load_project_config
from weaver.errors import ConfigError, SegmentNotFoundError
from weaver.storage.db import connect_database, connect_readonly_database, transaction
from weaver.storage.projects import get_project
from weaver.storage.segments import get_segment, update_segment_status
from weaver.storage.translations import get_latest_translation_text, record_translation

MANUAL_PROVIDER_NAME = "manual"
MANUAL_PROVIDER_MODEL = "manual"

SegmentSelector = Literal["first-failed", "next-stale", "recent"]


@dataclass(frozen=True)
class ManualEditResult:
    """Outcome of a manual segment override."""

    segment_id: str
    attempt: int
    translation: str


def apply_manual_translation(
    project_toml: Path,
    segment_id: str,
    translated_text: str,
    *,
    cwd: Path | None = None,
) -> ManualEditResult:
    """Persist a manual translation for one segment and mark it `manual`.

    Args:
        project_toml: Weaver project file.
        segment_id: Target segment id.
        translated_text: User-edited translation text.
        cwd: Working directory used to resolve relative project paths.

    Returns:
        ManualEditResult with the stored translation and attempt number.

    Raises:
        ConfigError: When project paths cannot be resolved or the project row is missing.
        SegmentNotFoundError: When `segment_id` does not exist in the project database.
        ValueError: When `translated_text` is empty after stripping whitespace.
    """

    cleaned = translated_text.strip()
    if not cleaned:
        raise ValueError(
            "Manual translation cannot be empty. "
            "Likely cause: editor was saved without any translation text. "
            "Next command: rerun `weaver edit <project.toml> <segment-id>` "
            "and enter the translation."
        )

    db_path = _resolve_database_path(project_toml, cwd or Path.cwd())
    with closing(connect_database(db_path)) as connection:
        project_row = connection.execute("SELECT id FROM projects ORDER BY id LIMIT 1").fetchone()
        if project_row is None:
            raise ConfigError(
                "Project database has no project row. "
                "Likely cause: database was not initialized by `weaver init`. "
                "Next command: run `weaver init <input.epub>`."
            )
        get_project(connection, int(project_row["id"]))

        segment = get_segment(connection, segment_id)
        if segment is None:
            raise SegmentNotFoundError(
                f"Segment `{segment_id}` was not found in the project database. "
                "Likely cause: the segment id is wrong or the source EPUB has been re-segmented. "
                "Next command: run `weaver inspect <project.toml>` to list segments."
            )

        with transaction(connection):
            attempt = record_translation(
                connection,
                segment_id=segment.id,
                text=cleaned,
                source_hash=segment.source_hash,
                provider=MANUAL_PROVIDER_NAME,
                model=MANUAL_PROVIDER_MODEL,
                raw_response=None,
                input_tokens=None,
                output_tokens=None,
            )
            update_segment_status(connection, segment_id=segment.id, status="manual")

    return ManualEditResult(segment_id=segment.id, attempt=attempt, translation=cleaned)


def edit_segment(
    project_toml: Path,
    segment_id: str,
    *,
    editor: str | None,
    cwd: Path | None = None,
) -> ManualEditResult:
    """Open one segment's translation in `$EDITOR` and persist the user's edit.

    Args:
        project_toml: Weaver project file.
        segment_id: Target segment id.
        editor: Editor command resolved from `$EDITOR`.
        cwd: Working directory used to resolve relative project paths.

    Returns:
        ManualEditResult with the stored translation.

    Raises:
        ConfigError: When the editor is not configured or project paths cannot be resolved.
        SegmentNotFoundError: When `segment_id` does not exist.
        ValueError: When the saved text is empty.
    """

    if not editor:
        raise ConfigError(
            "Cannot open editor because EDITOR is not set. "
            "Likely cause: no editor command is configured in this shell. "
            "Next command: set EDITOR, for example `set EDITOR=notepad` on Windows."
        )

    db_path = _resolve_database_path(project_toml, cwd or Path.cwd())
    with closing(connect_database(db_path)) as connection:
        segment = get_segment(connection, segment_id)
        if segment is None:
            raise SegmentNotFoundError(
                f"Segment `{segment_id}` was not found in the project database. "
                "Likely cause: the segment id is wrong or the source EPUB has been re-segmented. "
                "Next command: run `weaver inspect <project.toml>` to list segments."
            )
        existing = get_latest_translation_text(connection, segment_id=segment.id)
        starting_text = existing if existing is not None else segment.source_text

    edited = _open_editor_with_text(editor, starting_text)
    return apply_manual_translation(project_toml, segment.id, edited, cwd=cwd)


def resolve_segment_id(
    project_toml: Path,
    *,
    selector: SegmentSelector,
    cwd: Path | None = None,
) -> str:
    """Resolve a segment id from a shortcut predicate.

    Args:
        project_toml: Weaver project file.
        selector: Which segment to surface. `first-failed` and `next-stale`
            return the earliest segment in EPUB order (chapter spine, then block
            order) matching the corresponding status. `recent` returns the
            segment whose most recent translation row has the latest
            `created_at` timestamp.
        cwd: Working directory used to resolve relative project paths.

    Returns:
        Segment id string.

    Raises:
        SegmentNotFoundError: When no segment matches the predicate.
    """

    db_path = _resolve_database_path(project_toml, cwd or Path.cwd())
    with closing(connect_readonly_database(db_path)) as connection:
        if selector in ("first-failed", "next-stale"):
            status = "failed" if selector == "first-failed" else "stale"
            row = connection.execute(
                """
                SELECT s.id
                FROM segments s
                JOIN chapters c ON c.id = s.chapter_id
                WHERE s.status = ?
                ORDER BY c.spine_order, s.block_order
                LIMIT 1
                """,
                (status,),
            ).fetchone()
        else:
            row = connection.execute(
                """
                SELECT segment_id AS id
                FROM translations
                ORDER BY created_at DESC, attempt DESC
                LIMIT 1
                """
            ).fetchone()

    if row is None:
        raise SegmentNotFoundError(
            f"No segment matches `{selector}`. "
            "Likely cause: no segment has the requested status yet "
            "(or no translation has been recorded for `--recent`). "
            "Next command: run `weaver inspect <project.toml>` to see segment counts."
        )
    return str(row["id"])


def _open_editor_with_text(editor: str, initial_text: str) -> str:
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", suffix=".txt", delete=False
    ) as handle:
        handle.write(initial_text)
        temp_path = Path(handle.name)
    try:
        subprocess.run([editor, str(temp_path)], check=True)
        return temp_path.read_text(encoding="utf-8-sig")
    finally:
        temp_path.unlink(missing_ok=True)


def _resolve_database_path(project_toml: Path, cwd: Path) -> Path:
    data = load_project_config(project_toml)
    project_config = data["project"]
    raw_path = str(project_config["database_path"])
    path = Path(raw_path)
    if path.is_absolute():
        return path
    cwd_path = cwd / path
    if cwd_path.exists():
        return cwd_path
    return project_toml.parent / path
