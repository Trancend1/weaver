# MVP Stabilization Report (Sprint 9)

Stabilization-only sprint locking the Weaver MVP baseline after Sprints 1–8. No new
features; verification, doc alignment, and an end-to-end proof. This document is built
across the three stages: **9A audit + validation**, **9B doc/regression fixes**, **9C E2E proof + baseline report**.

> Stage status: **9A complete** · **9B complete** · 9C pending.
> Date: 2026-06-02 · Branch: `feat/MVP-stabilization`.

---

## Stage 9A — Audit & Validation

### 1. Validation matrix (regression sweep)

| Gate | Command | Result |
|---|---|---|
| Unit + integration tests | `uv run pytest -q` | ✅ **561 passed, 4 skipped** (73.65s) |
| Type check | `uv run pyright` | ✅ **0 errors, 0 warnings, 0 info** |
| Lint | `uv run ruff check .` | ✅ **All checks passed** |
| Format | `uv run ruff format --check .` | ✅ **218 files already formatted** |
| CLI smoke | `uv run weaver --help` | ✅ **15 commands** present (init, new, import, inspect, dashboard, translate, edit, export, preview, doctor, validate, serve, serve-api, glossary, secrets) |
| FastAPI smoke | `create_api_app()` + `TestClient` | ✅ `/health` 200 · `/version` 200 · `/projects` 200 · **37 routes** (workspace, translate, retranslate, glossary, characters, memory, batch, export all present) |
| Flask legacy smoke | `create_app()` + `test_client` | ✅ `/` 200 · **14 routes** |

**Skipped tests (all expected, none a regression):**
- `test_deepseek_live.py` — `DEEPSEEK_API_KEY` not set
- `test_gemini_live.py` — `GEMINI_API_KEY` not set
- `test_ollama_live.py` — no local Ollama
- `test_secret_store.py::…` — POSIX file-mode assertion (Windows host)

One non-fatal warning: Starlette `TestClient` httpx deprecation (third-party, test-only).

### 2. MVP acceptance status

Audited against `docs/MVP_SCOPE.md` required features and `src/weaver/`.

| # | MVP requirement | Status | Evidence |
|---|---|---|---|
| 1 | Project management — create; import TXT/EPUB/HTML; Novel→Volume→Chapter | ✅ exists | `services/project.py`, `services/import_source.py`, `readers/{epub,txt,html}.py`, `storage/{volumes,segments}.py`; schema v3 |
| 2 | Translation workspace — JP/EN two-column, edit, save, revision history | ✅ exists (API) | `services/chapter_workspace.py`, `workspace_edit.py`, `segment_history.py`; `GET …/chapters/{id}/workspace`, `PATCH …/segments/{id}/translation`, `GET …/segments/{id}/translations`. Polished UI deferred (ADR 005) |
| 3 | AI translation — provider/model config; chapter/selection; safe retranslate | ✅ exists | `services/workspace_translate.py`, `api/routers/translate.py`, `api/jobs.py`; 3 retranslate modes (`skip_existing`/`retranslate_non_manual`/`force_selected`) |
| 4 | Glossary — project-scoped CRUD; prompt injection | ✅ exists | `storage/glossary.py`, `services/glossary_terms.py`, `api/routers/glossary.py`; `<glossary>` block in `balanced_user.jinja2` |
| 5 | Character DB — JP/EN/gender/role/notes; injection | ✅ exists | schema v4 `characters`; `storage/characters.py`, `api/routers/characters.py`; `<characters>` prompt block |
| 6 | Translation memory — lookup-before-AI; reuse; AI fallback | ✅ exists | schema v5 `translation_memory`; lookup/save in `translate_one_segment`; `api/routers/translation_memory.py`; manual = source of truth |
| 7 | Batch translation — chapter/volume/novel; progress + per-unit status; no silent failure | ✅ exists | `services/batch_translate.py`, `api/routers/batch.py`, `BatchJob`; aggregate progress + cooperative cancel + SSE. Monitor UI deferred |
| 8 | Export — EPUB (priority) + TXT + HTML + DOCX | 🟡 partial (by design) | EPUB/TXT/HTML shipped: `services/export_book.py`, `renderers/{epub,epub_synthesis,txt,html}.py`, `api/routers/export.py` + `ExportJob`. **DOCX deferred (out of MVP)** → `target="docx"` returns 422 (handled, not a crash). Export UI deferred (ADR 005) |

**Acceptance checklist (`MVP_SCOPE.md` §Acceptance):** items 1–9 ✅. Item 10 (export) satisfied for EPUB/TXT/HTML with DOCX deferred + sprint-documented. Item 11 (final quality gate) is what Sprint 9 closes.

### 3. Blocker list

**No MVP-baseline blockers.** All required features exist or are documented deferrals. Every static + smoke gate is green.

Non-blocking findings to address in 9B (doc-only, no behavior change):
- **F1 — doc drift in `MVP_SCOPE.md`:** acceptance checklist items 10–11 (lines ~70–71) still show export + final gate as unchecked; export TXT/HTML now shipped (8C). Needs alignment.
- **F2 — CLI vs FastAPI export split undocumented:** the volume-aware EPUB/TXT/HTML export (`services/export_book.py`) is reachable **only via the FastAPI cockpit**. The CLI `export` command still uses the legacy single-project path (`services/export.py` → `export_epub_project`/`export_markdown_project`). This is consistent with web-cockpit-first MVP, but the surface split is not stated in ARCHITECTURE/QUICKSTART/COCKPIT docs.
- **F3 — `CLAUDE.md` §2.1/§2.3/§2.5 + Sprint 9 status** not yet reflecting Sprint 9 work.
- **F4 — Deferred list is scattered** across CLAUDE.md / MVP_SCOPE.md / ADR 005; should be consolidated into one "Known Gaps / Deferred" section (this report serves that, but cross-link from docs).

### 4. Deferred / out-of-MVP (confirmed, not blockers)

| Item | Disposition | Source of truth |
|---|---|---|
| DOCX export output | Deferred — out of MVP; enforced via 422 | CLAUDE.md §2.1, ADR 005 |
| Export UI (cockpit) | Deferred — post-MVP polish | ADR 005 |
| Combined EPUB / ZIP bundle | Deferred | CLAUDE.md Sprint 8 log |
| Flask decommission | Deferred — Sprint 10, gated on FastAPI parity audit | CLAUDE.md §2.1 |
| General UI polish | Deferred until MVP baseline | ADR 005 |
| Live provider tests (DeepSeek/Gemini/Ollama) | Skipped in CI by design — require API keys / local Ollama | pytest markers `requires_cloud`/`requires_ollama` |

### 5. Recommended fixes for 9B (stabilization-only)

1. Update `MVP_SCOPE.md` acceptance checklist: export → EPUB/TXT/HTML shipped, DOCX deferred; note final gate is Sprint 9. (F1)
2. Document the CLI-vs-FastAPI export split in `ARCHITECTURE.md`, `COCKPIT_WORKFLOW.md`, and `QUICKSTART.md`. (F2)
3. Update `CLAUDE.md` §2.1 (Sprint 9 → in progress/complete), §2.3, §2.5 phase log. (F3)
4. Add a consolidated "Known Gaps / Deferred" pointer from `CLAUDE.md` / `docs/README.md` to this report. (F4)
5. Refresh `MAINTENANCE.md` with the exact Sprint 9 validation commands + expected skip set.
6. **No behavior changes** to provider/TM/export/translation — doc + checklist alignment only.

---

## Stage 9B — Doc & Regression Fixes

Doc/regression alignment only — **no source-code or behavior changes**. The four 9A findings (F1–F4) plus the `MAINTENANCE.md` validation section.

### Files changed (docs only)

| File | Change | Finding |
|---|---|---|
| `docs/MVP_SCOPE.md` | Acceptance checklist: export item → `[x]` EPUB/TXT/HTML done, DOCX deferred (422); final-gate item annotated (9A ✅ / 9B ✅ / 9C pending); stale progress note refreshed to "Sprints 1–8 shipped" + Sprint 9 in progress | F1 |
| `docs/ARCHITECTURE.md` | `renderers/` inventory now states the **export surface split** explicitly (FastAPI = volume-aware `export_book.py`; CLI/Flask = legacy `export.py`) | F2 |
| `docs/COCKPIT_WORKFLOW.md` | Flask "Export" page row marked legacy single-project; FastAPI export section gains a surface-split callout | F2 |
| `docs/QUICKSTART.md` | CLI `export` flagged as legacy single-project; pointer to FastAPI volume-aware export | F2 |
| `CLAUDE.md` | §1 doc map (+ report link), §2.1 Sprint 9 → 🟡, §2.3 Sprint 9 status, §2.5 phase-log rows 9A + 9B | F3 |
| `docs/README.md` | "Where to start" table links the stabilization report | F4 |
| `docs/MAINTENANCE.md` | New "MVP stabilization validation" section: exact gate commands + expected 4-skip set | F4 |
| `docs/MVP_STABILIZATION_REPORT.md` | This stage section + status line | — |

### Doc fixes summary
- **F1 resolved** — `MVP_SCOPE.md` acceptance checklist matches shipped code (EPUB/TXT/HTML present; DOCX deferred, not a blocker).
- **F2 resolved** — the CLI-vs-FastAPI export split is now stated in all three surface docs as an **accepted web-first MVP boundary**, not a gap.
- **F3 resolved** — `CLAUDE.md` reflects Sprint 9 in progress (9A + 9B), with phase-log entries.
- **F4 resolved** — the consolidated deferred list (this report §4) is cross-linked from `CLAUDE.md` §1 and `docs/README.md`; `MAINTENANCE.md` records the validation commands + skip set.

### Re-validation (post-9B, docs-only change — matrix unchanged)

| Gate | Result |
|---|---|
| `uv run pytest -q` | ✅ 561 passed, 4 skipped |
| `uv run pyright` | ✅ 0 errors |
| `uv run ruff check .` | ✅ clean |
| `uv run ruff format --check .` | ✅ clean |
| CLI smoke | ✅ 15 commands |
| FastAPI smoke | ✅ 37 routes, 200s |
| Flask smoke | ✅ 14 routes, 200 |

### Remaining deferred list (unchanged from §4)
DOCX export output · export UI · combined EPUB/ZIP · Flask decommission (Sprint 10, parity-gated) · general UI polish (ADR 005) · live provider tests (require keys/Ollama).

## Stage 9C — E2E Proof & MVP Baseline Report

_Pending._
