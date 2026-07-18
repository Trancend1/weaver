# Handoff: v0.7.3 M3 — Enforcement Provenance + Honest Cost Accounting

**Track:** T3/T4 (Backend + Data/Storage)
**Branch:** `feat/v073-enforcement-provenance` (stacked on `fix/v073-audit-carryforward` — merge order M1 → M2 → M3; this PR then shows only its own commits)
**Scope:** Close A4a/A4b/A5 (enforcement provenance + token reconciliation), F6+N2 (explicit `max_retries` + hidden round-trip visibility), and N7 (CJK-aware token estimator) per CLAUDE.md §2.3 M3 and the execution-plan M3 slices.

## Gate-B decisions settled

- **M3.2 persistence shape (open decision #2):** columns on `translations` (migration **v14**), not a side table — provenance lives on the attempt row, no new join on read paths, A5 resolves by construction. Columns: `enforcement_violations` (JSON array; **NULL = never evaluated** → pre-v14 rows/memory reuse/manual saves render "not evaluated"; `'[]'` = evaluated clean), `repair_attempted`, `repair_outcome` (`accepted`/`discarded`/`failed`, CHECK-constrained), `repair_input_tokens`/`repair_output_tokens`. The persisted verdict always describes the **committed** text (recheck violations when a repair was accepted; the original verdict otherwise).
- **A5 token identity:** row `input_tokens`/`output_tokens` = **primary call only** (previously the accepted repair's usage overwrote them — the A5 bug); repair spend has its own columns; run summary = Σ(primary + repair). Reconciliation is exact by construction and asserted by test.
- **N2 wire-or-delete:** **both, in the right places** — the dead `[translation] max_retries` init key is deleted (retries are transport-level, they never belonged under `[translation]`), and `max_retries` becomes an explicit `OpenAIChatConfig` field (default 2 = the SDK's previously-silent default, now pinned and per-connection configurable via `[provider] max_retries` / connection config).
- **N7 recalibration:** two-class estimator (`estimate_tokens`: CJK char ≈ 1 token, other ≈ ¼) shared by window trim + dry-run; `MAX_CONTEXT_TOKENS` 600 → **1000**. Rationale: the old flat `chars//4` label "600" really admitted ~1.5–2k JP tokens; a typical 5-pair LN window costs ~700 honest tokens, so 1000 preserves the common-case window while roughly halving the old worst-case real spend. PROMPT_DESIGN.md §context budget + token table and ADR 020's stale "600 tokens" reference updated.

## What Changed (one commit per slice)

| Slice | Commit | Change |
| --- | --- | --- |
| M3 storage | `a898753` | Migration **v14** + `schema.sql`: five provenance columns on `translations` (additive, idempotent, CHECK on `repair_outcome`; tolerant of table-less minimal test DBs). `SCHEMA_VERSION = 14`. `record_translation` accepts provenance kwargs (validates `repair_outcome`); `TranslationAttempt` carries them; `list_translation_attempts` decodes violations JSON defensively (malformed → "not evaluated", never a failed history read). |
| M3.1+M3.2 service | `d05a52c` | `translate_one_segment`: `evaluate_translation` moved **out** of the `enforce_repair` gate — detection always runs, the flag gates only the repair re-ask (matches the `enforce_repair_enabled` docstring + ADR 019). Verdict/repair outcome/repair tokens persisted on the row. Return type is now `SegmentTranslationOutcome` (dataclass; total spend + `repair_call_made`/`json_repair_used`) replacing the 4-tuple. `TranslationRunSummary`/`ChapterTranslationResult`/`BatchChapterOutcome`/`BatchTranslationResult` gain `repair_calls` + `json_repair_calls`. |
| M3.3 (F6+N2) | `4ba62f8` | `OpenAIChatConfig.max_retries` (default 2) passed to `OpenAI(max_retries=...)`; registry reads `[provider] max_retries` (int, ≥ 0). Dead `[translation] max_retries` deleted from the init template. `TranslationResponse.json_repair_used` + the openai_chat JSON-parse-repair path now **sums usage across both calls** (first call's tokens were previously dropped) and flags the repair; counted into run summaries. |
| N7 | `baccfb9` | `estimate_tokens` two-class heuristic (no new dependency); `_trim_window` + dry-run estimates use it; `MAX_CONTEXT_TOKENS = 1000`; `DRY_RUN_TOKENS_PER_CHAR` deleted; PROMPT_DESIGN.md + ADR 020 + docstrings updated. |
| Surfacing | `f735406` | CLI translate summary prints `Repair calls: enforcement N | JSON N` (only when non-zero); chapter-translate job terminal events + batch result JSON carry both counts; segment-editor history partial gains a read-only **Enforcement** column ("not evaluated" / "clean" / "N findings · repair <outcome>" with violations in the tooltip — Gate B1: same widened SELECT, no new queries, no writes); `/translations` history endpoint returns the full provenance per attempt. |

## What Was Intentionally Not Changed

- No `[routing.repair]`/`TaskType.repair` (seam stays declared, ADR 019 §5); no violation-blocking behavior (findings visible, never blocking); no QA-page redesign (M3 non-goals).
- Fallback/cold-mark chain, transaction shape (provider call outside txn, one atomic commit per segment result), and prompt rendering untouched.
- M4 concurrency: nothing scaffolded; still blocked on ADR 020 Accepted.
- PROMPT_DESIGN.md's aspirational 429-backoff prose not rewritten — the openai SDK does retry 429s within the now-explicit `max_retries` budget; a doc-accuracy pass can ride M5.

## Validation Performed

- Slice-level suites green after each commit (`ruff check` + `ruff format` + targeted pytest; `pyright` 0/0/0 at slices 2, 3 and the final gate).
- Key regression evidence:
  - `tests/unit/storage/test_migrations.py::test_apply_migrations_v14_*` (forward from a seeded v13 DB with data preserved, idempotent double-run, CHECK rejects bogus outcome, fresh DB parity) + `tests/unit/storage/test_translation_provenance.py` (roundtrip; NULL vs `[]` distinction; `ValueError` on unknown outcome).
  - `tests/unit/services/test_translation.py`: enforce_repair=False → verdict persisted, **zero** `complete()` calls; clean → `'[]'`; repair accepted/failed/discarded each with exact row-level token splits reconciling against the outcome.
  - `tests/unit/services/test_translation_orchestrator.py::test_run_summary_reconciles_exactly_with_row_tokens_including_repair` — **A5 acceptance:** `SUM(input+repair_input) == summary.input_tokens` (102 == 102) on a 6-segment fixture where every segment repairs; `...::test_enforce_repair_off_run_persists_findings_with_zero_repair_calls` — **A4a acceptance**; `...::test_run_summary_counts_provider_json_repair_calls` — F6.
  - `tests/unit/providers/test_openai_chat.py`: JSON-repair sums usage (100/40) + flags `json_repair_used`; `OpenAI(...)` receives `max_retries` (7 when configured, pinned 2 by default). `tests/unit/providers/test_registry.py`: `[provider] max_retries` validated (int, ≥ 0).
  - `tests/integration/test_cli_init_template.py::test_init_template_has_no_dead_max_retries_key` (N2).
  - `tests/unit/services/test_translation.py::test_estimate_tokens_*` + `test_window_budget_trims_japanese_windows_by_real_cost` (N7: JP window of ~1750 honest tokens keeps 2 pairs under the 1000 budget; the old estimator would have kept all 5).
  - `tests/unit/api/test_workspace_history.py` + `test_ui_workspace.py::test_history_renders_enforcement_verdict_read_only` (manual = "not evaluated"; seeded AI attempt renders findings + repair outcome).
- Final gate (2026-07-18): `ruff check` clean; `ruff format --check` clean; `pyright` **0 errors, 0 warnings**; full suite `-m "not requires_cloud and not requires_ollama"` **1683 passed, 1 skipped** (was 1653 at M2 — +30 new tests); `uv run python -m bench.run_performance_budgets` **all budgets PASS** (translate 0.92 ms/segment; rolling-window flat cost **0.97×**; providers-hub/queue renders 0.03/0.04 s) — migration v14 introduced no budget regression; `uv run python -m bench.run_acceptance_gate` **AC-1…AC-9 PASS**.

## Known Risks

- Old (pre-v14) attempt rows and memory-reuse/manual attempts intentionally render "not evaluated" — that is the honest state, not a data gap.
- `estimate_tokens` is a heuristic (two classes only); Korean/Cyrillic/etc. fall in the ¼ class. Fine for JP→EN; revisit only with evidence.
- The `MAX_CONTEXT_TOKENS` recalibration changes prompt composition for **long-segment** JP windows (they trim sooner and by honest cost). Typical LN prose keeps its 5-pair window; bench flat-cost probe unaffected (fake pattern is pure-English).
- `repair_calls` counts issued re-asks including ones that failed transport-level (the call was made; its cost may be invisible if the provider errored before usage was returned).

## Recommended Next Role / Next Step

Release Captain / owner: merge order **M1 PR → M2 PR → M3 PR** (this branch). Then decide at M3 exit whether **M4** (bounded concurrency) ships in v0.7.3 or slips to v0.7.4 — ADR 020 must be **Accepted** first either way; M5 (release gate) closes the milestone.
