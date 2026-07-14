# Handoff: v0.7.3 M1 — Bench baseline + storage/algorithmic quick wins

**Track:** T8 (Performance & Runtime) + T4 (Storage) + T0 (Docs)
**Branch:** `perf/v073-storage-quick-wins` (one milestone = one branch = one PR)
**Date:** 2026-07-13
**Scope:** Execution plan M1 (`docs/superpowers/specs/2026-07-05-v073-performance-execution-plan.md`) + audit N1 (`audit_weaver_073.md`). Remove measurable local waste on the translate hot path and cockpit render paths with **zero behavior change**, and restore the broken bench baseline.

## What changed (by slice)

**Slice 1 — N1 (bench baseline restored, prerequisite):**
- `bench/run_performance_budgets.py` `_rewrite_project_for_fake`: v0.7.2 `weaver init` writes `[provider] type = ""` (empty protocol), so the old `type = "deepseek"` string-replace no-oped and translate/export/validate budgets never ran. Now replaces the **whole `[provider]` table** (regex, `count=1` guard) with the canonical fake block (`protocol = "fake"`) including `pattern = "Translated sentence."` (clean English so `weaver validate` stays exit 0 — the default `[FAKE] {source}` pattern retains Japanese and trips `untranslated_japanese` criticals → validate exit 1).
- `bench/run_acceptance_gate.py`: **same N1 bug fixed identically** (its own `_rewrite_project_for_fake` + the `_provider_unavailable` scenario, which now flips `protocol = "fake"` → `openai_chat` at an unreachable endpoint instead of the removed `type = "fake"` brand). Not named in the M1 slice but required by the "acceptance gate green" exit criterion and broken by the same root cause.

**M1.1 — pragmas (`storage/db.py`):** `PRAGMA synchronous = NORMAL` in `_open_database`; `busy_timeout = 10000` + `cache_size = -8000` in `connect_readonly_database`. NORMAL under WAL risks only last-txn loss on OS crash (never corruption); `reset_interrupted_segments` is the existing crash net.

**M1.2 — chapter-scoped rolling-window CTE (`storage/translations.py`):** both `list_previous_translated_segments` and `list_export_segment_states` scope the `latest` CTE to the chapter(s) via `JOIN segments ... WHERE chapter_id`. A segment belongs to exactly one chapter, so `MAX(attempt)` is unchanged → **byte-identical results** (pinned by `tests/unit/storage/test_translations_window.py`, which runs the pre-M1.2 global CTE inline as an oracle).

**M1.3 — single-parse config (`core/connection_registry.py`, `services/connections.py`):** `list_connections` parses `connections.toml` once (was twice); `list_connection_views` parses `secrets.toml` once and threads the pre-parsed name set into every card (was once per connection). Counting-seam test in `test_connections.py`.

**M1.4 — shared discovery cache (`services/project_discovery.py` + index/queue/providers + routers):** new opt-in `cache`/`ttl_seconds` params on `discover_projects` (default `None` = pre-v0.7.3 uncached behavior for all non-render callers), folded under the existing `app.state.workspace_cache` with a `discover:` key prefix. Wired into `build_workspace_index`, `build_workspace_queue` (new param), `build_workspace_providers` (new param), and the providers-hub `_config_ctx`. Steady-state queue poll now opens each project DB **once** (jobs only; discovery served from cache) — counting-seam tests in `test_workspace_queue.py` (warm = 2 opens / 2 projects; uncached = 4).
  - **Key discovery:** the cache key is `(toml_mtime, db_mtime)` only — **not** `-wal` mtime. A read-only inspect creates/touches the `-wal`, so a wal-sensitive key misses on the `-wal` absent→present transition (the queue seam test caught this for the discovery cache).
  - **Follow-up (corrected finding):** I initially flagged `workspace_index`'s `_CacheKey` as "silently defeated" the same way. On investigation that is **false** — its entry cache hits reliably (probe: 0 DB reopens on warm rebuild, even across a forced `-wal` transition), because `discover_projects` runs first and creates the `-wal` before the entry key is computed. That correctness, however, *relied on that side-effect ordering* (a fragile implicit coupling), and its key still carried `wal_mtime` while the discovery cache no longer did. **Fix applied:** unified `workspace_index._CacheKey` onto the same `(toml_mtime, db_mtime)` key (dropped `wal_mtime`), removing the implicit ordering dependency. Regression test `test_index_warm_rebuild_reopens_nothing_across_wal_transition` asserts 0 reopens across the transition. No behavior change beyond the identical bounded-staleness tradeoff already accepted for discovery.

**M1.5 — hoists / batching / index:**
- Casefold hoisted out of per-term loops in `_filter_glossary` (`services/translation.py`) and `check_glossary_mismatch` (`qa/checks.py`).
- `sync_document_segments` (`storage/segments.py`) now uses two `executemany` upserts (chapters then segments, FK order) instead of a per-row SELECT+INSERT loop; the segment upsert expresses the same stale-marking rule as `insert_segment`.
- `idx_glossary_candidates_project` added to `schema.sql` **and** migration **v13** (`SCHEMA_VERSION` 12 → 13; idempotent `CREATE INDEX IF NOT EXISTS`, table-existence guarded for the minimal test DBs). Forward + idempotency + fresh-DB tests added.
- **`PRAGMA table_info(segments)` guard (`workspace_context.py:172`): retained, not dropped.** `_segment_row` runs on a read-only connection with no schema-version gate before it, so a pre-v9 DB could reach it; a module-level cache would be unsafe across mixed-version DBs and it is one PRAGMA per single-segment render (not a hot loop). The plan explicitly permits keeping the guard.

**Doc cleanup:** removed the fictional "LRU cache on glossary term lookups" claim (`docs/SECURITY_AND_PERFORMANCE.md:183`, never implemented).

## ⚠ Roadmap drift flagged (decision rule #7)

The plan/CLAUDE.md label M3's enforcement-provenance migration as **"migration v13"**. M1.5's index legitimately needs a migration first, so it took **v13** and `SCHEMA_VERSION` is now **13**. **M3's provenance migration must become v14.** Update the execution plan + CLAUDE.md §2.3 M3 row when M3 starts. No code impact today.

## Validation (evidence)

- `uv run ruff check .` → **All checks passed**; `ruff format --check` clean; `uv run pyright src` + bench files → **0 errors**.
- `uv run pytest tests/unit -q` → **1485 passed, 1 skipped**.
- `uv run pytest tests/integration -q` → **139 passed, 1 skipped**.
- Full marked suite (`-m "not requires_cloud and not requires_ollama"`): see PR (run in progress at write time).
- **Bench** (`run_performance_budgets`, 10k-segment fixture, owner machine): all budgets PASS. Translate **0.64 ms/seg**; **rolling-window flat cost 1.009×** (first chapter 82.4µs vs last 83.2µs) — was 1.96× on the audit's fresh run, exit criterion (< 1.2×) **met**. New render budgets: providers-hub 0.039s, queue 0.036s (< 2s).
- **Acceptance gate** (`run_acceptance_gate`): **ALL PASS (AC-1…AC-9)**, incl. AC-9 provider-unavailable exit=3.

## Not changed (scope boundaries)

No schema change beyond the one index; no cache-invalidation redesign; `workspace_index._CacheKey` untouched; no provider/QA/hashing added to any render path (Gate B1 held); default behavior of every runtime path is today's behavior (`discover_projects` cache is opt-in).

## Recommended next role / next step

**Release Captain / Orchestrator:** open the M1 PR from `perf/v073-storage-quick-wins`. Then **M2** (`fix/v073-audit-carryforward`) — reliability + input-safety carry-forward. Before M3, renumber its migration to **v14** (see drift note above).
