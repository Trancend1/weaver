"""Export-history ledger writer (Sprint Q7 / WV-009).

Records one ledger row per export artifact on success and one row per export
attempt on failure. The write lives here in the service layer (ADR 002) — the
export router only builds a runner that calls :func:`run_export_recorded`; it
never touches SQLite. A failed ledger write is non-fatal: it must never break an
otherwise-successful export.
"""

from __future__ import annotations

import logging
import sqlite3
import uuid
from collections.abc import Callable
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from weaver.errors import WeaverError
from weaver.services.export_book import (
    ExportPlan,
    ExportProgressCallback,
    ExportResult,
    run_export,
)
from weaver.storage.db import connect_database, transaction
from weaver.storage.export_history import record_export

logger = logging.getLogger(__name__)


def run_export_recorded(
    plan: ExportPlan,
    db_path: Path,
    *,
    kind: str,
    qa_badge: str | None,
    version_label: str | None = None,
    job_id: str | None = None,
    should_cancel: Callable[[], bool] | None = None,
    progress_callback: ExportProgressCallback | None = None,
) -> ExportResult:
    """Run an export and record its outcome to the export-history ledger.

    On success, one ``succeeded`` row per artifact (with byte size from ``stat``).
    On failure, one ``failed`` row, then the original exception is re-raised so
    the job still terminates as failed.
    """

    try:
        result = run_export(plan, should_cancel=should_cancel, progress_callback=progress_callback)
    except Exception as exc:
        _record_failure(
            db_path,
            target=plan.target,
            kind=kind,
            qa_badge=qa_badge,
            version_label=version_label,
            job_id=job_id,
        )
        raise exc
    _record_result(
        db_path,
        result,
        kind=kind,
        qa_badge=qa_badge,
        version_label=version_label,
        job_id=job_id,
    )
    return result


def _record_result(
    db_path: Path,
    result: ExportResult,
    *,
    kind: str,
    qa_badge: str | None,
    version_label: str | None,
    job_id: str | None,
) -> None:
    """Write one ``succeeded`` ledger row per produced artifact (non-fatal)."""

    created_at = datetime.now(UTC).isoformat()
    try:
        with closing(connect_database(db_path)) as connection, transaction(connection):
            for artifact in result.artifacts:
                record_export(
                    connection,
                    id=uuid.uuid4().hex,
                    volume_id=artifact.volume_id,
                    format=result.target,
                    kind=kind,
                    status="succeeded",
                    qa_badge=qa_badge,
                    artifact_path=str(artifact.output_path),
                    byte_size=_byte_size(artifact.output_path),
                    job_id=job_id,
                    version_label=version_label,
                    created_at=created_at,
                )
    except (WeaverError, sqlite3.Error) as exc:
        logger.warning("export.ledger.record_failed", extra={"data": {"error": str(exc)}})


def _record_failure(
    db_path: Path,
    *,
    target: str,
    kind: str,
    qa_badge: str | None,
    version_label: str | None,
    job_id: str | None,
) -> None:
    """Write one ``failed`` ledger row for an export attempt (non-fatal)."""

    created_at = datetime.now(UTC).isoformat()
    try:
        with closing(connect_database(db_path)) as connection, transaction(connection):
            record_export(
                connection,
                id=uuid.uuid4().hex,
                volume_id=None,
                format=target,
                kind=kind,
                status="failed",
                qa_badge=qa_badge,
                artifact_path=None,
                byte_size=None,
                job_id=job_id,
                version_label=version_label,
                created_at=created_at,
            )
    except (WeaverError, sqlite3.Error) as exc:
        logger.warning("export.ledger.record_failed", extra={"data": {"error": str(exc)}})


def _byte_size(path: Path) -> int | None:
    try:
        return path.stat().st_size
    except OSError:
        return None
