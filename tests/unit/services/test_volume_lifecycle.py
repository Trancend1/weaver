"""Tests for ``services.volume_lifecycle`` (Sprint H2 — derived-first)."""

from __future__ import annotations

from typing import cast

import pytest

from weaver.services.volume_lifecycle import VolumeStatus, derive_volume_status


class _FakeJobs:
    """Stand-in for ``JobRegistry`` that returns ``running`` for selected chapter ids."""

    def __init__(self, running_chapter_ids: set[str]) -> None:
        self._running = running_chapter_ids

    def find_running(self, *, project_name: str, chapter_id: str):  # noqa: ARG002
        return object() if chapter_id in self._running else None


def _derive(
    *,
    segment_count: int,
    done_count: int,
    chapter_ids: tuple[str, ...] = ("c1",),
    running: tuple[str, ...] = (),
) -> VolumeStatus:
    jobs = _FakeJobs(set(running)) if running else None
    view = derive_volume_status(
        segment_count=segment_count,
        done_count=done_count,
        chapter_ids=chapter_ids,
        project_name="any-project",
        jobs=cast(object, jobs),  # type: ignore[arg-type]
    )
    return view.status


def test_empty_volume_reports_empty() -> None:
    assert _derive(segment_count=0, done_count=0) == "empty"


def test_imported_when_nothing_translated_yet() -> None:
    assert _derive(segment_count=42, done_count=0) == "imported"


def test_in_progress_when_partially_done() -> None:
    assert _derive(segment_count=42, done_count=10) == "in_progress"


def test_translated_when_all_done() -> None:
    assert _derive(segment_count=42, done_count=42) == "translated"


def test_translated_when_done_count_overshoots() -> None:
    # Defensive: a future bug in counting should still report translated, not
    # silently flip to in_progress.
    assert _derive(segment_count=42, done_count=99) == "translated"


def test_translating_overlay_supersedes_imported() -> None:
    assert (
        _derive(
            segment_count=42,
            done_count=0,
            chapter_ids=("c1", "c2"),
            running=("c2",),
        )
        == "translating"
    )


def test_translating_overlay_supersedes_in_progress() -> None:
    assert (
        _derive(
            segment_count=42,
            done_count=10,
            chapter_ids=("c1",),
            running=("c1",),
        )
        == "translating"
    )


def test_translating_overlay_supersedes_translated() -> None:
    assert (
        _derive(
            segment_count=42,
            done_count=42,
            chapter_ids=("c1",),
            running=("c1",),
        )
        == "translating"
    )


def test_no_jobs_argument_returns_static_status() -> None:
    view = derive_volume_status(
        segment_count=10,
        done_count=10,
        chapter_ids=("c1",),
        project_name="any",
        jobs=None,
    )
    assert view.status == "translated"
    assert view.label == "translated"


def test_view_is_terminal_for_static_states() -> None:
    static_terminal: list[VolumeStatus] = ["empty", "imported", "translated"]
    for status in static_terminal:
        view = (
            derive_volume_status(
                segment_count=10,
                done_count=10 if status == "translated" else 0,
                chapter_ids=(),
                project_name="any",
                jobs=None,
            )
            if status != "empty"
            else derive_volume_status(
                segment_count=0,
                done_count=0,
                chapter_ids=(),
                project_name="any",
                jobs=None,
            )
        )
        assert view.is_terminal is True, f"{status} should be terminal"


@pytest.mark.parametrize(
    ("status", "running"),
    [
        ("in_progress", False),
        ("translating", True),
    ],
)
def test_view_is_terminal_false_for_in_motion_states(status: str, running: bool) -> None:
    view = derive_volume_status(
        segment_count=10,
        done_count=5,
        chapter_ids=("c1",),
        project_name="any",
        jobs=_FakeJobs({"c1"}) if running else None,  # type: ignore[arg-type]
    )
    assert view.status == status
    assert view.is_terminal is False
