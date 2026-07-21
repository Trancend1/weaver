# ADR 020 — Bounded In-Process Translate Concurrency

## Status

**Accepted (2026-07-21).** Drafted at Gate A of the v0.7.3 performance release (Proposed
2026-07-05); accepted at Gate B of Milestone M4 of the
[v0.7.3 execution plan](../superpowers/specs/2026-07-05-v073-performance-execution-plan.md)
with the three decision points below settled. Implementation design:
[M4 design](../superpowers/specs/2026-07-21-v073-m4-bounded-concurrency-design.md).
Companion to ADR 018 (per-segment routing/fallback) and ADR 019 (enforcement loop). Unlocked by
the v0.7.2 audit H3 fix (commit `dee710f`): provider network calls now run **outside** any SQLite
write transaction, so multiple in-flight provider calls no longer imply holding the WAL write
lock concurrently.

## Context

Translation is strictly sequential in all three drivers — segment N+1 does not start until
segment N's result commits (`services/translation.py:338-382`,
`services/workspace_translate.py:261-303`, `services/batch_translate.py:353-373`). The provider
network call (seconds per segment on live endpoints) dominates wall-clock; every local
optimization combined cannot approach the win of overlapping 2–4 provider calls. Jobs already run
on one daemon thread per job (`api/jobs.py`), SQLite runs WAL with `busy_timeout = 10000`, and
the per-segment commit shape is short and atomic (H3). The remaining blockers are thread-safety
of shared per-run state, rolling-window semantics, and the absence of a latency-simulating test
provider.

## Decision

Add a **bounded in-process worker window** to the translate loops:

1. **Config:** `[translation] max_concurrent = 1..4`, absent = **1** (today's behavior
   bit-for-bit — byte-identical prompts, identical commit order semantics). Parsed in
   `core/config.py`, validated; surfaced as a cockpit field on the translate panel and a CLI flag.
2. **Mechanism:** a `ThreadPoolExecutor`-style bounded window **inside the existing per-job
   worker thread**. No external queue, worker daemon, or process pool (CLAUDE.md §3.5). No
   `asyncio` (web-layer-only fence, §3.2/§3.5).
3. **Per-worker SQLite connections:** `sqlite3` connections are not shareable across threads;
   each worker opens its own connection (existing `connect_database`). WAL + `busy_timeout` +
   `synchronous = NORMAL` (v0.7.3 M1.1) handle single-writer contention. The `in_progress`
   marker and the one-atomic-result commit stay per-segment short transactions (H3 shape,
   CLAUDE.md §4.2).
4. **Rolling-window semantics:** the context window for a segment is the last N **committed**
   segments (`list_previous_translated_segments`); in-flight neighbors are invisible. With the
   window already capped at ≤ 5 segments / 1000 CJK-aware estimated tokens (v0.7.3 M3, audit N7), the quality dilution is bounded and only
   occurs when the user opts in. Dispatch stays in block order; an optional capped window-gap
   policy is Decision Point 1 below.
5. **Shared state:** the `run_cold` fallback cold-mark dict goes behind a `threading.Lock`. This
   is defensive, not a bug fix: current usage is two single dict operations (`cold.get` and
   `cold[name] = ...`), which are atomic under CPython's GIL, so the live race is benign
   (last-writer-wins on near-identical values). The lock makes the invariant explicit and
   survives a future edit that turns this into a read-modify-write — it must not be described as
   closing a state-corruption hole. Progress counters keep flowing through the existing throttled
   job-store flush (≤ 1/s), with `index` redefined as the completion ordinal and the callback
   serialized under a lock. TM upserts on identical `(project_id, source_hash)` are
   last-writer-wins by construction; `protect_manual` must be verified to hold under the race.
6. **Cancellation/failure:** the cancel event is checked per segment (existing pattern); a
   worker failure must not orphan `in_progress` rows beyond what `reset_in_progress_segments`
   already reclaims.
7. **Test enablers (ship first):** `FakeProvider` gains a `latency_seconds` knob and optional
   synthetic token usage — without it no honest concurrency/scaling test exists (it currently
   returns instantly with `usage=None`).

## Trade-offs

| Option | Throughput | Quality | Complexity | Verdict |
|--------|-----------|---------|------------|---------|
| **Bounded thread window (this ADR)** | 2–4× live, proven by scaling bench | Window sees committed-only context; bounded, opt-in | Locked cold-mark, per-worker connections | **Accepted shape** |
| Sequential (status quo) | 1× | Exact today's semantics | none | Remains the default (`max_concurrent = 1`) |
| asyncio rewrite of services | same ceiling | same | rewrites the service layer; violates the asyncio fence (§3.2) | Rejected |
| Process pool | same ceiling | same | SQLite cross-process + memory duplication + Windows spawn cost | Rejected |
| External queue/worker daemon | higher ceiling nobody needs | same | banned (§3.5); wrong size for a single-user tool | Rejected |

**Risks:** WAL writer contention between workers (mitigated: commits are milliseconds, calls are
seconds, `busy_timeout = 10000`); provider-side rate limits surfacing as `ProviderError` storms
(mitigated: existing per-segment fallback + cold-mark; cap stays at 4); subtle test flakiness
(mitigated: deterministic FakeProvider latency + seeds).

## Consequences

- Live chapter/batch throughput scales ~linearly to the window size (target ≥ 2.4× at 3 workers
  on the 300 ms-latency bench; ≥ 2× on a live spot-check).
- The default experience is unchanged; the entire pre-existing suite must pass with the feature
  merged and unconfigured.
- The D9 lean fence holds: no circuit breaker, health score, or autoscaling — a fixed bounded
  window only.
- Failure stays visible: per-segment failures mark `failed` exactly as today; concurrency never
  retries beyond the existing bounded chain.

## Decision points settled at Gate B (2026-07-21, owner)

1. **Window-gap policy** — **plain last-N-committed window.** In-flight neighbors stay invisible.
   Block-order dispatch with a capped gap was rejected: added coordination and reduced throughput
   for an unmeasured quality gain, on a window already capped at ≤ 5 segments / 1000 tokens.
2. **Connection lifecycle** — **per-worker persistent connection** for the run. M1 established
   that connection-open count is material; per-segment open would pay open + migration-check on
   every segment.
3. **Cold-mark structure** — **`threading.Lock` around the existing dict** (Decision Rule 1:
   prefer existing architecture over a new abstraction). See Decision 5 for its actual scope.

## Related files

`services/translation.py` (`translate_project`, `translate_one_segment`),
`services/workspace_translate.py` (`run_translation`), `services/batch_translate.py`,
`storage/db.py`, `storage/translations.py`, `providers/fake.py`, `core/config.py`,
`bench/run_performance_budgets.py`.
