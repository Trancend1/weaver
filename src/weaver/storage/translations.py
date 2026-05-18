"""Translation repository functions."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime


def record_translation(
    connection: sqlite3.Connection,
    *,
    segment_id: str,
    text: str,
    source_hash: str,
    provider: str,
    model: str,
    raw_response: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
) -> int:
    """Store a translation attempt for one segment.

    Args:
        connection: Open writable SQLite connection.
        segment_id: Segment id the translation belongs to.
        text: Translated text.
        source_hash: Source hash used for this translation.
        provider: Provider name.
        model: Provider model name.
        raw_response: Optional provider raw response.
        input_tokens: Provider-reported input token count, if available.
        output_tokens: Provider-reported output token count, if available.

    Returns:
        Attempt number assigned to the translation.
    """

    row = connection.execute(
        """
        SELECT COALESCE(MAX(attempt), 0) + 1 AS next_attempt
        FROM translations
        WHERE segment_id = ?
        """,
        (segment_id,),
    ).fetchone()
    attempt = int(row["next_attempt"])
    connection.execute(
        """
        INSERT INTO translations (
          segment_id,
          attempt,
          text,
          source_hash,
          provider,
          model,
          created_at,
          raw_response,
          input_tokens,
          output_tokens
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            segment_id,
            attempt,
            text,
            source_hash,
            provider,
            model,
            datetime.now(UTC).isoformat(),
            raw_response,
            input_tokens,
            output_tokens,
        ),
    )
    return attempt


def get_latest_translation_text(connection: sqlite3.Connection, *, segment_id: str) -> str | None:
    """Return the most recent translation text for one segment.

    Args:
        connection: Open SQLite connection.
        segment_id: Segment id to look up.

    Returns:
        Latest translation text, or None if no translation has been recorded yet.
    """

    row = connection.execute(
        """
        SELECT text
        FROM translations
        WHERE segment_id = ?
        ORDER BY attempt DESC
        LIMIT 1
        """,
        (segment_id,),
    ).fetchone()
    if row is None:
        return None
    return str(row["text"])


def list_previous_translated_segments(
    connection: sqlite3.Connection,
    *,
    chapter_id: str,
    before_block_order: int,
    limit: int = 5,
) -> list[tuple[str, str]]:
    """Return latest translated source/target pairs before one segment.

    Args:
        connection: Open SQLite connection.
        chapter_id: Chapter to search within.
        before_block_order: Exclude segments at or after this block order.
        limit: Maximum number of previous translated/manual segments.

    Returns:
        `(source_text, translated_text)` pairs ordered oldest-first.
    """

    rows = connection.execute(
        """
        WITH latest AS (
          SELECT segment_id, MAX(attempt) AS attempt
          FROM translations
          GROUP BY segment_id
        )
        SELECT s.source_text, t.text
        FROM segments s
        JOIN latest l ON l.segment_id = s.id
        JOIN translations t ON t.segment_id = l.segment_id AND t.attempt = l.attempt
        WHERE s.chapter_id = ?
          AND s.block_order < ?
          AND s.status IN ('translated', 'manual')
          AND t.source_hash = s.source_hash
        ORDER BY s.block_order DESC
        LIMIT ?
        """,
        (chapter_id, before_block_order, limit),
    ).fetchall()
    return [(str(row["source_text"]), str(row["text"])) for row in reversed(rows)]
