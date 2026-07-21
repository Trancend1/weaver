"""Bounded-window segment runner (ADR 020)."""

from __future__ import annotations

import logging
import threading
import time

import pytest

from weaver.services.segment_runner import run_segment_window


class _FakeConnection:
    """Minimal closeable double standing in for a sqlite3.Connection."""

    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_sequential_window_visits_every_item_in_order() -> None:
    seen: list[int] = []

    def work(connection: _FakeConnection, item: int) -> str:
        seen.append(item)
        return f"done-{item}"

    completed: list[tuple[int, int, int, str]] = []

    run_segment_window(
        items=[1, 2, 3],
        max_concurrent=1,
        connection_factory=_FakeConnection,
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
    opened: list[_FakeConnection] = []

    def factory() -> _FakeConnection:
        connection = _FakeConnection()
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
    completed: list[tuple[int, int]] = []
    cancel = threading.Event()

    def work(connection: _FakeConnection, item: int) -> int:
        seen.append(item)
        if item == 2:
            cancel.set()
        return item

    cancelled = run_segment_window(
        items=[1, 2, 3, 4, 5],
        max_concurrent=1,
        connection_factory=_FakeConnection,
        work=work,
        on_complete=lambda ordinal, total, item, result: completed.append((ordinal, item)),
        should_cancel=cancel.is_set,
    )

    assert cancelled is True
    assert seen == [1, 2]
    assert completed == [(1, 1), (2, 2)]


def test_no_cancellation_reports_false() -> None:
    cancelled = run_segment_window(
        items=[1, 2],
        max_concurrent=1,
        connection_factory=_FakeConnection,
        work=lambda connection, item: item,
        on_complete=lambda ordinal, total, item, result: None,
    )
    assert cancelled is False


def test_connection_is_closed_after_run() -> None:
    connection = _FakeConnection()
    run_segment_window(
        items=[1],
        max_concurrent=1,
        connection_factory=lambda: connection,
        work=lambda connection, item: item,
        on_complete=lambda ordinal, total, item, result: None,
    )
    assert connection.closed is True


def test_connection_is_closed_when_work_raises() -> None:
    connection = _FakeConnection()

    def work(conn: _FakeConnection, item: int) -> int:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        run_segment_window(
            items=[1],
            max_concurrent=1,
            connection_factory=lambda: connection,
            work=work,
            on_complete=lambda ordinal, total, item, result: None,
        )

    assert connection.closed is True


def test_connection_is_closed_when_on_complete_raises() -> None:
    connection = _FakeConnection()

    def on_complete(ordinal: int, total: int, item: int, result: int) -> None:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        run_segment_window(
            items=[1],
            max_concurrent=1,
            connection_factory=lambda: connection,
            work=lambda conn, item: item,
            on_complete=on_complete,
        )

    assert connection.closed is True


def test_concurrent_window_opens_one_connection_per_worker() -> None:
    opened: list[_FakeConnection] = []
    lock = threading.Lock()

    def factory() -> _FakeConnection:
        connection = _FakeConnection()
        with lock:
            opened.append(connection)
        return connection

    def work(connection: _FakeConnection, item: int) -> int:
        # Load-bearing: connections are opened lazily, on a worker's first
        # dispatched item. Without the delay one worker could drain all 12 items
        # before the others are scheduled, and fewer than 3 would ever open one.
        time.sleep(0.02)
        return item

    run_segment_window(
        items=list(range(12)),
        max_concurrent=3,
        connection_factory=factory,
        work=work,
        on_complete=lambda ordinal, total, item, result: None,
    )

    assert len(opened) == 3
    assert all(connection.closed for connection in opened)


def test_concurrent_window_processes_every_item() -> None:
    seen: list[int] = []
    lock = threading.Lock()

    def work(connection: _FakeConnection, item: int) -> int:
        time.sleep(0.01)
        with lock:
            seen.append(item)
        return item

    run_segment_window(
        items=list(range(20)),
        max_concurrent=4,
        connection_factory=_FakeConnection,
        work=work,
        on_complete=lambda ordinal, total, item, result: None,
    )

    assert sorted(seen) == list(range(20))


def test_completion_ordinals_are_dense_and_serialized() -> None:
    ordinals: list[int] = []
    concurrent_entries = 0
    max_concurrent_entries = 0
    lock = threading.Lock()

    def on_complete(ordinal: int, total: int, item: int, result: int) -> None:
        nonlocal concurrent_entries, max_concurrent_entries
        with lock:
            concurrent_entries += 1
            max_concurrent_entries = max(max_concurrent_entries, concurrent_entries)
        ordinals.append(ordinal)
        time.sleep(0.001)
        with lock:
            concurrent_entries -= 1

    run_segment_window(
        items=list(range(20)),
        max_concurrent=4,
        connection_factory=_FakeConnection,
        work=lambda connection, item: item,
        on_complete=on_complete,
    )

    assert sorted(ordinals) == list(range(1, 21))
    assert max_concurrent_entries == 1


def test_concurrent_window_actually_overlaps() -> None:
    def work(connection: _FakeConnection, item: int) -> int:
        time.sleep(0.05)
        return item

    start = time.perf_counter()
    run_segment_window(
        items=list(range(8)),
        max_concurrent=4,
        connection_factory=_FakeConnection,
        work=work,
        on_complete=lambda ordinal, total, item, result: None,
    )
    elapsed = time.perf_counter() - start

    # 8 items x 50 ms sequential = 400 ms; 4 workers should land near 100 ms.
    assert elapsed < 0.25


def test_concurrent_cancellation_stops_dispatch() -> None:
    seen: list[int] = []
    lock = threading.Lock()
    cancel = threading.Event()

    def work(connection: _FakeConnection, item: int) -> int:
        with lock:
            seen.append(item)
        if item == 1:
            cancel.set()
        return item

    cancelled = run_segment_window(
        items=list(range(50)),
        max_concurrent=2,
        connection_factory=_FakeConnection,
        work=work,
        on_complete=lambda ordinal, total, item, result: None,
        should_cancel=cancel.is_set,
    )

    assert cancelled is True
    assert len(seen) < 50


def test_worker_exception_propagates_and_closes_connections() -> None:
    opened: list[_FakeConnection] = []
    lock = threading.Lock()

    def factory() -> _FakeConnection:
        connection = _FakeConnection()
        with lock:
            opened.append(connection)
        return connection

    def work(connection: _FakeConnection, item: int) -> int:
        if item == 3:
            raise RuntimeError("boom")
        return item

    with pytest.raises(RuntimeError, match="boom"):
        run_segment_window(
            items=list(range(10)),
            max_concurrent=2,
            connection_factory=factory,
            work=work,
            on_complete=lambda ordinal, total, item, result: None,
        )

    assert all(connection.closed for connection in opened)


def test_connection_factory_failure_propagates_when_every_open_fails() -> None:
    """A run where no work happened must raise, never return a clean summary."""
    attempts: list[int] = []
    lock = threading.Lock()

    def factory() -> _FakeConnection:
        with lock:
            attempts.append(1)
        raise RuntimeError("cannot open database")

    processed: list[int] = []

    def work(connection: _FakeConnection, item: int) -> int:
        with lock:
            processed.append(item)
        return item

    with pytest.raises(RuntimeError, match="cannot open database"):
        run_segment_window(
            items=list(range(10)),
            max_concurrent=3,
            connection_factory=factory,
            work=work,
            on_complete=lambda ordinal, total, item, result: None,
        )

    assert processed == []
    # Every worker retires after its own failed open instead of re-failing on
    # each dequeued item.
    assert len(attempts) == 3


def test_partial_connection_factory_failure_propagates_and_closes_the_rest() -> None:
    """A window that silently shrinks is still a failure the caller must see."""
    opened: list[_FakeConnection] = []
    lock = threading.Lock()
    calls = 0

    def factory() -> _FakeConnection:
        nonlocal calls
        with lock:
            calls += 1
            index = calls
        if index == 1:
            raise RuntimeError("cannot open database")
        connection = _FakeConnection()
        with lock:
            opened.append(connection)
        return connection

    processed: list[int] = []

    def work(connection: _FakeConnection, item: int) -> int:
        time.sleep(0.01)
        with lock:
            processed.append(item)
        return item

    with pytest.raises(RuntimeError, match="cannot open database"):
        run_segment_window(
            items=list(range(12)),
            max_concurrent=3,
            connection_factory=factory,
            work=work,
            on_complete=lambda ordinal, total, item, result: None,
        )

    # The surviving workers drain the rest of the queue and still close cleanly.
    assert opened
    assert all(connection.closed for connection in opened)
    assert len(processed) == 12 - 1


def test_earliest_dispatched_failure_wins_over_earlier_wall_clock_failure() -> None:
    """Index-addressed failure slots, not append order, decide what is re-raised.

    Item 0 is dispatched first but raises LAST in wall-clock; item 1 is
    dispatched second and raises FIRST. A wall-clock-ordered failure list would
    re-raise item 1's KeyError, so this test is the pin for the dispatch-order
    contract that `_run_concurrent` documents.
    """
    later_failed = threading.Event()

    def work(connection: _FakeConnection, item: int) -> int:
        if item == 0:
            assert later_failed.wait(timeout=10.0), "item 1 never failed"
            raise ValueError("earliest-dispatched")
        if item == 1:
            later_failed.set()
            raise KeyError("later-dispatched")
        return item

    with pytest.raises(ValueError, match="earliest-dispatched"):
        run_segment_window(
            items=list(range(6)),
            max_concurrent=2,
            connection_factory=_FakeConnection,
            work=work,
            on_complete=lambda ordinal, total, item, result: None,
        )


def test_secondary_worker_exceptions_are_logged_not_discarded(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def work(connection: _FakeConnection, item: int) -> int:
        # Two different failures, so a dropped one is unmistakable.
        if item == 2:
            raise ValueError("first-failure")
        if item == 5:
            raise KeyError("second-failure")
        time.sleep(0.01)
        return item

    # Dispatch order decides which failure wins, not completion timing.
    with (
        caplog.at_level(logging.ERROR, logger="weaver.services.segment_runner"),
        pytest.raises(ValueError, match="first-failure"),
    ):
        run_segment_window(
            items=list(range(8)),
            max_concurrent=2,
            connection_factory=_FakeConnection,
            work=work,
            on_complete=lambda ordinal, total, item, result: None,
        )

    logged = [record for record in caplog.records if record.levelno == logging.ERROR]
    assert len(logged) == 1
    assert "5" in logged[0].getMessage()
    assert logged[0].exc_info is not None
    assert isinstance(logged[0].exc_info[1], KeyError)
