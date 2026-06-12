# Sprint Q — Workspace v2 · Final Validation Report

> **Role.** Sprint Q Final Validator / Release Captain (Gate D).
> **Date.** 2026-06-12 · **Branch.** `chore/validator-realease` (cut from `main` after PR #44).
> **Baseline.** `main` @ `06ee654` (*Merge PR #44 — `feat/cleanup-docs-reconciliation-final-integration`*).
> **Purpose.** Prove Sprint Q is **actually complete** — not just passing tests — and reconcile every audit artifact (WV / QF / G / R) against the merged tree. Companions: [SPRINT_Q_DEEP_AUDIT](SPRINT_Q_DEEP_AUDIT.md) · [SPRINT_Q_EXECUTION_PLAN](SPRINT_Q_EXECUTION_PLAN.md) · [SPRINT_Q_RISK_REGISTER](SPRINT_Q_RISK_REGISTER.md) · [SPRINT_Q_HANDOFF](SPRINT_Q_HANDOFF.md) · [ISSUE_BACKLOG](ISSUE_BACKLOG.md).

---

## 0. Headline verdict

**Sprint Q (Workspace v2) is COMPLETE and merged to `main`.** All stages Q0–Q12 are implemented, tested, documented, and integrated (Q1–Q10 via PR #41/#42/#43; **Q11+Q12 via PR #44**). The full gate is green; one residual layer-boundary defect was found and fixed during this pass.

| Dimension | Result |
|---|---|
| Stage completion (Q0–Q12) | ✅ 13/13 stages done + merged |
| Backlog (WV-001..014) | ✅ 13 complete · 1 spike-complete (WV-014) — 2 narrowly-scoped, documented deferrals inside completed items |
| New findings (QF-01..22) | ✅ 20 resolved · 2 accepted-with-monitoring (QF-09, QF-17) |
| Gap matrix (G-01..15) | ✅ 15/15 closed (G-13/G-15 doc-closed) |
| Risk register (R-01..23) | ✅ 20 mitigated (test/grep/smoke evidence) · 3 accepted (R-06 partial, R-13, R-14 monitored) |
| Validation matrix | ✅ pytest 1351/4 · pyright 0 · ruff clean · `weaver --help` · cargo check 0 err · `weaver-desktop.exe` built |
| **Fix applied this pass** | `ui_qa.py:240` raw `SELECT id FROM projects` → `get_first_project_id()` (last raw-SQL-in-router spot; QF-01/QF-02 residual) |

**Important correction to prior docs:** CLAUDE.md/AGENTS.md described Sprint Q as "code-complete; sprint PR pending / Q11+Q12 not yet merged." That is **stale** — PR #44 already merged the `feat/cleanup-docs-reconciliation-final-integration` branch (which stacks Q11+Q12) into `main`. Both files are reconciled in this pass.

---

## 1. Stage completion (Q0–Q12)

Each stage: implementation present · docs match · tests exist · gate recorded · no hidden critical gap.

| Stage | Scope | Impl evidence | Tests | Status |
|---|---|---|---|---|
| Q0 | Planning (deep audit, exec plan, risk register, handoff) | `.docs/audit/SPRINT_Q_*` (4 docs) | n/a | ✅ |
| Q1 | Identity + read layer (WV-010) | `storage/migrations.py` v10 (`projects.uuid`); `services/workspace_index.py` | `test_workspace_index.py`, `test_migrations.py`, grep-gate | ✅ |
| Q2 | Read-path & failure-visibility hardening | `connect_database` no longer in `api/routers/`; `reset_interrupted_segments` relocated to init + `recover_all_projects`; `ui.py` split into `ui_admin/_candidates/_jobs/_qa/_queue/_review/_workspace` | router-SQL/silent-failure grep-gate | ✅ |
| Q3 | Global shell + dashboard | `workspace.html`, `dashboard.html`, `ui_workspace` router | UI tests | ✅ |
| Q4 | Queue hub (`stale_running` distinct) | `queue_hub.html`, `ui_queue` | queue tests | ✅ |
| Q5 | Resources hub (read-only) | `services/workspace_resources.py`, `resources_hub.html` | resources tests | ✅ |
| Q6 | Providers hub | `services/workspace_providers.py`, `providers_hub.html` | `test_ui_providers.py` (secret-leak + no-provider-call regression) | ✅ |
| Q7 | Export gate + ledger | `services/export_gate.py`, `services/export_ledger.py`, `storage/export_history.py` (v11) | gate/ledger/migration tests | ✅ |
| Q8 | Analytics | `services/project_analytics.py` | analytics reconciliation + spy tests | ✅ |
| Q9 | Content Explorer v2 | `ui_explorer.py`, `services/segment_listing.py`; render-path hashing removed (`snapshot_info`) | explorer tests | ✅ |
| Q10 | Editor Context Panel | `services/workspace_context.py`, `partials/_workspace_context.html` | context tests | ✅ |
| Q11 | Validation completion (WV-007/008/011/014) | `_structure_issues`/`QASource` (`translation_qa.py`, `qa/report.py`); 3 checks (`qa/checks.py`); v12 drop; ADR 013; ruby spike | `test_migrations.py` (v12 fwd/idempotent/non-empty-refusal), check unit pairs, `test_epub_ruby_spike.py` | ✅ |
| Q12 | Residual cleanup + final gate | `raw_response` honored; `MAX_UPLOAD_BYTES` (256 MiB) + `SourceTooLargeError`; export-path doc; `_single_project_id` dedup | upload-cap + raw-response unit tests | ✅ |

No stage hides a critical gap. Deferrals (batch generation, honorific/forbidden checks, ruby import fix, `{id}` route migration) are explicit, documented, and out-of-scope by design.

---

## 2. Backlog resolution — WV-001..014

| WV | Title | Status | Stage | Evidence | Follow-up |
|---|---|---|---|---|---|
| WV-001 | Candidate/draft generation in UI | ✅ Complete | P | `ui_candidate_generate`/`ui_draft_generate` | Chapter/selection **batch** gen deferred (needs JobRegistry) — documented |
| WV-002 | Reading/output preview | ✅ Complete | P | `services/reading_preview.py` | — |
| WV-003 | Review status + queue | ✅ Complete | P | schema v9 `segments.review_status`; `segment_review.py` | — |
| WV-004 | Navigation unification | ✅ Complete | P + Q3 | global Workspace shell (`workspace.html`) | — |
| WV-005 | Project Overview | ✅ Complete | P | `services/project_overview.py` | — |
| WV-006 | Status taxonomy + dead branches | ✅ Complete | P + Q3 | `api/status_labels.py` (+ review/validation/export axes) | — |
| WV-007 | Structure validation joined into QA | ✅ Complete | Q11 | `_structure_issues`, `source="structure"`, `_STRUCTURE_SEVERITY_MAP` (no re-parse; EPUB `error`→`warning`, never blocks Final) | — |
| WV-008 | Missing checks + `error` tier | ✅ Complete (checks) / **Deferred** (tier) | Q11 | 3 deterministic checks added; **ADR 013** keeps 3-tier | Honorific + forbidden-terms checks deferred (not safely deterministic / no data store) — documented |
| WV-009 | Final-export gate + export history | ✅ Complete | Q7 | `export_gate.py` (Draft always; Final+`require_clean` blocks on critical); `export_ledger.py` + v11 `export_history` | `job_id` NULL carried (see §5) |
| WV-010 | Stable project id + cross-project read layer | ✅ Complete | Q1 | v10 `projects.uuid`; `services/workspace_index.py` (readonly, mtime-cached, error-isolated) | — |
| WV-011 | `qa_warnings` wire-or-remove | ✅ Complete (removed) | Q11 | conditional migration v12 (`COUNT==0` then `DROP`); `schema.sql` note | — |
| WV-012 | Two preview / two export paths | ✅ Complete | Q9 + Q12 | SD-7 preview naming resolved; `export_book` canonical / `export.py` CLI-only (ARCHITECTURE.md §boundary) | — |
| WV-013 | Editor context panel | ✅ Complete | Q10 | `services/workspace_context.py` + `_workspace_context.html` (lazy, zero provider/QA/hash) | — |
| WV-014 | Ruby + vertical-text fidelity | ✅ Spike complete | Q11 | [WV-014_RUBY_VERTICAL_TEXT_SPIKE](WV-014_RUBY_VERTICAL_TEXT_SPIKE.md) + `test_epub_ruby_spike.py` | **One real defect:** ruby flatten on import (`itertext()`) → post-Q follow-up (changes `source_hash`). Vertical text preserved. |

---

## 3. New-finding resolution — QF-01..22

| QF | Summary | Status | Stage | Evidence |
|---|---|---|---|---|
| QF-01 | Single-project assumption in 28 call sites | ✅ Resolved | Q1/Q2/Q12 + **this pass** | resolver `get_first_project_id`; router copies extracted; **last raw copy in `ui_qa.py:240` fixed this pass** |
| QF-02 | Raw SQL inside routers | ✅ Resolved | Q2 + **this pass** | `rg '\.execute\(' api/routers/` → **0**; `connect_database(` in routers → 0 |
| QF-03 | Writable connections for pure reads | ✅ Resolved | Q2 | `connect_database` (db.py:48) no longer calls `reset_interrupted_segments`; absent from routers |
| QF-04 | Silent failure swallows | ✅ Resolved | Q2 | `except WeaverError: pass` → 0; `suppress(HTTPException)` → 0 |
| QF-05 | Overview hashes every EPUB per render | ✅ Resolved | Q2/Q9 | hash-free `snapshot_info`; no `compute_source_hash` in any hub/index service |
| QF-06 | Stale `source_path` → image-preview 500 | ✅ Resolved | Q2 | `image_preview.py` catches `FileNotFoundError`/`KeyError`/`BadZipFile` → `WeaverError` (422). *Minor residual:* `PermissionError`/`IsADirectoryError` (OSError siblings) still uncaught — edge cases, low severity |
| QF-07 | `raw_response_logging` dead flag | ✅ Resolved | Q12a-1 | flag honored, default false stops persisting |
| QF-08 | No upload size cap | ✅ Resolved | Q12a-2 | `MAX_UPLOAD_BYTES = 256 MiB` + `SourceTooLargeError` |
| QF-09 | Startup auto-migrates every DB; locked skipped | ⚠ **Accepted (documented)** | Q2 doc | ADR-010-correct; documented in MAINTENANCE; `stale_running` reconciliation handles ghost rows |
| QF-10 | Module-size violations (`ui.py` 1414) | ✅ Resolved | Q2 | `ui.py` split into 7 sub-routers |
| QF-11 | Identity has 3 drift-able sources | ✅ Resolved | Q1 | `projects.uuid` (v10) + duplicate-uuid conflict flag |
| QF-12 | Readonly never migrates; schema drift | ✅ Resolved | Q1 | index reads schema-version marker → typed `needs_upgrade`/`error` entry; never auto-migrates |
| QF-13 | Status-label helper covers 2/5 axes | ✅ Resolved | Q3/Q7/Q11 | review label added Q3; validation/export with their stages |
| QF-14 | Three "preview" surfaces | ✅ Resolved | Q9 (SD-7) | Content Explorer rename; global route retitled "Inspect a source" |
| QF-15 | Legacy markdown exporter present | ✅ Resolved (doc) | Q12a-3 | `export_book` canonical / `export.py` CLI-only (ARCHITECTURE.md) |
| QF-16 | `qa_warnings` 3-tier CHECK vs WV-008 | ✅ Resolved | Q11 | table dropped (v12); moot |
| QF-17 | Desktop port race + PATH sidecar | ⚠ **Accepted (R-13)** | — | documented in INSTALL_DESKTOP; token kept out of logs; `desktop/` untouched in Q |
| QF-18 | Blueprint "sourceless creation" stale | ✅ Resolved (doc) | Q12 | annotated |
| QF-19 | Dashboard discovery uncached/unbudgeted | ✅ Resolved | Q1 | `workspace_index` mtime-cache + `@pytest.mark.perf` budget |
| QF-20 | Absolute paths in render contexts | ✅ Resolved | Q1 | route-facing models path-free; hub-template leak grep → clean |
| QF-21 | `snapshot_status` writable-open pile-up | ✅ Resolved | Q2 | folded into QF-05 fix (readonly `snapshot_info`) |
| QF-22 | No global active-jobs affordance | ✅ Resolved | Q3 | topbar jobs chip from in-memory `JobRegistry` |

---

## 4. Gap-matrix & risk-register final pass

### 4.1 Gap matrix G-01..15

All closed. G-01/G-02 (identity + read layer) → Q1. G-03/G-04 (dashboard/shell) → Q3. G-05 queue → Q4. G-06 resources → Q5. G-07 providers → Q6. G-08 export gate → Q7. G-09 analytics → Q8. G-10 explorer → Q9. G-11 editor → Q10. G-12 QA join → Q11. G-13 dead-code retirement → Q11/Q12. G-14 layer rules → Q2 (+ this pass's `ui_qa.py` fix). G-15 sourceless creation → Q12 doc.

### 4.2 Risk register R-01..23 — required explicit checks

| Required check | Verdict | Evidence |
|---|---|---|
| No writable DB reads in routers (R-01) | ✅ | `connect_database(` in `api/routers/` → **0** |
| No migrations/reset on read path (R-02) | ✅ | `reset_interrupted_segments` only in `db.py` init path + `job_store.recover_all_projects` (startup) |
| No cross-project path leak in hubs (R-03/R-05) | ✅ | hub-template grep for `project_root/source_path/db_path/.weaver` → 0 |
| No provider key leakage (R-07) | ✅ | `workspace_providers` uses env-var **name** only; `test_secret_value_never_rendered` |
| No provider call on render (R-08/R-22) | ✅ | no `translate/healthcheck/get_client` in `workspace_providers`; `test_no_provider_call_on_hub_get` |
| No QA scan on hub render (R-08) | ✅ | no `analyze_novel/run_all_checks` in any hub service |
| No source EPUB hashing on dashboard/hub render (R-09) | ✅ | no `compute_source_hash/hashlib` in index/hub services |
| No global mutable store (R-12) | ✅ | no `workspace.db`/global index DB; in-process cache only |
| No external queue (locked stack) | ✅ | no `celery/rq/redis/ProcessPool` in `src/` |
| No desktop contract regression | ✅ | `desktop/` last touched `60c8fb7` (Sprint O); no Q commit; cargo check/build green |

| Risk | Disposition | Evidence |
|---|---|---|
| R-01 writable reads in routers | ✅ Mitigated | grep-gate 0 |
| R-02 migrate/reset on read | ✅ Mitigated | reset relocated |
| R-03 index leakage | ✅ Mitigated | leak grep + tests |
| R-04 stale index | ✅ Mitigated | mtime+TTL cache; deletion test |
| R-05 path leakage | ✅ Mitigated | basename/relative hub render |
| R-06 logs/raw_response privacy | ◑ **Partial-accepted** | scrubber + `raw_response` default-off (Q12a-1); event metadata in local logs by design |
| R-07 provider key leakage | ✅ Mitigated | secret-leak regression test |
| R-08 QA/provider on render | ✅ Mitigated | spy tests + greps |
| R-09 source hashing on render | ✅ Mitigated | hash-free render path |
| R-10 N+1 SQLite fan-out | ✅ Mitigated | cached index + perf smoke |
| R-11 swallowed failures | ✅ Mitigated | suppress/pass grep 0 |
| R-12 global mutable store | ✅ Mitigated | no new store |
| R-13 desktop residuals | ⚠ **Accepted** | documented; `desktop/` frozen |
| R-14 scope creep | ✅ Held (monitored) | per-stage non-goals respected |
| R-15 migration sequencing | ✅ Mitigated | v10→v11→v12 strictly serial; `SCHEMA_VERSION=12` |
| R-16 UI-test churn | ✅ Mitigated | router split first; pinned hooks intact |
| R-17 duplicate identity | ✅ Mitigated | duplicate-uuid conflict flag |
| R-18 WAL readonly failures | ✅ Mitigated | typed degraded entries |
| R-19 ghost running jobs | ✅ Mitigated | `stale_running` classification |
| R-20 ADR-013 stall | ✅ Mitigated | ADR 013 written (deferred tier) |
| R-21 ledger/disk drift | ✅ Mitigated | `stat` → "missing" state |
| R-22 healthcheck cost | ✅ Mitigated | explicit button; no-call test |
| R-23 router/module size | ✅ Mitigated | `ui.py` split |

---

## 5. Carried known issues (tracked, non-blocking)

Documented in [docs/MAINTENANCE.md](../../docs/MAINTENANCE.md) "Carried known issues":

1. **`export_history.job_id` always NULL** — the JobRegistry generates the id after the runner closure; wiring needs a small ADR-010-adjacent API change. Deferred post-Q.
2. **v10 projects show `needs_upgrade` in the Exports hub** until a writable open migrates them to v11+ (read paths never migrate). Resolves on next write.
3. **`volume_lifecycle` `exported` overlay** kept-deferred — lifecycle stays pure-derived; `export_history` ledger is the honest export record.
4. **Ruby/furigana import flatten (WV-014)** — `<ruby>` reading leaks into `source_text` via `itertext()`; scoped post-Q follow-up (changes `source_hash` → reviewed re-import). Vertical text preserved.
5. **Desktop sidecar = PATH-dependent** (QF-17/R-13) — single-file bundle needs PyInstaller (post-Q). `desktop/` unchanged since Sprint O.
6. **`image_preview` minor residual (QF-06)** — `PermissionError`/`IsADirectoryError` (OSError siblings) on a stale source still uncaught; `FileNotFoundError` is handled. Low severity; candidate for the same broaden-to-`OSError` follow-up.
7. **`desktop/src/sidecar.rs` dead-code warnings** (3) — `POLL_INTERVAL`, `log_path` field+method unused. Pre-existing since Sprint O; not touched (Q desktop fence). Cargo cleanup candidate next time `desktop/` is opened.

---

## 6. Validation matrix (commands actually run, 2026-06-12)

| Command | Result |
|---|---|
| `uv run pytest -q` | ✅ **1351 passed, 4 skipped** (421s) — 4 expected skips (deepseek/gemini/ollama live, POSIX mode) |
| `uv run pyright` | ✅ **0 errors, 0 warnings, 0 informations** |
| `uv run ruff check .` | ✅ **All checks passed** |
| `uv run ruff format --check .` | ✅ **364 files already formatted** |
| `uv run weaver --help` | ✅ exit 0 |
| `cd desktop && cargo check` | ✅ **0 errors, 3 warnings** (pre-existing dead-code in `sidecar.rs`) |
| `cd desktop && cargo tauri build --no-bundle` | ✅ release `weaver-desktop.exe` (**3.1 MB**) built in 2m32s; 0 errors |

---

## 7. Security smoke

Run as part of the full suite (all green). Surfaces verified:

- **Provider secret not rendered** — `test_ui_providers.py::test_secret_value_never_rendered` (seeds `sk-SUPER-SECRET…`, asserts absent from HTML); service renders env-var **name** only.
- **No provider call on hub render** — `test_no_provider_call_on_hub_get` (FakeProvider call counter = 0).
- **Provider/session secret not logged** — `logging_setup.scrub_provider_record`; CI greps provider.log (existing).
- **Desktop session gate** — `test_desktop_security.py` (401 without token header on `/ui`; `/healthz`/`/static` public by design).
- **Image preview ADR-012 endpoint** — `test_image_preview_security.py` (manifest-id-keyed, MIME allowlist, 8 MiB cap, `../`/absolute rejected, `nosniff`/`no-store`).
- **Traversal probes** — source-browser `_safe_join` resolve-then-containment (unchanged).
- **Cross-project path leak** — hub templates contain no absolute `project_root`/`source_path`/`db_path` (grep clean).

> Note: CLAUDE.md/MAINTENANCE.md cite an informal "security smoke 67" grouping — those tests are a subset of the full 1351 and all pass; this report verifies the surfaces directly rather than re-running the author's ad-hoc grouping.

## 8. Performance smoke

- **Workspace index budget** — `@pytest.mark.perf` smoke (`test_workspace_index.py`) collected and green.
- **No source hashing on dashboard/hub render** — `compute_source_hash`/`hashlib` absent from all index/hub services (grep).
- **No QA scan on hub render** — `analyze_novel`/`run_all_checks` absent from hub services (grep).
- **No provider call on provider hub** — confirmed (spy test + grep).
- **Analytics deterministic, stored-data only** — `project_analytics.py` aggregates persisted counts/tokens; no QA/provider on render.

## 9. Desktop smoke note

Interactive GUI runtime smoke **cannot be automated in this environment** (headless). What is mechanically proven this pass:

- `cargo check` → 0 errors; `cargo tauri build --no-bundle` → `weaver-desktop.exe` (3.1 MB) built.
- `desktop/` is **byte-unchanged since Sprint O** (last commit `60c8fb7`, 2026-06-10) — no Sprint Q regression possible; the Sprint O runtime smoke remains the live-validated baseline.

**Manual maintainer steps (one-time, to fully close Gate D runtime):**
launch `weaver-desktop.exe` → confirm `/healthz` polled before window → `/ui` dashboard renders → visit queue / resources / providers / exports / analytics hubs → close window → confirm no orphan `weaver` process → confirm `%APPDATA%\Weaver\logs\runtime.log` + `sidecar.console.log` exist and contain **no** session-token value.

---

## 10. Changes applied this pass

1. **`src/weaver/api/routers/ui_qa.py`** — replaced raw `connection.execute("SELECT id FROM projects ORDER BY id LIMIT 1")` in `_snapshot_export_advisories` with `get_first_project_id(connection)` (imported from `storage/projects.py`). This was the **last** raw-SQL-in-router occurrence (QF-01/QF-02 residual that Q2/Q12a-4 missed). Behavior identical (same query, same `None`-guard); router is now SQL-free. Verified: pytest 1351/4, pyright 0, ruff clean.
2. **Docs reconciled** — CLAUDE.md + AGENTS.md status headers, roadmap legend, §2.3 active phase, §2.4 gate status, §2.5 phase log: "code-complete / PR pending / Q11+Q12 not merged" → "**COMPLETE — merged via PR #44**." This report added and cross-linked.

---

## 11. Release Captain verdict

**Gate D: SIGNED.** Sprint Q is implemented, validated, documented, integrated to `main`, and reconciled. No blocking gap. Carried items (§5) are tracked, non-blocking, and honestly disclosed. The only un-automatable check is the interactive desktop GUI runtime smoke (§9), reduced to a one-time manual maintainer step because `desktop/` is unchanged since the Sprint-O-validated baseline.
