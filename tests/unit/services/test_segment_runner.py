"""Bounded-window segment runner (ADR 020)."""

from __future__ import annotations

import threading

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
