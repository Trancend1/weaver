# Handoff: v0.7.3 M2 — Reliability + Input-Safety Carry-Forward

**Track:** T3/T7 (Backend + Security/Reliability)
**Branch:** `fix/v073-audit-carryforward` (based on `perf/v073-storage-quick-wins` — M1 must merge first; this PR then shows only its own commits)
**Scope:** Close the v0.7.2 audit carry-forward A1/A2+A7/A3/A8 plus the 2026-07-13 measured-audit input-safety findings N3/N4/N5 (CLAUDE.md §2.3 M2).

## What Changed (one commit per slice)

| Slice | Commit | Change |
| --- | --- | --- |
| M2.1 (A2+A7) | `631ce46` | New `core/toml_write.py`: `escape_toml_string` (covers `\n`/`\r`/`\t` + all C0/DEL via `\uXXXX`) replaces **4** identical incomplete `_escape` copies (`connection_registry`, `secret_store`, `config_writer`, and `project.py`'s `_escape_toml` — one more than the audit counted; folded in `119fdd3`). `guard_unparseable_toml`: a write over a present-but-unparseable `connections.toml`/`secrets.toml` moves it aside to `<file>.corrupt-<timestamp>` and raises `ConfigError` naming the backup; retry writes fresh. **Gate-B decision #4 settled: move-aside + error** (not backup-then-silent-rewrite) — the cockpit renders `WeaverError` strings inline, so the user sees the backup path and the retry path; a silent rewrite would hide the data loss. |
| M2.2 (A1) | `789b5a1` | `preflight_provider_chain` (in `services/translation.py`; replaces `workspace_translate.build_healthy_provider`): healthy primary = today's behavior; dead primary + healthy fallback = logged warning + run proceeds (per-segment try-next chain cold-marks and advances, ADR 018 D4); abort only when no candidate is healthy. Warning carried on `TranslationPlan`/`ChapterTranslationResult`/`BatchPlan`/`BatchTranslationResult`/`TranslationRunSummary`, echoed by CLI, included in job terminal events. No pre-seeding of the cold map — the first segment's failure cold-marks the primary exactly like a mid-run death (consistency over the one saved timeout). |
| M2.3 (A3) | `3ac0bbd` | `normalize_provider_config` no longer clobbers legacy brands to `"custom"`. New attempts record `provider="deepseek"/"gemini"/"ollama"`; cockpit provider view shows the real brand. |
| M2.4 (A8) | `119fdd3` | `inspect_project` resolves the provider via `services/routing.resolve_chain` (like translate); `--healthcheck` probes the resolved primary. Connection-first projects show the resolved Active AI. |
| N3 | `a78e55d` | `/projects/epub-preview` enforces `MAX_UPLOAD_BYTES` via shared `source_intake.ensure_upload_within_limit` (422, same message as create/import). |
| N4 | `28d8de5` | `readers/epub.py`: `read_epub` + `parse_epub_structure` reject archives whose central-directory declared uncompressed total exceeds `MAX_UNCOMPRESSED_BYTES` (1 GiB = 4× upload cap) **before** any parse. zipfile enforces declared sizes on extraction, so the bound is sound. Non-zip files fall through to the parser's own error. |
| N5 | `7e49abe` | Per-chapter import degradation (Gate-B decision: broken chapter = validation issue). `read_epub` skips an unparseable spine chapter and records it on new `DocumentIR.read_issues`; carried through `VolumeResult`/`InitResult`/`ImportVolumeResponse`; `weaver init`/`import` echo warnings; `volume.chapter_skipped` runtime event logged. **Measured nuance:** mildly broken markup (unclosed tags) is *repaired* by ebooklib/lxml and imports fine — only content unparseable even after repair (binary garbage, empty/truncated files) hits the skip path. |

## What Was Intentionally Not Changed

- No pre-flight healthchecking of fallbacks beyond first-healthy detection (per-segment chain stays lazy); no registry format change (M2 non-goals).
- Enforcement provenance/persistence, N2 (`max_retries` dead key), N7 (CJK token estimator) — M3 scope.
- No cockpit UI template work for `preflight_warning`/`read_issues` — both are in the JSON/SSE payloads and the CLI output; template surfacing can ride a later UI pass if wanted.
- Preview path (`parse_epub_structure`) was already chapter-degradation-tolerant; only the size guard was added there.

## Validation Performed

- Per-slice: targeted suites green (see commit messages); counting evidence in tests:
  - `tests/unit/core/test_toml_write.py` (escape round-trips incl. C0/DEL; guard moves corrupt file aside + names backup) + corrupt-store round-trip tests in `test_secret_store.py`/`test_connection_registry.py`.
  - `tests/unit/services/test_translation.py::test_preflight_*` (4 chain cases) + `test_workspace_translate.py::test_dead_primary_*` (e2e: dead `openai_chat` primary on a closed local port + fake fallback → run completes, `failed == 0`; no-fallback abort unchanged).
  - `tests/unit/providers/test_registry_custom.py::test_legacy_brand_is_preserved_as_engine_name` (+ updated legacy-alias expectations).
  - `tests/integration/test_cli_healthcheck.py::test_inspect_connection_first_project_shows_resolved_active_ai`.
  - `tests/unit/api/test_epub_preview.py::test_epub_preview_upload_over_cap_is_rejected` (N3), `tests/unit/readers/test_epub_size_guard.py` (N4, 4 tests), `tests/unit/readers/test_epub_chapter_degradation.py` (N5, 3 tests).
- Full gate (2026-07-14): `ruff check` clean; `ruff format --check` clean (390 files); `pyright` **0 errors, 0 warnings**. First full-suite run surfaced one stale A3 expectation (`test_patch_project_scope_persists` asserted the old `"custom"` clobber) — fixed in `tests/unit/api/test_config.py`; **full suite green: 1653 passed, 1 skipped** (`-m "not requires_cloud and not requires_ollama"`). `uv run python -m bench.run_performance_budgets`: **all budgets PASS** (translate 0.52 ms/seg; rolling-window flat cost **1.04×**; providers-hub/queue renders 0.02 s). `uv run python -m bench.run_acceptance_gate`: **AC-1…AC-9 PASS**.

## Known Risks

- The dead-primary e2e tests hit `http://127.0.0.1:9/v1` (closed port). Windows refuses instantly; on a machine where that port is filtered instead of closed, the 1 s connection timeout bounds it, but the two tests add ~15 s to the suite.
- A1's warning is visible in CLI/log/SSE payloads, but the cockpit HTML does not yet render `preflight_warning` — attempt history still shows the fallback provider per segment, so the substitution is discoverable, not hidden.
- N4 ceiling (1 GiB declared) is a named constant; a legitimate media-heavy EPUB over 1 GiB uncompressed would be rejected with an actionable message.

## Recommended Next Role / Next Step

Release Captain / owner: merge M1 PR (`perf/v073-storage-quick-wins`), then open the M2 PR from this branch. Next milestone: **M3 — enforcement provenance + honest cost accounting** (`feat/v073-enforcement-provenance`, migration v14, N2+N7 grouped).
