"""Per-segment editor context panel data (Sprint Q10).

Read-only service that assembles all translator-relevant context for one
segment: glossary term hits, character mentions, existing candidates,
history summary, and lightweight deterministic consistency warnings.

Rules:
- Zero provider calls.
- Zero QA scan / no hashing on render.
- Uses existing storage only; one readonly db open per call.
"""

from __future__ import annotations

import sqlite3
import unicodedata
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from weaver.core.segment import normalize_japanese_text
from weaver.errors import ChapterNotFoundError, SegmentNotFoundError
from weaver.services.project_paths import resolve_database_path
from weaver.storage.candidates import list_candidates_for_segment
from weaver.storage.characters import list_characters
from weaver.storage.db import connect_readonly_database
from weaver.storage.glossary import list_glossary_terms
from weaver.storage.projects import get_project
from weaver.storage.translations import list_translation_attempts


@dataclass(frozen=True)
class GlossaryMatch:
    """One glossary term that occurs in the source segment."""

    source: str
    target: str
    category: str | None


@dataclass(frozen=True)
class CharacterMention:
    """One character whose name occurs in the source segment."""

    jp_name: str
    en_name: str
    role: str | None


@dataclass(frozen=True)
class CandidateSummary:
    """Lightweight view of an existing candidate for the segment."""

    id: str
    candidate_text: str
    status: str
    provider: str
    model: str


@dataclass(frozen=True)
class HistorySummary:
    """Translation history summary for the segment."""

    attempts_count: int
    last_attempt_text: str | None
    last_attempt_at: str | None


@dataclass(frozen=True)
class SegmentContext:
    """Complete context payload for the editor panel."""

    segment_id: str
    source_text: str
    translated_text: str | None
    status: str
    review_status: str
    glossary_matches: list[GlossaryMatch]
    character_mentions: list[CharacterMention]
    candidates: list[CandidateSummary]
    history: HistorySummary
    warnings: list[str]


def build_segment_context(
    project_toml: Path,
    chapter_id: str,
    segment_id: str,
    *,
    cwd: Path | None = None,
) -> SegmentContext:
    """Assemble read-only context for one segment.

    Args:
        project_toml: Path to the project's ``project.toml``.
        chapter_id: Chapter the segment belongs to.
        segment_id: Target segment id.
        cwd: Working directory used to resolve project-relative paths.

    Returns:
        :class:`SegmentContext` with glossary hits, characters, candidates,
        history summary, and deterministic warnings.

    Raises:
        ChapterNotFoundError: If the chapter doesn't exist.
        SegmentNotFoundError: If the segment doesn't exist or is in another chapter.
    """

    db_path = resolve_database_path(project_toml, cwd=cwd)

    with closing(connect_readonly_database(db_path)) as conn:
        if not _chapter_exists(conn, chapter_id):
            raise ChapterNotFoundError(
                f"Chapter '{chapter_id}' was not found in this project. "
                "Likely cause: the chapter id is wrong or its volume was removed."
            )

        project = _load_single_project(conn)
        seg = _segment_row(conn, segment_id, chapter_id)
        if seg is None:
            raise SegmentNotFoundError(
                f"Segment '{segment_id}' was not found in chapter '{chapter_id}'. "
                "Likely cause: the segment id is wrong or belongs to another chapter."
            )

        glossary_matches = _find_glossary_matches(conn, project.id, seg["source_text"])
        character_mentions = _find_character_mentions(conn, project.id, seg["source_text"])
        candidates = _fetch_candidates(conn, segment_id)
        history = _fetch_history_summary(conn, segment_id)
        warnings = _build_warnings(
            seg["source_text"],
            seg["translated_text"] if seg["translated_text"] is not None else None,
            glossary_matches,
        )

        _rs = seg["review_status"]
        review_status = str(_rs if _rs is not None else "not_reviewed")

    return SegmentContext(
        segment_id=segment_id,
        source_text=str(seg["source_text"]),
        translated_text=seg["translated_text"] if seg["translated_text"] is not None else None,
        status=str(seg["status"]),
        review_status=review_status,
        glossary_matches=glossary_matches,
        character_mentions=character_mentions,
        candidates=candidates,
        history=history,
        warnings=warnings,
    )


# --------------------------------------------------------------------------- #
#  Helpers
# --------------------------------------------------------------------------- #


def _chapter_exists(conn: sqlite3.Connection, chapter_id: str) -> bool:
    row = conn.execute("SELECT 1 FROM chapters WHERE id = ?", (chapter_id,)).fetchone()
    return row is not None


def _load_single_project(conn: sqlite3.Connection):
    row = conn.execute("SELECT id FROM projects ORDER BY id LIMIT 1").fetchone()
    if row is None:
        raise ChapterNotFoundError("No project found in database.")
    return get_project(conn, int(row["id"]))


def _segment_row(conn: sqlite3.Connection, segment_id: str, chapter_id: str) -> sqlite3.Row | None:
    columns = {str(r["name"]) for r in conn.execute("PRAGMA table_info(segments)").fetchall()}
    review_col = "s.review_status" if "review_status" in columns else "'not_reviewed'"
    return conn.execute(
        f"""
        SELECT s.id, s.source_text, s.status, s.chapter_id,
               {review_col} AS review_status,
               (SELECT t.text
                FROM translations t
                WHERE t.segment_id = s.id
                ORDER BY t.attempt DESC
                LIMIT 1) AS translated_text
        FROM segments s
        WHERE s.id = ? AND s.chapter_id = ?
        """,
        (segment_id, chapter_id),
    ).fetchone()


def _normalize_for_match(text: str) -> str:
    """Normalize text for deterministic matching."""
    text = normalize_japanese_text(text)
    text = unicodedata.normalize("NFKC", text)
    return text.lower()


def _find_glossary_matches(
    conn: sqlite3.Connection, project_id: int, source_text: str
) -> list[GlossaryMatch]:
    terms = list_glossary_terms(conn, project_id=project_id)
    if not terms:
        return []

    normalized_text = _normalize_for_match(source_text)
    matches: list[GlossaryMatch] = []

    for term in terms:
        lookup = term.source if term.case_sensitive else _normalize_for_match(term.source)
        if lookup in normalized_text:
            matches.append(
                GlossaryMatch(source=term.source, target=term.target, category=term.category)
            )

    return matches


def _find_character_mentions(
    conn: sqlite3.Connection, project_id: int, source_text: str
) -> list[CharacterMention]:
    characters = list_characters(conn, project_id=project_id)
    if not characters:
        return []

    normalized_text = _normalize_for_match(source_text)
    mentions: list[CharacterMention] = []

    for char in characters:
        lookup = _normalize_for_match(char.jp_name)
        if lookup in normalized_text:
            mentions.append(
                CharacterMention(jp_name=char.jp_name, en_name=char.en_name, role=char.role)
            )

    return mentions


def _fetch_candidates(conn: sqlite3.Connection, segment_id: str) -> list[CandidateSummary]:
    rows = list_candidates_for_segment(conn, segment_id=segment_id, status=None)
    return [
        CandidateSummary(
            id=str(r.id),
            candidate_text=r.candidate_text or "",
            status=r.status,
            provider=r.provider,
            model=r.model,
        )
        for r in rows
    ]


def _fetch_history_summary(conn: sqlite3.Connection, segment_id: str) -> HistorySummary:
    attempts = list_translation_attempts(conn, segment_id=segment_id)
    if not attempts:
        return HistorySummary(attempts_count=0, last_attempt_text=None, last_attempt_at=None)
    last = attempts[-1]
    return HistorySummary(
        attempts_count=len(attempts),
        last_attempt_text=last.text,
        last_attempt_at=last.created_at,
    )


def _build_warnings(
    source_text: str,
    translated_text: str | None,
    glossary_matches: list[GlossaryMatch],
) -> list[str]:
    warnings: list[str] = []

    if translated_text and glossary_matches:
        normalized_translation = _normalize_for_match(translated_text)
        for match in glossary_matches:
            if match.target:
                lookup = _normalize_for_match(match.target)
                if lookup not in normalized_translation:
                    warnings.append(
                        f"Glossary term '{match.source}' → '{match.target}' "
                        "may be missing from the translation."
                    )

    # Deterministic punctuation/honorific checks could be added here
    # but are deferred to Q11 (WV-008).

    return warnings
