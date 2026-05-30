"""Tests for the in-memory background translation job registry (Sprint 4A)."""

from __future__ import annotations

import pytest

from weaver.api.jobs import JobRegistry
from weaver.services.workspace_translate import ChapterTranslationResult


def _result() -> ChapterTranslationResult:
    return ChapterTranslationResult(
        chapter_id="ch-1",
        selected=2,
        translated=2,
        failed=0,
        skipped=0,
        input_tokens=20,
        output_tokens=10,
        cancelled=False,
    )


def test_submit_runs_runner_to_done_with_result() -> None:
    registry = JobRegistry()
    job = registry.submit(
        project_name="demo", chapter_id="ch-1", mode="chapter", runner=_result
    )
    job.wait(timeout=5)

    assert job.status == "done"
    assert job.result == _result()
    assert job.error is None
    assert registry.get(job.id) is job


def test_failing_runner_marks_job_failed() -> None:
    registry = JobRegistry()

    def boom() -> ChapterTranslationResult:
        raise RuntimeError("kaboom")

    job = registry.submit(project_name="demo", chapter_id="ch-1", mode="chapter", runner=boom)
    job.wait(timeout=5)

    assert job.status == "failed"
    assert job.result is None
    assert job.error == "kaboom"


def test_get_unknown_job_returns_none() -> None:
    assert JobRegistry().get("nope") is None


@pytest.mark.parametrize("mode", ["chapter", "selection"])
def test_submit_records_mode_and_chapter(mode: str) -> None:
    registry = JobRegistry()
    job = registry.submit(project_name="demo", chapter_id="ch-9", mode=mode, runner=_result)
    job.wait(timeout=5)

    assert job.mode == mode
    assert job.chapter_id == "ch-9"
    assert job.project_name == "demo"
