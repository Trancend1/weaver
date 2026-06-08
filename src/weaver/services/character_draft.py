"""Character Page text draft service (Sprint L4).

Extracts text content from XHTML-based character pages in an EPUB and generates
draft text entries. **No OCR, no image processing** — only pages with actual
text content are processed. Drafts are stored as ``draft`` status in the
``character_page_drafts`` table and never auto-mutate the character DB.

Character pages are identified by the preservation snapshot's image role
classification (``character_page``) and the chapter's XHTML content.
"""

from __future__ import annotations

import json
import re
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from weaver.services.project_paths import resolve_database_path
from weaver.storage.character_drafts import (
    CharacterDraftRecord,
    insert_draft,
    update_draft_status,
)
from weaver.storage.db import connect_database, transaction
from weaver.storage.segments import SegmentRecord, list_chapter_segments

DRAFT_PROMPT_VERSION = "character-draft-1.0"

CHARACTER_PAGE_HEADING_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^(character|登場人物|主要登場人物|キャラクター)"),
    re.compile(r"(profile|人物紹介|プロフィール)"),
    re.compile(r"^(name|名前|氏名)"),
)


def generate_character_draft(
    project_toml: Path,
    chapter_id: str,
    *,
    cwd: Path | None = None,
) -> CharacterDraftRecord | None:
    """Generate a character page draft from a chapter's XHTML text content.

    Only processes chapters that contain character-related text content
    (detected via heading patterns and page context). No OCR, no images.

    Args:
        project_toml: Path to the project's ``project.toml``.
        chapter_id: Chapter id to analyze for character page content.
        cwd: Working directory for path resolution.

    Returns:
        A CharacterDraftRecord if the chapter has character page content,
        or ``None`` if no character content was detected.
    """

    db_path = resolve_database_path(project_toml, cwd=cwd)
    with closing(connect_database(db_path)) as connection:
        segments = list_chapter_segments(connection, chapter_id=chapter_id)

        page_text = _extract_page_text(connection, chapter_id, segments)
        if page_text is None:
            return None

        heading = _extract_heading(page_text)
        page_identifier = _page_identifier(chapter_id, heading)

        project = _load_project_id(connection)
        if project is None:
            return None  # pragma: no cover

        if not _is_character_page(page_text, heading):
            return None

        volume_id = _resolve_volume_id(connection, chapter_id=chapter_id)
        draft_text = _build_draft_text(page_text, heading)

        provenance = {
            "prompt_version": DRAFT_PROMPT_VERSION,
            "chapter_id": chapter_id,
            "source": "xhtml_text",
            "created_at": datetime.now(UTC).isoformat(),
            "method": "text_extraction",
            "no_ocr": True,
        }

        segment_id = _find_character_segment(segments)

        with transaction(connection):
            draft = insert_draft(
                connection,
                project_id=project,
                volume_id=volume_id,
                chapter_id=chapter_id,
                segment_id=segment_id,
                source_text=page_text,
                draft_text=draft_text,
                heading=heading,
                page_identifier=page_identifier,
                provenance_json=json.dumps(provenance, ensure_ascii=False),
            )

    return draft


def _extract_page_text(
    connection: sqlite3.Connection,
    chapter_id: str,
    segments: list[SegmentRecord],
) -> str | None:
    """Extract combined text content from a chapter's segments.

    Concatenates source text from all segments to form the page text.
    Returns None if the chapter has no segments.
    """

    if not segments:
        return None
    texts = [seg.source_text for seg in segments if seg.source_text.strip()]
    if not texts:
        return None
    return "\n".join(texts)


def _extract_heading(page_text: str) -> str | None:
    """Extract the first character-page-like heading from the text.

    Looks for lines that match known character page heading patterns
    (Japanese and English). Returns the matching line or None.
    """

    for line in page_text.splitlines():
        stripped = line.strip()
        for pattern in CHARACTER_PAGE_HEADING_PATTERNS:
            if pattern.search(stripped):
                return stripped[:200]
    return None


def _is_character_page(page_text: str, heading: str | None) -> bool:
    """Determine whether the text content represents a character page.

    Uses heading detection and content heuristics. No image/OCR checks.
    """

    if heading is not None:
        return True

    content_lower = page_text.lower()
    character_keywords = {
        "name",
        "age",
        "gender",
        "alias",
        "称号",
        "年齢",
        "性別",
        "身長",
        "height",
        "weight",
        "体重",
        "birthday",
        "誕生日",
    }
    found = sum(1 for kw in character_keywords if kw in content_lower)
    return found >= 2


def _build_draft_text(page_text: str, heading: str | None) -> str:
    """Build a structured draft text from the page text content.

    Extracts name, description, aliases, and notes from the raw text
    using structural patterns. Falls back to the raw text if parsing
    is not possible.
    """

    lines = page_text.splitlines()
    draft_parts: list[str] = []

    if heading:
        draft_parts.append(f"## {heading}")

    name = _extract_name(lines)
    if name:
        draft_parts.append(f"**Name:** {name}")

    aliases = _extract_aliases(lines)
    if aliases:
        draft_parts.append(f"**Aliases:** {', '.join(aliases)}")

    description = _extract_description(lines)
    if description:
        draft_parts.append(f"\n{description}")

    return "\n\n".join(draft_parts) if draft_parts else page_text


def _extract_name(lines: list[str]) -> str | None:
    """Extract the character name from text lines.

    Looks for patterns like ``名前: value`` or ``Name: value``.
    Returns the first match or None.
    """

    name_patterns = (
        re.compile(r"(?:名前|name|氏名)\s*[:：]\s*(.+)", re.IGNORECASE),
        re.compile(r"^(登場人物|character)\s*[:：]?\s*(.+)", re.IGNORECASE),
    )
    for pattern in name_patterns:
        for line in lines:
            match = pattern.search(line)
            if match:
                candidate = match.group(1).strip()
                if candidate and len(candidate) < 100:
                    return candidate
    return None


def _extract_aliases(lines: list[str]) -> list[str]:
    """Extract aliases/alternate names from text lines."""

    alias_patterns = (
        re.compile(r"(?:別名|alias|aka|通称|also known as)\s*[:：]?\s*(.+)", re.IGNORECASE),
    )
    aliases: list[str] = []
    for pattern in alias_patterns:
        for line in lines:
            match = pattern.search(line)
            if match:
                candidate = match.group(1).strip()
                if candidate and len(candidate) < 200:
                    aliases.append(candidate)
    return aliases


def _extract_description(lines: list[str]) -> str | None:
    """Extract description text (non-heading, non-name lines)."""

    excluded = {
        "name",
        "age",
        "gender",
        "alias",
        "note",
        "status",
        "role",
        "名前",
        "年齢",
        "性別",
        "別名",
        "称号",
        "身長",
        "体重",
    }
    desc_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        lower = stripped.lower()
        is_header = any(
            stripped.startswith(prefix) for prefix in ("#", "##", "■", "●", "・", "【", "《")
        )
        is_key_value = ":" in stripped or "：" in stripped
        is_excluded = any(excluded_word in lower for excluded_word in excluded)
        if not is_header and not (is_key_value and is_excluded):
            desc_lines.append(stripped)

    text = "\n".join(desc_lines).strip()
    return text if len(text) > 10 else None


def _page_identifier(chapter_id: str, heading: str | None) -> str | None:
    """Build a human-readable page identifier."""

    if heading:
        return f"{chapter_id}::{heading[:80]}"
    return chapter_id


def _load_project_id(connection: sqlite3.Connection) -> int | None:
    row = connection.execute("SELECT id FROM projects ORDER BY id LIMIT 1").fetchone()
    if row is None:
        return None
    return int(row["id"])


def _resolve_volume_id(connection: sqlite3.Connection, *, chapter_id: str) -> int | None:
    row = connection.execute(
        "SELECT volume_id FROM chapters WHERE id = ?",
        (chapter_id,),
    ).fetchone()
    if row is None or row["volume_id"] is None:
        return None
    return int(row["volume_id"])


def _find_character_segment(segments: list[SegmentRecord]) -> str | None:
    """Find the first segment that looks like a character name or heading."""
    name_pattern = re.compile(r"(?:名前|name)\s*[:：]", re.IGNORECASE)
    for seg in segments:
        if name_pattern.search(seg.source_text):
            return seg.id
    return segments[0].id if segments else None


def approve_draft(
    project_toml: Path,
    draft_id: str,
    *,
    cwd: Path | None = None,
) -> CharacterDraftRecord:
    """Approve a character page draft.

    The draft status becomes ``approved``. No automatic mutation of the
    character DB — the user must explicitly sync character data.

    Args:
        project_toml: Path to the project's ``project.toml``.
        draft_id: Draft id to approve.
        cwd: Working directory for path resolution.

    Returns:
        The updated CharacterDraftRecord.
    """

    return _transition_draft(project_toml, draft_id, "approved", cwd=cwd)


def reject_draft(
    project_toml: Path,
    draft_id: str,
    *,
    cwd: Path | None = None,
) -> CharacterDraftRecord:
    """Reject a character page draft.

    The draft status becomes ``rejected``. The record is retained for audit.

    Args:
        project_toml: Path to the project's ``project.toml``.
        draft_id: Draft id to reject.
        cwd: Working directory for path resolution.

    Returns:
        The updated CharacterDraftRecord.
    """

    return _transition_draft(project_toml, draft_id, "rejected", cwd=cwd)


def _transition_draft(
    project_toml: Path,
    draft_id: str,
    new_status: str,
    *,
    cwd: Path | None = None,
) -> CharacterDraftRecord:
    from weaver.errors import CharacterDraftNotFoundError
    from weaver.storage.character_drafts import get_draft

    db_path = resolve_database_path(project_toml, cwd=cwd)
    with closing(connect_database(db_path)) as connection:
        try:
            get_draft(connection, draft_id=draft_id)
        except LookupError as exc:
            raise CharacterDraftNotFoundError(
                f"Character page draft '{draft_id}' was not found. "
                "Likely cause: the draft id is wrong or was deleted."
            ) from exc
        with transaction(connection):
            updated = update_draft_status(
                connection,
                draft_id=draft_id,
                status=new_status,
            )
    return updated
