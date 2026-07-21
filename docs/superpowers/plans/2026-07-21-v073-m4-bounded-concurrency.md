# v0.7.3 M4 — Bounded Translate Concurrency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an opt-in `[translation] max_concurrent = 1..4` bounded worker window to the translate loops, so live chapter/batch runs overlap 2–4 provider calls instead of running strictly sequentially.

**Architecture:** One shared bounded-window runner (`services/segment_runner.py`) drives both segment loops (`translate_project`, `run_translation`). Each worker owns a persistent SQLite connection for the run; `translate_one_segment` is unchanged. Default `max_concurrent = 1` reproduces today's behavior bit-for-bit. `batch_translate` inherits concurrency for free — it delegates per chapter to `run_translation`.

**Tech Stack:** Python 3.11+, `concurrent.futures.ThreadPoolExecutor`, `threading.Lock`, sqlite3 (WAL, `busy_timeout = 10000`), pytest, typer, Jinja2 + HTMX.

**Spec:** [2026-07-21-v073-m4-bounded-concurrency-design.md](../specs/2026-07-21-v073-m4-bounded-concurrency-design.md)
**ADR:** [020](../../decisions/020-bounded-translate-concurrency.md) (Accepted 2026-07-21)

---

## File Structure

| File | Responsibility |
| --- | --- |
| `src/weaver/providers/fake.py` (modify) | Add `latency_seconds` + synthetic token usage so concurrency is measurable |
| `src/weaver/services/segment_runner.py` (create) | The bounded-window runner: dispatch, per-worker connections, completion-ordinal progress, cancellation. Sole home of thread code. |
| `src/weaver/services/translation.py` (modify) | `translate_project` delegates its loop to the runner; validate `max_concurrent`; lock the cold-mark |
| `src/weaver/services/workspace_translate.py` (modify) | `run_translation` delegates its loop to the runner |
| `src/weaver/cli/` (modify) | `--max-concurrent` flag on the translate command |
| `src/weaver/api/` + templates (modify) | Cockpit field on the translate panel |
| `bench/run_performance_budgets.py` (modify) | Concurrency scaling budget |

Tests mirror the source tree under `tests/unit/...` and `tests/integration/...`.

---

## Task 1: FakeProvider latency + synthetic token usage

Ships first: without it there is no honest concurrency test — `FakeProvider` currently returns instantly with `usage=None`, so a 3-worker bench would "pass" without demonstrating any overlap.

**Files:**
- Modify: `src/weaver/providers/fake.py:25-66`
- Test: `tests/unit/providers/test_fake.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/providers/test_fake.py`:

```python
import time

from weaver.providers.fake import FakeProvider
from weaver.providers.types import TranslationRequest


def _request() -> TranslationRequest:
    return TranslationRequest(
        segment_id="seg-1",
        source_text="こんにちは",
        normalized_source_text="こんにちは",
        glossary_terms=(),
        previous_segments=(),
        honorific_policy="preserve",
        characters=(),
    )


def test_latency_seconds_delays_translate() -> None:
    provider = FakeProvider(latency_seconds=0.05)
    start = time.perf_counter()
    provider.translate(_request())
    assert time.perf_counter() - start >= 0.05


def test_latency_seconds_defaults_to_zero() -> None:
    provider = FakeProvider()
    start = time.perf_counter()
    provider.translate(_request())
    assert time.perf_counter() - start < 0.05


def test_negative_latency_rejected() -> None:
    with pytest.raises(ValueError, match="latency_seconds"):
        FakeProvider(latency_seconds=-1.0)


def test_synthetic_usage_reported_when_enabled() -> None:
    provider = FakeProvider(report_token_usage=True)
    response = provider.translate(_request())
    assert response.input_tokens is not None
    assert response.output_tokens is not None
    assert response.input_tokens > 0


def test_usage_is_none_by_default() -> None:
    response = FakeProvider().translate(_request())
    assert response.input_tokens is None
    assert response.output_tokens is None
```

Add `import pytest` at the top of the file if it is not already imported. Check `TranslationRequest`'s actual field names in `src/weaver/providers/types.py` before running — if they differ from the helper above, match the real signature rather than editing the type.

- [ ] **Step 2: Run tests to verify they fail**

Run: `rtk pytest tests/unit/providers/test_fake.py -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'latency_seconds'`

- [ ] **Step 3: Implement**

In `src/weaver/providers/fake.py`, extend `__init__` and both call paths:

```python
    def __init__(
        self,
        *,
        pattern: str = "[FAKE] {source}",
        fail_rate: float = 0.0,
        seed: int = 0,
        model: str = "fake-1",
        completion: str = '{"target": "[FAKE]"}',
        latency_seconds: float = 0.0,
        report_token_usage: bool = False,
    ) -> None:
        if not 0.0 <= fail_rate <= 1.0:
            raise ValueError("fail_rate must be in [0.0, 1.0]")
        if latency_seconds < 0.0:
            raise ValueError("latency_seconds must be >= 0.0")
        self._pattern = pattern
        self._fail_rate = fail_rate
        self._random = random.Random(seed)
        self._model = model
        self._completion = completion
        self._latency_seconds = latency_seconds
        self._report_token_usage = report_token_usage
```

Update the class docstring to document both knobs — state that `latency_seconds` simulates provider round-trip time for concurrency benchmarking and that `report_token_usage` returns a deterministic character-based estimate.

In `translate`, sleep before the failure roll so injected failures also cost latency, and return synthetic usage:

```python
    def translate(self, request: TranslationRequest) -> TranslationResponse:
        if self._latency_seconds > 0.0:
            time.sleep(self._latency_seconds)
        if self._fail_rate > 0.0 and self._random.random() < self._fail_rate:
            raise ProviderResponseError(
                "FakeProvider synthetic failure. "
                "Likely cause: fail_rate>0 sampled this segment. "
                "Next command: rerun with FakeProvider(fail_rate=0) to disable injection."
            )

        translation = self._pattern.format(source=request.normalized_source_text)
        raw = json.dumps(
            {
                "translation": translation,
                "notes": [],
                "uncertain_terms": [],
            },
            ensure_ascii=False,
        )
        input_tokens = output_tokens = None
        if self._report_token_usage:
            input_tokens = max(1, len(request.normalized_source_text))
            output_tokens = max(1, len(translation) // 4)
        return TranslationResponse(
            translation=translation,
            notes=(),
            uncertain_terms=(),
            raw_response=raw,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
```

Apply the same `time.sleep(self._latency_seconds)` guard at the top of `complete`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `rtk pytest tests/unit/providers/test_fake.py -v`
Expected: PASS, all tests

- [ ] **Step 5: Verify no existing test regressed**

Run: `rtk pytest tests/ -q`
Expected: PASS — the same count as the M3 baseline (1683 passed, 1 skipped) plus the new tests. Defaults are unchanged, so nothing should break.

- [ ] **Step 6: Commit**

```bash
git add src/weaver/providers/fake.py tests/unit/providers/test_fake.py
git commit -m "feat(providers): add FakeProvider latency and synthetic usage knobs

Enables honest concurrency and scaling tests for M4 — the provider
previously returned instantly with usage=None, so a multi-worker bench
could not demonstrate overlap. Both knobs default off."
```

---

## Task 2: Config validation for `max_concurrent`

**Files:**
- Modify: `src/weaver/services/translation.py:411-418` (beside the `honorifics` validation)
- Test: `tests/unit/services/test_translation.py`

- [ ] **Step 1: Write the failing tests**

The validator is a module-level function so it can be tested without a full run. Append to `tests/unit/services/test_translation.py`:

```python
import pytest

from weaver.errors import ConfigError
from weaver.services.translation import resolve_max_concurrent


def test_absent_max_concurrent_defaults_to_one() -> None:
    assert resolve_max_concurrent({}) == 1


def test_valid_values_accepted() -> None:
    for value in (1, 2, 3, 4):
        assert resolve_max_concurrent({"max_concurrent": value}) == value


@pytest.mark.parametrize("value", [0, 5, -1, 100])
def test_out_of_range_rejected(value: int) -> None:
    with pytest.raises(ConfigError, match="max_concurrent"):
        resolve_max_concurrent({"max_concurrent": value})


@pytest.mark.parametrize("value", ["3", 2.5, True, None])
def test_non_integer_rejected(value: object) -> None:
    with pytest.raises(ConfigError, match="max_concurrent"):
        resolve_max_concurrent({"max_concurrent": value})
```

Note `True` is included deliberately: `isinstance(True, int)` is `True` in Python, so a bare `isinstance` check would wrongly accept it.

- [ ] **Step 2: Run tests to verify they fail**

Run: `rtk pytest tests/unit/services/test_translation.py -k max_concurrent -v`
Expected: FAIL — `ImportError: cannot import name 'resolve_max_concurrent'`

- [ ] **Step 3: Implement**

Add near `VALID_HONORIFIC_POLICIES` in `src/weaver/services/translation.py`:

```python
# Bounded translate concurrency (ADR 020). Absent = 1 = today's sequential
# behavior bit-for-bit. The cap is fixed at 4 — no autoscaling (D9 fence).
MAX_CONCURRENT_LIMIT = 4


def resolve_max_concurrent(translation_config: Mapping[str, Any]) -> int:
    """Read and validate `[translation] max_concurrent`.

    Args:
        translation_config: The parsed `[translation]` table.

    Returns:
        The worker-window size, 1 when the key is absent.

    Raises:
        ConfigError: When the value is not an integer in 1..4.
    """

    if "max_concurrent" not in translation_config:
        return 1
    value = translation_config["max_concurrent"]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(
            f"Invalid max_concurrent value `{value!r}` (expected type: integer). "
            "Likely cause: project.toml [translation] max_concurrent was hand-edited. "
            "Next command: edit project.toml and set an integer between 1 and "
            f"{MAX_CONCURRENT_LIMIT}."
        )
    if not 1 <= value <= MAX_CONCURRENT_LIMIT:
        raise ConfigError(
            f"Invalid max_concurrent value `{value}` "
            f"(expected: between 1 and {MAX_CONCURRENT_LIMIT}). "
            "Likely cause: project.toml [translation] max_concurrent is out of range. "
            "Next command: edit project.toml and set a value between 1 and "
            f"{MAX_CONCURRENT_LIMIT}."
        )
    return value
```

Ensure `Mapping` and `Any` are imported (`from collections.abc import Mapping`, `from typing import Any`) — check the existing imports first and add only what is missing.

- [ ] **Step 4: Run tests to verify they pass**

Run: `rtk pytest tests/unit/services/test_translation.py -k max_concurrent -v`
Expected: PASS, 11 tests

- [ ] **Step 5: Commit**

```bash
git add src/weaver/services/translation.py tests/unit/services/test_translation.py
git commit -m "feat(translate): validate [translation] max_concurrent (1..4, default 1)

Follows the existing honorifics validation pattern: ConfigError stating
what failed, likely cause, and next command. Rejects bool explicitly
since isinstance(True, int) is True."
```

---

## Task 3: The bounded-window runner — sequential path first

Build the runner so that `max_concurrent = 1` is exercised and pinned **before** any thread code exists. This makes the determinism gate a real regression net rather than an afterthought.

**Files:**
- Create: `src/weaver/services/segment_runner.py`
- Test: `tests/unit/services/test_segment_runner.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/services/test_segment_runner.py`:

```python
"""Bounded-window segment runner (ADR 020)."""

from __future__ import annotations

import threading

from weaver.services.segment_runner import run_segment_window


def test_sequential_window_visits_every_item_in_order() -> None:
    seen: list[int] = []

    def work(connection: object, item: int) -> str:
        seen.append(item)
        return f"done-{item}"

    completed: list[tuple[int, int, str]] = []

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
        connection_factory=_FakeConnection,
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
        connection_factory=_FakeConnection,
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `rtk pytest tests/unit/services/test_segment_runner.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'weaver.services.segment_runner'`

- [ ] **Step 3: Implement the sequential path**

Create `src/weaver/services/segment_runner.py`:

```python
"""Bounded worker window for per-segment translation (ADR 020).

The sole home of translate-loop thread code. Both segment loops
(`translation.translate_project` and `workspace_translate.run_translation`)
delegate here so the race-prone dispatch logic exists once.

`max_concurrent = 1` runs strictly sequentially on the calling thread — no
executor, no threads — reproducing pre-M4 behavior bit-for-bit.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from contextlib import closing
from typing import Protocol, TypeVar

TItem = TypeVar("TItem")
TResult = TypeVar("TResult")


class _Closeable(Protocol):
    def close(self) -> None: ...


def run_segment_window(
    *,
    items: Sequence[TItem],
    max_concurrent: int,
    connection_factory: Callable[[], _Closeable],
    work: Callable[[_Closeable, TItem], TResult],
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
    connection_factory: Callable[[], _Closeable],
    work: Callable[[_Closeable, TItem], TResult],
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `rtk pytest tests/unit/services/test_segment_runner.py -v`
Expected: PASS, 5 tests

- [ ] **Step 5: Commit**

```bash
git add src/weaver/services/segment_runner.py tests/unit/services/test_segment_runner.py
git commit -m "feat(translate): add bounded-window segment runner (sequential path)

max_concurrent=1 runs on the calling thread with no executor, preserving
pre-M4 behavior exactly. The concurrent path follows."
```

---

## Task 4: The concurrent path

**Files:**
- Modify: `src/weaver/services/segment_runner.py`
- Test: `tests/unit/services/test_segment_runner.py`

- [ ] **Step 1: Write the failing tests**

> **Connection doubles must be closeable.** The runner closes every connection it opens, unconditionally — `connection_factory` is typed `Callable[[], TConnection]` with `TConnection` bound to a `_Closeable` Protocol. Use the `_FakeConnection` double established in Task 3, never `object()`; a bare `object()` is both a type error and an `AttributeError` at close time.

Append to `tests/unit/services/test_segment_runner.py`:

```python
import time


def test_concurrent_window_opens_one_connection_per_worker() -> None:
    opened: list[_FakeConnection] = []
    lock = threading.Lock()

    def factory() -> _FakeConnection:
        connection = _FakeConnection()
        with lock:
            opened.append(connection)
        return connection

    run_segment_window(
        items=list(range(12)),
        max_concurrent=3,
        connection_factory=factory,
        work=lambda connection, item: item,
        on_complete=lambda ordinal, total, item, result: None,
    )

    assert len(opened) == 3
    assert all(connection.closed for connection in opened)


def test_concurrent_window_processes_every_item() -> None:
    seen: list[int] = []
    lock = threading.Lock()

    def work(connection: object, item: int) -> int:
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
    def work(connection: object, item: int) -> int:
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


def test_worker_exception_propagates_and_closes_connections() -> None:
    closed: list[bool] = []
    lock = threading.Lock()

    class Recorder:
        def close(self) -> None:
            with lock:
                closed.append(True)

    def work(connection: object, item: int) -> int:
        if item == 3:
            raise RuntimeError("boom")
        return item

    with pytest.raises(RuntimeError, match="boom"):
        run_segment_window(
            items=list(range(10)),
            max_concurrent=2,
            connection_factory=Recorder,
            work=work,
            on_complete=lambda ordinal, total, item, result: None,
        )

    assert len(closed) == 2
```

Add `import pytest` to the file's imports.

- [ ] **Step 2: Run tests to verify they fail**

Run: `rtk pytest tests/unit/services/test_segment_runner.py -k concurrent -v`
Expected: FAIL — `NotImplementedError: concurrent path lands in Task 4`

- [ ] **Step 3: Implement**

Replace the `raise NotImplementedError(...)` line in `run_segment_window` with a call to `_run_concurrent(...)` passing the same arguments plus `max_concurrent`, and add:

```python
def _run_concurrent(
    *,
    items: Sequence[TItem],
    total: int,
    max_concurrent: int,
    connection_factory: Callable[[], _Closeable],
    work: Callable[[_Closeable, TItem], TResult],
    on_complete: Callable[[int, int, TItem, TResult], None],
    should_cancel: Callable[[], bool] | None,
) -> bool:
    """Bounded window: one persistent connection per worker thread.

    Connections are thread-local because sqlite3 connections are not shareable
    across threads. `on_complete` is serialized under `progress_lock` so the
    completion ordinal stays dense and callbacks never run concurrently.
    """

    local = threading.local()
    connections: list[_Closeable] = []
    connections_lock = threading.Lock()
    progress_lock = threading.Lock()
    completed = 0
    cancelled = False

    def worker(item: TItem) -> None:
        nonlocal completed
        connection = getattr(local, "connection", None)
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
```

Add to the imports at the top of the module:

```python
import threading
from concurrent.futures import Future, ThreadPoolExecutor
```

Two things this shape buys deliberately. Connections are created lazily inside `worker` and cached on `threading.local`, so exactly one connection exists per worker thread that actually ran — not one per item. And `future.result()` is re-raised after the `with` block drains, so a worker exception surfaces to the caller instead of vanishing into the executor, while `finally` still closes every connection that was opened.

- [ ] **Step 4: Run tests to verify they pass**

Run: `rtk pytest tests/unit/services/test_segment_runner.py -v`
Expected: PASS, 10 tests

If `test_concurrent_window_actually_overlaps` is flaky on a loaded machine, do **not** widen the threshold silently — rerun to confirm, and if it is genuinely marginal, raise the per-item sleep rather than the assertion bound, so the test keeps proving overlap.

- [ ] **Step 5: Commit**

```bash
git add src/weaver/services/segment_runner.py tests/unit/services/test_segment_runner.py
git commit -m "feat(translate): add bounded concurrent path to segment runner

One persistent connection per worker thread via threading.local (sqlite3
connections are not shareable across threads). Completion ordinals stay
dense under a progress lock; worker exceptions re-raise to the caller."
```

---

## Task 5: Lock the cold-mark map

Scope note: current usage is two single dict operations (`cold.get` at `translation.py:675`, `cold[name] = ...` at `:690`), atomic under CPython's GIL, so the live race is benign. The lock makes the invariant explicit and survives a future edit that turns this into a read-modify-write. Do not describe it as fixing a corruption bug.

**Files:**
- Modify: `src/weaver/services/translation.py:670-691`
- Test: `tests/unit/services/test_translation.py`

- [ ] **Step 1: Write the failing test**

```python
def test_cold_marks_are_safe_under_concurrent_access() -> None:
    from weaver.services.translation import ColdMarks

    marks = ColdMarks()
    errors: list[BaseException] = []

    def hammer() -> None:
        try:
            for _ in range(500):
                marks.mark("engine-a", 1.0)
                marks.is_cold("engine-a", now=0.0)
        except BaseException as exc:  # pragma: no cover - diagnostic
            errors.append(exc)

    threads = [threading.Thread(target=hammer) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert marks.is_cold("engine-a", now=0.0) is True
    assert marks.is_cold("engine-b", now=0.0) is False
```

Add `import threading` to the test file if absent.

- [ ] **Step 2: Run test to verify it fails**

Run: `rtk pytest tests/unit/services/test_translation.py -k cold_marks -v`
Expected: FAIL — `ImportError: cannot import name 'ColdMarks'`

- [ ] **Step 3: Implement**

Add to `src/weaver/services/translation.py`:

```python
class ColdMarks:
    """Per-run fallback cold-mark map, safe for the M4 worker window.

    ADR 018 D4: a failed engine is skipped for a short window, never
    circuit-broken. The lock is defensive — today's two call sites are single
    dict operations, atomic under CPython — but it keeps the invariant explicit
    if this ever becomes a read-modify-write.
    """

    def __init__(self) -> None:
        self._until: dict[str, float] = {}
        self._lock = threading.Lock()

    def is_cold(self, engine_name: str, *, now: float) -> bool:
        with self._lock:
            return self._until.get(engine_name, 0.0) > now

    def mark(self, engine_name: str, until: float) -> None:
        with self._lock:
            self._until[engine_name] = until
```

Change `translate_one_segment`'s parameter from `cold: dict[str, float] | None = None` to `cold: ColdMarks | None = None`, and rewrite the two call sites:

```python
        warm = [c for c in candidates if cold is None or not cold.is_cold(c[0].name, now=now)]
```

```python
            except ProviderError:
                if cold is not None:
                    cold.mark(cand_provider.name, now + _FALLBACK_COLD_SECONDS)
                continue
```

Replace `run_cold: dict[str, float] = {}` with `run_cold = ColdMarks()` at both `translation.py:400` and `workspace_translate.py:271`. Add `import threading` to `translation.py` if absent.

Note the original `warm` predicate was `cold.get(...) <= now` (not cold when the mark has expired); `not is_cold(...)` preserves that exactly — verify the boundary case rather than assuming it.

- [ ] **Step 4: Run tests to verify they pass**

Run: `rtk pytest tests/unit/services/test_translation.py tests/unit/services/test_workspace_translate.py tests/unit/services/test_routing.py -v`
Expected: PASS. Any test constructing `cold={}` directly must be updated to `ColdMarks()` — grep for `cold=` under `tests/` and fix each occurrence.

- [ ] **Step 5: Commit**

```bash
git add src/weaver/services/translation.py src/weaver/services/workspace_translate.py tests/
git commit -m "refactor(translate): move fallback cold-marks behind ColdMarks

Defensive locking ahead of the M4 worker window; the existing race is
benign (two atomic dict ops under CPython). Behavior is unchanged."
```

---

## Task 6: Wire `translate_project` to the runner

**Files:**
- Modify: `src/weaver/services/translation.py:427-509`
- Test: `tests/unit/services/test_translation_orchestrator.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_translate_project_default_is_sequential(tmp_path) -> None:
    """max_concurrent absent => one connection, segment order preserved."""
    # Build a project with 5 pending segments using the existing fixture helper
    # in this file; assert the run completes and every segment is translated.
    # Then assert the FakeProvider saw segments in source order.


def test_translate_project_honours_max_concurrent(tmp_path) -> None:
    """max_concurrent = 3 with a latency provider beats sequential wall-clock."""
```

Fill these in using the project-fixture helper already used by the other tests in `tests/unit/services/test_translation_orchestrator.py` — read the top of that file and reuse its setup rather than inventing a second fixture style. The first test must assert: all segments translated, counters match, and the provider observed source order. The second must assert wall-clock for `max_concurrent=3` with `FakeProvider(latency_seconds=0.05)` over 9 segments is under 60% of the `max_concurrent=1` run over the same fixture.

- [ ] **Step 2: Run tests to verify they fail**

Run: `rtk pytest tests/unit/services/test_translation_orchestrator.py -k max_concurrent -v`
Expected: FAIL — concurrency not yet wired, so the second test's timing assertion fails.

- [ ] **Step 3: Implement**

In `translate_project`, replace the `for index, segment in enumerate(selected, start=1):` loop body (`translation.py:446-492`) with a runner call. The connection opened at line 427 stays for the pre-loop reads (project load, glossary, segment selection) and the post-loop `_read_segment_counts`; the runner opens its own worker connections.

```python
        max_concurrent = resolve_max_concurrent(translation_config)

        def _translate(worker_connection: sqlite3.Connection, segment: SegmentRecord):
            block = block_by_id.get(segment.id)
            if block is None:
                raise ConfigError(
                    f"Segment `{segment.id}` is missing from the current source EPUB. "
                    "Likely cause: project state and source file are out of sync. "
                    "Next command: rerun `weaver init <input.epub>` for this source."
                )
            return translate_one_segment(
                connection=worker_connection,
                segment=segment,
                source_text=block.source_text,
                normalized_source_text=block.normalized_source_text,
                project=project,
                glossary_terms=glossary_terms,
                honorific_policy=honorific_policy,
                provider=active_provider,
                provider_model=provider_model,
                characters=characters,
                persist_raw_response=persist_raw_response,
                fallbacks=fallback_engines,
                cold=run_cold,
                enforce_repair=enforce_repair,
                profile=profile,
            )

        def _accumulate(
            ordinal: int, total: int, segment: SegmentRecord, outcome
        ) -> None:
            nonlocal translated_count, reused_count, input_tokens, output_tokens
            nonlocal repair_calls, json_repair_calls
            if outcome.translated:
                translated_count += 1
                input_tokens += outcome.input_tokens or 0
                output_tokens += outcome.output_tokens or 0
            if outcome.reused_from_memory:
                reused_count += 1
            if outcome.repair_call_made:
                repair_calls += 1
            if outcome.json_repair_used:
                json_repair_calls += 1
            if progress_callback is not None:
                progress_callback(
                    ordinal,
                    total,
                    segment,
                    outcome.translated,
                    outcome.input_tokens,
                    outcome.output_tokens,
                )

        run_segment_window(
            items=selected,
            max_concurrent=max_concurrent,
            connection_factory=lambda: connect_database(db_path),
            work=_translate,
            on_complete=_accumulate,
            should_cancel=should_cancel,
        )
```

`_accumulate` mutates shared counters, but the runner serializes `on_complete` under its progress lock, so no additional locking is needed here. Import `run_segment_window` from `weaver.services.segment_runner`. Annotate the `outcome` parameters as `SegmentTranslationOutcome`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `rtk pytest tests/unit/services/test_translation_orchestrator.py -v`
Expected: PASS

- [ ] **Step 5: Run the determinism gate**

Run: `rtk pytest tests/ -q`
Expected: PASS at the M3 baseline count plus the new tests. This is the gate that proves `max_concurrent` absent leaves behavior unchanged — if anything here fails, fix it before continuing rather than adjusting the test.

- [ ] **Step 6: Commit**

```bash
git add src/weaver/services/translation.py tests/unit/services/test_translation_orchestrator.py
git commit -m "feat(translate): run translate_project through the bounded window

Default max_concurrent=1 keeps the sequential path; counters stay in the
driver's closure and are serialized by the runner's progress lock."
```

---

## Task 7: Wire `run_translation` to the runner

**Files:**
- Modify: `src/weaver/services/workspace_translate.py:273-320`
- Test: `tests/unit/services/test_workspace_translate.py`

- [ ] **Step 1: Write the failing test**

```python
def test_run_translation_honours_max_concurrent(tmp_path) -> None:
    """A latency-provider chapter plan completes faster with a 3-worker window."""
```

Fill this in using the existing chapter-plan fixture at the top of `tests/unit/services/test_workspace_translate.py`. Assert that `translated`, `reused_from_memory`, and `failed` on the returned `ChapterTranslationResult` are identical between a `max_concurrent=1` and a `max_concurrent=3` run over the same fixture, and that the 3-worker wall-clock is under 60% of the sequential one with `FakeProvider(latency_seconds=0.05)`.

Also add a batch-level test in `tests/unit/services/test_batch_translate.py` asserting a multi-chapter batch run produces identical counters at `max_concurrent=1` and `max_concurrent=3` — batch inherits concurrency through `run_translation` and must be covered, not assumed.

- [ ] **Step 2: Run tests to verify they fail**

Run: `rtk pytest tests/unit/services/test_workspace_translate.py -k max_concurrent -v`
Expected: FAIL on the timing assertion.

- [ ] **Step 3: Implement**

`max_concurrent` must reach `run_translation` through the plan object rather than a new parameter, so the batch driver passes it through unchanged. Add a `max_concurrent: int = 1` field to the chapter-plan dataclass (find it near the top of `workspace_translate.py`), populate it where the plan is built from `translation_config` via `resolve_max_concurrent`, and replace the loop body (`workspace_translate.py:274-320`) with a `run_segment_window` call following the same closure shape as Task 6.

Keep `run_translation`'s inline `failed += 1` in the `else` branch — that differs from `translate_project`, which reads final counts from the database, and the difference must be preserved.

- [ ] **Step 4: Run tests to verify they pass**

Run: `rtk pytest tests/unit/services/test_workspace_translate.py tests/unit/services/test_batch_translate.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/weaver/services/workspace_translate.py tests/unit/services/test_workspace_translate.py tests/unit/services/test_batch_translate.py
git commit -m "feat(translate): run chapter translation through the bounded window

max_concurrent travels on the chapter plan so batch_translate inherits
concurrency without its own segment loop."
```

---

## Task 8: CLI flag

**Files:**
- Modify: the translate command in `src/weaver/cli/` (locate with `rtk grep -n "def translate" src/weaver/cli/`)
- Test: `tests/integration/test_cli_translate.py`

- [ ] **Step 1: Write the failing test**

```python
def test_translate_max_concurrent_flag_overrides_config(tmp_path) -> None:
    """--max-concurrent 3 runs and reports success on the fake provider."""


def test_translate_rejects_out_of_range_max_concurrent(tmp_path) -> None:
    """--max-concurrent 9 exits with the ConfigError code (7)."""
```

Fill these in with the CLI-runner fixture already used in that file. The second must assert exit code 7 (`ConfigError`, PRD_v2.md §10 AC-9) and that the message names `max_concurrent`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `rtk pytest tests/integration/test_cli_translate.py -k max_concurrent -v`
Expected: FAIL — no such option.

- [ ] **Step 3: Implement**

Add `--max-concurrent` as an `int | None = None` typer option on the translate command. When provided it overrides `[translation] max_concurrent`; when omitted the config value (or 1) applies. Route the override through `resolve_max_concurrent` so CLI and config share one validator and one error message — do not add a second range check in the CLI layer.

- [ ] **Step 4: Run tests to verify they pass**

Run: `rtk pytest tests/integration/test_cli_translate.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/weaver/cli tests/integration/test_cli_translate.py
git commit -m "feat(cli): add --max-concurrent to weaver translate"
```

---

## Task 9: Cockpit field

**Files:**
- Modify: the translate panel template and its route (locate with `rtk grep -rn "enforce_repair" src/weaver/api src/weaver/web` to find where the sibling translate settings are rendered)
- Test: `tests/unit/api/` (mirror the existing translate-panel test file)

- [ ] **Step 1: Write the failing test**

Assert the translate panel renders a `max_concurrent` control with the current value selected, and that posting an out-of-range value returns a validation error rather than a 500. Follow the existing panel tests for the request/assertion style.

- [ ] **Step 2: Run test to verify it fails**

Run: `rtk pytest tests/unit/api -k max_concurrent -v`
Expected: FAIL

- [ ] **Step 3: Implement**

Render the field beside the existing translate settings, as a 1–4 select (the range is fixed and small, so a select prevents the invalid-input path from being reachable through the UI at all). Per CLAUDE.md §4.2, do not rename or remove any existing route, template, CSS, HTMX, or DOM hook. Validation goes through `resolve_max_concurrent` at the service boundary; the router stays thin.

- [ ] **Step 4: Run tests to verify they pass**

Run: `rtk pytest tests/unit/api -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/weaver/api src/weaver/web tests/unit/api
git commit -m "feat(cockpit): expose max_concurrent on the translate panel"
```

---

## Task 10: Concurrency scaling bench budget

**Files:**
- Modify: `bench/run_performance_budgets.py`
- Test: the bench run itself

- [ ] **Step 1: Add the scaling probe**

Add a budget that translates the same fixture twice with `FakeProvider(latency_seconds=0.3)` — once at `max_concurrent=1`, once at `max_concurrent=3` — and reports the speedup ratio. Budget: **≥ 2.4×**. Follow the existing `_measure_cli` / `BudgetResult` pattern in that file rather than inventing a new reporting shape.

Two traps this file has already caught, per the §2.5 phase log — do not rediscover them:
- The fake pattern must be pure English (no `{source}`, no JP) or `weaver validate` exits 1 on `untranslated_japanese` criticals.
- Never read the bench exit code through a `| tee` or `| tail` pipe; the pipe's exit code masks the real one.

- [ ] **Step 2: Run the bench**

Run: `rtk proxy powershell -NoProfile -Command "uv run python bench/run_performance_budgets.py"`
Expected: all budgets PASS, including the new concurrency budget at ≥ 2.4×.

- [ ] **Step 3: Commit**

```bash
git add bench/run_performance_budgets.py
git commit -m "test(bench): add concurrency scaling budget (>=2.4x at 3 workers)"
```

---

## Task 11: Final gate and docs

- [ ] **Step 1: Run the full gate**

```bash
rtk proxy powershell -NoProfile -Command "uv run ruff check ."
rtk proxy powershell -NoProfile -Command "uv run ruff format --check ."
rtk proxy powershell -NoProfile -Command "uv run pyright"
rtk pytest tests/ -q
rtk proxy powershell -NoProfile -Command "uv run python bench/run_performance_budgets.py"
rtk proxy powershell -NoProfile -Command "uv run python bench/run_acceptance_gate.py"
```

Expected: ruff/format/pyright clean; full suite green at the M3 baseline (1683 passed, 1 skipped) plus the new tests; all budgets PASS; AC-1…AC-9 PASS.

Record the actual numbers. Do not write "expected to pass" anywhere — CLAUDE.md Decision Rule 6.

- [ ] **Step 2: Update the docs**

- `CLAUDE.md` §2.3: mark M4 done with its evidence line; §2.4: tick the throughput exit criterion with the measured ratio; §2.5: add the M4 carry-forward lesson.
- **Also correct the stale §2.3 status block** — it still claims M1–M3 are "none merged/pushed" when `main == origin/main` and all three are merged. M5's release gate would otherwise work from a false status.
- Write the handoff to `docs/superpowers/handoffs/2026-07-21-v073-m4-bounded-concurrency.md` using the §8 protocol.
- Record the `services/translation.py` size carry-forward (965 lines, over the §4.2 400-line guidance; the runner extraction reduces but does not resolve it).

- [ ] **Step 3: Commit and open the PR**

```bash
git add -A
git commit -m "docs(v073): record M4 completion — status, exit criteria, handoff"
```

Open the PR only when the owner asks. One PR = one concern: M4 only.

---

## Self-Review Notes

**Spec coverage:** runner §1 → Tasks 3+4; config §2 → Task 2 (+8, +9 surfaces); FakeProvider §3 → Task 1; connections/shared state §4 → Tasks 3+4+6; rolling window §5 → no code change (plain last-N-committed is the existing `list_previous_translated_segments` behavior, made explicit by committed-only visibility); progress/cancel §6 → Tasks 3+4+6; cold-mark §7 → Task 5; testing → every task + Tasks 10+11; carry-forward → Task 11.

**Known plan gaps, deliberately left to execution:** Tasks 6–9 describe test intent and assertions but delegate fixture construction to the existing helpers in each target file. Inlining invented fixtures would risk diverging from the established setup style in files that already have one. Read the target file's existing fixtures first.
