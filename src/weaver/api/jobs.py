"""In-memory background translation jobs for the FastAPI cockpit (Sprint 4A/4B).

A translate request submits a runner; the runner executes on one daemon thread,
reporting per-segment progress and honouring a cooperative cancel flag. The job's
live progress, terminal state, and result are read back by job id, and progress
events can be streamed as Server-Sent Events.

# JobRegistry is temporary infrastructure.
# Do not build Celery, Redis, RabbitMQ, Kafka, Dramatiq, RQ, or distributed workers.
# Single-process thread worker only.

Stdlib + shared service types only; no FastAPI imports so the registry
stays trivially testable and framework-agnostic (ADR 004).
"""

from __future__ import annotations

import json
import queue
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from weaver.services.batch_translate import (
    BatchProgressCallback,
    BatchProgressSnapshot,
    BatchTranslationResult,
)
from weaver.services.export_book import (
    ExportProgressCallback,
    ExportProgressSnapshot,
    ExportResult,
)
from weaver.services.translation import ProgressCallback
from weaver.services.workspace_translate import ChapterTranslationResult
from weaver.storage.segments import SegmentRecord

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
    _cancel: threading.Event = field(default_factory=threading.Event)
    _lock: threading.Lock = field(default_factory=threading.Lock)
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
        self.queue.put(
            {
                "event": "progress",
                "data": {
                    "current": index,
                    "total": total,
                    "segment_id": segment.id,
                    "status": "translated" if translated else "failed",
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                },
            }
        )

    def run(self) -> None:
        """Execute the runner on the worker thread, emitting queue events.

        Emits ``progress`` per segment (via :meth:`on_progress`), then exactly one
        terminal event (``done`` | ``cancelled`` | ``error``), then the stream-end
        sentinel. The broad ``except`` is the web-boundary analogue of the CLI
        boundary (CLAUDE.md §4.2): an unhandled worker-thread exception would
        vanish silently, so it is surfaced — on the job and on the stream — not
        swallowed.
        """

        try:
            self.result = self.runner(self.should_cancel, self.on_progress)
        except Exception as exc:  # noqa: BLE001 - web boundary; surfaced, not swallowed
            self.status = "failed"
            self.error = str(exc)
            self.queue.put({"event": "error", "data": {"message": str(exc)}})
        else:
            self.status = "cancelled" if self.should_cancel() else "done"
            result = self.result
            self.queue.put(
                {
                    "event": self.status,
                    "data": {
                        "selected": result.selected,
                        "translated": result.translated,
                        "reused_from_memory": result.reused_from_memory,
                        "failed": result.failed,
                        "skipped": result.skipped,
                        "input_tokens": result.input_tokens,
                        "output_tokens": result.output_tokens,
                        "cancelled": result.cancelled,
                    },
                }
            )
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
        self.queue.put({"event": "progress", "data": _batch_progress_data(snapshot)})

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
            self.queue.put({"event": "error", "data": {"message": str(exc)}})
        else:
            result = self.result
            self.status = "cancelled" if result.cancelled else "done"
            self.queue.put({"event": self.status, "data": _batch_result_data(result)})
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
        self.queue.put({"event": "progress", "data": _export_progress_data(snapshot)})

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
            self.queue.put({"event": "error", "data": {"message": str(exc)}})
        else:
            result = self.result
            self.status = "cancelled" if result.cancelled else "done"
            self.queue.put({"event": self.status, "data": _export_result_data(result)})
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
    return {
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


class JobRegistry:
    """Thread-safe registry of background translate jobs, keyed by id.

    Chapter jobs (:class:`TranslationJob`) and batch jobs (:class:`BatchJob`)
    live in separate dicts; both key on a globally-unique ``uuid4().hex``, so a
    batch id is never resolvable via :meth:`get` and vice-versa.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, TranslationJob] = {}
        self._batch_jobs: dict[str, BatchJob] = {}
        self._export_jobs: dict[str, ExportJob] = {}

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

        job = TranslationJob(
            id=uuid.uuid4().hex,
            project_name=project_name,
            chapter_id=chapter_id,
            mode=mode,
            runner=runner,
            progress=JobProgress(total=total),
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

        job = BatchJob(
            id=uuid.uuid4().hex,
            project_name=project_name,
            scope=scope,
            scope_id=scope_id,
            mode=mode,
            runner=runner,
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

        job = ExportJob(
            id=uuid.uuid4().hex,
            project_name=project_name,
            scope=scope,
            scope_id=scope_id,
            target=target,
            runner=runner,
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


def format_sse(event: dict[str, Any]) -> str:
    """Serialize one queue event to a ``text/event-stream`` frame.

    Args:
        event: ``{"event": <name>, "data": <json-serializable dict>}``.

    Returns:
        An SSE frame: an ``event:`` line, a ``data:`` line (compact JSON), and the
        terminating blank line.
    """

    name = str(event["event"])
    payload = json.dumps(event["data"], ensure_ascii=False)
    return f"event: {name}\ndata: {payload}\n\n"
