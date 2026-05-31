"""Tests for the in-memory background translation job registry (Sprint 4A/4B)."""

from __future__ import annotations

import queue
import threading
import time
from typing import Any

import pytest

from weaver.api.jobs import JobRegistry
from weaver.services.workspace_translate import ChapterTranslationResult
from weaver.storage.segments import SegmentRecord


def _result(translated: int = 2, cancelled: bool = False) -> ChapterTranslationResult:
    return ChapterTranslationResult(
        chapter_id="ch-1",
        selected=2,
        translated=translated,
        reused_from_memory=0,
        failed=0,
        skipped=0,
        input_tokens=20,
        output_tokens=10,
        cancelled=cancelled,
    )


def _segment() -> SegmentRecord:
    return SegmentRecord(
        id="seg-1",
        chapter_id="ch-1",
        block_order=0,
        kind="paragraph",
        source_text="x",
        source_hash="h",
        status="pending",
    )


def _drain(q: queue.Queue[dict[str, Any] | None]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    while True:
        event = q.get(timeout=5)
        if event is None:
            break
        events.append(event)
    return events


def _submit(registry: JobRegistry, runner, *, total: int = 2):
    return registry.submit(
        project_name="demo", chapter_id="ch-1", mode="chapter", total=total, runner=runner
    )


def test_submit_runs_runner_to_done_with_result() -> None:
    registry = JobRegistry()
    job = _submit(registry, lambda should_cancel, on_progress: _result())
    job.wait(timeout=5)

    assert job.status == "done"
    assert job.result == _result()
    assert job.error is None
    assert registry.get(job.id) is job


def test_failing_runner_marks_job_failed_and_emits_error_event() -> None:
    registry = JobRegistry()

    def boom(should_cancel, on_progress) -> ChapterTranslationResult:
        raise RuntimeError("kaboom")

    job = _submit(registry, boom)
    job.wait(timeout=5)

    assert job.status == "failed"
    assert job.result is None
    assert job.error == "kaboom"
    assert [e["event"] for e in _drain(job.queue)] == ["error"]


def test_get_unknown_job_returns_none() -> None:
    assert JobRegistry().get("nope") is None


def test_submit_seeds_progress_total() -> None:
    registry = JobRegistry()
    job = _submit(registry, lambda should_cancel, on_progress: _result(), total=7)
    job.wait(timeout=5)

    assert job.snapshot().total == 7


def test_on_progress_updates_snapshot_and_emits_progress_events() -> None:
    registry = JobRegistry()
    segment = _segment()

    def runner(should_cancel, on_progress) -> ChapterTranslationResult:
        on_progress(1, 2, segment, True, 5, 3)
        on_progress(2, 2, segment, False, None, None)
        return _result(translated=1)

    job = _submit(registry, runner)
    job.wait(timeout=5)

    snap = job.snapshot()
    assert (snap.current, snap.total, snap.translated, snap.failed) == (2, 2, 1, 1)
    assert [e["event"] for e in _drain(job.queue)] == ["progress", "progress", "done"]


def test_request_cancel_stops_runner_and_marks_cancelled() -> None:
    registry = JobRegistry()
    started = threading.Event()

    def runner(should_cancel, on_progress) -> ChapterTranslationResult:
        started.set()
        while not should_cancel():
            time.sleep(0.01)
        return _result(translated=1, cancelled=True)

    job = _submit(registry, runner)
    assert started.wait(timeout=5)
    job.request_cancel()
    job.wait(timeout=5)

    assert job.status == "cancelled"
    assert [e["event"] for e in _drain(job.queue)] == ["cancelled"]


@pytest.mark.parametrize("mode", ["chapter", "selection"])
def test_submit_records_mode_and_chapter(mode: str) -> None:
    registry = JobRegistry()
    job = registry.submit(
        project_name="demo",
        chapter_id="ch-9",
        mode=mode,
        total=1,
        runner=lambda should_cancel, on_progress: _result(),
    )
    job.wait(timeout=5)

    assert job.mode == mode
    assert job.chapter_id == "ch-9"
    assert job.project_name == "demo"
