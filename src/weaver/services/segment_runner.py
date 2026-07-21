"""Bounded worker window for per-segment translation (ADR 020).

The sole home of translate-loop thread code. Both segment loops
(`translation.translate_project` and `workspace_translate.run_translation`)
delegate here so the race-prone dispatch logic exists once.

`max_concurrent = 1` runs strictly sequentially on the calling thread — no
executor, no threads — reproducing pre-M4 behavior bit-for-bit.
"""

from __future__ import annotations

import logging
import queue
import threading
from collections.abc import Callable, Sequence
from contextlib import closing
from typing import Protocol, TypeVar

_LOGGER = logging.getLogger(__name__)


class _Closeable(Protocol):
    def close(self) -> None: ...


TConnection = TypeVar("TConnection", bound=_Closeable)
TItem = TypeVar("TItem")
TResult = TypeVar("TResult")


def run_segment_window(
    *,
    items: Sequence[TItem],
    max_concurrent: int,
    connection_factory: Callable[[], TConnection],
    work: Callable[[TConnection, TItem], TResult],
    on_complete: Callable[[int, int, TItem, TResult], None],
    should_cancel: Callable[[], bool] | None = None,
) -> bool:
    """Run `work` over `items` through a bounded worker window.

    Args:
        items: Segments to process, in dispatch order.
        max_concurrent: Worker-window size (1 = sequential, caller-validated).
        connection_factory: Opens one SQLite connection. Called at most once per
            worker, lazily on that worker's first dispatched item, so a worker
            that never receives an item never opens a connection.
        work: Receives a worker-owned connection and one item.
        on_complete: Called as `(ordinal, total, item, result)` where `ordinal`
            is the 1-based completion ordinal. Never entered concurrently.
        should_cancel: Checked before each dispatch; in-flight work finishes.

    Returns:
        True when the run stopped early because `should_cancel` fired.

    Raises:
        Exception: Whatever `connection_factory`, `work`, or `on_complete`
            raised. When `max_concurrent > 1`, a worker failure does not halt
            dispatch —
            only `should_cancel` gates it — so items queued after a failing one
            still run to completion and still fire `on_complete`, committing
            real writes. The first failure in dispatch order is re-raised; any
            others are logged at error level. Callers must not read a raise as
            "nothing else happened". The sequential path stops dispatch outright.
    """

    total = len(items)
    if max_concurrent == 1:
        return _run_sequential(
            items=items,
            total=total,
            connection_factory=connection_factory,
            work=work,
            on_complete=on_complete,
            should_cancel=should_cancel,
        )
    return _run_concurrent(
        items=items,
        total=total,
        max_concurrent=max_concurrent,
        connection_factory=connection_factory,
        work=work,
        on_complete=on_complete,
        should_cancel=should_cancel,
    )


def _run_sequential(
    *,
    items: Sequence[TItem],
    total: int,
    connection_factory: Callable[[], TConnection],
    work: Callable[[TConnection, TItem], TResult],
    on_complete: Callable[[int, int, TItem, TResult], None],
    should_cancel: Callable[[], bool] | None,
) -> bool:
    with closing(connection_factory()) as connection:
        for ordinal, item in enumerate(items, start=1):
            if should_cancel is not None and should_cancel():
                return True
            result = work(connection, item)
            on_complete(ordinal, total, item, result)
    return False


def _run_concurrent(
    *,
    items: Sequence[TItem],
    total: int,
    max_concurrent: int,
    connection_factory: Callable[[], TConnection],
    work: Callable[[TConnection, TItem], TResult],
    on_complete: Callable[[int, int, TItem, TResult], None],
    should_cancel: Callable[[], bool] | None,
) -> bool:
    """Bounded window: one dedicated worker thread per slot, one connection per thread.

    Uses a hand-rolled worker pool rather than `ThreadPoolExecutor` on purpose:
    each worker thread opens at most one connection and closes it itself, in a
    `finally`, before its function returns — `sqlite3.connect()` defaults to
    `check_same_thread=True`, which rejects *any* use of the connection
    (`close()` included) from a thread other than the one that created it, and
    `ThreadPoolExecutor` gives no way to address a specific pooled thread for a
    "close yourself" follow-up job, so closing can never be delegated back to
    the coordinator thread once a worker has opened its connection. (Verified:
    `threading.local.__del__`-based auto-close on thread exit is NOT a
    reliable substitute — it does not run deterministically before
    `Thread.join()` returns.)

    `on_complete` fires in completion order (whichever item's `work()` call
    finishes first, first) under `progress_lock`, so the ordinal stays dense
    and callbacks never run concurrently — same contract as before. Failures
    are recorded per-item into a fixed-size, index-addressed slot so the
    re-raised failure is always the earliest-**dispatched** (original list
    order) one, regardless of which worker thread actually raises first --
    `test_earliest_dispatched_failure_wins_over_earlier_wall_clock_failure`
    pins this by making the earliest-dispatched item fail LAST in wall-clock,
    which a completion-ordered failure list gets wrong.
    """

    work_queue: queue.SimpleQueue[tuple[int, TItem] | None] = queue.SimpleQueue()
    for index, item in enumerate(items):
        work_queue.put((index, item))
    worker_count = max(1, min(max_concurrent, total)) if total else 0
    for _ in range(worker_count):
        work_queue.put(None)  # one stop signal per worker thread

    progress_lock = threading.Lock()
    completed = 0
    cancelled = threading.Event()
    failures: list[tuple[TItem, BaseException] | None] = [None] * total

    def run_worker() -> None:
        nonlocal completed
        connection: TConnection | None = None
        try:
            while True:
                queued = work_queue.get()
                if queued is None:
                    return
                index, item = queued
                if should_cancel is not None and should_cancel():
                    cancelled.set()
                    return
                try:
                    if connection is None:
                        # Opened lazily, inside the per-item try, so a
                        # `connection_factory()` failure is attributed to the
                        # item that was already dispatched to this worker and
                        # travels the same `failures` path as a work() failure.
                        # Opening it above the loop would leave the exception
                        # captured by nothing: the worker would die, the window
                        # would silently shrink, and a run where every factory
                        # call failed would return normally with zero items
                        # processed (CLAUDE.md 4.3 gate 5).
                        connection = connection_factory()
                    result = work(connection, item)
                    with progress_lock:
                        completed += 1
                        ordinal = completed
                        on_complete(ordinal, total, item, result)
                except BaseException as exc:  # noqa: BLE001 - mirrors
                    # concurrent.futures.thread._WorkItem.run: capture whatever
                    # the factory/work()/on_complete() raised so it can be
                    # inspected in dispatch order below; never silently dropped.
                    failures[index] = (item, exc)
                    if connection is None:
                        # The factory failed: this worker has nothing to work
                        # with, so it retires instead of re-failing every item
                        # it dequeues. Its share of the queue is drained by the
                        # surviving workers (items precede every stop signal),
                        # and the recorded failure is re-raised after join.
                        return
        finally:
            if connection is not None:
                connection.close()

    threads = [threading.Thread(target=run_worker) for _ in range(worker_count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    real_failures = [entry for entry in failures if entry is not None]
    for failed_item, suppressed in real_failures[1:]:
        _LOGGER.error(
            "Segment worker failed for item %r; re-raising the first failure only.",
            failed_item,
            exc_info=suppressed,
        )
    if real_failures:
        raise real_failures[0][1]
    return cancelled.is_set()
