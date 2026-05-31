"""Translation memory repository functions (schema v5).

Project-scoped source->target store keyed by the normalized source hash
(``UNIQUE(project_id, source_hash)``). The key is always the stored
``segments.source_hash`` (NFKC + whitespace-collapsed, SHA-256 via
``core.segment.compute_source_hash``); callers never recompute the hash from
provider request text, so the lookup key cannot drift.

Used by ``services/translation.translate_one_segment`` to skip the provider on an
exact match (lookup-before-AI) and to save successful provider output and manual
edits. Manual edits are treated as the source of truth: ``save_translation_memory``
with ``protect_manual=True`` (the provider-success path) never overwrites a
``manual`` row, while manual saves upsert unconditionally.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime

_COLUMNS = "source_text, source_hash, target_text, provider, model, created_at, updated_at"

_UPSERT_SQL = """
    INSERT INTO translation_memory (
      project_id, source_text, source_hash, target_text, provider, model, created_at, updated_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(project_id, source_hash) DO UPDATE SET
      source_text = excluded.source_text,
      target_text = excluded.target_text,
      provider = excluded.provider,
      model = excluded.model,
      updated_at = excluded.updated_at
"""

# Appended to the upsert so a provider-origin save cannot clobber a manual entry.
_PROTECT_MANUAL_TAIL = " WHERE translation_memory.provider != 'manual'"


@dataclass(frozen=True)
class TranslationMemoryRecord:
    """Stored translation-memory row (project-scoped, keyed by source_hash)."""

    source_text: str
    source_hash: str
    target_text: str
    provider: str | None
    model: str | None
    created_at: str
    updated_at: str


def lookup_translation_memory(
    connection: sqlite3.Connection, *, project_id: int, source_hash: str
) -> TranslationMemoryRecord | None:
    """Return the stored translation for one source hash, or None on a miss.

    Exact match only. The lookup key is the caller's existing
    ``segment.source_hash``; it is never recomputed here.
    """

    row = connection.execute(
        f"SELECT {_COLUMNS} FROM translation_memory WHERE project_id = ? AND source_hash = ?",
        (project_id, source_hash),
    ).fetchone()
    if row is None:
        return None
    return _from_row(row)


def save_translation_memory(
    connection: sqlite3.Connection,
    *,
    project_id: int,
    source_text: str,
    source_hash: str,
    target_text: str,
    provider: str,
    model: str,
    protect_manual: bool = False,
) -> TranslationMemoryRecord:
    """Insert or refresh one translation-memory entry (keyed by source_hash).

    Args:
        connection: Open writable SQLite connection.
        project_id: Owning project row id.
        source_text: Normalized source text (display only; the hash is the key).
        source_hash: The stored ``segment.source_hash`` (authoritative key).
        target_text: Translation to store.
        provider: Origin provider name (real provider, or ``"manual"``).
        model: Origin model name.
        protect_manual: When True (provider-success path), the upsert does not
            overwrite an existing ``manual`` row; manual saves leave it False so
            the latest manual edit always wins.

    Returns:
        The stored :class:`TranslationMemoryRecord` after the upsert.
    """

    now = datetime.now(UTC).isoformat()
    sql = _UPSERT_SQL + (_PROTECT_MANUAL_TAIL if protect_manual else "")
    connection.execute(
        sql,
        (project_id, source_text, source_hash, target_text, provider, model, now, now),
    )
    stored = lookup_translation_memory(connection, project_id=project_id, source_hash=source_hash)
    if stored is None:  # pragma: no cover - upsert always yields a row
        raise RuntimeError("Translation memory upsert did not persist a row")
    return stored


def list_translation_memory(
    connection: sqlite3.Connection, *, project_id: int
) -> list[TranslationMemoryRecord]:
    """List a project's translation-memory entries in stable insertion order."""

    rows = connection.execute(
        f"SELECT {_COLUMNS} FROM translation_memory WHERE project_id = ? ORDER BY id",
        (project_id,),
    ).fetchall()
    return [_from_row(row) for row in rows]


def delete_translation_memory(
    connection: sqlite3.Connection, *, project_id: int, source_hash: str
) -> bool:
    """Delete one translation-memory entry; return whether a row was removed.

    Only the ``translation_memory`` row is removed. Translation attempt history,
    manual edits, glossary, and character data are never touched.
    """

    cursor = connection.execute(
        "DELETE FROM translation_memory WHERE project_id = ? AND source_hash = ?",
        (project_id, source_hash),
    )
    return cursor.rowcount > 0


def count_memory_reuses(
    connection: sqlite3.Connection, *, project_id: int, provider_marker: str
) -> int:
    """Count translation attempts served from memory (provider == ``provider_marker``).

    Project-scoped via the chapter join. With exact-only matching every reuse is an
    exact hit, so this is both the exact-hit count and the reused-from-memory count.
    """

    row = connection.execute(
        """
        SELECT COUNT(*) AS reuse_count
        FROM translations t
        JOIN segments s ON s.id = t.segment_id
        JOIN chapters c ON c.id = s.chapter_id
        WHERE c.project_id = ? AND t.provider = ?
        """,
        (project_id, provider_marker),
    ).fetchone()
    return int(row["reuse_count"])


def _from_row(row: sqlite3.Row) -> TranslationMemoryRecord:
    return TranslationMemoryRecord(
        source_text=str(row["source_text"]),
        source_hash=str(row["source_hash"]),
        target_text=str(row["target_text"]),
        provider=_optional_str(row["provider"]),
        model=_optional_str(row["model"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)
