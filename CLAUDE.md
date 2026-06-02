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
| [docs/COCKPIT_WORKFLOW.md](docs/COCKPIT_WORKFLOW.md) | Web cockpit (Flask baseline → FastAPI target) |
| [docs/PROVIDER_AND_MODEL_CONFIG.md](docs/PROVIDER_AND_MODEL_CONFIG.md) | Providers, models, secret store |
| [docs/TRANSLATION_PIPELINE.md](docs/TRANSLATION_PIPELINE.md) | Import → segment → translate → QA → export |
| [docs/MVP_SCOPE.md](docs/MVP_SCOPE.md) | MVP features, gap analysis, sprint mapping, acceptance |
| [docs/MVP_STABILIZATION_REPORT.md](docs/MVP_STABILIZATION_REPORT.md) | Sprint 9 baseline: validation matrix, acceptance audit, **consolidated deferred/known-gaps list** |
| [docs/MAINTENANCE.md](docs/MAINTENANCE.md) | Cleanup, testing, regression, release, migration discipline |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Active ADR index (`001`–`005`) |
| [docs/decisions/](docs/decisions/) | Active ADRs `001`–`005` |
| [ENGINEERING_STANDARDS.md](docs/ENGINEERING_STANDARDS.md) · [PROMPT_DESIGN.md](docs/PROMPT_DESIGN.md) · [SECURITY_AND_PERFORMANCE.md](docs/SECURITY_AND_PERFORMANCE.md) · [AI_SLOP_PREVENTION.md](docs/AI_SLOP_PREVENTION.md) | Supplementary reference specs (still active) |
| [docs/archive/](docs/archive/) | Archived ADRs `0001`–`0020`, pre-reset specs (PRD_v2, SYSTEM_ARCHITECTURE), strategy docs — historical |

---

## 2. Progress

### 2.1 Roadmap

**Foundation (shipped, v0.6.0):** CLI complete (init, inspect, translate, edit, glossary, export, validate, preview, doctor, new, dashboard, serve, secrets) + Flask web cockpit end-to-end (discovery, monitor+SSE, file browse/upload, provider config, translate+stop, export, glossary review). Detail: git history + `docs/archive/`.

**Active: MVP Web Cockpit Foundation** — build the consistency-first translator workflow (ADR `003`) and begin the FastAPI direction (ADR `004`).

| Sprint | Scope                                                                             | Difficulty | Risk         | Status |
| ------ | --------------------------------------------------------------------------------- | ---------: | ------------ | ------ |
| 1      | Project structure & novel management (Novel/Volume/Chapter; TXT/EPUB/HTML import) |       4/10 | 🟢 Low       | ✅      |
| 2      | FastAPI cockpit foundation (2A app+`/health`+`/version` · 2B project read APIs · 2C import API) |       5/10 | 🟢 Low       | ✅      |
| 3      | Translation workspace, FastAPI (JP/EN two-column read, edit, save, revision history) |       7/10 | 🟡 Medium    | ✅      |
| 4      | Provider & AI translation (config, translate chapter/selection, safe retranslate) |     9.5/10 | 🔴 Very High | ✅      |
| 5      | Glossary & character database (project-scoped, prompt injection)                  |       8/10 | 🔴 High      | ✅      |
| 6      | Translation memory (source→target store, lookup-before-AI, reuse)                 |      10/10 | 🔴 Very High | ✅      |
| 7      | Batch translation & progress (chapter/volume/novel, job status)                   |       9/10 | 🔴 Very High | ✅      |
| 8      | Export (EPUB priority, TXT, HTML, DOCX)                                           |       6/10 | 🟡 Medium    | ✅      |
| 9      | MVP stabilization (smoke CLI+web, regression, acceptance checklist, UI/UX plan)   |       7/10 | 🟡 Medium    | 🟡      |
| 10     | Flask decommission — only after FastAPI parity audit                              |       5/10 | 🟡 Medium    | ⬜      |


Legend: ✅ complete · 🟡 in progress · ⏳ next · ⬜ pending · 🚫 blocked.

> Re-sequenced 2026-05-30: FastAPI foundation inserted as Sprint 2; remaining MVP sprints shifted +1; Flask decommission appended (Sprint 10, gated on FastAPI parity). Sprint detail + MVP gap analysis in [docs/MVP_SCOPE.md](docs/MVP_SCOPE.md). Sprint ordering is dependency-driven, not calendar.
>
> Sprint 8 (Export) is marked ✅ having shipped **EPUB/TXT/HTML** via the framework-agnostic service + FastAPI endpoints; **DOCX is deferred** (out of MVP) and the export **UI** is post-MVP polish (ADR `005`).

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

Focus: build the core JP→EN light-novel translator workflow before UI polish.

Rules:
- Web/cockpit is the primary development focus.
- Web/cockpit backend direction is **FastAPI-first** (ADR `004`) — but the **Flask cockpit stays the working baseline** until migration parity. Do not delete Flask now; no FastAPI implementation until its own sprint/gate.
- CLI must remain functional and wire-compatible.
- Shared/core must stay framework-agnostic (ADR `002`).
- UI polish starts only after MVP baseline is clear (ADR `005`).
- MVP gaps must map to actionable sprints (ADR `003`).

Reset status: Tasks 1–5 done (audit · cleanup/ADR reset · docs rewrite · fresh baseline · MVP gap finalize + sprint lock — all checks green; gap table verified against `src/weaver/` in [docs/MVP_SCOPE.md](docs/MVP_SCOPE.md)).

Sprint status: Sprints 1–8 complete. **Sprint 7 complete (7A+7B+7C)** — batch translation at chapter/volume/novel scope on the existing per-chapter pipeline + job infra. 7A: `services/batch_translate.py` (`prepare_batch_translation`→`BatchPlan`, `run_batch_translation`→`BatchTranslationResult`); validate-once setup extracted from `prepare_chapter_translation` (`validate_provider_config`/`load_translation_context`/`build_healthy_provider`/`select_chapter_targets`/`load_single_project`); ordered chapter-id helpers `list_chapter_ids_for_volume`/`list_chapter_ids_for_project` + `chapter_exists` in `storage/segments.py`; `VolumeNotFoundError`; deterministic reading order; empty scope = `done(0)`; counter invariant `translated+failed==segments_total`, `reused_from_memory⊆translated`; cooperative cancel before each chapter (+ per-segment via `run_translation`). 7B: `BatchJob`/`BatchProgress` + `JobRegistry.submit_batch`/`get_batch` (separate `_batch_jobs` dict; batch id not resolvable via chapter `get`); `api/routers/batch.py` (`POST /projects/{name}/batch/{novel|volumes/{id}|chapters/{id}}` → 202; `GET/POST/GET /projects/{name}/batch/jobs/{id}[/cancel|/events]`); Pydantic batch schemas; chapter `/translate*`+`/retranslate*` untouched; TM semantics unchanged; no external queue; Flask untouched. 7C: docs (TRANSLATION_PIPELINE §10b, COCKPIT_WORKFLOW batch API, ARCHITECTURE inventory, MVP_SCOPE gap+acceptance) + this status. 522 tests green. **Sprint 5 complete (5A+5B+5C)** — 5A: FastAPI direct glossary CRUD (`GET/POST/PATCH/DELETE /projects/{name}/glossary[/{source}]`), project-scoped, same `glossary_terms` table as candidate-review flow. 5B: character DB (schema v4, `characters` table `UNIQUE(project_id,jp_name)`); `GET/POST/PATCH/DELETE /projects/{name}/characters[/{jp_name}]`; `CharacterNotFoundError`→404. 5C: `CharacterContext` + `TranslationContext.characters`; `build_context` filters by `jp_name` substring (cap 20); `load_character_contexts` wired into `translate_one_segment`, `translate_project`, and `prepare_chapter_translation`→`run_translation`; `<characters>` block in `balanced_user.jinja2`; system-prompt rule for name consistency. 469 tests green; PR #8. **Sprint 6 complete (6A+6B)** — TM engine + FastAPI read/delete API. 6A: schema v5 `translation_memory` (`UNIQUE(project_id,source_hash)`); `lookup`/`save`/`list`/`delete`; lookup-before-AI in `translate_one_segment` (hit → record `memory` attempt, skip provider; miss-success → save); `use_translation_memory` flag off for retranslate; manual edits = source of truth (`protect_manual`); `reused_from_memory` on summaries. 6B: `services/translation_memory.py` + `api/routers/translation_memory.py` (`GET /projects/{name}/memory` overview+stats, `DELETE …/{source_hash}` TM-row-only); `reused_from_memory` surfaced in CLI/web/API. 491 tests green. **Sprint 8 in progress — 8A complete (Export Foundation).** Volume-aware EPUB export for the Novel/Volume/Chapter model: `services/export_book.py` (`prepare_export`→`ExportPlan`, `run_export`→`ExportResult`, `export_novel`/`export_volume`/`export_chapter`); **per-volume artifact** (one EPUB per volume, no cross-EPUB merge). EPUB-sourced volumes reuse `renderers/epub.py` write-back; **TXT/HTML-sourced volumes** use new `renderers/epub_synthesis.py` (`synthesize_epub`, built from persisted IR/DB — source files never re-read). Publishable rule: **latest** attempt with matching `source_hash`, status `translated`/`manual` (manual preserved; **history never exported**); other statuses → **source fallback** (`FallbackByStatus`: pending/in_progress/failed/stale/skipped/untranslated; hash-mismatched translated/manual → `untranslated`); export never blocks/blanks/drops. **Read-only** (no new `translations` rows; provider + TM untouched). New storage: `get_chapter`/`ChapterRecord`, `list_export_segment_states`/`ExportSegmentState`; `services/project_paths.resolve_output_dir`; collision-safe filenames (reading-order index + volume id). EPUB target only — TXT/HTML/DOCX output, FastAPI export endpoints, UI, batch export, combined EPUB deferred (8B+). 539 tests green; pyright 0; ruff + format clean. **8B complete (FastAPI export endpoints).** `ExportJob`/`ExportProgress` + `JobRegistry.submit_export`/`get_export` (separate `_export_jobs` dict — export id not resolvable via chapter/batch `get`); `api/routers/export.py` (`POST /projects/{name}/export/{novel|volumes/{id}|chapters/{id}}` → 202; `GET/POST/GET …/export/jobs/{id}[/cancel|/events]` status/cancel/SSE); per-volume progress + cooperative cancel (before each volume); Pydantic export schemas; `run_export` gained optional `should_cancel`/`progress_callback` (8A callers unchanged) + `ExportResult.cancelled`. EPUB-only; no DOCX/TXT/HTML output, combined EPUB, ZIP, or UI; translation/TM/provider + Flask untouched. 551 tests green; pyright 0; ruff + format clean. **8C complete (TXT + HTML output targets).** `renderers/txt.py` (`render_txt`) + `renderers/html.py` (`render_html`) + shared `renderers/rendered_document.py` (`RenderChapter` + `block_to_html`, now used by `epub_synthesis` too); `EXPORT_TARGETS = {epub, txt, html}`; `export_book` dispatches by target (`_render_volume`/`_build_volume_plan` target-aware; artifacts under `output/<target>/`, extension = target); TXT/HTML build from the DB (`_resolved_chapters`, no source re-read) with the same publishable + source-fallback rule; `ExportError` for TXT/HTML write failures. Endpoints accept `target` ∈ {epub,txt,html} (docx → 422). EPUB-source→TXT/HTML proven not to re-read source. 561 tests green; pyright 0; ruff + format clean. **DOCX output + export UI deferred** (DOCX out of MVP; UI is post-MVP polish per ADR 005). **Sprint 9 — MVP stabilization — in progress.** 9A (audit + validation) complete: 561 tests, pyright 0, ruff + format clean, CLI smoke (15 commands), FastAPI smoke (37 routes), Flask smoke (14 routes); **no MVP-baseline blockers** (DOCX confirmed deferred via 422, not a blocker). 9B (doc/regression alignment) complete: MVP_SCOPE acceptance checklist updated (EPUB/TXT/HTML done, DOCX deferred), CLI-vs-FastAPI export split documented (ARCHITECTURE/COCKPIT/QUICKSTART), MAINTENANCE Sprint 9 validation commands + skip set, consolidated deferred list cross-linked. Full report: [docs/MVP_STABILIZATION_REPORT.md](docs/MVP_STABILIZATION_REPORT.md). Next: **9C — final E2E workflow proof + MVP baseline report**.

### 2.4 Exit Criteria

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

| Era | Outcome |
|---|---|
| Phases 0–13 (v0.6.0) | CLI + Flask web cockpit shipped. Detail in git history + `docs/archive/`. |
| Reset Tasks 1–5 | Controlled reset to MVP Web Cockpit Foundation + FastAPI direction. ADRs reset to `001`–`005`; MVP gap finalized + 8-sprint plan locked (Task 5). Gate 5 pending review. |
| Sprint 1 | Novel/Volume/Chapter model (schema v3, v2→v3 migration); EPUB/TXT/HTML import; `weaver import` CLI; Flask project-detail tree + multi-format import UI; ADR 006. 345 tests green. |
| Sprint 2 | FastAPI cockpit (`src/weaver/api/`, own namespace, no Flask import): `create_api_app()`, `/health`, `/version`, `GET /projects`, `GET /projects/{name}/tree`, `POST /projects/{name}/import`; `weaver serve-api`; reuses `services/project_tree` + `import_source`. Flask baseline intact. 361 tests green. |
| Sprint 3 | 3A read workspace: `services/chapter_workspace.py` + `GET …/chapters/{chapter_id}/workspace` (source + latest translation); nav via tree. 3B save: `services/workspace_edit.py` + `PATCH …/segments/{segment_id}/translation` (chapter-scoped ownership; source preserved; one `transaction()`; status→`manual`; `saved_at`). 3C history: `storage.list_translation_attempts` + `services/segment_history.py` + `GET …/segments/{segment_id}/translations` (all attempts oldest-first; no new table — reuses `translations.attempt`); save-state/autosave contract in COCKPIT_WORKFLOW.md (UI debounce deferred). Path-resolver consolidated to `services/project_paths.py`. 393 tests green. |
| Sprint 4A | FastAPI AI-translation foundation. `services/workspace_translate.py`: `prepare_chapter_translation` (validate chapter/selection + build/healthcheck provider + glossary, raises typed errors) and `run_translation` (per-segment loop, one txn each) — DB-derived normalized text via `normalize_japanese_text` (no source re-read, volume-safe); skip already-`translated`/`manual`. `api/jobs.py`: thread-backed `JobRegistry` (multi-job, keyed by id). Router `api/routers/translate.py`: `POST …/chapters/{id}/translate`, `POST …/chapters/{id}/translate-segments` (202 + job_id), `GET …/jobs/{job_id}`; per-request `provider`/`model` override; provider unhealthy→502. Reuse: extracted `translate_one_segment` + `build_context(normalized_source_text=…)` from `services/translation.py`; new `storage.list_chapter_translation_targets`; secrets applied at API startup. CLI + Flask intact. 413 tests green. **4B/4C pending** (progress/SSE/cancel/polling; safe-retranslate). |
| Sprint 4B | Progress + cancellation + status enrichment on the 4A job foundation. `TranslationJob` gains a `JobProgress` snapshot (current/total/translated/failed), a cancel `Event` (`request_cancel`/`should_cancel`), and a thread-safe SSE event queue; runner signature → `(should_cancel, progress)` wired into `run_translation`. New endpoints `POST …/jobs/{job_id}/cancel` (cooperative) and `GET …/jobs/{job_id}/events` (SSE: per-segment `progress` then terminal `done`/`cancelled`/`error`); `GET …/jobs/{job_id}` enriched with live `progress`. `JobRegistry` stays single-process thread worker — **no external queue** (Celery/Redis/RQ/etc. explicitly out). Skip-translated/manual behavior unchanged; retranslate/overwrite still deferred to 4C. 420 tests green. |
| Sprint 4C | Safe retranslate with explicit overwrite modes. `prepare_chapter_translation(mode=…)` + `_mode_allows`; storage `list_chapter_translation_targets` → `list_chapter_segments` (mode filter moved into the service). Modes: `skip_existing` (pending/failed/stale only — never overwrite), `retranslate_non_manual` (also `translated`; `manual` protected), `force_selected` (any, incl. `manual`). Endpoints `POST …/chapters/{id}/retranslate` + `…/retranslate-segments` (Pydantic `Literal` mode → invalid = 422). Every retranslate appends a new `translations.attempt`; prior attempts (incl. manual edits) stay as immutable history. Job progress/cancel unchanged. 428 tests green. **Sprint 4 done.** |
| Sprint 5A | FastAPI direct glossary CRUD. `storage/glossary.py`: `get/upsert/delete_glossary_term` (same `glossary_terms` table; `_upsert_term` delegates). `services/glossary_terms.py` (framework-agnostic). `api/routers/glossary.py`: `GET/POST/PATCH/DELETE /projects/{name}/glossary[/{source}]`. `GlossaryTermNotFoundError`→404; `ValueError`→422. Injection proof: `build_context().glossary_terms` + rendered `<glossary>` block verified in unit test. 445 tests green. |
| Sprint 5B | Character DB (schema v4). `characters` table (`UNIQUE(project_id,jp_name)`); `_migrate_to_v4` (idempotent). `storage/characters.py`, `services/characters.py`, `api/routers/characters.py`: `GET/POST/PATCH/DELETE /projects/{name}/characters[/{jp_name}]`; `CharacterNotFoundError`→404. Fields: jp_name + en_name required; gender/role/notes optional. Japanese path-param decoding verified (エリナ/魔王). 466 tests green. |
| Sprint 5C | Character context injection. `CharacterContext` dataclass; `TranslationContext.characters: tuple[...] = ()`. `build_context` + `_filter_characters` (jp_name substring, cap 20); `load_character_contexts` maps storage→DTO. Wired into `translate_one_segment`, `translate_project` (CLI), and cockpit `prepare_chapter_translation`→`run_translation`. `<characters>` TSV block in `balanced_user.jinja2`; system-prompt rule for consistent naming. `PROMPT_DESIGN.md` updated. 469 tests green; PR #8. **Sprint 5 done.** |
| Sprint 6A | Translation-memory engine. Schema v5 `translation_memory` (`UNIQUE(project_id,source_hash)`; `_migrate_to_v5`). `storage/translation_memory.py`: `lookup`/`save(protect_manual=…)`/`list`/`delete`/`count_memory_reuses`. Lookup-before-AI in `translate_one_segment` (new `use_translation_memory` flag; return now 4-tuple `(translated, reused, in_tok, out_tok)`): hit → record `memory`-tagged attempt + skip provider; miss-success → `save(protect_manual=True)`; failure → no save. Key is always the stored `segment.source_hash` (never recomputed). Retranslate bypasses lookup (`use_translation_memory = mode=="skip_existing"`) but still refreshes. **Manual edits = TM source of truth**: wired into `workspace_edit` + `manual_edit`; provider saves never overwrite a `manual` row. `reused_from_memory` added to `TranslationRunSummary` + `ChapterTranslationResult`. 483 tests green. |
| Sprint 6B | TM read/manage API. `services/translation_memory.py` (`get_memory_overview` → total_entries/exact_hits/reused_from_memory/entries; `delete_entry`). `api/routers/translation_memory.py`: `GET /projects/{name}/memory`, `DELETE …/{source_hash}` (TM-row-only — history/manual/glossary/characters untouched); `TranslationMemoryNotFoundError`→404. `reused_from_memory` surfaced in FastAPI job status + SSE done event, Flask job summary, and CLI translate output. Docs: `TRANSLATION_PIPELINE.md` §5/§6, `ARCHITECTURE.md` gap list. 491 tests green. **Sprint 6 done.** |
| Sprint 7A | Batch planning service (framework-agnostic). `services/batch_translate.py`: `prepare_batch_translation`→`BatchPlan` (scope chapter/volume/novel; validate-once provider build+healthcheck; glossary+characters loaded once; one `TranslationPlan` per chapter) and `run_batch_translation`→`BatchTranslationResult` (per-chapter `run_translation`; aggregate `chapters_total/done`, `segments_total`, `translated`, `reused_from_memory`, `skipped`, `failed`, tokens, timing; per-chapter `BatchChapterOutcome`). Extracted shared helpers from `workspace_translate.py` (`validate_provider_config`/`load_translation_context`/`build_healthy_provider`/`select_chapter_targets`/`load_single_project`). `storage/segments.py`: `chapter_exists`, `list_chapter_ids_for_volume`, `list_chapter_ids_for_project` (deterministic reading order). `VolumeNotFoundError`. Empty scope = `done(0)`; invariant `translated+failed==segments_total`, `reused_from_memory⊆translated`; cancel before each chapter + per-segment. 508 tests green. |
| Sprint 7B | FastAPI batch endpoints + `BatchJob`. `api/jobs.py`: `BatchJob`/`BatchProgress` (sibling of `TranslationJob`, same cancel/SSE/sentinel) + `JobRegistry.submit_batch`/`get_batch` (separate `_batch_jobs` dict — batch id never resolvable via chapter `get`). `api/routers/batch.py`: `POST /projects/{name}/batch/{novel|volumes/{volume_id}|chapters/{chapter_id}}` → 202; `GET /projects/{name}/batch/jobs/{id}` (aggregate progress + result), `POST …/cancel`, `GET …/events` (SSE). Pydantic `BatchTranslateRequest`/`BatchJob{Response,ProgressResponse,ResultResponse,StatusResponse}`/`BatchChapterOutcomeResponse`. Errors: project/volume/chapter→404, invalid mode→422, unhealthy provider→502. Chapter `/translate*`+`/retranslate*` untouched; TM unchanged; no external queue; Flask untouched. 522 tests green. |
| Sprint 7C | Docs + regression. `TRANSLATION_PIPELINE.md` §10b (batch), `COCKPIT_WORKFLOW.md` (batch API table + lifecycle), `ARCHITECTURE.md` (api/ + services/ + storage/ inventory; batch shipped), `MVP_SCOPE.md` (batch row → exists ✅, sprint-map renumber aligned to CLAUDE.md, acceptance checkbox). Full sweep: 522 tests green, ruff + ruff-format clean, pyright 0 errors, CLI + Flask + FastAPI-route smoke. **Sprint 7 done.** |
| Sprint 8A | Export Foundation (framework-agnostic, **EPUB only**). `services/export_book.py`: `prepare_export`→`ExportPlan` / `run_export`→`ExportResult` + `export_novel`/`export_volume`/`export_chapter`; scope novel/volume/chapter; **per-volume EPUB artifact** (no cross-EPUB merge). EPUB-sourced volumes reuse `render_translated_epub` (write-back, re-reads source EPUB); TXT/HTML-sourced volumes → new `renderers/epub_synthesis.py` `synthesize_epub` (built from persisted IR/DB; **source files never re-read**). Publishable = latest attempt, `source_hash`-matched, status `translated`/`manual` (**manual preserved; history never exported**); other statuses → source fallback (`FallbackByStatus`: pending/in_progress/failed/stale/skipped/untranslated; hash-mismatched translated/manual → `untranslated`). **Read-only**: no new `translations` rows; provider + TM untouched. New storage: `get_chapter`/`ChapterRecord`, `list_export_segment_states`/`ExportSegmentState`; `services/project_paths.resolve_output_dir`; collision-safe filenames (reading-order index + volume id). Deferred (8B+): FastAPI export endpoints, UI, DOCX, batch export, combined EPUB. 539 tests green; ruff + format clean; pyright 0 errors. |
| Sprint 8B | FastAPI export endpoints + `ExportJob` (thin adapter over 8A; **no domain logic duplicated**). `api/jobs.py`: `ExportJob`/`ExportProgress` + `JobRegistry.submit_export`/`get_export` (separate `_export_jobs` dict — export id never resolvable via chapter `get` or batch `get_batch`). `api/routers/export.py`: `POST /projects/{name}/export/{novel|volumes/{volume_id}|chapters/{chapter_id}}` → 202; `GET /…/export/jobs/{id}` (per-volume progress + result), `POST …/cancel`, `GET …/events` (SSE). Pydantic `ExportRequest` + `ExportJob{Response,ProgressResponse,ResultResponse,StatusResponse}` + `ExportArtifactResponse`/`ExportFallbackByStatusResponse`. `run_export` gained optional `should_cancel`/`progress_callback` (per-volume; 8A callers unchanged) + `ExportResult.cancelled`. Errors: project/volume/chapter→404, unsupported target→422, unknown job→404. EPUB only; no DOCX/TXT/HTML output, combined EPUB, ZIP, or UI; translation/TM/provider + Flask untouched. 551 tests green; ruff + format clean; pyright 0 errors. |
| Sprint 8C | TXT + HTML output targets (reuse 8A/8B; **no provider/TM/translation changes**). New `renderers/txt.py` (`render_txt`) + `renderers/html.py` (`render_html`); shared `renderers/rendered_document.py` (`RenderChapter` + `block_to_html`) extracted from `epub_synthesis.py` and used by all three renderers. `export_book`: `EXPORT_TARGETS = {epub, txt, html}` + `ExportTarget` literal; `_render_volume`/`_build_volume_plan` target-aware (artifacts under `output/<target>/`, extension = target); TXT/HTML built from the DB via `_resolved_chapters` (no source re-read) with the same publishable + source-fallback rule; `ExportError` for TXT/HTML write failures (+ collision guard). FastAPI export endpoints accept `target` ∈ {epub,txt,html}; `docx` → 422 (unchanged). Tests: renderer units (`test_txt.py`/`test_html.py`), service novel/volume/chapter for TXT/HTML + EPUB-source→TXT no-reread guard, endpoint target tests. DOCX output, export UI, combined EPUB, ZIP deferred. 561 tests green; ruff + format clean; pyright 0 errors. **Sprint 8 done.** |
| Sprint 9A | MVP stabilization — audit + validation (no code/behavior changes). Full regression sweep green: `pytest` 561 passed / 4 skipped (expected: DeepSeek/Gemini/Ollama live + POSIX file-mode on Windows), pyright 0 errors, ruff check + format clean, CLI smoke (15 commands), FastAPI smoke (`create_api_app` + TestClient: `/health`·`/version`·`/projects` 200, 37 routes), Flask legacy smoke (`create_app` + test_client: `/` 200, 14 routes). MVP acceptance audit: features 1–7 exist with evidence; feature 8 (export) partial-by-design (EPUB/TXT/HTML shipped, DOCX → 422). **No MVP-baseline blockers**; 4 doc-only findings (F1 checklist drift, F2 CLI-vs-FastAPI export split, F3 CLAUDE.md status, F4 scattered deferred list). New artifact: `docs/MVP_STABILIZATION_REPORT.md`. |
| Sprint 9B | MVP stabilization — doc/regression alignment (no behavior changes). F1: `MVP_SCOPE.md` acceptance checklist (export item → EPUB/TXT/HTML done + DOCX deferred; final-gate annotated; stale progress note refreshed to Sprints 1–8). F2: CLI-vs-FastAPI export split documented in `ARCHITECTURE.md`, `COCKPIT_WORKFLOW.md`, `QUICKSTART.md` (FastAPI = volume-aware EPUB/TXT/HTML; CLI/Flask = legacy single-project exporter — accepted web-first boundary). F3: `CLAUDE.md` §1 doc map + §2.1 (Sprint 9 → 🟡) + §2.3 + §2.5. F4: consolidated deferred list lives in `MVP_STABILIZATION_REPORT.md` §4, cross-linked. `MAINTENANCE.md`: Sprint 9 validation commands + expected 4-skip set. Re-validation green (same matrix as 9A). Next: 9C E2E proof + baseline report. |

---

## 3. Stack (Locked)

**Use:** Python 3.11+ · uv · pyproject.toml · ruff · pyright (basic) · pytest · typer · rich · pydantic v2 · tomllib · sqlite3 (WAL, no ORM) · ebooklib · openai SDK · google-generativeai · Jinja2.

**Web cockpit:** **Flask (sync) — legacy working baseline.** **FastAPI — target direction** (ADR `004`), behind optional extra `weaver[web]`; core install pulls no web framework. asyncio unlocked **only** for the future FastAPI web layer. Migration is staged, route-by-route, preserving Flask until parity.

**Still rejected (no reintroduction without ADR):** Django · SQLAlchemy · Celery · RQ · Docker · React/Node build · OpenTelemetry · Sentry. asyncio remains rejected outside the web layer.

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
- Shared/core stays framework-agnostic (no web `Request`/`Response`, no DI wiring, no template/CLI output). Pydantic only at the web boundary.
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
