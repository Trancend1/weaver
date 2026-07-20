# v0.7.3 M4 — Bounded Translate Concurrency (Design)

**Date:** 2026-07-21
**Milestone:** M4 of the [v0.7.3 execution plan](2026-07-05-v073-performance-execution-plan.md)
**Branch:** `feat/v073-bounded-concurrency`
**Decision record:** [ADR 020](../../decisions/020-bounded-translate-concurrency.md) (Accepted 2026-07-21)

## Problem

Translation is strictly sequential in all three drivers: segment N+1 does not start until
segment N commits. On live endpoints the provider network call (seconds per segment) dominates
wall-clock, so no local optimization approaches the win of overlapping 2–4 provider calls.

The v0.7.2 audit H3 fix (`dee710f`) unlocked this: provider calls now run outside any SQLite
write transaction, so concurrent in-flight calls no longer imply holding the WAL write lock.

## Current shape

There are **two** segment loops, not three:

| Driver | Loop | Shape |
| --- | --- | --- |
| `services/translation.py:427-494` | `translate_project` | own segment loop |
| `services/workspace_translate.py:273-320` | `run_translation` | own segment loop |
| `services/batch_translate.py:367-375` | batch driver | **chapter** loop; delegates each chapter to `run_translation` |

Both segment loops open one connection for the whole run
(`with closing(connect_database(...))`), iterate segments, call
`translate_one_segment(connection=..., cold=run_cold, ...)`, accumulate counters, and invoke
`progress_callback(index, total, segment, translated, in_tok, out_tok)`.

`batch_translate` has no segment loop of its own — it iterates chapters and calls
`run_translation` per chapter, so it inherits concurrency for free with no changes. Its
`on_segment` callback (`batch_translate.py:352-366`) only increments counters, so it is
insensitive to dispatch order once the callback is serialized (§6).

`FakeProvider` (`providers/fake.py`) returns instantly with `usage=None` — there is no honest
concurrency test or bench without a latency knob.

## Design

### 1. Shared bounded-window runner

New module `services/segment_runner.py` exposing one bounded-window runner used by **both**
segment loops. The alternative — implementing concurrency separately in each driver — duplicates
the most race-prone code in the codebase.

Aggregation stays in each driver's own closure: `translate_project` reads final counts from the
database while `run_translation` counts `failed` inline, and the runner must not homogenize that
difference.

The runner takes the segment list, a per-worker connection factory, and a per-segment closure;
it returns aggregated counters. `translate_one_segment` itself is **unchanged** — the concurrency
lives strictly above it.

Mechanism: a bounded worker window inside the existing per-job worker thread
(`ThreadPoolExecutor` with `max_workers = max_concurrent`). No external queue, worker daemon, or
process pool (CLAUDE.md §3.5). No `asyncio` (web-layer-only fence, §3.2/§3.5).

### 2. Configuration

`[translation] max_concurrent`, integer `1..4`, absent = **1** (today's behavior bit-for-bit).

`core/config.py` is a loader only; validation follows the existing `honorifics` pattern
(`translation.py:411-418`) — a `ConfigError` stating what failed, likely cause, and next command.
Surfaced additionally as a CLI flag and a cockpit field on the translate panel.

### 3. FakeProvider enabler (ships first)

`FakeProvider` gains `latency_seconds` and optional synthetic token usage. Without it there is no
honest concurrency or scaling test: it currently returns instantly, so a 3-worker bench would
"pass" without demonstrating overlap.

### 4. Connections and shared state

- **Per-worker persistent connection** for the duration of the run (opened once, closed at the
  end), avoiding per-segment open + migration-check cost. M1 established that connection-open
  count is material.
- `project`, `glossary_terms`, and `characters` are read once before dispatch and shared
  read-only across workers.
- Commit shape is unchanged (H3): one segment result = one short atomic transaction; the
  `in_progress` marker stays its own short transaction; `reset_in_progress_segments` remains the
  crash net.

### 5. Rolling-window semantics

Plain **last-N-committed** window: a worker sees only committed segments; in-flight neighbors are
invisible. With the window already capped at ≤ 5 segments / 1000 CJK-aware estimated tokens
(M3, audit N7), quality dilution is bounded and only occurs when the user opts in.

Rejected: block-order dispatch with a capped gap — added coordination and reduced throughput for
an unmeasured quality gain.

### 6. Progress and cancellation

Under concurrency `index` is no longer in segment order. `index` becomes the **completion
ordinal** (1..N in commit order), incremented under a lock that also serializes the
`progress_callback` invocation. This preserves "n of total" semantics in the job store and
guarantees the callback is never entered concurrently.

Cancellation is checked before each dispatch; in-flight workers run to completion rather than
being killed. Per-segment failures mark `failed` exactly as today; concurrency never retries
beyond the existing bounded chain.

### 7. Cold-mark locking — scope correction

ADR 020 §Decision 5 implies the shared `run_cold` dict is a correctness hazard. Reading the code,
it is not: usage is two single dict operations — `cold.get(...)` (`translation.py:675`) and
`cold[name] = ...` (`translation.py:690`). Both are atomic under CPython's GIL, so the live race
is **benign** (two workers cold-mark near-identical values, last-writer-wins).

A `threading.Lock` is still added — roughly three lines — because it makes the invariant explicit
and survives a future edit that turns this into a read-modify-write. It must **not** be described
as closing a state-corruption hole, because there is none. ADR 020's wording is adjusted
accordingly when it moves to Accepted.

`protect_manual` on TM upserts is verified to hold under the race (last-writer-wins on identical
`(project_id, source_hash)` is correct by construction).

## Testing

Test-driven, `FakeProvider` only — never live LLMs in CI.

1. **Determinism gate:** `max_concurrent = 1` is bit-for-bit identical to today (test-pinned),
   and the full pre-existing suite passes with the feature merged and unconfigured.
2. **Config validation:** out-of-range and non-integer values raise `ConfigError`.
3. **Concurrency correctness:** counters, completion-ordinal progress, and cancellation behave
   under a multi-worker run with `latency_seconds` set.
4. **Bench:** FakeProvider at 300 ms latency, 3 workers ⇒ ≥ 2.4× wall-clock vs sequential.
5. **Live spot-check** (M5, owner machine): ≥ 2×.

## Non-goals

No circuit breaker, health score, or autoscaling (D9 fence). No `asyncio`, process pool, or
external queue. Cap stays at 4. No provider-family changes.

## Carry-forward (not this PR)

`services/translation.py` is 965 lines, well over the §4.2 400-line guidance. Extracting the
runner reduces it but does not resolve it. Splitting the module further is a separate concern
(§4.4: one PR = one concern) and is recorded here rather than bundled into M4.
