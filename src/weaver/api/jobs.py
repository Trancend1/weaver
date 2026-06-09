"""In-memory + SQLite-backed background jobs for the FastAPI cockpit.

A translate / batch / export request submits a runner; the runner executes on
one daemon thread, reporting per-segment progress and honouring a cooperative
cancel flag. The job's live progress, terminal state, and result are read back
by job id, and progress events can be streamed as Server-Sent Events.

Sprint I (ADR 010) added a SQLite durability layer behind this in-memory
registry. When the registry is constructed with a ``base_dir``, every status
transition + sampled progress snapshot + SSE event is mirrored to the owning
project's ``weaver.db`` so a browser refresh, a navigation, or a process
restart never loses the job's state.

# JobRegistry is single-process, in-thread infrastructure.
# Do not build Celery, Redis, RabbitMQ, Kafka, Dramatiq, RQ, or distributed workers.
# SQLite is the durability layer (ADR 010), not a queue.

Stdlib + shared service types only; no FastAPI imports so the registry
stays trivially testable and framework-agnostic (ADR 004).
"""

from __future__ import annotations

import json
import logging
import queue
import sqlite3
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from weaver.errors import WeaverError
from weaver.services.batch_translate import (
    BatchProgressCallback,
    BatchProgressSnapshot,
    BatchTranslationResult,
)
from weaver.services.epub_export_fidelity import report_to_dict
from weaver.services.export_book import (
    ExportProgressCallback,
    ExportProgressSnapshot,
    ExportResult,
)
from weaver.services.job_store import (
    JOB_KIND_BATCH,
    JOB_KIND_EXPORT,
    JOB_KIND_PARSE,
    JOB_KIND_TRANSLATE,
    append_event,
    db_path_for,
    insert_job,
    update_job_progress,
    update_job_terminal,
)
from weaver.services.logging_setup import log_job_event
from weaver.services.translation import ProgressCallback
from weaver.services.workspace_translate import ChapterTranslationResult
from weaver.storage.db import connect_database
from weaver.storage.segments import SegmentRecord

logger = logging.getLogger("weaver.job")
_PROGRESS_FLUSH_INTERVAL_SECONDS = 1.0

# A runner is a closure built by the route around ``run_translation``. It receives
# a cooperative cancel predicate and a progress callback, and returns the run
# result; keeping the registry decoupled from the translation service makes it
# testable with a fake runner.
ShouldCancel = Callable[[], bool]
JobRunner = Callable[[ShouldCancel, ProgressCallback], ChapterTranslationResult]
# A batch runner is the multi-chapter analogue, built around ``run_batch_translation``.
BatchJobRunner = Callable[[ShouldCancel, BatchProgressCallback], BatchTranslationResult]
# An export runner is built around ``run_export`` (per-volume progress).
ExportJobRunner = Callable[[ShouldCancel, ExportProgressCallback], ExportResult]

# Sentinel pushed onto the event queue when the worker finishes (any outcome), so
# an SSE generator knows to stop draining.
_STREAM_END: None = None


class JobStorage:
    """Per-job persistence mediator (ADR 010).

    Wraps the SQLite calls each running job needs: status, progress, events.
    A single instance is created once per submitted job and shared with the
    worker thread. ``db_path=None`` means persistence is disabled (used in
    pure-memory tests + when the registry has no books-dir).

    Connections are opened **per call** — never shared across threads — so the
    registry remains GIL-bound but never collides on a sqlite3 handle.
    """

    def __init__(self, *, job_id: str, db_path: Path | None) -> None:
        self.job_id = job_id
        self.db_path = db_path
        self._last_flush = 0.0
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self.db_path is not None

    def insert(
        self,
        *,
        kind: str,
        project_name: str,
        scope: str | None,
        scope_id: str | None,
        chapter_id: str | None,
        mode: str | None,
        target: str | None,
        total_units: int,
    ) -> None:
        if not self.enabled:
            return
        try:
            with closing(connect_database(self.db_path)) as conn:  # type: ignore[arg-type]
                insert_job(
                    conn,
                    job_id=self.job_id,
                    kind=kind,
                    project_name=project_name,
                    scope=scope,
                    scope_id=scope_id,
                    chapter_id=chapter_id,
                    mode=mode,
                    target=target,
                    total_units=total_units,
                )
        except (WeaverError, sqlite3.Error) as exc:
            logger.warning(
                "job.insert.failed", extra={"data": {"job_id": self.job_id, "error": str(exc)}}
            )
            return
        # G6 lifecycle event — separate from the SSE event log (job_events).
        log_job_event(
            "job.submitted",
            job_id=self.job_id,
            kind=kind,
            project=project_name,
            scope=scope,
            scope_id=scope_id,
            chapter_id=chapter_id,
            target=target,
            total_units=total_units,
        )

    def flush_progress(
        self,
        *,
        done_units: int,
        failed_units: int,
        skipped_units: int = 0,
        total_units: int | None = None,
        current_label: str | None = None,
        force: bool = False,
    ) -> None:
        """Flush counters at most once per :data:`_PROGRESS_FLUSH_INTERVAL_SECONDS`.

        ``force=True`` bypasses the interval — terminal flushes use it.
        """
        if not self.enabled:
            return
        with self._lock:
            now = time.monotonic()
            if not force and now - self._last_flush < _PROGRESS_FLUSH_INTERVAL_SECONDS:
                return
            self._last_flush = now
        try:
            with closing(connect_database(self.db_path)) as conn:  # type: ignore[arg-type]
                update_job_progress(
                    conn,
                    job_id=self.job_id,
                    done_units=done_units,
                    failed_units=failed_units,
                    skipped_units=skipped_units,
                    total_units=total_units,
                    current_label=current_label,
                )
        except (WeaverError, sqlite3.Error) as exc:
            logger.warning(
                "job.progress.failed", extra={"data": {"job_id": self.job_id, "error": str(exc)}}
            )

    def append_event(self, *, event: str, data: dict[str, Any]) -> int | None:
        """Persist one SSE event and return the new event id (or None on failure)."""
        if not self.enabled:
            return None
        try:
            with closing(connect_database(self.db_path)) as conn:  # type: ignore[arg-type]
                return append_event(
                    conn,
                    project_id=None,
                    job_id=self.job_id,
                    event=event,
                    data=data,
                )
        except (WeaverError, sqlite3.Error) as exc:
            logger.warning(
                "job.event.failed",
                extra={"data": {"job_id": self.job_id, "error": str(exc), "event": event}},
            )
            return None

    def finish(
        self,
        *,
        status: str,
        result: dict[str, Any] | None,
        error_summary: str | None,
    ) -> None:
        """Synchronously persist a terminal status before the terminal SSE event."""
        if not self.enabled:
            return
        try:
            with closing(connect_database(self.db_path)) as conn:  # type: ignore[arg-type]
                update_job_terminal(
                    conn,
                    job_id=self.job_id,
                    status=status,
                    result=result,
                    error_summary=error_summary,
                )
        except (WeaverError, sqlite3.Error) as exc:
            logger.warning(
                "job.finish.failed",
                extra={"data": {"job_id": self.job_id, "error": str(exc), "status": status}},
            )
            return
        log_job_event(
            "job.finished",
            job_id=self.job_id,
            status=status,
            error_summary=error_summary,
        )


@dataclass
class JobProgress:
    """Live per-segment progress snapshot for one job."""

    current: int = 0
    total: int = 0
    translated: int = 0
    failed: int = 0


@dataclass
class TranslationJob:
    """One background translate run, its progress, and its terminal state.

    ``status`` is a small state machine driven by the worker thread:
    ``running`` → ``done`` | ``failed`` | ``cancelled``.
    """

    id: str
    project_name: str
    chapter_id: str
    mode: str  # "chapter" | "selection"
    runner: JobRunner
    status: str = "running"
    result: ChapterTranslationResult | None = None
    error: str | None = None
    progress: JobProgress = field(default_factory=JobProgress)
    queue: queue.Queue[dict[str, Any] | None] = field(default_factory=queue.Queue)
    storage: JobStorage | None = None
    _cancel: threading.Event = field(default_factory=threading.Event)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _updated_segment_ids: list[str] = field(default_factory=list)
    _thread: threading.Thread | None = field(default=None, repr=False)

    def request_cancel(self) -> None:
        """Signal the worker to stop after the current segment (idempotent)."""

        self._cancel.set()

    def should_cancel(self) -> bool:
        """True once :meth:`request_cancel` has been called."""

        return self._cancel.is_set()

    def snapshot(self) -> JobProgress:
        """Return a consistent copy of the live progress counters."""

        with self._lock:
            return JobProgress(
                current=self.progress.current,
                total=self.progress.total,
                translated=self.progress.translated,
                failed=self.progress.failed,
            )

    def drain_updated_segment_ids(self) -> list[str]:
        with self._lock:
            segment_ids = list(self._updated_segment_ids)
            self._updated_segment_ids.clear()
            return segment_ids

    def on_progress(
        self,
        index: int,
        total: int,
        segment: SegmentRecord,
        translated: bool,
        input_tokens: int | None,
        output_tokens: int | None,
    ) -> None:
        """Update the progress snapshot and emit a ``progress`` SSE event."""

        with self._lock:
            self.progress.current = index
            self.progress.total = total
            if translated:
                self.progress.translated += 1
            else:
                self.progress.failed += 1
            if segment.id not in self._updated_segment_ids:
                self._updated_segment_ids.append(segment.id)
            current = self.progress.current
            done = self.progress.translated
            failed = self.progress.failed
        if self.storage is not None:
            self.storage.flush_progress(
                done_units=done,
                failed_units=failed,
                total_units=total,
                current_label=segment.id,
            )
        data = {
            "current": index,
            "total": total,
            "segment_id": segment.id,
            "status": "translated" if translated else "failed",
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        }
        event_id = self.storage.append_event(event="progress", data=data) if self.storage else None
        envelope: dict[str, Any] = {"event": "progress", "data": data}
        if event_id is not None:
            envelope["id"] = event_id
        self.queue.put(envelope)
        _ = current  # silence unused (kept for symmetry with snapshot path)

    def run(self) -> None:
        """Execute the runner on the worker thread, emitting queue events.

        Emits ``progress`` per segment (via :meth:`on_progress`), then exactly one
        terminal event (``done`` | ``cancelled`` | ``error``), then the stream-end
        sentinel. The broad ``except`` is the web-boundary analogue of the CLI
        boundary (CLAUDE.md §4.2): an unhandled worker-thread exception would
        vanish silently, so it is surfaced — on the job and on the stream — not
        swallowed. SQLite mirroring is synchronous before the terminal event so
        a refresh-after-finish always sees the persisted terminal row.
        """

        terminal_data: dict[str, Any]
        try:
            self.result = self.runner(self.should_cancel, self.on_progress)
        except Exception as exc:  # noqa: BLE001 - web boundary; surfaced, not swallowed
            self.error = str(exc)
            terminal_data = {"message": str(exc)}
            if self.storage is not None:
                self.storage.flush_progress(
                    done_units=self.progress.translated,
                    failed_units=self.progress.failed,
                    force=True,
                )
                self.storage.finish(status="failed", result=None, error_summary=str(exc))
            event_id = (
                self.storage.append_event(event="error", data=terminal_data)
                if self.storage
                else None
            )
            self.status = "failed"
            envelope: dict[str, Any] = {"event": "error", "data": terminal_data}
            if event_id is not None:
                envelope["id"] = event_id
            self.queue.put(envelope)
        else:
            terminal_status = "cancelled" if self.should_cancel() else "done"
            result = self.result
            terminal_data = {
                "selected": result.selected,
                "translated": result.translated,
                "reused_from_memory": result.reused_from_memory,
                "failed": result.failed,
                "skipped": result.skipped,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "cancelled": result.cancelled,
            }
            if self.storage is not None:
                self.storage.flush_progress(
                    done_units=result.translated,
                    failed_units=result.failed,
                    skipped_units=result.skipped,
                    total_units=self.progress.total,
                    force=True,
                )
                self.storage.finish(
                    status=terminal_status, result=terminal_data, error_summary=None
                )
            event_id = (
                self.storage.append_event(event=terminal_status, data=terminal_data)
                if self.storage
                else None
            )
            self.status = terminal_status
            envelope = {"event": terminal_status, "data": terminal_data}
            if event_id is not None:
                envelope["id"] = event_id
            self.queue.put(envelope)
        finally:
            self.queue.put(_STREAM_END)

    def wait(self, timeout: float | None = None) -> None:
        """Block until the worker thread finishes (or ``timeout`` elapses)."""

        if self._thread is not None:
            self._thread.join(timeout)


@dataclass
class BatchProgress:
    """Live aggregate progress snapshot for one batch job (mutable)."""

    scope: str = "novel"
    scope_id: str | None = None
    mode: str = "skip_existing"
    provider: str = ""
    model: str = ""
    chapters_total: int = 0
    chapters_done: int = 0
    current_chapter_id: str | None = None
    segments_total: int = 0
    segments_done: int = 0
    translated: int = 0
    reused_from_memory: int = 0
    skipped: int = 0
    failed: int = 0


@dataclass
class BatchJob:
    """One background batch (chapter/volume/novel) translate run.

    Sibling of :class:`TranslationJob`: same status state machine
    (``running`` → ``done`` | ``failed`` | ``cancelled``), cancel flag, SSE event
    queue, and stream-end sentinel, but carries aggregate batch progress and a
    :class:`BatchTranslationResult`.
    """

    id: str
    project_name: str
    scope: str  # "chapter" | "volume" | "novel"
    scope_id: str | None
    mode: str
    runner: BatchJobRunner
    status: str = "running"
    result: BatchTranslationResult | None = None
    error: str | None = None
    progress: BatchProgress = field(default_factory=BatchProgress)
    queue: queue.Queue[dict[str, Any] | None] = field(default_factory=queue.Queue)
    storage: JobStorage | None = None
    _cancel: threading.Event = field(default_factory=threading.Event)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _thread: threading.Thread | None = field(default=None, repr=False)

    def request_cancel(self) -> None:
        """Signal the worker to stop after the current segment/chapter."""

        self._cancel.set()

    def should_cancel(self) -> bool:
        """True once :meth:`request_cancel` has been called."""

        return self._cancel.is_set()

    def snapshot(self) -> BatchProgress:
        """Return a consistent copy of the live aggregate counters."""

        with self._lock:
            return BatchProgress(
                scope=self.progress.scope,
                scope_id=self.progress.scope_id,
                mode=self.progress.mode,
                provider=self.progress.provider,
                model=self.progress.model,
                chapters_total=self.progress.chapters_total,
                chapters_done=self.progress.chapters_done,
                current_chapter_id=self.progress.current_chapter_id,
                segments_total=self.progress.segments_total,
                segments_done=self.progress.segments_done,
                translated=self.progress.translated,
                reused_from_memory=self.progress.reused_from_memory,
                skipped=self.progress.skipped,
                failed=self.progress.failed,
            )

    def on_progress(self, snapshot: BatchProgressSnapshot) -> None:
        """Adopt a batch progress snapshot and emit a ``progress`` SSE event."""

        with self._lock:
            self.progress = BatchProgress(
                scope=snapshot.scope,
                scope_id=snapshot.scope_id,
                mode=snapshot.mode,
                provider=snapshot.provider,
                model=snapshot.model,
                chapters_total=snapshot.chapters_total,
                chapters_done=snapshot.chapters_done,
                current_chapter_id=snapshot.current_chapter_id,
                segments_total=snapshot.segments_total,
                segments_done=snapshot.segments_done,
                translated=snapshot.translated,
                reused_from_memory=snapshot.reused_from_memory,
                skipped=snapshot.skipped,
                failed=snapshot.failed,
            )
        if self.storage is not None:
            self.storage.flush_progress(
                done_units=snapshot.segments_done,
                failed_units=snapshot.failed,
                skipped_units=snapshot.skipped,
                total_units=snapshot.segments_total,
                current_label=snapshot.current_chapter_id,
            )
        data = _batch_progress_data(snapshot)
        event_id = self.storage.append_event(event="progress", data=data) if self.storage else None
        envelope: dict[str, Any] = {"event": "progress", "data": data}
        if event_id is not None:
            envelope["id"] = event_id
        self.queue.put(envelope)

    def run(self) -> None:
        """Execute the runner on the worker thread, emitting queue events.

        Emits ``progress`` per snapshot, then exactly one terminal event
        (``done`` | ``cancelled`` | ``error``), then the stream-end sentinel. The
        broad ``except`` is the web-boundary analogue (CLAUDE.md §4.2): an
        unhandled worker-thread exception is surfaced, not swallowed.
        """

        try:
            self.result = self.runner(self.should_cancel, self.on_progress)
        except Exception as exc:  # noqa: BLE001 - web boundary; surfaced, not swallowed
            self.status = "failed"
            self.error = str(exc)
            if self.storage is not None:
                self.storage.finish(status="failed", result=None, error_summary=str(exc))
            data = {"message": str(exc)}
            event_id = self.storage.append_event(event="error", data=data) if self.storage else None
            envelope: dict[str, Any] = {"event": "error", "data": data}
            if event_id is not None:
                envelope["id"] = event_id
            self.queue.put(envelope)
        else:
            result = self.result
            self.status = "cancelled" if result.cancelled else "done"
            data = _batch_result_data(result)
            if self.storage is not None:
                self.storage.flush_progress(
                    done_units=result.segments_total,
                    failed_units=result.failed,
                    skipped_units=result.skipped,
                    total_units=result.segments_total,
                    force=True,
                )
                self.storage.finish(status=self.status, result=data, error_summary=None)
            event_id = (
                self.storage.append_event(event=self.status, data=data) if self.storage else None
            )
            envelope = {"event": self.status, "data": data}
            if event_id is not None:
                envelope["id"] = event_id
            self.queue.put(envelope)
        finally:
            self.queue.put(_STREAM_END)

    def wait(self, timeout: float | None = None) -> None:
        """Block until the worker thread finishes (or ``timeout`` elapses)."""

        if self._thread is not None:
            self._thread.join(timeout)


@dataclass
class ExportProgress:
    """Live per-volume progress snapshot for one export job (mutable)."""

    target: str = "epub"
    scope: str = "novel"
    scope_id: str | None = None
    volumes_total: int = 0
    volumes_done: int = 0
    current_volume_id: int | None = None
    current_volume_title: str | None = None
    translated_segments: int = 0
    fallback_segments: int = 0


@dataclass
class ExportJob:
    """One background export run, its progress, and its terminal state.

    Sibling of :class:`BatchJob`: same status state machine
    (``running`` → ``done`` | ``failed`` | ``cancelled``), cancel flag, SSE event
    queue, and stream-end sentinel, but carries per-volume export progress and an
    :class:`ExportResult`.
    """

    id: str
    project_name: str
    scope: str  # "novel" | "volume" | "chapter"
    scope_id: str | None
    target: str
    runner: ExportJobRunner
    status: str = "running"
    result: ExportResult | None = None
    error: str | None = None
    progress: ExportProgress = field(default_factory=ExportProgress)
    queue: queue.Queue[dict[str, Any] | None] = field(default_factory=queue.Queue)
    storage: JobStorage | None = None
    _cancel: threading.Event = field(default_factory=threading.Event)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _thread: threading.Thread | None = field(default=None, repr=False)

    def request_cancel(self) -> None:
        """Signal the worker to stop before the next volume (idempotent)."""

        self._cancel.set()

    def should_cancel(self) -> bool:
        """True once :meth:`request_cancel` has been called."""

        return self._cancel.is_set()

    def snapshot(self) -> ExportProgress:
        """Return a consistent copy of the live progress counters."""

        with self._lock:
            return ExportProgress(
                target=self.progress.target,
                scope=self.progress.scope,
                scope_id=self.progress.scope_id,
                volumes_total=self.progress.volumes_total,
                volumes_done=self.progress.volumes_done,
                current_volume_id=self.progress.current_volume_id,
                current_volume_title=self.progress.current_volume_title,
                translated_segments=self.progress.translated_segments,
                fallback_segments=self.progress.fallback_segments,
            )

    def on_progress(self, snapshot: ExportProgressSnapshot) -> None:
        """Adopt an export progress snapshot and emit a ``progress`` SSE event."""

        with self._lock:
            self.progress = ExportProgress(
                target=snapshot.target,
                scope=snapshot.scope,
                scope_id=snapshot.scope_id,
                volumes_total=snapshot.volumes_total,
                volumes_done=snapshot.volumes_done,
                current_volume_id=snapshot.current_volume_id,
                current_volume_title=snapshot.current_volume_title,
                translated_segments=snapshot.translated_segments,
                fallback_segments=snapshot.fallback_segments,
            )
        if self.storage is not None:
            label = snapshot.current_volume_title or (
                str(snapshot.current_volume_id) if snapshot.current_volume_id is not None else None
            )
            self.storage.flush_progress(
                done_units=snapshot.volumes_done,
                failed_units=0,
                total_units=snapshot.volumes_total,
                current_label=label,
            )
        data = _export_progress_data(snapshot)
        event_id = self.storage.append_event(event="progress", data=data) if self.storage else None
        envelope: dict[str, Any] = {"event": "progress", "data": data}
        if event_id is not None:
            envelope["id"] = event_id
        self.queue.put(envelope)

    def run(self) -> None:
        """Execute the runner on the worker thread, emitting queue events.

        Emits ``progress`` per volume, then exactly one terminal event
        (``done`` | ``cancelled`` | ``error``), then the stream-end sentinel. The
        broad ``except`` is the web-boundary analogue (CLAUDE.md §4.2): an
        unhandled worker-thread exception is surfaced, not swallowed.
        """

        try:
            self.result = self.runner(self.should_cancel, self.on_progress)
        except Exception as exc:  # noqa: BLE001 - web boundary; surfaced, not swallowed
            self.status = "failed"
            self.error = str(exc)
            if self.storage is not None:
                self.storage.finish(status="failed", result=None, error_summary=str(exc))
            data = {"message": str(exc)}
            event_id = self.storage.append_event(event="error", data=data) if self.storage else None
            envelope: dict[str, Any] = {"event": "error", "data": data}
            if event_id is not None:
                envelope["id"] = event_id
            self.queue.put(envelope)
        else:
            result = self.result
            self.status = "cancelled" if result.cancelled else "done"
            data = _export_result_data(result)
            if self.storage is not None:
                self.storage.flush_progress(
                    done_units=result.volumes_exported,
                    failed_units=0,
                    total_units=result.volumes_total,
                    force=True,
                )
                self.storage.finish(status=self.status, result=data, error_summary=None)
            event_id = (
                self.storage.append_event(event=self.status, data=data) if self.storage else None
            )
            envelope = {"event": self.status, "data": data}
            if event_id is not None:
                envelope["id"] = event_id
            self.queue.put(envelope)
        finally:
            self.queue.put(_STREAM_END)

    def wait(self, timeout: float | None = None) -> None:
        """Block until the worker thread finishes (or ``timeout`` elapses)."""

        if self._thread is not None:
            self._thread.join(timeout)


def _batch_progress_data(snapshot: BatchProgressSnapshot) -> dict[str, Any]:
    return {
        "scope": snapshot.scope,
        "scope_id": snapshot.scope_id,
        "mode": snapshot.mode,
        "provider": snapshot.provider,
        "model": snapshot.model,
        "chapters_total": snapshot.chapters_total,
        "chapters_done": snapshot.chapters_done,
        "current_chapter_id": snapshot.current_chapter_id,
        "segments_total": snapshot.segments_total,
        "segments_done": snapshot.segments_done,
        "translated": snapshot.translated,
        "reused_from_memory": snapshot.reused_from_memory,
        "skipped": snapshot.skipped,
        "failed": snapshot.failed,
    }


def _batch_result_data(result: BatchTranslationResult) -> dict[str, Any]:
    return {
        "scope": result.scope,
        "scope_id": result.scope_id,
        "mode": result.mode,
        "provider": result.provider,
        "model": result.model,
        "chapters_total": result.chapters_total,
        "chapters_done": result.chapters_done,
        "segments_total": result.segments_total,
        "translated": result.translated,
        "reused_from_memory": result.reused_from_memory,
        "skipped": result.skipped,
        "failed": result.failed,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "cancelled": result.cancelled,
        "started_at": result.started_at,
        "finished_at": result.finished_at,
        "duration_seconds": result.duration_seconds,
    }


def _export_progress_data(snapshot: ExportProgressSnapshot) -> dict[str, Any]:
    return {
        "target": snapshot.target,
        "scope": snapshot.scope,
        "scope_id": snapshot.scope_id,
        "volumes_total": snapshot.volumes_total,
        "volumes_done": snapshot.volumes_done,
        "current_volume_id": snapshot.current_volume_id,
        "current_volume_title": snapshot.current_volume_title,
        "translated_segments": snapshot.translated_segments,
        "fallback_segments": snapshot.fallback_segments,
    }


def _export_result_data(result: ExportResult) -> dict[str, Any]:
    data: dict[str, Any] = {
        "target": result.target,
        "scope": result.scope,
        "scope_id": result.scope_id,
        "output_dir": str(result.output_dir),
        "volumes_total": result.volumes_total,
        "volumes_exported": result.volumes_exported,
        "chapters_exported": result.chapters_exported,
        "translated_segments": result.translated_segments,
        "fallback_segments": result.fallback_segments,
        "generated_at": result.generated_at,
        "cancelled": result.cancelled,
        "artifacts": [
            {
                "volume_id": artifact.volume_id,
                "volume_title": artifact.volume_title,
                "source_format": artifact.source_format,
                "output_path": str(artifact.output_path),
                "chapters_exported": artifact.chapters_exported,
                "translated_segments": artifact.translated_segments,
                "fallback_segments": artifact.fallback_segments,
                "fallback_by_status": {
                    "pending": artifact.fallback_by_status.pending,
                    "in_progress": artifact.fallback_by_status.in_progress,
                    "failed": artifact.fallback_by_status.failed,
                    "stale": artifact.fallback_by_status.stale,
                    "skipped": artifact.fallback_by_status.skipped,
                    "untranslated": artifact.fallback_by_status.untranslated,
                },
            }
            for artifact in result.artifacts
        ],
    }
    if result.fidelity_reports:
        data["fidelity_reports"] = [report_to_dict(r) for r in result.fidelity_reports]
    return data


# --- parse jobs (Sprint J3 — reparse-as-Job, ADR 010-adjacent) -------------


@dataclass
class ParseResult:
    """Outcome of a successful EPUB reparse."""

    volume_id: int
    source_hash: str
    parser_version: int
    manifest_count: int
    spine_count: int
    nav_count: int
    image_count: int
    validation_count: int


ParseJobRunner = Callable[[ShouldCancel], ParseResult]


@dataclass
class ParseProgress:
    """Single-unit progress envelope for a parse job (one volume = one unit)."""

    current: int = 0
    total: int = 1


@dataclass
class ParseJob:
    """One background EPUB reparse run, its progress, and terminal state.

    Sibling of :class:`TranslationJob` / :class:`BatchJob` / :class:`ExportJob`:
    same state machine (``running`` → ``done`` | ``failed`` | ``cancelled``),
    same cancel flag + SSE queue + stream-end sentinel. A reparse is logically
    one unit of work (one volume), so ``ParseProgress`` carries just current/total.
    """

    id: str
    project_name: str
    volume_id: int
    runner: ParseJobRunner
    status: str = "running"
    result: ParseResult | None = None
    error: str | None = None
    progress: ParseProgress = field(default_factory=ParseProgress)
    queue: queue.Queue[dict[str, Any] | None] = field(default_factory=queue.Queue)
    storage: JobStorage | None = None
    _cancel: threading.Event = field(default_factory=threading.Event)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _thread: threading.Thread | None = field(default=None, repr=False)

    def request_cancel(self) -> None:
        self._cancel.set()

    def should_cancel(self) -> bool:
        return self._cancel.is_set()

    def snapshot(self) -> ParseProgress:
        with self._lock:
            return ParseProgress(current=self.progress.current, total=self.progress.total)

    def run(self) -> None:
        try:
            self.result = self.runner(self.should_cancel)
        except Exception as exc:  # noqa: BLE001 — web boundary; surfaced, not swallowed
            self.status = "failed"
            self.error = str(exc)
            data = {"message": str(exc)}
            if self.storage is not None:
                self.storage.finish(status="failed", result=None, error_summary=str(exc))
            event_id = self.storage.append_event(event="error", data=data) if self.storage else None
            envelope: dict[str, Any] = {"event": "error", "data": data}
            if event_id is not None:
                envelope["id"] = event_id
            self.queue.put(envelope)
        else:
            result = self.result
            assert result is not None
            self.status = "cancelled" if self.should_cancel() else "done"
            with self._lock:
                self.progress.current = 1
            data = {
                "volume_id": result.volume_id,
                "source_hash": result.source_hash,
                "parser_version": result.parser_version,
                "manifest_count": result.manifest_count,
                "spine_count": result.spine_count,
                "nav_count": result.nav_count,
                "image_count": result.image_count,
                "validation_count": result.validation_count,
                "cancelled": self.status == "cancelled",
            }
            if self.storage is not None:
                self.storage.flush_progress(
                    done_units=1,
                    failed_units=0,
                    total_units=1,
                    force=True,
                )
                self.storage.finish(status=self.status, result=data, error_summary=None)
            event_id = (
                self.storage.append_event(event=self.status, data=data) if self.storage else None
            )
            envelope = {"event": self.status, "data": data}
            if event_id is not None:
                envelope["id"] = event_id
            self.queue.put(envelope)
        finally:
            self.queue.put(_STREAM_END)

    def wait(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout)


class JobRegistry:
    """Thread-safe registry of background translate jobs, keyed by id.

    Chapter jobs (:class:`TranslationJob`) and batch jobs (:class:`BatchJob`)
    live in separate dicts; both key on a globally-unique ``uuid4().hex``, so a
    batch id is never resolvable via :meth:`get` and vice-versa.

    When constructed with a ``base_dir`` (the books directory), every job's
    status, sampled progress, and SSE events are persisted to the owning
    project's ``weaver.db`` via :class:`JobStorage`. When ``base_dir`` is
    ``None`` (tests, ad-hoc registry) jobs run in memory only — the same
    behaviour Sprints 4A/4B shipped.
    """

    def __init__(self, base_dir: Path | None = None) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, TranslationJob] = {}
        self._batch_jobs: dict[str, BatchJob] = {}
        self._export_jobs: dict[str, ExportJob] = {}
        self._parse_jobs: dict[str, ParseJob] = {}
        self._base_dir = base_dir

    @property
    def base_dir(self) -> Path | None:
        return self._base_dir

    def _storage_for(self, project_name: str, job_id: str) -> JobStorage:
        db_path: Path | None = None
        if self._base_dir is not None:
            db_path = db_path_for(self._base_dir, project_name)
        return JobStorage(job_id=job_id, db_path=db_path)

    def submit(
        self,
        *,
        project_name: str,
        chapter_id: str,
        mode: str,
        total: int,
        runner: JobRunner,
    ) -> TranslationJob:
        """Register a job and start its worker thread.

        Args:
            project_name: Owning project (``.weaver/<name>`` directory name).
            chapter_id: Chapter the job translates.
            mode: ``"chapter"`` or ``"selection"``.
            total: Number of segments the job will attempt (seeds progress.total).
            runner: Closure that performs the translation and returns its result.

        Returns:
            The created :class:`TranslationJob` (already running).
        """

        job_id = uuid.uuid4().hex
        storage = self._storage_for(project_name, job_id)
        storage.insert(
            kind=JOB_KIND_TRANSLATE,
            project_name=project_name,
            scope="chapter",
            scope_id=chapter_id,
            chapter_id=chapter_id,
            mode=mode,
            target=None,
            total_units=total,
        )
        job = TranslationJob(
            id=job_id,
            project_name=project_name,
            chapter_id=chapter_id,
            mode=mode,
            runner=runner,
            progress=JobProgress(total=total),
            storage=storage,
        )
        thread = threading.Thread(
            target=job.run,
            name=f"weaver-translate-{job.id}",
            daemon=True,
        )
        job._thread = thread
        with self._lock:
            self._jobs[job.id] = job
        thread.start()
        return job

    def get(self, job_id: str) -> TranslationJob | None:
        """Return the chapter job with ``job_id``, or None when unknown."""

        with self._lock:
            return self._jobs.get(job_id)

    def find_running(self, *, project_name: str, chapter_id: str) -> TranslationJob | None:
        """Return the first running job matching project+chapter, or None.

        Used by the workspace view to re-attach a progress panel after page
        navigation so the user does not accidentally start a second job while
        one is still running.
        """

        with self._lock:
            for job in self._jobs.values():
                if (
                    job.project_name == project_name
                    and job.chapter_id == chapter_id
                    and job.status == "running"
                ):
                    return job
            return None

    def submit_batch(
        self,
        *,
        project_name: str,
        scope: str,
        scope_id: str | None,
        mode: str,
        runner: BatchJobRunner,
    ) -> BatchJob:
        """Register a batch job and start its worker thread.

        Args:
            project_name: Owning project (``.weaver/<name>`` directory name).
            scope: ``"chapter"`` | ``"volume"`` | ``"novel"``.
            scope_id: Chapter or volume id; None for novel scope.
            mode: Overwrite mode applied per chapter.
            runner: Closure that performs the batch and returns its result.

        Returns:
            The created :class:`BatchJob` (already running).
        """

        job_id = uuid.uuid4().hex
        storage = self._storage_for(project_name, job_id)
        storage.insert(
            kind=JOB_KIND_BATCH,
            project_name=project_name,
            scope=scope,
            scope_id=scope_id,
            chapter_id=None,
            mode=mode,
            target=None,
            total_units=0,
        )
        job = BatchJob(
            id=job_id,
            project_name=project_name,
            scope=scope,
            scope_id=scope_id,
            mode=mode,
            runner=runner,
            storage=storage,
        )
        thread = threading.Thread(
            target=job.run,
            name=f"weaver-batch-{job.id}",
            daemon=True,
        )
        job._thread = thread
        with self._lock:
            self._batch_jobs[job.id] = job
        thread.start()
        return job

    def get_batch(self, job_id: str) -> BatchJob | None:
        """Return the batch job with ``job_id``, or None when unknown."""

        with self._lock:
            return self._batch_jobs.get(job_id)

    def submit_export(
        self,
        *,
        project_name: str,
        scope: str,
        scope_id: str | None,
        target: str,
        runner: ExportJobRunner,
    ) -> ExportJob:
        """Register an export job and start its worker thread.

        Args:
            project_name: Owning project (``.weaver/<name>`` directory name).
            scope: ``"novel"`` | ``"volume"`` | ``"chapter"``.
            scope_id: Volume or chapter id; None for novel scope.
            target: Output format (``"epub"``).
            runner: Closure that performs the export and returns its result.

        Returns:
            The created :class:`ExportJob` (already running).
        """

        job_id = uuid.uuid4().hex
        storage = self._storage_for(project_name, job_id)
        storage.insert(
            kind=JOB_KIND_EXPORT,
            project_name=project_name,
            scope=scope,
            scope_id=scope_id,
            chapter_id=None,
            mode=None,
            target=target,
            total_units=0,
        )
        job = ExportJob(
            id=job_id,
            project_name=project_name,
            scope=scope,
            scope_id=scope_id,
            target=target,
            runner=runner,
            storage=storage,
        )
        thread = threading.Thread(
            target=job.run,
            name=f"weaver-export-{job.id}",
            daemon=True,
        )
        job._thread = thread
        with self._lock:
            self._export_jobs[job.id] = job
        thread.start()
        return job

    def get_export(self, job_id: str) -> ExportJob | None:
        """Return the export job with ``job_id``, or None when unknown."""

        with self._lock:
            return self._export_jobs.get(job_id)

    def submit_parse(
        self,
        *,
        project_name: str,
        volume_id: int,
        runner: ParseJobRunner,
    ) -> ParseJob:
        """Register an EPUB-reparse job and start its worker thread (Sprint J3).

        Args:
            project_name: Owning project (``.weaver/<name>`` directory name).
            volume_id: Volume row id whose source EPUB will be reparsed into
                the preservation snapshot.
            runner: Closure that performs the parse and returns its
                :class:`ParseResult`.

        Returns:
            The created :class:`ParseJob` (already running).
        """

        job_id = uuid.uuid4().hex
        storage = self._storage_for(project_name, job_id)
        storage.insert(
            kind=JOB_KIND_PARSE,
            project_name=project_name,
            scope="volume",
            scope_id=str(volume_id),
            chapter_id=None,
            mode=None,
            target=None,
            total_units=1,
        )
        job = ParseJob(
            id=job_id,
            project_name=project_name,
            volume_id=volume_id,
            runner=runner,
            storage=storage,
        )
        thread = threading.Thread(
            target=job.run,
            name=f"weaver-parse-{job.id}",
            daemon=True,
        )
        job._thread = thread
        with self._lock:
            self._parse_jobs[job.id] = job
        thread.start()
        return job

    def get_parse(self, job_id: str) -> ParseJob | None:
        """Return the parse job with ``job_id``, or None when unknown."""

        with self._lock:
            return self._parse_jobs.get(job_id)


def format_sse(event: dict[str, Any]) -> str:
    """Serialize one queue event to a ``text/event-stream`` frame.

    Args:
        event: ``{"event": <name>, "data": <json-serializable dict>, "id"?: int}``.

    Returns:
        An SSE frame with an optional ``id:`` line (used for Last-Event-Id
        resume per Sprint I4 / ADR 010 §SSE resume), an ``event:`` line, a
        ``data:`` line (compact JSON), and the terminating blank line.
    """

    name = str(event["event"])
    payload = json.dumps(event["data"], ensure_ascii=False)
    if "id" in event and event["id"] is not None:
        return f"id: {event['id']}\nevent: {name}\ndata: {payload}\n\n"
    return f"event: {name}\ndata: {payload}\n\n"


def parse_last_event_id(value: str | None) -> int:
    """Parse the ``Last-Event-Id`` header / query value to a positive int.

    Returns ``0`` for missing, empty, or unparseable values — that is, replay
    everything from the beginning. Never raises (a malformed header from a
    reconnecting client should not 500).
    """
    if value is None:
        return 0
    raw = str(value).strip()
    if not raw:
        return 0
    try:
        parsed = int(raw)
    except ValueError:
        return 0
    return parsed if parsed > 0 else 0


def replay_persisted_events(
    db_path: Path | None, job_id: str, *, after_id: int
) -> Iterator[dict[str, Any]]:
    """Yield persisted SSE-event envelopes for ``job_id`` with id > ``after_id``."""
    from weaver.services.job_store import list_events_after  # local import; module-level cycle risk

    if db_path is None:
        return
    try:
        with closing(connect_database(db_path)) as conn:
            for row in list_events_after(conn, job_id=job_id, after_id=after_id):
                yield {"event": row.event, "data": row.data, "id": row.id}
    except (WeaverError, sqlite3.Error) as exc:
        logger.warning("job.replay.failed", extra={"data": {"job_id": job_id, "error": str(exc)}})
