"""Export-history ledger persistence (schema v11, Sprint Q7 / WV-009).

One row per export artifact on success and one row per export attempt on
failure. Storage layer only: framework-agnostic, no web/CLI types. Writes flow
through the export service (``services/export_ledger.py``); routers never call
these functions directly.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class ExportHistoryRow:
    """One persisted export-history ledger entry."""

    id: str
    volume_id: int | None
    format: str
    kind: str  # draft | final
    status: str  # succeeded | failed
    qa_badge: str | None
    artifact_path: str | None
    byte_size: int | None
    job_id: str | None
    version_label: str | None
    created_at: str


def record_export(
    connection: sqlite3.Connection,
    *,
    id: str,
    volume_id: int | None,
    format: str,
    kind: str,
    status: str,
    qa_badge: str | None,
    artifact_path: str | None,
    byte_size: int | None,
    job_id: str | None,
    version_label: str | None,
    created_at: str,
) -> None:
    """Insert one export-history row. Caller owns the transaction/commit."""

    connection.execute(
        """
        INSERT INTO export_history (
          id, volume_id, format, kind, status, qa_badge,
          artifact_path, byte_size, job_id, version_label, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            id,
            volume_id,
            format,
            kind,
            status,
            qa_badge,
            artifact_path,
            byte_size,
            job_id,
            version_label,
            created_at,
        ),
    )


def list_export_history(
    connection: sqlite3.Connection, *, limit: int = 50
) -> list[ExportHistoryRow]:
    """Return the most recent export-history rows, newest first."""

    rows = connection.execute(
        """
        SELECT id, volume_id, format, kind, status, qa_badge,
               artifact_path, byte_size, job_id, version_label, created_at
        FROM export_history
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [_row_to_history(row) for row in rows]


def _row_to_history(row: sqlite3.Row) -> ExportHistoryRow:
    return ExportHistoryRow(
        id=str(row["id"]),
        volume_id=int(row["volume_id"]) if row["volume_id"] is not None else None,
        format=str(row["format"]),
        kind=str(row["kind"]),
        status=str(row["status"]),
        qa_badge=str(row["qa_badge"]) if row["qa_badge"] is not None else None,
        artifact_path=str(row["artifact_path"]) if row["artifact_path"] is not None else None,
        byte_size=int(row["byte_size"]) if row["byte_size"] is not None else None,
        job_id=str(row["job_id"]) if row["job_id"] is not None else None,
        version_label=str(row["version_label"]) if row["version_label"] is not None else None,
        created_at=str(row["created_at"]),
    )
