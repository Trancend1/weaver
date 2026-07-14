# Execution Plan — v0.7.3 Performance & Reliability Release (ADR 020 draft, P0/P1)

**Status:** 📋 Planned — Gate A (scope + exit criteria) defined 2026-07-05; no implementation
started. Baseline: tag `v0.7.2` + PR #56 merged (audit blockers H1–H3), suite 1614 passed.
**Governs:** the v0.7.3 release: measurable translation-pipeline performance wins + closure of
the full v0.7.2 audit carry-forward ledger (Medium/Low findings A1–A8). No feature ships unless
it directly improves speed, accuracy, reliability, or maintainability.
**Branch target:** one branch + one PR per milestone (`perf/…`, `fix/…`, `feat/…` below).
**Companion:** [ADR 020 — Bounded Translate Concurrency](../../decisions/020-bounded-translate-concurrency.md)
(Proposed; must be Accepted before M4 implementation).

---

## Evidence baseline (2026-07-05 investigation)

| # | Finding | Anchor |
|---|---------|--------|
| F1 | Provider calls strictly sequential in all 3 drivers; segment N+1 waits for N's commit. Dominant live wall-clock cost. | `services/translation.py:338-382`, `services/workspace_translate.py:261-303`, `services/batch_translate.py:353-373` |
| F2 | Rolling-window query is O(n²) across a run: `WITH latest AS (SELECT segment_id, MAX(attempt) FROM translations GROUP BY segment_id)` aggregates the whole table, unscoped, once per provider-bound segment. | `storage/translations.py:172-191` |
| F3 | No `PRAGMA synchronous` → FULL under WAL; 2 commits/segment ≈ 20k fsyncs per 10k-segment novel. `connect_readonly_database` sets no pragmas at all (0 ms busy_timeout). | `storage/db.py:147-157`, `storage/db.py:81-104` |
| F4 | `list_connections` parses `connections.toml` N+1 times per call; `list_connection_views` parses `secrets.toml` once per connection. Hit on every providers/routing render. | `core/connection_registry.py:90-93`, `services/connections.py:191-224` |
| F5 | `discover_projects` is uncached (parses every project.toml + opens every project DB); called twice per providers-hub render and every 3 s by the queue poll; runs before the workspace-index 5 s cache check, largely defeating it. | `services/project_discovery.py:55`, `services/workspace_index.py:90`, `services/workspace_queue.py:90,180`, `api/templates/queue_hub.html:12` |
| F6 | Up to 3 sequential network round-trips per segment: primary + JSON-parse-repair + enforcement repair; plus silent openai-SDK default retries (`max_retries` never set). | `providers/openai_chat.py:102-122`, `services/translation.py:586-621` |
| F7 | Hoistable per-segment CPU: `_filter_glossary` re-casefolds the source inside the per-term loop (same pattern in `check_glossary_mismatch`); `sync_document_segments` inserts per-row (doc mandates `executemany`); segment-editor render runs `PRAGMA table_info(segments)` per view. | `services/translation.py:140-153`, `qa/checks.py:185-220`, `storage/segments.py:79-88`, `services/workspace_context.py:171` |
| F8 | Already good (do not touch): TM exact-match index-backed; prompt templates `@cache`d; glossary/characters/provider/config hoisted per-run; OpenAI client reused; SSE throttled 1/s; Gate B1 held everywhere. | `providers/prompts.py:16-37`, `services/translation.py:280-330` |

**Honest impact framing:** on live runs, provider latency (seconds/segment) dwarfs local costs.
M1's DB/CPU wins buy large-project scalability (killing O(n²) growth) and cockpit snappiness;
**M4 concurrency is the only lever that multiplies live throughput.** GPU efficiency is N/A —
Weaver runs no local inference (Ollama is an external server).

---

## Scope & non-goals (whole release)

**In scope:** milestones M1–M5 below — algorithmic/storage quick wins, the full audit
carry-forward (A1–A8), enforcement provenance + cost accounting (one schema decision),
opt-in bounded translate concurrency (ADR 020), and the validation/release gate.

**Out of scope (explicit non-goals):**
- **Streaming responses** (owner-confirmed defer): strict-JSON `response_format` means streaming
  cannot shorten batch runs; only perceived single-segment latency, at incremental-parser cost.
- Circuit breaker / health scores / presets / routing ledger (ADR 018 D9 fence stands).
- Fuzzy TM matching (quality risk; separate proposal if ever), new provider families,
  `asyncio` outside the web layer, external queue/worker daemon, SPA/Node, telemetry (§3.4/§3.5).
- Deferred memory items (assessed, low-leverage, **no scaffolding**): upload full-buffering
  (bounded ≤ 200 MB by the zip-bomb ceiling; `api/routers/projects.py:99,181,424`,
  `api/routers/ui.py:427,473`), EPUB `ZipFile` re-opens at init (`readers/epub.py:185-1229`),
  DOCX in-memory build (`renderers/docx.py:202`).
- No speculative cache layers: fix the callers (F4/F5) instead of adding caches. Also fix the
  stale doc claim of a "glossary LRU cache" (`docs/SECURITY_AND_PERFORMANCE.md:183` — documented
  but never implemented).

**Hard-rule fences (must hold every slice):**
- Gate B1: zero provider calls / hashing / QA scans on render paths.
- One segment **result** = one atomic commit; provider network calls never inside an open
  transaction (H3 shape, CLAUDE.md §4.2).
- Failure visible, never silently substituted; cost (incl. repair/retry round-trips) visible.
- No new runtime dependency; no new architectural layer; default behavior of every change is
  today's behavior unless the milestone says otherwise (M4 defaults to `max_concurrent = 1`).
- Every perf change lands with a bench budget or scaling probe; >20% regression on an existing
  budget needs explicit justification (`docs/SECURITY_AND_PERFORMANCE.md` §Benchmark Suite).

---

## Milestone M1 — Algorithmic & storage quick wins (P0, `perf/v073-storage-quick-wins`)

**Goal:** remove the measurable local waste on the translate hot path and the cockpit render
paths, with zero behavior change.

**Slices (anchors):**
- **M1.1** `PRAGMA synchronous = NORMAL` in `_open_database` (`storage/db.py:147-157`); add
  `busy_timeout` (+ modest `cache_size`) to `connect_readonly_database` (`storage/db.py:81-104`).
  NORMAL under WAL risks only last-txn loss on OS crash (never corruption) —
  `reset_in_progress_segments` is already the crash net for exactly that window.
- **M1.2** Scope the F2 CTE to the chapter (filter inside the CTE), fixing
  `list_previous_translated_segments` (`storage/translations.py:153-192`) and the same CTE shape
  in `list_export_segment_states` (`storage/translations.py:211-253`) for consistency. If the
  scaling probe still shows growth, escalate to an in-memory window maintained across the chapter
  loop (follow-up, not default).
- **M1.3** (=A6) Single-parse `list_connections` (`core/connection_registry.py:90-93`); memoize
  `load_secrets` within one `list_connection_views` call (`services/connections.py:191-224`).
- **M1.4** (F5) Per-request reuse of `discover_projects` results on the providers hub (both
  consumers share one result) + fold discovery under the existing `workspace_index` 5 s mtime
  cache (`services/workspace_index.py:65-105` `_CacheKey` pattern); give `build_workspace_queue`
  (`services/workspace_queue.py:90,180`) the same treatment. No new cache layer.
- **M1.5** (F7) Hoist casefolds out of the per-term loops (`services/translation.py:140-153`,
  `qa/checks.py:185-220`); `executemany` in `sync_document_segments` (`storage/segments.py:79-88`);
  add `idx_glossary_candidates_project`; drop or one-shot-cache the per-render
  `PRAGMA table_info(segments)` (`services/workspace_context.py:171`) — verify first that
  read-only paths can never see a pre-v10 DB (migrations run on writable connect only); if they
  can, keep the guard with a cached result.

**Bench additions (land in this milestone):** in `bench/run_performance_budgets.py` —
(1) flat-cost scaling probe: per-segment fake-translate time, first-100 vs last-100 on the 10k
fixture, delta < 20%; (2) render-path budget for the providers-hub and queue builds.

**Acceptance:**
- Identical query results for M1.2 proven by a regression test against the current pairs.
- Providers/routing render: ≤ 1 parse of `connections.toml` and ≤ 1 of `secrets.toml` per render;
  queue poll: ≤ 1 DB open per project per poll (asserted via counting seams in tests).
- Existing budgets green; new probes green; full gate green.

**Non-goals:** no schema change beyond the one new index; no cache invalidation redesign.

---

## Milestone M2 — Reliability carry-forward, small fixes (P0, `fix/v073-audit-carryforward`)

**Goal:** close the small audit findings, including the one silent-data-loss edge.

**Slices (anchors):**
- **M2.1** (A2+A7, coupled) Shared TOML escape helper covering `\n`, `\r`, `\t`, C0 controls —
  replaces the 3 identical incomplete `_escape` copies (`core/connection_registry.py:199-200`,
  `core/secret_store.py:155-156`, `services/config_writer.py:379-380`). Keep tolerant **reads**
  (`load_connections` `core/connection_registry.py:76-79`, `load_secrets`
  `core/secret_store.py:63-66`); on **write**, if the existing file is present-but-unparseable,
  back it up to `<file>.corrupt-<timestamp>` before rewriting — never silently destroy.
  Round-trip tests for control-char values.
- **M2.2** (A1) Dead primary no longer aborts a run that has a configured fallback chain: on
  primary healthcheck failure, warn + let the per-segment try-next chain (which already
  cold-marks and advances) carry the run; abort only when no candidate is healthy.
  `services/translation.py:280-289`, `services/workspace_translate.py:417-440`
  (`build_healthy_provider`); update `tests/integration/test_cli_healthcheck.py` expectations.
- **M2.3** (A3) Preserve the legacy brand in attempt history: stop clobbering `type` at
  `providers/registry.py:108` (`normalize_provider_config` — docstring already promises brand
  preservation); engine name at `providers/registry.py:174` derives from the preserved brand.
  Verify `tests/unit/services/test_provider_config.py` parametrized brands.
- **M2.4** (A8) `weaver inspect` routes through `services/routing` resolution like the translate
  path instead of reading raw `[provider]` (`services/project.py:244-275`); verify
  `tests/integration/test_cli_epub_inspect.py`, `test_cli_inspect_percentages.py`.

**Acceptance:**
- A corrupt `connections.toml`/`secrets.toml` is never destroyed by a subsequent write; the
  backup file exists and the user-facing error names the backup path.
- Dead primary + healthy fallback → run completes on the fallback (e2e test); dead primary +
  no fallback → today's abort message unchanged.
- A legacy `type = "deepseek"` project records `provider="deepseek"` on new attempts.
- `weaver inspect` on a connection-first project shows the resolved Active AI, not a KeyError.

**Non-goals:** no healthchecking of fallbacks at pre-flight beyond what M2.2 needs (per-segment
chain stays lazy); no registry format change.

---

## Milestone M3 — Enforcement provenance + cost accounting (P1, `feat/v073-enforcement-provenance`)

**Goal:** enforcement outcomes become persistent, visible, and cost-reconciled (A4+A5, coupled),
and hidden round-trips become countable (F6).

**Slices (anchors):**
- **M3.1** (A4a) Move `evaluate_translation` out of the `if enforce_repair:` block in
  `translate_one_segment` (`services/translation.py:586-595`) — detection always runs; the flag
  gates only the repair re-ask, matching the `enforce_repair_enabled` docstring
  (`services/translation.py:709-712`) and the ADR 019 plan.
- **M3.2** (A4b+A5) Persist verdicts/repair outcomes and reconcile tokens. **Recommended shape
  (settle at Gate B):** columns on `translations` (migration **v14** — M1.5 took v13 for
  `idx_glossary_candidates_project`, so `SCHEMA_VERSION` is already 13) — violations JSON,
  `repair_attempted`/`repair_outcome`, repair token columns. Provenance belongs on the attempt
  row; avoids a new join on read paths; A5 resolves by construction (row carries final-attempt
  tokens + repair delta; run summary = sum of rows). Surface in the run summary
  (`TranslationRunSummary`, `services/translation.py:386-396`) and the segment editor
  (read-only render — Gate B1: no new writes on render). Old rows render as "not evaluated".
- **M3.3** (F6) Pin explicit `max_retries` on the OpenAI client (`providers/openai_chat.py:194-203`,
  today's silent SDK default) and count JSON-repair + enforcement-repair calls into the run
  summary, so "cost is visible" (§4.3 gate 6) covers hidden round-trips.

**Acceptance:**
- `enforce_repair = false` → detection still runs and persists findings; zero repair calls.
- Per-segment row tokens + run summary reconcile exactly on a repaired fixture
  (`sum(rows) == summary`, incl. repair).
- Migration v14 forward-tested + idempotent (T4 rules); pre-v14 DB opens and renders cleanly.
- Run summary shows repair/JSON-repair call counts.

**Non-goals:** no `[routing.repair]`/`TaskType.repair` (seam stays declared, ADR 019 §5);
no violation-blocking behavior (findings stay visible, never blocking); no QA-page redesign.

---

## Milestone M4 — Bounded translate concurrency (P1, `feat/v073-bounded-concurrency`, ADR 020)

**Goal:** opt-in `[translation] max_concurrent = 1..4` (default **1** = today's behavior
bit-for-bit). A bounded in-process worker window inside the existing per-job thread — no external
queue/daemon (§3.5). **Blocked until ADR 020 is Accepted.**

**Slices (anchors):**
- **M4.1 Enablers first:** `FakeProvider` gains a `latency_seconds` knob + optional synthetic
  token usage (`providers/fake.py` — today it returns instantly with `usage=None`, so no honest
  concurrency test is possible); concurrency scaling bench (300 ms fake latency, 3 workers vs 1).
- **M4.2 Core:** bounded window in `translate_project` (`services/translation.py:338-382`) and
  `run_translation` (`services/workspace_translate.py:261-303`); per-worker SQLite connections
  (sqlite3 connections are not shareable across threads); `run_cold` cold-mark dict behind a
  lock; `in_progress` marker + result commit stay per-segment short txns (H3 shape).
- **M4.3 Surfaces:** `[translation] max_concurrent` parsed in `core/config.py` (validated 1–4,
  absent = 1), cockpit field on the translate panel, CLI flag.

**Decision points (settle in ADR 020 at its Gate B — see the ADR for the full table):**
rolling-window semantics under concurrency (window = last N *committed* segments; in-flight
neighbors invisible; bounded quality trade-off, opt-in only); TM upsert races on identical
`(project_id, source_hash)` (last-writer-wins upsert is benign — verify `protect_manual` holds);
cancellation/failure inside the window must not orphan `in_progress` rows.

**Acceptance:**
- `max_concurrent = 1` (default): entire existing suite passes unchanged; byte-identical prompts.
- Scaling bench: 3 workers ≥ 2.4× vs sequential at 300 ms fake latency.
- Kill/cancel mid-window leaves no orphan `in_progress` rows after `reset_in_progress_segments`.
- Fallback chain + cold-marking correct under concurrency (test with `fail_rate` + latency).

**Non-goals:** no asyncio rewrite, no process pool, no concurrency for glossary-suggest/candidate
tasks, no dynamic autoscaling — a fixed bounded window only.

---

## Milestone M5 — Validation, live checks, release gate (P0 to ship, `chore/v073-release-gate`)

- Full bench suite + acceptance gate (`bench/run_acceptance_gate.py` AC-1..AC-9) green;
  before/after numbers for F2/F3/F5 + the scaling probe recorded in the gate report handoff.
- **Live validation (owner-run):** Gemini over `…/v1beta/openai` (the H2 endpoint fix has never
  been proven against a live key; pick a current default model — `gemini-1.5-flash` is retired
  upstream) and Ollama over `:11434/v1`. Add the missing `requires_cloud` Gemini test and the
  first `requires_ollama` test (marker declared in `pyproject.toml:94` with zero usages today).
- **E2 repair token-cost delta** measured on a live run (M3.3 makes it visible) → owner decision
  to keep `enforce_repair` default-on.
- Concurrency live spot-check at `max_concurrent = 2` on a real endpoint.
- CHANGELOG, version bump (pyproject single source + drift guard), regression checklist per
  `docs/MAINTENANCE.md`, tag `v0.7.3`.

---

## Sequencing & gates

```
M1 (quick wins) ──► M2 (carry-forward) ──► M3 (provenance/cost) ──► M4 (concurrency, ADR 020) ──► M5 (gate)
   │ flat-cost probes + idx v13 land here      │ migration v14           │ blocked on ADR 020 Accepted
```

- One milestone = one branch = one PR. Each slice: `uv run ruff check .` + `ruff format --check .`
  + `pyright` + `pytest -q -m "not requires_cloud and not requires_ollama"` green before the next.
- Gate B1 check per milestone: no provider/QA/hashing work added to any render path (M3.2's
  segment-editor surfacing is read-only).
- Per-milestone handoff note (§8) with bench evidence pasted.
- M1/M2 are independently shippable; M3 before M4 so concurrency tests can assert cost
  reconciliation; M4 is the only milestone that may slip to v0.7.4 without breaking the release
  (M1–M3+M5 still ship a coherent perf+reliability release — decide at M3 exit).

## Release exit criteria (mirrors CLAUDE.md §2.4)

1. Throughput: `max_concurrent = 3` ⇒ ≥ 2.4× chapter wall-clock vs sequential on the
   latency-simulating FakeProvider bench; live spot-check ≥ 2×.
2. Scalability: fake-provider per-segment cost flat across the 10k fixture (last-100 vs
   first-100 delta < 20%).
3. Cockpit latency: providers-hub + queue renders do ≤ 1 TOML parse per file and ≤ 1 DB open per
   project per render.
4. Reliability: A2/A7 silent-data-loss closed; A1 dead-primary fallback works; enforcement
   outcomes persisted + surfaced (A4).
5. Accuracy accounting: row tokens reconcile with run summary incl. repair (A5); attempt history
   records the real brand (A3); `weaver inspect` routing-aware (A8).
6. No regressions: existing budgets + acceptance gate + full suite green; Gate B1 intact.

## Open implementation decisions (settle at each milestone's Gate B, not now)

1. **M1.5 `PRAGMA table_info` guard** — drop vs one-shot cache; depends on whether read-only
   paths can ever see a pre-v10 DB.
2. **M3.2 persistence shape** — columns on `translations` (recommended) vs side table; decide
   with the migration diff in hand.
3. **M4 window-gap policy** — plain last-N-committed window vs block-order dispatch with a
   capped gap; decide in ADR 020 with the quality trade-off written down.
4. **M2.1 corrupt-file behavior** — backup-then-rewrite vs refuse-and-error; pick after checking
   which the cockpit error surface renders more actionably.
