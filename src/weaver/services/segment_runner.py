"""Bounded worker window for per-segment translation (ADR 020).

The sole home of translate-loop thread code. Both segment loops
(`translation.translate_project` and `workspace_translate.run_translation`)
delegate here so the race-prone dispatch logic exists once.

`max_concurrent = 1` runs strictly sequentially on the calling thread — no
executor, no threads — reproducing pre-M4 behavior bit-for-bit.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TypeVar

TConnection = TypeVar("TConnection")
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
    raise NotImplementedError("concurrent path lands in Task 4")


def _run_sequential(
    *,
    items: Sequence[TItem],
    total: int,
    connection_factory: Callable[[], TConnection],
    work: Callable[[TConnection, TItem], TResult],
    on_complete: Callable[[int, int, TItem, TResult], None],
    should_cancel: Callable[[], bool] | None,
) -> bool:
    connection = connection_factory()
    try:
        for ordinal, item in enumerate(items, start=1):
            if should_cancel is not None and should_cancel():
                return True
            result = work(connection, item)
            on_complete(ordinal, total, item, result)
        return False
    finally:
        close = getattr(connection, "close", None)
        if close is not None:
            close()
