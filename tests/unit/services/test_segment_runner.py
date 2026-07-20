"""Bounded-window segment runner (ADR 020)."""

from __future__ import annotations

import threading

from weaver.services.segment_runner import run_segment_window


def test_sequential_window_visits_every_item_in_order() -> None:
    seen: list[int] = []

    def work(connection: object, item: int) -> str:
        seen.append(item)
        return f"done-{item}"

    completed: list[tuple[int, int, int, str]] = []

    run_segment_window(
        items=[1, 2, 3],
        max_concurrent=1,
        connection_factory=lambda: object(),
        work=work,
        on_complete=lambda ordinal, total, item, result: completed.append(
            (ordinal, total, item, result)
        ),
    )

    assert seen == [1, 2, 3]
    assert [c[0] for c in completed] == [1, 2, 3]
    assert [c[1] for c in completed] == [3, 3, 3]
    assert [c[2] for c in completed] == [1, 2, 3]


def test_sequential_window_opens_one_connection() -> None:
    opened: list[object] = []

    def factory() -> object:
        connection = object()
        opened.append(connection)
        return connection

    run_segment_window(
        items=[1, 2, 3],
        max_concurrent=1,
        connection_factory=factory,
        work=lambda connection, item: item,
        on_complete=lambda ordinal, total, item, result: None,
    )

    assert len(opened) == 1


def test_cancellation_stops_dispatch() -> None:
    seen: list[int] = []
    cancel = threading.Event()

    def work(connection: object, item: int) -> int:
        seen.append(item)
        if item == 2:
            cancel.set()
        return item

    cancelled = run_segment_window(
        items=[1, 2, 3, 4, 5],
        max_concurrent=1,
        connection_factory=lambda: object(),
        work=work,
        on_complete=lambda ordinal, total, item, result: None,
        should_cancel=cancel.is_set,
    )

    assert cancelled is True
    assert seen == [1, 2]


def test_no_cancellation_reports_false() -> None:
    cancelled = run_segment_window(
        items=[1, 2],
        max_concurrent=1,
        connection_factory=lambda: object(),
        work=lambda connection, item: item,
        on_complete=lambda ordinal, total, item, result: None,
    )
    assert cancelled is False


def test_connection_is_closed_after_run() -> None:
    class Recorder:
        def __init__(self) -> None:
            self.closed = False

        def close(self) -> None:
            self.closed = True

    recorder = Recorder()
    run_segment_window(
        items=[1],
        max_concurrent=1,
        connection_factory=lambda: recorder,
        work=lambda connection, item: item,
        on_complete=lambda ordinal, total, item, result: None,
    )
    assert recorder.closed is True
