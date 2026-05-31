"""Unit tests for the JobManager registry and SSE formatting (Phase 12a)."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass

from weaver.services.translation import TranslationRunSummary
from weaver.web.job_manager import JobManager, format_sse

# Loose alias: the progress callback only reads ``segment.id``, so tests pass a
# minimal fake rather than constructing a full SegmentRecord.
_Callback = Callable[..., None]
_Cancel = Callable[[], bool]


@dataclass
class _FakeSegment:
    id: str


def _summary() -> TranslationRunSummary:
    return TranslationRunSummary(
        total_segments=2,
        selected_segments=2,
        translated_segments=2,
        reused_from_memory=0,
        failed_segments=0,
        pending_segments=0,
        stale_segments=0,
        input_tokens=10,
        output_tokens=8,
    )


def _drain(job) -> list[dict]:
    events: list[dict] = []
    while True:
        event = job.queue.get(timeout=5)
        if event is None:
            break
        events.append(event)
    return events


def test_start_runs_and_emits_progress_then_done() -> None:
    manager = JobManager()

    def runner(progress_callback: _Callback, should_cancel: _Cancel) -> TranslationRunSummary:
        progress_callback(1, 2, _FakeSegment("seg-1"), True, 5, 4)
        progress_callback(2, 2, _FakeSegment("seg-2"), True, 5, 4)
        return _summary()

    job = manager.start("novel", runner)
    assert job is not None

    events = _drain(job)

    kinds = [e["event"] for e in events]
    assert kinds == ["progress", "progress", "done"]
    assert events[0]["data"]["segment_id"] == "seg-1"
    assert events[-1]["data"]["translated"] == 2
    assert job.status == "done"


def test_second_start_rejected_while_running() -> None:
    manager = JobManager()
    release = threading.Event()

    def blocking_runner(
        progress_callback: _Callback, should_cancel: _Cancel
    ) -> TranslationRunSummary:
        release.wait(timeout=5)
        return _summary()

    first = manager.start("novel", blocking_runner)
    assert first is not None
    assert manager.is_running() is True

    second = manager.start("other", lambda cb, sc: _summary())
    assert second is None  # one job at a time

    release.set()
    _drain(first)
    assert manager.is_running() is False


def test_runner_exception_emits_error_event() -> None:
    manager = JobManager()

    def failing_runner(
        progress_callback: _Callback, should_cancel: _Cancel
    ) -> TranslationRunSummary:
        raise RuntimeError("provider exploded")

    job = manager.start("novel", failing_runner)
    assert job is not None

    events = _drain(job)

    assert [e["event"] for e in events] == ["error"]
    assert events[0]["data"]["message"] == "provider exploded"
    assert job.status == "error"


def test_request_cancel_sets_flag_and_marks_cancelled() -> None:
    manager = JobManager()
    started = threading.Event()
    release = threading.Event()
    observed: dict[str, bool] = {}

    def runner(progress_callback: _Callback, should_cancel: _Cancel) -> TranslationRunSummary:
        started.set()
        release.wait(timeout=5)
        observed["cancelled"] = should_cancel()
        return _summary()

    job = manager.start("novel", runner)
    assert job is not None
    assert started.wait(timeout=5)

    assert manager.request_cancel("novel") is True
    release.set()

    events = _drain(job)
    assert observed["cancelled"] is True
    assert job.status == "cancelled"
    assert events[-1]["event"] == "done"
    assert events[-1]["data"]["cancelled"] is True


def test_request_cancel_wrong_project_is_noop() -> None:
    manager = JobManager()
    release = threading.Event()

    def runner(progress_callback: _Callback, should_cancel: _Cancel) -> TranslationRunSummary:
        release.wait(timeout=5)
        return _summary()

    job = manager.start("novel", runner)
    assert job is not None
    assert manager.request_cancel("other") is False
    release.set()
    _drain(job)
    assert job.status == "done"


def test_format_sse_frame() -> None:
    frame = format_sse({"event": "progress", "data": {"current": 1, "total": 3}})
    assert frame == 'event: progress\ndata: {"current": 1, "total": 3}\n\n'
