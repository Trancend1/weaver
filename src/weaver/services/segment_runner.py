"""Bounded worker window for per-segment translation (ADR 020).

The sole home of translate-loop thread code. Both segment loops
(`translation.translate_project` and `workspace_translate.run_translation`)
delegate here so the race-prone dispatch logic exists once.

`max_concurrent = 1` runs strictly sequentially on the calling thread — no
executor, no threads — reproducing pre-M4 behavior bit-for-bit.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import closing
from typing import Protocol, TypeVar


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
        connection_factory: Opens one SQLite connection; called once per worker.
        work: Receives a worker-owned connection and one item.
        on_complete: Called as `(ordinal, total, item, result)` where `ordinal`
            is the 1-based completion ordinal. Never entered concurrently.
        should_cancel: Checked before each dispatch; in-flight work finishes.

    Returns:
        True when the run stopped early because `should_cancel` fired.
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
    """Bounded window: one persistent connection per worker thread.

    Connections are thread-local because sqlite3 connections are not shareable
    across threads. `on_complete` is serialized under `progress_lock` so the
    completion ordinal stays dense and callbacks never run concurrently.
    """

    local = threading.local()
    connections: list[TConnection] = []
    connections_lock = threading.Lock()
    progress_lock = threading.Lock()
    completed = 0
    cancelled = False

    def worker(item: TItem) -> None:
        nonlocal completed
        connection: TConnection | None = getattr(local, "connection", None)
        if connection is None:
            connection = connection_factory()
            local.connection = connection
            with connections_lock:
                connections.append(connection)
        result = work(connection, item)
        with progress_lock:
            completed += 1
            ordinal = completed
            on_complete(ordinal, total, item, result)

    try:
        with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
            futures: list[Future[None]] = []
            for item in items:
                if should_cancel is not None and should_cancel():
                    cancelled = True
                    break
                futures.append(executor.submit(worker, item))
            for future in futures:
                future.result()
    finally:
        for connection in connections:
            connection.close()
    return cancelled
