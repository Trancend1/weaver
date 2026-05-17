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
          raw_response
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
        ),
    )
    return attempt
