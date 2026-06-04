# Weaver

Offline-capable, glossary-aware **JP→EN** light-novel translation workbench. Two surfaces: a **CLI** and a local **web cockpit**. Web-cockpit-first development focus; CLI stays functional.

**Not:** SaaS, consumer product, hosted service, complex SPA.

> Currently in a **controlled reset** (audit → cleanup → docs rewrite → fresh baseline → MVP plan → UI/UX plan). See [claude.local.md](claude.local.md) for the reset operating plan and `docs/decisions/001`. Phase 0–13 history (v0.6.0) lives in git history and [docs/archive/](docs/archive/).

---

## 1. Documentation Map

Docs are the spec. Code follows docs. If code contradicts docs, ask first.

| Doc | Purpose |
|-----|---------|
| [README.md](README.md) | User-facing: install, quickstart, commands |
| [docs/README.md](docs/README.md) | Docs index — what Weaver is, CLI/web split, where to start |
| [docs/QUICKSTART.md](docs/QUICKSTART.md) | Install + end-to-end CLI/web walkthrough |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Module map, layer boundaries, data flow |
| [docs/CLI_WORKFLOW.md](docs/CLI_WORKFLOW.md) | CLI day-to-day flow, limitations, rules |
| [docs/COCKPIT_WORKFLOW.md](docs/COCKPIT_WORKFLOW.md) | Web cockpit (FastAPI; Jinja2 + HTMX UI + JSON API) |
| [docs/PROVIDER_AND_MODEL_CONFIG.md](docs/PROVIDER_AND_MODEL_CONFIG.md) | Providers, models, secret store |
| [docs/TRANSLATION_PIPELINE.md](docs/TRANSLATION_PIPELINE.md) | Import → segment → translate → QA → export |
| [docs/MVP_SCOPE.md](docs/MVP_SCOPE.md) | MVP features, gap analysis, sprint mapping, acceptance |
| [docs/MVP_STABILIZATION_REPORT.md](docs/MVP_STABILIZATION_REPORT.md) | Sprint 9 baseline: validation matrix, acceptance audit, **consolidated deferred/known-gaps list** |
| [docs/RC1_REPORT.md](docs/RC1_REPORT.md) | **MVP RC1**: validation/soak/clean-install evidence, release notes, known issues, deferred roadmap, recommended version tag |
| [docs/SPRINT10_PARITY_AUDIT.md](docs/SPRINT10_PARITY_AUDIT.md) | Flask↔FastAPI parity matrix, gap closure (10A–10E), decommission risk |
| [docs/SPRINT11A_UI_PLAN.md](docs/SPRINT11A_UI_PLAN.md) | FastAPI UI shell plan (Sprint 11A) |
| [docs/MAINTENANCE.md](docs/MAINTENANCE.md) | Cleanup, testing, regression, release, migration discipline |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Active ADR index (`001`–`007`) |
| [docs/decisions/](docs/decisions/) | Active ADRs `001`–`007` |
| [ENGINEERING_STANDARDS.md](docs/ENGINEERING_STANDARDS.md) · [PROMPT_DESIGN.md](docs/PROMPT_DESIGN.md) · [SECURITY_AND_PERFORMANCE.md](docs/SECURITY_AND_PERFORMANCE.md) · [AI_SLOP_PREVENTION.md](docs/AI_SLOP_PREVENTION.md) | Supplementary reference specs (still active) |
| [docs/archive/](docs/archive/) | Archived ADRs `0001`–`0020`, pre-reset specs (PRD_v2, SYSTEM_ARCHITECTURE), strategy docs — historical |

---

## 2. Progress

### 2.1 Roadmap

**Foundation (shipped, v0.6.0):** CLI complete (init, inspect, translate, edit, glossary, export, validate, preview, doctor, new, dashboard, serve, secrets) + Flask web cockpit end-to-end (discovery, monitor+SSE, file browse/upload, provider config, translate+stop, export, glossary review). Detail: git history + `docs/archive/`.

**Active: MVP Web Cockpit Foundation** — build the consistency-first translator workflow (ADR `003`) and begin the FastAPI direction (ADR `004`).

| Sprint | Scope | Difficulty | Risk | Status |
| ------ | ----- | ---------: | ---- | ------ |
| 1  | Project structure & novel management (Novel/Volume/Chapter; TXT/EPUB/HTML import) | 4/10 | 🟢 Low | ✅ |
| 2  | FastAPI cockpit foundation (2A app+`/health`+`/version` · 2B project read APIs · 2C import API) | 5/10 | 🟢 Low | ✅ |
| 3  | Translation workspace, FastAPI (JP/EN two-column read, edit, save, revision history) | 7/10 | 🟡 Medium | ✅ |
| 4  | Provider & AI translation (config, translate chapter/selection, safe retranslate) | 9.5/10 | 🔴 Very High | ✅ |
| 5  | Glossary & character database (project-scoped, prompt injection) | 8/10 | 🔴 High | ✅ |
| 6  | Translation memory (source→target store, lookup-before-AI, reuse) | 10/10 | 🔴 Very High | ✅ |
| 7  | Batch translation & progress (chapter/volume/novel, job status) | 9/10 | 🔴 Very High | ✅ |
| 8  | Export (EPUB priority, TXT, HTML; DOCX deferred) | 6/10 | 🟡 Medium | ✅ |
| 9  | MVP stabilization (smoke CLI+web, regression, acceptance checklist, E2E baseline) | 7/10 | 🟡 Medium | ✅ |
| 10 | Flask↔FastAPI parity audit + gap closure (10A audit → KEEP · 10B create/browse · 10C config/secret · 10D glossary-review · 10E re-audit). Functional parity complete; only UI gap remains. | 5/10 | 🟡 Medium | ✅ |
| 11 | FastAPI UI functional parity (ADR `007`: Jinja2+HTMX, presentation-only, reuse Sprint 2–10 APIs) — 11A shell ✅ · 11B-1 create/import ✅ · 11B-1.5 import-collision fix ✅ · 11B-2 workspace read/save/history ✅ · 11B-3 translate/retranslate/jobs/export ✅ · 11C glossary/character/TM/config ✅. **Functional parity, not visual polish.** | 7/10 | 🟡 Medium | ✅ |
| 12 | FastAPI UI parity audit + default-`serve` decision (12A audit → FastAPI UI is a 12/12 functional superset · 12B flip: `serve`→FastAPI UI, `serve-api` headless, Flask kept as `serve-flask`) | 4/10 | 🟡 Medium | ✅ |
| 13 | Flask decommission (13A readiness audit → 13A.5 real-workflow soak proved the FastAPI default stable, fallback unused → 13B removed `serve-flask`, `src/weaver/web/**`, Flask-only tests, and the `flask` dependency). FastAPI is now the only web cockpit. | 5/10 | 🟡 Medium | ✅ |

Legend: ✅ complete · 🟡 in progress · ⏳ next · ⬜ pending · 🚫 blocked.

> Re-sequenced 2026-05-30: FastAPI foundation inserted as Sprint 2; remaining MVP sprints shifted +1; Flask decommission appended (Sprints 10–13, gated on FastAPI parity + UI). Sprint detail + MVP gap analysis in [docs/MVP_SCOPE.md](docs/MVP_SCOPE.md). Sprint ordering is dependency-driven, not calendar.

### 2.2 Reusable Phase Gate

Before starting any sprint, run this gate:

1. Read the active sprint scope (§2.3) and its acceptance criteria.
2. List the sprint's exit criteria in plain language.
3. Verify each with a concrete command, test, file check, or manual inspection.
4. State what is usable now, what is internal-only, what is not yet user-facing.
5. If every criterion passes, update §2.1 / §2.3 / §2.4 / §2.5.
6. If any fails, do not proceed — mark the row blocked and record the missing proof.

Required reminder before any phase transition: **"Check exit criteria first. No next phase until evidence exists. Explain the detail for manual inspection."**

### 2.3 Active Phase — MVP Web Cockpit Foundation

Focus: build the core JP→EN light-novel translator workflow, then reach FastAPI UI parity, before any visual polish.

**Rules:**
- Web/cockpit is the primary development focus.
- Web backend is **FastAPI** (ADR `004`). `weaver serve` = FastAPI cockpit (UI), `weaver serve-api` = same app headless. **Sprint 13B removed the Flask cockpit entirely** (`serve-flask`, `src/weaver/web/**`, Flask-only tests, `flask` dependency) — FastAPI is the only web surface. The Flask→FastAPI migration is complete.
- CLI must remain functional and wire-compatible.
- Shared/core must stay framework-agnostic (ADR `002`). UI/templates carry no business logic.
- UI is **functional parity, not visual polish** (ADR `005` polish rubric is for later). UI stack pinned by ADR `007` (Jinja2 + HTMX, no Node/build, no SPA).
- MVP gaps map to actionable sprints (ADR `003`).

**Sprint status** (full per-sprint detail in §2.5):

- **Sprints 1–10 ✅** — MVP cockpit foundation (Novel/Volume/Chapter; FastAPI workspace, translate/safe-retranslate, glossary + candidate review, character DB, translation memory, batch, volume-aware EPUB/TXT/HTML export) **and** Flask↔FastAPI parity audit + gap closure (10A–10E). All functional/domain parity complete; only the rendered web UI remained as a gap.
- **Sprint 11 ✅ — FastAPI UI functional parity (complete):**
  - 11A shell ✅ (dashboard, project tree, nav, state primitives)
  - 11B-1 create/import + file browser ✅
  - 11B-1.5 import-collision bugfix ✅ (chapter/segment ids now volume-scoped)
  - 11B-2 workspace read/save/history ✅ (two-column JP/EN, per-segment save → `manual`, history)
  - 11B-3 translate/retranslate + job progress/cancel + export ✅ (self-polling HTMX panels)
  - 11C glossary CRUD + candidate review, character DB, TM read/delete, provider/secret config ✅
- **Sprint 12 ✅ — FastAPI UI parity audit + default-`serve` flip:**
  - 12A audit ✅ — FastAPI UI is a **12/12 functional superset** of the Flask UI (Flask covers only 7/12). All validation green. Report: [docs/SPRINT12_UI_PARITY_AUDIT.md](docs/SPRINT12_UI_PARITY_AUDIT.md). Gate 12A decision (maintainer, 2026-06-03): **Option 2 — flip default to FastAPI, keep Flask as fallback.**
  - 12B flip ✅ — `weaver serve` → FastAPI cockpit (UI; default), `weaver serve-api` → same FastAPI app headless, `weaver serve-flask` → legacy Flask (fallback). Default-command change only; no Flask route/template/dependency removal; reversible.
- **Sprint 13 ✅ — Flask decommission:**
  - 13A readiness audit ✅ — stability of the 12B flip verified; Flask dependency map clean (self-contained `web/`, one external importer); Gate 13A (maintainer, 2026-06-04): **Option B — postpone, soak first.** Report: [docs/SPRINT13A_DECOMMISSION_READINESS.md](docs/SPRINT13A_DECOMMISSION_READINESS.md).
  - 13A.5 soak ✅ — full multi-format/multi-volume novel workflow against a live `weaver serve` FastAPI cockpit: **25/25 steps, `serve-flask` never used, no regressions.** Gate 13A.5 (maintainer, 2026-06-04): **Option A — proceed.** Report: [docs/SPRINT13A5_SOAK_RESULT.md](docs/SPRINT13A5_SOAK_RESULT.md).
  - 13B removal ✅ — removed `weaver serve-flask`, `src/weaver/web/**` (10 py + 5 templates + 2 static), Flask-only tests (`tests/unit/web/`, `test_web_cockpit.py`), and the `flask>=3.0` dependency. FastAPI is the only web cockpit.

**Locked posture (ADR `004` · Sprint 13B, 2026-06-04):** `serve` = **FastAPI** cockpit (UI + API) · `serve-api` = FastAPI headless. **Flask is fully removed** — no `serve-flask`, no `src/weaver/web/**`, no `flask` dependency. The web layer is FastAPI only; shared/core stays framework-agnostic (ADR `002`).

**Note (legacy CLI):** `weaver translate` and the legacy `services/export.py` are **single-volume** (they re-read the project's init source) — multi-volume translate/export is the cockpit's job (batch + `export_book`). This is unchanged by 11B-1.5; legacy CLI translate never supported multi-volume.

**Validation baseline (Sprint 13B, 2026-06-04):** 651 tests / 4 skipped (−37 Flask-only tests removed) · pyright 0 · ruff + format clean (226 files) · `serve`→FastAPI cockpit (`/`→307, `/ui`/`/ui/new`/`/ui/config`→200) · `serve-flask` gone (no such command) · CLI 15 commands · no `weaver.web` imports · `flask` absent from env + `uv.lock`.

### 2.4 Exit Criteria

> **Status (Sprint 9C, 2026-06-02): all criteria below met — MVP baseline LOCKED.** Verified end-to-end on the real light-novel EPUB; evidence in [docs/MVP_STABILIZATION_REPORT.md](docs/MVP_STABILIZATION_REPORT.md). DOCX export is the only deferred sub-item (out of MVP, 422 — not a blocker).

MVP acceptance gate (full checklist in `docs/MVP_SCOPE.md`, Task 5). At minimum, before UI polish:

- Create a novel project; import TXT/EPUB/HTML; Novel/Volume/Chapter structure exists.
- JP/EN two-column workspace; edits persist; revision record exists or sprint-mapped.
- Provider/model configurable; translate chapter + selection; retranslate is safe.
- Glossary project-scoped and injected into prompt; model instructed to follow it.
- Character DB project-scoped and injected into prompt.
- Translation memory: lookup before AI call; reuse on match; AI fallback on miss.
- Batch chapter/volume/novel with visible progress + per-unit status; errors not silent.
- Export EPUB (priority) + TXT/HTML/DOCX present or sprint-mapped.
- Quality gate: CLI not broken; web not broken; docs match code; active ADRs `001`+; gaps sprint-mapped; no premature UI polish.

### 2.5 Phase Log

One row per sprint/stage, chronological. Keep entries terse; deep detail lives in the linked docs and git history.

| Sprint | Outcome |
|---|---|
| Phases 0–13 (v0.6.0) | CLI + Flask web cockpit shipped. Detail in git history + `docs/archive/`. |
| Reset Tasks 1–5 | Controlled reset to MVP Web Cockpit Foundation + FastAPI direction. ADRs reset to `001`–`005`; MVP gap finalized + 8-sprint plan locked (Task 5). |
| Sprint 1 | Novel/Volume/Chapter model (schema v3, v2→v3 migration); EPUB/TXT/HTML import; `weaver import` CLI; Flask project-detail tree + multi-format import UI; ADR 006. 345 tests green. |
| Sprint 2 | FastAPI cockpit (`src/weaver/api/`, own namespace, no Flask import): `create_api_app()`, `/health`, `/version`, `GET /projects`, `GET /projects/{name}/tree`, `POST /projects/{name}/import`; `weaver serve-api`; reuses `services/project_tree` + `import_source`. Flask baseline intact. 361 tests green. |
| Sprint 3 | 3A read workspace: `services/chapter_workspace.py` + `GET …/chapters/{chapter_id}/workspace` (source + latest translation); nav via tree. 3B save: `services/workspace_edit.py` + `PATCH …/segments/{segment_id}/translation` (chapter-scoped ownership; source preserved; one `transaction()`; status→`manual`; `saved_at`). 3C history: `storage.list_translation_attempts` + `services/segment_history.py` + `GET …/segments/{segment_id}/translations` (all attempts oldest-first; reuses `translations.attempt`). Path-resolver consolidated to `services/project_paths.py`. 393 tests green. |
| Sprint 4A | FastAPI AI-translation foundation. `services/workspace_translate.py`: `prepare_chapter_translation` (validate + build/healthcheck provider + glossary, typed errors) and `run_translation` (per-segment loop, one txn each) — DB-derived normalized text (no source re-read, volume-safe); skip already-`translated`/`manual`. `api/jobs.py`: thread-backed `JobRegistry`. Router `api/routers/translate.py`: `POST …/chapters/{id}/translate[-segments]` (202 + job_id), `GET …/jobs/{job_id}`; per-request provider/model override; provider unhealthy→502. 413 tests green. |
| Sprint 4B | Progress + cancellation on the 4A job foundation. `TranslationJob` gains `JobProgress` (current/total/translated/failed), a cancel `Event`, and a thread-safe SSE queue; runner → `(should_cancel, progress)`. New `POST …/jobs/{job_id}/cancel` + `GET …/jobs/{job_id}/events` (SSE per-segment then terminal); status enriched with live progress. Single-process thread worker — **no external queue**. 420 tests green. |
| Sprint 4C | Safe retranslate with explicit overwrite modes. `prepare_chapter_translation(mode=…)` + `_mode_allows`; `list_chapter_segments` (mode filter in service). Modes: `skip_existing` (pending/failed/stale only), `retranslate_non_manual` (also `translated`; `manual` protected), `force_selected` (any, incl. `manual`). `POST …/chapters/{id}/retranslate[-segments]` (invalid mode → 422). Every retranslate appends a new attempt; prior attempts stay immutable history. **Sprint 4 done.** 428 tests green. |
| Sprint 5A | FastAPI direct glossary CRUD. `storage/glossary.py`: `get/upsert/delete_glossary_term` (same `glossary_terms` table). `services/glossary_terms.py` (framework-agnostic). `GET/POST/PATCH/DELETE /projects/{name}/glossary[/{source}]`; `GlossaryTermNotFoundError`→404; `ValueError`→422. Injection proof: `build_context().glossary_terms` + rendered `<glossary>` block verified. 445 tests green. |
| Sprint 5B | Character DB (schema v4). `characters` table (`UNIQUE(project_id,jp_name)`); `_migrate_to_v4`. `storage/characters.py`, `services/characters.py`, `api/routers/characters.py`: `GET/POST/PATCH/DELETE /projects/{name}/characters[/{jp_name}]`; `CharacterNotFoundError`→404. jp_name + en_name required; gender/role/notes optional. JP path-param decoding verified (エリナ/魔王). 466 tests green. |
| Sprint 5C | Character context injection. `CharacterContext`; `TranslationContext.characters`. `build_context` + `_filter_characters` (jp_name substring, cap 20); `load_character_contexts` wired into `translate_one_segment`, CLI `translate_project`, and cockpit `run_translation`. `<characters>` TSV block in `balanced_user.jinja2`; system-prompt name-consistency rule. **Sprint 5 done.** 469 tests green; PR #8. |
| Sprint 6A | Translation-memory engine. Schema v5 `translation_memory` (`UNIQUE(project_id,source_hash)`). `storage/translation_memory.py`: `lookup`/`save(protect_manual)`/`list`/`delete`/`count_memory_reuses`. Lookup-before-AI in `translate_one_segment` (hit → record `memory` attempt + skip provider; miss-success → save). Retranslate bypasses lookup but refreshes. **Manual edits = TM source of truth**; provider saves never overwrite a `manual` row. `reused_from_memory` on summaries. 483 tests green. |
| Sprint 6B | TM read/manage API. `services/translation_memory.py` (`get_memory_overview`, `delete_entry`). `GET /projects/{name}/memory`, `DELETE …/{source_hash}` (TM-row-only); `TranslationMemoryNotFoundError`→404. `reused_from_memory` surfaced in FastAPI job status/SSE, Flask job summary, CLI translate output. **Sprint 6 done.** 491 tests green. |
| Sprint 7A | Batch planning service (framework-agnostic). `services/batch_translate.py`: `prepare_batch_translation`→`BatchPlan` (scope chapter/volume/novel; validate-once; glossary+characters once; one `TranslationPlan` per chapter) and `run_batch_translation`→`BatchTranslationResult` (aggregate counters + per-chapter `BatchChapterOutcome`). Extracted shared helpers from `workspace_translate.py`. `storage/segments.py`: `chapter_exists`, `list_chapter_ids_for_volume/project` (deterministic order). `VolumeNotFoundError`. Invariant `translated+failed==segments_total`; cancel before each chapter + per-segment. 508 tests green. |
| Sprint 7B | FastAPI batch endpoints + `BatchJob`. `api/jobs.py`: `BatchJob`/`BatchProgress` + `JobRegistry.submit_batch`/`get_batch` (separate `_batch_jobs`). `POST /projects/{name}/batch/{novel|volumes/{id}|chapters/{id}}` → 202; `GET …/batch/jobs/{id}`, `POST …/cancel`, `GET …/events` (SSE). Pydantic batch schemas. project/volume/chapter→404, invalid mode→422, unhealthy provider→502. Chapter routes untouched; no external queue; Flask untouched. 522 tests green. |
| Sprint 7C | Docs + regression. `TRANSLATION_PIPELINE.md` §10b, `COCKPIT_WORKFLOW.md` batch API, `ARCHITECTURE.md` inventory, `MVP_SCOPE.md` batch row. **Sprint 7 done.** 522 tests green, ruff + format clean, pyright 0, CLI/Flask/FastAPI smoke. |
| Sprint 8A | Export Foundation (framework-agnostic, **EPUB only**). `services/export_book.py`: `prepare_export`→`ExportPlan` / `run_export`→`ExportResult` + `export_novel/volume/chapter`; **per-volume EPUB artifact**. EPUB-sourced reuse `render_translated_epub` (write-back); TXT/HTML-sourced → `renderers/epub_synthesis.py` `synthesize_epub` (from DB; source never re-read). Publishable = latest, `source_hash`-matched, `translated`/`manual` (history never exported); else source fallback (`FallbackByStatus`). Read-only. New storage: `get_chapter`/`ChapterRecord`, `list_export_segment_states`. 539 tests green. |
| Sprint 8B | FastAPI export endpoints + `ExportJob` (thin adapter; no domain logic duplicated). `api/jobs.py`: `ExportJob`/`ExportProgress` + `submit_export`/`get_export` (separate `_export_jobs`). `POST /projects/{name}/export/{novel|volumes/{id}|chapters/{id}}` → 202; `GET …/export/jobs/{id}`, `POST …/cancel`, `GET …/events` (SSE). `run_export` gained optional `should_cancel`/`progress_callback` + `ExportResult.cancelled`. EPUB only; project/volume/chapter→404, unsupported target→422. 551 tests green. |
| Sprint 8C | TXT + HTML output targets (reuse 8A/8B). `renderers/txt.py` + `renderers/html.py` + shared `renderers/rendered_document.py` (`RenderChapter` + `block_to_html`). `EXPORT_TARGETS = {epub, txt, html}`; `export_book` dispatches by target (artifacts under `output/<target>/`). TXT/HTML built from DB (no source re-read), same publishable + fallback rule. Endpoints accept `target` ∈ {epub,txt,html}; `docx`→422. **DOCX output + export UI deferred** (ADR 005). **Sprint 8 done.** 561 tests green. |
| Sprint 9A | MVP stabilization — audit + validation (no behavior change). 561 tests / 4 skipped, pyright 0, ruff + format clean, CLI smoke (15), FastAPI smoke (37 routes), Flask smoke (14 routes). Acceptance audit: features 1–7 evidenced; feature 8 (export) partial-by-design (EPUB/TXT/HTML; DOCX→422). **No MVP-baseline blockers**; 4 doc-only findings. New artifact: `docs/MVP_STABILIZATION_REPORT.md`. |
| Sprint 9B | MVP stabilization — doc/regression alignment (no behavior change). `MVP_SCOPE.md` acceptance checklist; CLI-vs-FastAPI export split documented (ARCHITECTURE/COCKPIT/QUICKSTART); `CLAUDE.md` status; consolidated deferred list in `MVP_STABILIZATION_REPORT.md` §4; `MAINTENANCE.md` Sprint 9 validation commands + 4-skip set. Re-validation green. |
| Sprint 9C | MVP stabilization — E2E proof + baseline (no behavior change). Full workflow on the **real 18-chapter / 2945-segment EPUB** via FastAPI cockpit + services: create → import TXT/HTML → tree → glossary → character → translate → manual edit → history → safe retranslate (skip/force/manual-protect) → TM reuse (`reused_from_memory=1`) → batch → export EPUB/TXT/HTML → artifact verification; 14/14 steps green. **Live-provider translation verified for real** via Groq (`custom`, `llama-3.3-70b-versatile`) — 3/3 narrative segments, `failed=0`; one healthcheck json-mode fix (`providers/deepseek.py`) + regression test. Keys env-only, redacted, never committed. **MVP baseline LOCKED. Sprint 9 done.** 562 tests green. Report: [docs/MVP_STABILIZATION_REPORT.md](docs/MVP_STABILIZATION_REPORT.md). |
| Sprint 10A | Flask↔FastAPI parity audit (**audit only — no code change, no removal**). Flask (13 routes, legacy flat single-project, full HTML UI) vs FastAPI (41 routes, Novel/Volume/Chapter MVP, headless JSON). FastAPI = domain superset but **parity incomplete** on 4 counts: web UI; provider/secret config-write API; glossary candidate-review; create-novel + file browser. All 4 reachable via CLI. **Gate 10A decision: KEEP Flask** — `serve`=Flask, `serve-api`=FastAPI; no flip/deletion. Artifact: [docs/SPRINT10_PARITY_AUDIT.md](docs/SPRINT10_PARITY_AUDIT.md). 562 tests green. |
| Sprint 10B | FastAPI Create Novel + File Browser — **closes parity gap #4** (no UI, no Flask removal/flip). Browser logic → framework-agnostic `services/source_browser.py` (`list_directory`/`resolve_source`/`sanitize_source_filename`/`store_uploaded_source`); `web/file_browser.py` re-exports it (Flask unchanged). `GET /projects/browse?dir=` (sandboxed) + `POST /projects/create` (upload **or** browsed `source_path`, optional provider/template; no-source→422, duplicate→409, bad source/provider→422). Sourceless creation unsupported (name from stem). 586 tests (+24), smokes FastAPI 43 / Flask 13 / CLI 15. |
| Sprint 10C | FastAPI Provider/Secret Config Write API — **closes parity gap #2** (no UI, no Flask removal/flip). Framework-agnostic `services/provider_config.py` (redacted `read_config`/`write_config`/`store_secret`/`remove_secret`) reuses `config_writer.set_provider` + `core/secret_store`; new `SecretNotFoundError`. `GET /config` (defaults + secret names; `?project=` adds `[provider]` + `api_key_set`; unknown→404), `PATCH /config` (scope project\|global; unknown provider/scope/missing project→422), `POST/DELETE /config/secrets/{env_name}` (store value→201, invalid/empty→422, unknown→404). **Secrets keyed by env-var name** (existing store abstraction). **Key values never accepted by PATCH, never returned** (verified vs responses + OpenAPI). 609 tests (+23), smokes FastAPI 47 / Flask 13 / CLI 15 + redaction clean. |
| Sprint 10D | FastAPI Glossary Candidate Review API — **closes parity gap #3** (no UI, no Flask removal/flip). Thin adapter `api/routers/glossary_review.py` over existing `services/glossary_review` + `services/glossary_diff` — no new logic, **no second glossary store**. `GET …/glossary/candidates` (paged + counts + `find`), `POST …/candidates/{id}/{approve,edit,reject}`, `GET …/glossary/conflicts`, `GET …/glossary/diff?a=&b=`. Approve/edit write the same `glossary_terms` rows; CRUD unchanged & not shadowed. New typed `GlossaryCandidateNotFoundError`→404 (still `WeaverError`, Flask handler unchanged); edit-empty/diff-out-of-range→422. 622 tests (+13, 1 retargeted), smokes FastAPI 53 / Flask 13 / CLI `glossary` intact. **Only parity gap #1 (web UI) remains.** |
| Sprint 10E | Flask↔FastAPI parity **re-audit** (audit only — no code change, no removal). Flask 13 vs FastAPI 53 route objects; every Flask route maps 1:1+ to FastAPI (matrix in [docs/SPRINT10_PARITY_AUDIT.md](docs/SPRINT10_PARITY_AUDIT.md) §9); gaps #2/#3/#4 confirmed closed. **All functional parity complete — only the rendered web UI (gap #1) remains, a deliberate ADR-005 deferral.** Decommission risk: removing Flask now = 🔴 High (only browser cockpit); coupling 🟢 Low. **Gate 10E decision (maintainer, 2026-06-03): Option 1 — KEEP Flask as legacy UI/fallback.** Flask removal requires a FastAPI UI first, then another parity audit (Sprint 12). **Sprint 10 complete.** 622 tests green. |
| Sprint 11A | FastAPI UI shell (ADR `007`: server-rendered Jinja2 + HTMX, no Node/build, no SPA; **no Flask removal/flip**). `api/templating.py` (`Jinja2Templates` + `/static` mount; no new dep — `jinja2` already core), vendored `api/static/htmx.min.js` (pinned 1.9.12, no CDN) + minimal `app.css`, templates `base/dashboard/project/not_found/error.html`, **presentation-only** `api/routers/ui.py` over `project_discovery`/`project_tree`/`global_config`. Routes: `GET /`→307 `/ui`, `GET /ui` (dashboard), `GET /ui/projects/{name}` (tree; unknown→404 HTML), `/static/*`. UI under `/ui`, `include_in_schema=False`; JSON API unchanged + unshadowed. State primitives loading/empty/error/404. No visual polish. 630 tests (+8), pyright 0, ruff + format clean; smokes FastAPI 56 route objs (incl. JP titles), Flask 13, CLI 15. |
| Sprint 11B-1 | Core Workflow UI — create/import + file browser (Jinja2 + HTMX; **no Flask removal/flip**). New `services/source_intake.py` (`resolve_intake_source`, framework-agnostic); JSON `POST /projects/create` refactored onto it (behavior identical). UI routes (presentation-only, reuse services): `GET/POST /ui/new` (create → 303), `GET /ui/browse?dir=` (sandboxed fragment), `POST /ui/projects/{name}/import` (→ refreshed `#tree`; errors → `HX-Retarget:#import_error`). Templates `new.html` + `partials/{_tree,_browse,_import_error}.html`; project view gains import panel + browser. 641 tests (+11), pyright 0, ruff + format clean; full flow proven (browse→create→import→tree refresh). **Surfaced a pre-existing storage bug** (chapter re-parenting on duplicate-content import; chapter IDs not volume-scoped) — reproduces without UI, fixed in 11B-1.5. |
| Sprint 11C | Consistency/admin UI — glossary/characters/TM/config (Jinja2 + HTMX; **no Flask removal/flip; no glossary/character/TM/provider behavior change**). New `api/routers/ui_admin.py` (presentation-only) over existing services: glossary term CRUD + candidate review (approve/edit/reject, conflicts, coverage diff), character DB CRUD, TM read/delete, provider/model + secret config. Pages `/ui/projects/{name}/{glossary,characters,memory}` + `/ui/config` (global + `?project=` scope); each mutation re-renders its HTMX fragment. Templates `{glossary,characters,memory,config}.html` + `partials/{_glossary_terms,_glossary_candidates,_glossary_diff,_characters,_memory,_config_form,_secrets}.html`; project page links glossary/characters/memory; base nav adds Config. **API-key values accepted only by the secret-set form, never rendered back** (verified: value absent from fragment + page). Secret store + global config isolated to tmp in tests. 683 tests (+15 `test_ui_admin.py`), pyright 0, ruff + format clean; smokes Flask 13 / FastAPI 87 (+17) / CLI 15 intact. **Sprint 11 complete — FastAPI UI functional parity reached.** |
| Sprint 11B-3 | Translate/retranslate + job progress + export UI (Jinja2 + HTMX; **no Flask removal/flip; no provider/TM/export behavior change**). Workspace gains a Translate button + Retranslate mode select (`skip_existing`/`retranslate_non_manual`/`force_selected`); project page gains an Export control (EPUB/TXT/HTML). UI routes reuse the JSON-router start helpers (`translate._start_job`, `export._start_export`) over the shared `JobRegistry` + services — no job logic re-implemented. Self-polling HTMX panels (`hx-trigger="load delay:1s"`) show live progress + Cancel + terminal result (translate counts / export artifact paths); terminal panels drop the poll trigger. Errors (e.g. unhealthy provider → 502) render in-panel. New routes: `POST …/chapters/{id}/translate|retranslate`, `GET/POST …/jobs/{id}[/cancel]`, `POST …/export`, `GET/POST …/export/jobs/{id}[/cancel]`. Templates `partials/{_job,_export_job,_job_error}.html`. 668 tests (+13 `test_ui_jobs.py`), pyright 0, ruff + format clean; rendered proof (translate→done translated 4; export epub→1/1 volumes, artifact path). Flask 13 / FastAPI 70 (+7) / CLI 15 intact. |
| Sprint 11B-2 | Workspace UI — read/save/history (Jinja2 + HTMX; **no Flask removal/flip**). Project-tree chapters link to a two-column JP/EN workspace; per-segment save (status → `manual`) swaps the refreshed row via HTMX; per-segment translation history loads on demand. Presentation-only `api/routers/ui.py` routes (`GET /ui/projects/{name}/chapters/{id}`, `POST …/segments/{id}`, `GET …/segments/{id}/history`) reuse `services/chapter_workspace`, `services/workspace_edit.save_segment_translation`, `services/segment_history` — no logic in UI. Templates `workspace.html` + `partials/{_segment,_history}.html`; `_tree.html` chapters now linked; layout-only CSS. 655 tests (+9 `test_ui_workspace.py`), pyright 0, ruff + format clean; rendered proof (read → save `manual` → reload persists → history attempt). Manual edit survives refresh; both duplicate volumes' chapters open (11B-1.5 guard). Flask 13 / FastAPI 63 (+3) / CLI 15 intact. |
| Sprint 12A | FastAPI UI parity **audit** + default-`serve` decision (audit only — no code change). Re-enumerated live: Flask 14 url-map rules (13 functional) vs FastAPI 53 JSON + 35 UI route entries. Parity matrix across the 12 audited capabilities (dashboard, create/import/browse, tree, workspace read/save/history, translate/retranslate/jobs, export, glossary CRUD, candidate review, characters, TM, provider config, secret write): **FastAPI UI = 12/12, a strict superset of the Flask UI (7/12)**. No functional gap blocks a flip; only differences are visual polish (deferred, ADR 005), legacy markdown export (Flask-only, no consumer), operational continuity. Artifact: [docs/SPRINT12_UI_PARITY_AUDIT.md](docs/SPRINT12_UI_PARITY_AUDIT.md). **Gate 12A decision (maintainer, 2026-06-03): Option 2 — flip default to FastAPI, keep Flask as `serve-flask`.** 683 tests green. |
| Sprint 12B | Default-`serve` flip (CLI + docs; **no Flask route/template/dependency removal; reversible**). `weaver serve` → FastAPI cockpit (UI; default, :8765, opens browser, `--books-dir`/`--no-browser`/`--reload`); `weaver serve-api` → same FastAPI app headless (:8000); new `weaver serve-flask` → legacy Flask cockpit (verbatim old `serve` body, :8765). Shared `_run_fastapi_cockpit` helper (uvicorn factory + optional chdir for `books_dir` + Timer browser-open). Docs updated (QUICKSTART, COCKPIT_WORKFLOW, ARCHITECTURE, CLAUDE.md). New `tests/integration/test_cli_serve_routing.py` (+5): `serve`→FastAPI factory, `serve-flask`→Flask `run_server`, help-text routing. 688 tests / 4 skipped, pyright 0, ruff + format clean (238 files); CLI 16 commands; `serve`/`serve-api`/`serve-flask --help` ok; FastAPI UI (`/ui`,`/ui/new`,`/ui/config`→200) + Flask fallback (`/`→200) smokes green. **Sprint 12 complete.** |
| Sprint 11B-1.5 | Import volume-id collision fix (storage/services; **no UI/Flask/serve change**). Chapter/segment ids were content-derived (`compute_chapter_id`/`compute_segment_id`, blake2b) with no volume component, so importing a source whose content collided with an existing volume re-parented its chapters via the `ON CONFLICT(id)` upsert (first volume → 0 chapters). Fix: new `core.segment.scope_id_to_volume` + `core.ir.scope_document_to_volume`; the freshly-read `DocumentIR` is scoped **once** to its volume at every read→persist boundary (`initialize_project`, `import_volume`, CLI `translate_project` re-read, legacy `export.py` markdown/epub, volume-aware `export_book.py` EPUB write-back); `sync_document_segments` stores ids as-given (no double-scope). Re-syncing the same volume reproduces the same ids (idempotent); **no schema change / migration** (existing rows keep their ids). Duplicate import now keeps both volumes' chapters; ids disjoint across volumes. Note: legacy CLI translate/export stay single-volume (unchanged); multi-volume is the cockpit's job. 646 tests (+5 `test_import_volume_collision.py`; 1 export-test helper scoped to mirror production), pyright 0, ruff + format clean; UI repro now `[(2,6),(2,6)]`; Flask 13 / FastAPI 60 / CLI 15 intact. |
| Sprint 13A | Flask decommission **readiness audit** (audit only — no removal). Stability of the 12B flip verified green (688 tests / 4 skipped, pyright 0, ruff + format clean); FastAPI UI smoke (`/`→307, `/ui`/`/ui/new`/`/ui/config`→200) + Flask fallback smoke (14 rules, `/`→200). Flask dependency map: `src/weaver/web/**` self-contained (872 LoC + 5 templates + 2 static); **only one external runtime importer** (`cli/main.py` `serve-flask`); `job_manager.py` Flask-only (FastAPI uses `api/jobs.py`); `file_browser.py` a re-export shim over `services/source_browser.py`; `flask>=3.0` the only Flask-specific dep. No 🔴 code risk; residual risk operational (losing the only fallback UI). **Gate 13A decision (maintainer, 2026-06-04): Option B — postpone removal one cycle, prove the flipped default on a real workflow first.** Artifact: [docs/SPRINT13A_DECOMMISSION_READINESS.md](docs/SPRINT13A_DECOMMISSION_READINESS.md). |
| Sprint 13A.5 | FastAPI default **soak test** (no code/flip change). Full novel workflow driven against a **live `weaver serve` FastAPI cockpit** over HTTP (`fake` provider per §4.2; multi-format EPUB/TXT/HTML, 3 volumes): create → import ×3 → workspace read/save(`manual`)/history → translate (3 ok, 1 manual-protected) → retranslate `force_selected` (4 ok) → glossary/character/TM/config → batch novel (11 translated, 0 failed) → export EPUB/TXT/HTML (3/3 artifacts on disk each). **25/25 steps passed; `serve-flask` never started; no blockers/regressions.** Reusable driver `scripts/soak_13a5.py`. Validation green (688/4-skip, pyright 0, ruff+format clean, CLI 16, FastAPI UI smoke). **Gate 13A.5 decision (maintainer, 2026-06-04): Option A — proceed to Flask decommission.** Artifact: [docs/SPRINT13A5_SOAK_RESULT.md](docs/SPRINT13A5_SOAK_RESULT.md). |
| Sprint 13B | **Flask decommission** (Flask-specific removal only; no FastAPI/serve/serve-api behavior change; services/core/storage/providers untouched). Removed: `weaver serve-flask` command + its `serve` epilog/docstring references; `src/weaver/web/**` (10 py + 5 templates + 2 static); Flask-only tests `tests/unit/web/{test_job_manager,test_file_browser}.py` + `tests/integration/test_web_cockpit.py` (`test_cli_serve_routing.py` retargeted to FastAPI-only — `serve`/`serve-api` routing + asserts `serve-flask` gone); `flask>=3.0` from the `web` extra (`uv.lock` refreshed — flask/werkzeug/blinker/itsdangerous gone). Doc sweep: README, QUICKSTART, COCKPIT_WORKFLOW, ARCHITECTURE, MAINTENANCE, TRANSLATION_PIPELINE, PROVIDER_AND_MODEL_CONFIG, DECISIONS + dated status notes on ADR 002/004/007. **651 tests / 4 skipped** (−37 Flask-only), pyright 0, ruff + format clean (226 files), CLI **15** commands, FastAPI UI smoke green, `serve-flask`→no-such-command, `import flask`→ModuleNotFoundError, no `weaver.web` imports in tree. Re-validated via `scripts/soak_13a5.py` against live `weaver serve` (25/25). **Sprint 13 complete — FastAPI is the sole web cockpit.** |
| MVP RC1 | **Release-candidate verification sprint** (no new features/UI/providers/migration; doc + tooling fixes only). All PRs (`#1`–`#16`) merged; full validation green (**653 tests / 4 skipped**, pyright 0, ruff + format clean, 227 files); CLI 15 commands; cockpit soak 25/25 ("Flask fallback NOT used"); **clean-env wheel install** smoke green (`flask` absent, console script + `serve` work). Fixed 7 stale-Flask source docstrings + 3 README cockpit bullets (Markdown→EPUB/TXT/HTML, first-N/retry→retranslate modes); made `scripts/soak_13a5.py` UTF-8-safe on Windows cp1252; populated `CHANGELOG.md` `[Unreleased]`. No secret leaks, no orphaned artifacts. **Verdict: GO for RC1.** Recommended tag `v0.7.0-rc.1` (alt `v1.0.0-rc.1`). Report: [docs/RC1_REPORT.md](docs/RC1_REPORT.md). |

---

## 3. Stack (Locked)

**Use:** Python 3.11+ · uv · pyproject.toml · ruff · pyright (basic) · pytest · typer · rich · pydantic v2 · tomllib · sqlite3 (WAL, no ORM) · ebooklib · openai SDK · google-generativeai · Jinja2.

**Web cockpit:** **FastAPI** (ADR `004`), behind optional extra `weaver[web]` (FastAPI + Uvicorn + python-multipart); core install pulls no web framework. UI is server-rendered **Jinja2 + HTMX**, no Node/build, no SPA (ADR `007`); HTMX vendored as a static asset (no CDN). asyncio unlocked **only** for the FastAPI web layer. The legacy Flask cockpit was removed in Sprint 13B (Flask→FastAPI migration complete; FastAPI is the sole web surface).

**Still rejected (no reintroduction without ADR):** Flask · Django · SQLAlchemy · Celery · RQ · Docker · React/Node build · SPA framework · OpenTelemetry · Sentry. asyncio remains rejected outside the web layer.

**Providers:**

| Provider | Role | Auth |
|----------|------|------|
| `deepseek` | Default cloud | `DEEPSEEK_API_KEY` |
| `gemini` | Free-tier cloud | `GEMINI_API_KEY` |
| `ollama` | Local, optional | None |
| `custom` | Any OpenAI-compatible endpoint | env var named by `api_key_env` |
| `fake` | CI/dev default | None |

Provider types are registry-driven (`providers/registry.py`). API keys resolve from env vars or the local secret store `~/.weaver/secrets.toml` (mode `0o600`, env wins); **never** in `project.toml`/global config, never logged, never rendered.

---

## 4. AI Instructions

### 4.1 Before Coding
- Read the relevant doc/ADR section. Docs are authoritative.
- Match sprint order. No jumping ahead. Run the §2.2 phase gate before a new sprint.
- Use exact names/values from docs for types, schemas, exit codes. No improvisation.
- When unsure: ask. Do not invent fields, prompts, commands, exit codes.
- During the reset: respect [claude.local.md](claude.local.md) task order and stop at each gate.

### 4.2 Code Rules (Non-Negotiable)

Source: [ENGINEERING_STANDARDS.md](docs/ENGINEERING_STANDARDS.md), ADR `002`.

- Type hints on every public function. Pyright basic must pass.
- One concept per file. Split if >400 lines or >5 public functions.
- Forbidden filenames: `utils.py`, `helpers.py`, `manager.py`. Name modules for what they do.
- No `**kwargs` in public APIs. No `except: pass`; no `except Exception: pass` outside the CLI/web boundary.
- All errors via the `WeaverError` hierarchy (`src/weaver/errors.py`). User-facing errors: **what failed / likely cause / next command**.
- State writes go through services. CLI/web never touch SQLite directly. One segment translation = one transaction.
- Shared/core stays framework-agnostic (no web `Request`/`Response`, no DI wiring, no template/CLI output). Pydantic only at the web boundary. UI templates/routes carry no business logic.
- API keys via env vars or `~/.weaver/secrets.toml` only — never in config, never logged, never rendered. Shell env wins.
- `@dataclass(frozen=True)` for value types. `pathlib.Path` for paths. Atomic writes (`tempfile` + `replace`) for valuable state.
- Tests mirror source tree. Use `FakeProvider`, never live LLMs in CI. Fixtures = public-domain only.

### 4.3 Anti-Slop

Source: [AI_SLOP_PREVENTION.md](docs/AI_SLOP_PREVENTION.md).

- No "smart"/"AI-powered"/"magical"/"intelligent" feature names. No chat UIs, avatars, sparkles, fortune-cookie loaders.
- Deterministic by default. LLM only when determinism is impossible AND output is verifiable AND the user can override.
- No config flags for unbuilt features. No stub functions, no commented-out code, no abstractions with one caller.

### 4.4 Scope Discipline

- Build only what the active sprint (§2.3) and ADR `003` list. Deferred/advanced items get no scaffolding "for later".
- One PR = one concern. No bundled refactor + feature.
- Reset tasks do not implement MVP features (Task 5 plans them; sprints build them).

### 4.5 Communication

- Terse, technical. No filler, no apology, no marketing language.
- Reference files as `[name](path/file.md)` or `src/weaver/foo.py:42`. State decisions directly.

### 4.6 Contribution Identity

- Agentic AI must not appear as a GitHub contributor, author, committer, co-author, or bot identity.
- Do not add `Co-Authored-By`, `Generated-By`, `Assisted-By`, or similar trailers for any AI tool.
- Commit author and committer = the maintainer account only.
- Before any commit/PR, scan the message + recent history for AI attribution trailers/bot authors.
- The repo hooks in `.githooks/` are mandatory local guardrails. Keep `git config core.hooksPath .githooks` enabled.
- If an AI attribution trailer or bot author is found after commit, stop work and clean history before opening/updating PRs.
