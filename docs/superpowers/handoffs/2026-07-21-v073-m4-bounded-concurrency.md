# Handoff: Backend Engineer — v0.7.3 M4 Bounded Translate Concurrency

**Track:** T3 (Backend/API & Services) + T8 (Performance & Runtime)
**Date:** 2026-07-21
**Branch:** `feat/v073-bounded-concurrency` (21 commits, `337e82d`…`2fc8f5d`) — **not merged, not pushed**
**ADR:** [020](../../decisions/020-bounded-translate-concurrency.md) — raised **Proposed → Accepted (2026-07-21)** in `337e82d`
**Plan:** [2026-07-21-v073-m4-bounded-concurrency.md](../plans/2026-07-21-v073-m4-bounded-concurrency.md) (11 tasks, all done)

---

## Scope

Opt-in `[translation] max_concurrent = 1..4` bounded worker window so a live
translate run overlaps 2–4 provider calls instead of running strictly
sequentially. **Default 1 reproduces pre-M4 behavior bit-for-bit** — no
executor, no threads, sequential dispatch on the calling thread.

Unlocked by the v0.7.2 audit fix `dee710f`, which moved provider network calls
outside SQLite write transactions.

## Files / Areas Touched

| Area | Files |
| --- | --- |
| New runner (sole home of translate-loop thread code) | `src/weaver/services/segment_runner.py` (214 lines) |
| Config validation + `translate_project` wiring | `src/weaver/services/translation.py` |
| Chapter path + plan field | `src/weaver/services/workspace_translate.py` |
| Batch hand-off | `src/weaver/services/batch_translate.py` |
| Storage lock acquisition | `src/weaver/storage/db.py` |
| Provider latency knob | `src/weaver/providers/fake.py` |
| CLI flag | `src/weaver/cli/main.py` |
| Cockpit field | `src/weaver/api/routers/translate.py`, `ui_workspace.py`, `templates/workspace.html` |
| Bench | `bench/run_performance_budgets.py` |
| Tests | `test_segment_runner.py` (new), `test_translation.py`, `test_translation_orchestrator.py`, `test_workspace_translate.py`, `test_batch_translate.py`, `test_db.py`, `test_cli_translate.py`, `test_ui_workspace.py`, `test_fake_provider.py` |

## What Changed

1. **`run_segment_window`** — one public function, generic over item/result/
   connection types. `max_concurrent == 1` → sequential on the calling thread.
   Otherwise a hand-rolled worker pool: one persistent connection per worker
   thread, `on_complete` serialized under a progress lock, completion ordinals
   dense and 1-based, cooperative cancel checked before each dispatch.
2. **`ColdMarks`** — the per-run ADR 018 D4 fallback cold-mark dict moved behind
   a lock. **Defensive, not a bug fix** (see Known Risks).
3. **Both segment loops** (`translate_project`, `run_translation`) delegate to
   the runner. `batch_translate` inherits through the chapter plan.
4. **Surfaces**: `weaver translate --max-concurrent N`, and a 1–4 select on the
   cockpit chapter translate form defaulting to "project setting".
5. **`BEGIN` → `BEGIN IMMEDIATE`** in `storage/db.py` — see below.

## What Was Intentionally Not Changed

- No asyncio outside the web layer, no process pool, no external queue, no
  worker daemon (CLAUDE.md §3.5 / ADR 020 D9 fence).
- No autoscaling, circuit breaker, health scores, or presets. The cap is a
  fixed 4.
- No change to the rolling context window: plain last-N-committed is the
  existing `list_previous_translated_segments` behavior, now made explicit by
  committed-only visibility.
- `run_translation` keeps its inline `failed += 1`; `translate_project` keeps
  reading final counts from the database. The difference is deliberate.

## Validation Performed

All commands run on the owner machine at `2fc8f5d`.

```
uv run ruff check .          → All checks passed!
uv run ruff format --check . → 393 files already formatted
uv run pyright               → 0 errors, 0 warnings, 0 informations
uv run pytest tests/ -q      → 1731 passed, 2 skipped (302.56s)
```

Bench (`PYTHONPATH=. uv run python bench/run_performance_budgets.py`, **exit 0**,
read without a pipe per the M1 phase-log warning):

| Budget | Target | Measured | Result |
| --- | --- | --- | --- |
| translate concurrency scaling | ≥ 2.4× speedup | **2.77×** | PASS |
| rolling-window flat cost | < 1.2× growth | 0.90× | PASS |
| weaver translate fake provider | < 50 ms/segment | 0.65 ms/segment | PASS |

Acceptance gate (`bench/run_acceptance_gate.py`, **exit 0**): AC-1…AC-9 **PASS**.

### Mutation evidence (tests proven load-bearing, not vacuous)

Every concurrency test below was verified by deliberately breaking the
implementation and confirming the test fails, then restoring:

| Contract | Mutation | Result |
| --- | --- | --- |
| Segment ordering (sequential) | `selected = reversed(selected)` | FAILS |
| Concurrency actually engaged (`translate_project`) | force `max_concurrent = 1` | FAILS (2.04 < 2.04×0.6) |
| Concurrency actually engaged (`run_translation`) | force `max_concurrent = 1` | FAILS (1.42 < 1.41×0.6) |
| Batch inherits the window | drop `max_concurrent=` from the plan | FAILS (`At index 0 diff: 1 != 3`) |
| Cockpit override reaches the plan | drop the `replace(plan, …)` | FAILS (`assert seen == [3]`) |
| Connection closed on every path | remove `finally: connection.close()` | 2 tests FAIL |
| Factory failure propagates | move the open outside the `try` | 2 tests `DID NOT RAISE` |
| Earliest-**dispatched** failure re-raised | wall-clock-ordered failure list | FAILS |
| `BEGIN IMMEDIATE` | revert to plain `BEGIN` | FAILS, 3 of 4 workers `database is locked` |

## Known Risks

1. **`BEGIN IMMEDIATE` is a storage-layer change riding in the M4 PR.** It
   affects all 36 `with transaction(...)` call sites, not just the translate
   path. It is **load-bearing for M4**, not incidental: the hot-path result
   transaction opens with `record_translation()`, whose first statement is
   `SELECT MAX(attempt)` — the read-then-upgrade shape SQLite reports as
   immediate `SQLITE_BUSY` *without* invoking the busy handler. Probe: 4
   threads × 40 transactions → plain `BEGIN` 121/160 errors in 0.055 s (proving
   the 2 s busy timeout was never consulted); `BEGIN IMMEDIATE` 0/160.
   History was deliberately **not** rewritten to split it out, because the
   Task 6 wiring commit is broken without it. All 36 sites were read: none is
   read-mostly or long-running-read, and `transaction()` requires a writable
   connection, so no cockpit render path can reach it (Gate B1 intact). Net
   behavior shift: a POST-path write contending with a running concurrent job
   now *waits* up to `busy_timeout` (10 s) instead of erroring — an improvement
   over the previous `OperationalError` → 500, but worth watching in M5.
2. **A partially-successful concurrent run surfaces as a bare exception.** Under
   `max_concurrent > 1` a segment failure does not halt dispatch (only
   `should_cancel` does), so later segments still translate and commit real
   writes; the earliest-**dispatched** failure is then re-raised and the summary
   object is discarded. The only route to actual run state is the database.
   This is ADR 020's designed behavior and is documented in both `Raises:`
   contracts — **but if M5 judges it unacceptable, changing it is a behavior
   change, not a docstring fix.**
3. **`ColdMarks` is defensive clarity, not a bug fix.** Today's two call sites
   are single dict operations, atomic under CPython's GIL, so the pre-existing
   race is benign (last-writer-wins on near-identical values). The lock keeps
   the invariant explicit if this ever becomes a read-modify-write. ADR 020
   Decision 5 was corrected so the permanent record does not overclaim.
4. **`services/translation.py` is 1105 lines**, well over the §4.2 400-line
   guidance (965 when the plan was written; M4 added the validator, `ColdMarks`,
   and the wiring closures). The `segment_runner.py` extraction reduced but did
   not resolve it. A split is a separate concern with its own plan — do not
   bundle it into a release gate.
5. **Timing tests are wall-clock assertions.** Thresholds are conservative
   (0.6× where the ideal is 0.33×) and were repeated without flake, but they are
   the kind of test that degrades on a loaded CI box. The 3-worker fixture in
   `test_translation_orchestrator.py` measures **2.34×**, just under the ≥2.4×
   exit criterion — that criterion targets the bench harness (2.77× PASS), not
   the unit test.
6. **Gate skipped:** the code-quality review stage was skipped for Task 5
   (`b320997`, 28 lines, followed the plan verbatim) under the CLAUDE.md §9
   gate-skip rule. Gate C (validation) was **not** skipped — spec review PASSed
   and the full unit suite ran.

### Process finding (for M5)

**The CLAUDE.md test-count baseline is not reproducible across environments.**
The recorded "1683 passed, 1 skipped" shifts with the machine:
`tests/integration/providers/test_openai_chat_live.py:17` skips when
`DEEPSEEK_API_KEY` is unset, and `tests/unit/core/test_secret_store.py:104`
skips off-POSIX. Measured here: full `tests/` collection 1691 → 1731 passed /
2 skipped. Treat recorded counts as evidence at time of writing, never as a
target to match.

## Recommended Next Role / Next Step

**Release Captain (T9) → M5 `chore/v073-release-gate`.**

Single next action: open the M4 PR (owner decision — nothing is pushed), then
start M5 with the live validations that M4 could not cover offline — Gemini over
`…/v1beta/openai`, the first `requires_ollama` test, the E2 repair token-cost
delta, and a live concurrency spot-check confirming ≥ 2× against a real provider
(the 2.77× above is a simulated-latency figure, not a network measurement).
