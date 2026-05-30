"""In-memory background translation jobs for the FastAPI cockpit (Sprint 4A).

A small thread-backed registry: a translate request submits a runner, the runner
executes on one daemon thread, and the job's terminal state (``done`` / ``failed``)
plus result are read back by job id. This is the foundation only — live per-segment
progress, an SSE stream, and a cancel endpoint arrive in Stage 4B.

Stdlib + shared service types only; no FastAPI or Flask imports so the registry
stays trivially testable and framework-agnostic (ADR 004).
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from weaver.services.workspace_translate import ChapterTranslationResult

# A runner is a closure built by the route around ``run_translation``. It takes no
# arguments and returns the run result; keeping the registry decoupled from the
# translation service makes it testable with a fake runner.
JobRunner = Callable[[], ChapterTranslationResult]


@dataclass
class TranslationJob:
    """One background translate run and its terminal state.

    ``status`` is a small state machine driven by the worker thread:
    ``running`` → ``done`` | ``failed``.
    """

    id: str
    project_name: str
    chapter_id: str
    mode: str  # "chapter" | "selection"
    runner: JobRunner
    status: str = "running"
    result: ChapterTranslationResult | None = None
    error: str | None = None
    _thread: threading.Thread | None = field(default=None, repr=False)

    def run(self) -> None:
        """Execute the runner on the worker thread, capturing the outcome.

        The broad ``except`` is the web-boundary analogue of the CLI boundary
        (CLAUDE.md §4.2): an unhandled worker-thread exception would vanish
        silently, so it is surfaced on the job as a ``failed`` status with the
        message, not swallowed.
        """

        try:
            self.result = self.runner()
        except Exception as exc:  # noqa: BLE001 - web boundary; surfaced, not swallowed
            self.status = "failed"
            self.error = str(exc)
        else:
            self.status = "done"

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
        self, *, project_name: str, chapter_id: str, mode: str, runner: JobRunner
    ) -> TranslationJob:
        """Register a job and start its worker thread.

        Args:
            project_name: Owning project (``.weaver/<name>`` directory name).
            chapter_id: Chapter the job translates.
            mode: ``"chapter"`` or ``"selection"``.
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
