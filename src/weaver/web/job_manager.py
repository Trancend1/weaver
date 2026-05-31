"""In-memory, threaded, single-job translate registry (ADR ``0019``).

One translate job runs at a time, guarded by a global lock. The worker runs in
one ``threading.Thread`` (no asyncio, no broker) and pushes progress events onto
a thread-safe ``queue.Queue``. The SSE route drains the queue to the browser.

Phase 12a shipped the skeleton (start a job, stream progress). Phase 12b adds
cooperative cancel: the stop button sets a flag the runner checks between
segments, so the worker stops cleanly leaving state consistent (ADR ``0019``).
"""

from __future__ import annotations

import json
import queue
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from weaver.services.translation import ProgressCallback, TranslationRunSummary

# A runner is a closure built by the route around ``translate_project``. It
# receives a progress callback and a ``should_cancel`` predicate, and returns the
# run summary. Keeping the registry decoupled from ``translate_project`` makes it
# testable with a fake runner.
ShouldCancel = Callable[[], bool]
JobRunner = Callable[[ProgressCallback, ShouldCancel], TranslationRunSummary]

# Sentinel pushed onto the queue when the worker thread finishes (any outcome),
# so the SSE generator knows to stop draining.
_STREAM_END: None = None


@dataclass
class TranslationJob:
    """One translate run and its live progress queue.

    Mutable on purpose: ``status`` is a small state machine
    (``running`` → ``done`` | ``cancelled`` | ``error``) driven by the worker
    thread. ``_cancel`` is set from another thread by the stop route; the runner
    polls :meth:`should_cancel` between segments.
    """

    project_name: str
    runner: JobRunner
    queue: queue.Queue[dict[str, Any] | None] = field(default_factory=queue.Queue)
    status: str = "running"
    summary: TranslationRunSummary | None = None
    error_message: str | None = None
    _cancel: threading.Event = field(default_factory=threading.Event)

    def request_cancel(self) -> None:
        """Signal the worker to stop after the current segment (idempotent)."""

        self._cancel.set()

    def should_cancel(self) -> bool:
        """True once :meth:`request_cancel` has been called."""

        return self._cancel.is_set()

    def run(self) -> None:
        """Execute the runner on the worker thread, emitting queue events.

        Emits ``progress`` per segment, then exactly one terminal event
        (``done`` or ``error``), then the stream-end sentinel. The broad
        ``except`` is the web boundary analogue of the CLI boundary
        (CLAUDE.md §4.2): an unhandled worker-thread exception would vanish
        silently, so it is surfaced to the browser as an ``error`` event.
        """

        def on_progress(
            index: int,
            total: int,
            segment: Any,
            translated: bool,
            input_tokens: int | None,
            output_tokens: int | None,
        ) -> None:
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

        try:
            summary = self.runner(on_progress, self.should_cancel)
        except Exception as exc:  # noqa: BLE001 - web boundary; surfaced, not swallowed
            self.status = "error"
            self.error_message = str(exc)
            self.queue.put({"event": "error", "data": {"message": str(exc)}})
        else:
            self.summary = summary
            self.status = "cancelled" if self.should_cancel() else "done"
            self.queue.put(
                {
                    "event": "done",
                    "data": {
                        "selected": summary.selected_segments,
                        "translated": summary.translated_segments,
                        "reused_from_memory": summary.reused_from_memory,
                        "failed": summary.failed_segments,
                        "pending": summary.pending_segments,
                        "stale": summary.stale_segments,
                        "input_tokens": summary.input_tokens,
                        "output_tokens": summary.output_tokens,
                        "cancelled": self.should_cancel(),
                    },
                }
            )
        finally:
            self.queue.put(_STREAM_END)


class JobManager:
    """Single-job registry. One translate job at a time, no queue."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._job: TranslationJob | None = None

    def start(self, project_name: str, runner: JobRunner) -> TranslationJob | None:
        """Start a translate job unless one is already running.

        Args:
            project_name: ``.weaver/<name>`` directory name of the target.
            runner: Closure that runs the translation given a progress callback.

        Returns:
            The new TranslationJob, or None when a job is already running (the
            caller should reject with a clear message + link to the running
            job, per ADR ``0019``).
        """

        with self._lock:
            if self._job is not None and self._job.status == "running":
                return None
            job = TranslationJob(project_name=project_name, runner=runner)
            self._job = job
        thread = threading.Thread(
            target=job.run,
            name=f"weaver-translate-{project_name}",
            daemon=True,
        )
        thread.start()
        return job

    @property
    def current(self) -> TranslationJob | None:
        """The most recently started job, if any."""

        return self._job

    def is_running(self) -> bool:
        """True when a job is currently in the ``running`` state."""

        return self._job is not None and self._job.status == "running"

    def request_cancel(self, project_name: str) -> bool:
        """Request cancel of the running job for ``project_name``.

        Returns:
            True when a matching running job was signalled; False when no job is
            running or it belongs to a different project.
        """

        job = self._job
        if job is None or job.project_name != project_name or job.status != "running":
            return False
        job.request_cancel()
        return True


def format_sse(event: dict[str, Any]) -> str:
    """Serialize one queue event to a ``text/event-stream`` frame.

    Args:
        event: ``{"event": <name>, "data": <json-serializable dict>}``.

    Returns:
        An SSE frame: an ``event:`` line, a ``data:`` line (compact JSON), and
        the terminating blank line.
    """

    name = str(event["event"])
    payload = json.dumps(event["data"], ensure_ascii=False)
    return f"event: {name}\ndata: {payload}\n\n"
