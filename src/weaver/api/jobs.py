"""In-memory background translation jobs for the FastAPI cockpit (Sprint 4A/4B).

A translate request submits a runner; the runner executes on one daemon thread,
reporting per-segment progress and honouring a cooperative cancel flag. The job's
live progress, terminal state, and result are read back by job id, and progress
events can be streamed as Server-Sent Events.

# JobRegistry is temporary infrastructure.
# Do not build Celery, Redis, RabbitMQ, Kafka, Dramatiq, RQ, or distributed workers.
# Single-process thread worker only.

Stdlib + shared service types only; no FastAPI or Flask imports so the registry
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

from weaver.services.translation import ProgressCallback
from weaver.services.workspace_translate import ChapterTranslationResult
from weaver.storage.segments import SegmentRecord

# A runner is a closure built by the route around ``run_translation``. It receives
# a cooperative cancel predicate and a progress callback, and returns the run
# result; keeping the registry decoupled from the translation service makes it
# testable with a fake runner.
ShouldCancel = Callable[[], bool]
JobRunner = Callable[[ShouldCancel, ProgressCallback], ChapterTranslationResult]

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


class JobRegistry:
    """Thread-safe registry of background translate jobs, keyed by id."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, TranslationJob] = {}

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
        """Return the job with ``job_id``, or None when unknown."""

        with self._lock:
            return self._jobs.get(job_id)


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
