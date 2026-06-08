# Weaver

Offline-capable, glossary-aware **JP→EN** light-novel translation workbench. Two surfaces: a **CLI** and a local **web cockpit**. Web-cockpit-first development focus; CLI stays functional.

**Not:** SaaS, consumer product, hosted service, complex SPA.

> **Status (2026-06-08):** **`v0.7.0` stable.** Phases A–F complete. **Sprints G + H complete.** Strategic pivot (ADR `009`): post-Phase-F roadmap is Sprint G–O on the line "HTMX-first, FastAPI-stable, Tauri-sidecar-ready". The earlier "Phase Final — npm `@weaver/cli` wrapper" target is **deferred legacy** — replaced by a Tauri sidecar path that hardens the FastAPI runtime first. **Active sprint: Sprint I — Persistent Job Core (SQLite-backed, in-process; ADR `010`).** Full plan: [docs/weaver_next_plan.md](docs/weaver_next_plan.md). Governing ADRs: `009` (strategic pivot), `010` (persistent job core), `011` (Project terminology). Sprint H gate (last green): **904 tests / 4 skipped**, pyright 0, ruff + format clean, clean wheel build.

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
| [docs/DESIGN_NOTES.md](docs/DESIGN_NOTES.md) | Cockpit UI design system: tokens, layout modes, components, states, a11y, and the hard constraints to preserve when editing `app.css`/templates |
| [docs/PROVIDER_AND_MODEL_CONFIG.md](docs/PROVIDER_AND_MODEL_CONFIG.md) | Providers, models, secret store |
| [docs/TRANSLATION_PIPELINE.md](docs/TRANSLATION_PIPELINE.md) | Import → segment → translate → QA → export |
| [docs/MVP_SCOPE.md](docs/MVP_SCOPE.md) | MVP features, gap analysis, sprint mapping, acceptance |
| [docs/PHASE_F_PLAN.md](docs/PHASE_F_PLAN.md) | Phase F — EPUB light-novel metadata/structure parsing plan and closeout status |
| [docs/EPUB_PARSER_AUDIT.md](docs/EPUB_PARSER_AUDIT.md) | Additive EPUB parser/preview/fidelity audit and OCR gating notes |
| [docs/weaver_next_plan.md](docs/weaver_next_plan.md) | **Active post-Phase-F roadmap: Sprint G–O (HTMX-first, FastAPI-stable, Tauri-sidecar-ready). Governed by ADR `009`. Sprints G + H complete; Sprint I (persistent job core, ADR `010`) is the active sprint.** |
| [docs/SIDECAR_CONTRACT.md](docs/SIDECAR_CONTRACT.md) | Sprint G7 — runtime contract a Tauri (or any) host shell binds against: lifecycle, endpoints, exit codes, session token. |
| [docs/SPRINT_G_RUNTIME_AUDIT.md](docs/SPRINT_G_RUNTIME_AUDIT.md) | Sprint G1 read-only audit driving G2–G7: dev-only assumptions, hardcoded paths, missing runtime contracts. |
| [docs/MAINTENANCE.md](docs/MAINTENANCE.md) | Cleanup, testing, regression, release, migration discipline |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Active ADR index (`001`–`011`) |
| [docs/decisions/](docs/decisions/) | Active ADRs `001`–`011` (`009` strategic pivot · `010` persistent job core · `011` Project terminology) |
| [ENGINEERING_STANDARDS.md](docs/ENGINEERING_STANDARDS.md) · [PROMPT_DESIGN.md](docs/PROMPT_DESIGN.md) · [SECURITY_AND_PERFORMANCE.md](docs/SECURITY_AND_PERFORMANCE.md) · [AI_SLOP_PREVENTION.md](docs/AI_SLOP_PREVENTION.md) | Supplementary reference specs (still active) |

> Completed point-in-time records (Phase A UI audit, MVP per-sprint log, Flask→FastAPI sprint audits, pre-reset specs/strategy/old ADRs) were removed from the tree on 2026-06-05; they remain in **git history**. On 2026-06-06 the completed-phase plans (B, D), the RC1 / MVP-stabilization reports, and the Phase-E design exploration (`DESIGN.md` / `DESIGN_GUIDE.md`) were likewise retired into **git history**.

---

## 2. Progress

### 2.1 Roadmap

Forward-looking roadmap. Phases A–F shipped (`v0.7.0` stable). The post-Phase-F roadmap is the Sprint G–O sequence in [docs/weaver_next_plan.md](docs/weaver_next_plan.md), governed by ADR [`009`](docs/decisions/009-htmx-first-fastapi-stable-tauri-sidecar-ready.md).

```txt
Foundation (v0.6.0) ✅
  → MVP Web Cockpit Foundation — Sprints 1–13 ✅  (v0.7.0-rc.1)
  → Phase A — UI/UX Polish ✅
  → Phase B — Translation QA & Consistency Checks ✅
  → Phase C — Release hardening ✅  (v0.7.0 stable)
  → Phase D — DOCX export · QA config · combined ZIP · QA tree badges · provider hardening ✅
  → Phase E — Design System & UI overhaul ✅
  → Phase F — EPUB Light Novel Metadata, Structure & Image Text Completeness ✅
  → Sprint G — FastAPI Stability & Tauri-Ready Runtime Foundation ✅
  → Sprint H — Project & Volume Lifecycle Contract (Novel → Project; ADR 011) ✅
  → Sprint I — Persistent Job Core (SQLite-backed, in-process; ADR 010)         ⏳ active
  → Sprint J — EPUB Preservation Snapshot & Parser Hardening (persists Phase F)
  → Sprint K — Export Fidelity Integration (consumes Sprint J)
  → Sprint L — Candidate Review + Character Text Draft
  → Sprint M — Image Preview / OCR Security Gate (ADR 012)
  → Sprint N — Tauri Shell Alpha
  → Sprint O — Production Desktop Packaging
```

| Phase / Sprint | Scope | Status |
| -------------- | ----- | ------ |
| MVP (Sprints 1–13) | Core JP→EN cockpit: Novel/Volume/Chapter structure & import; two-column workspace; provider AI translate + safe retranslate; glossary + character DB (prompt injection); translation memory; batch; EPUB/TXT/HTML export. FastAPI made the sole web surface (Flask removed, Sprint 13B). | ✅ `v0.7.0-rc.1` |
| Phase A — UI/UX Polish | Cockpit UI polish on Jinja2 + HTMX (ADR `007`): shared shell / a11y / responsive @390px, workspace UX, dashboard + admin clarity. Presentation/copy only; no backend/provider/stack change. | ✅ |
| Phase B — Translation QA & Consistency Checks | Read-only, deterministic QA reports before export (report-first, no auto-fix): QA engine → JSON API → UI report/badges → advisory pre-export warning. No provider calls, no mutation, no semantic/vector. ADR `008`. Stages B1–B6. | ✅ |
| Phase C — Release hardening | CHANGELOG `[Unreleased]` → `[0.7.0]` (Phase A + B entries); version consistency; soak 25/25; clean wheel install; annotated tag `v0.7.0`. | ✅ `v0.7.0` |
| Phase D — multi-item | DOCX export · QA thresholds config · combined ZIP bundle · QA tree badges · provider config hardening. | ✅ |
| Phase E — Design System & UI overhaul | Token system + hybrid layout; project delete (web + CLI); external-browser launch fix. Reference: `docs/DESIGN_NOTES.md`. No backend behavior change. | ✅ |
| Phase F — EPUB Light Novel Metadata, Structure & Image Text Completeness | Additive EPUB package parsing foundation: OPF metadata, manifest/resources, spine, NAV/NCX, image classification, deterministic validation, read-only preview API/UI, translation preservation context, export fidelity checks, broader fixtures. `read_epub()`, `DocumentIR`, import, translation, export, OCR behavior unchanged. Plan: [docs/PHASE_F_PLAN.md](docs/PHASE_F_PLAN.md). | ✅ |
| Sprint G — FastAPI Stability & Tauri-Ready Runtime Foundation | Runtime endpoints (`/healthz`, `/version`, `/runtime/status`); env modes (`dev`/`desktop`/`test`); app-data directory abstraction (`services/app_paths.py`); relative-route + asset hardening; desktop security baseline (127.0.0.1 only, CORS strict, `/docs` off, session-token draft); structured logs (runtime/backend/job/export/provider); `docs/SIDECAR_CONTRACT.md`. Governed by ADR `009`. | ✅ |
| Sprint H — Project & Volume Lifecycle Contract | Novel → Project copy/CLI/docs consolidation per ADR `011` (no schema rename — schema already uses `projects`/`volumes`); derived-only volume lifecycle status (`empty\|imported\|in_progress\|translated\|translating`) in `services/volume_lifecycle.py`; explicit JSON + HTMX delete on projects/volumes; lifecycle event logging (`project.created`/`volume.imported`/`volume.deleted`/`project.deleted`) via Sprint G `logging_setup`. **No schema migration.** | ✅ |
| **Sprint I — Persistent Job Core & Realtime Contract** | SQLite-backed JobRegistry (ADR `010`; tables `jobs`, `job_progress_snapshots`; `job_events.job_id` additive); standardized status + progress schema; cold-start recovery (`running` → `failed`); SSE resume via `Last-Event-Id`; one Job Detail UI; wire `import_source`/`translation`/`batch_translate`/`export_book`. **No external queue.** Schema v3 → v4. | ✅ |
| Sprint J — EPUB Preservation Snapshot & Parser Hardening | Persist Phase F `ParsedEpub` into 6 additive tables keyed by `volume_id`; source-hash + parser-version invalidation; reparse-as-Job (consumes Sprint I); image-format dimension coverage (JPEG/WebP/SVG); CLI `weaver epub-inspect`. Schema v4 → v5. | ⏳ active  |
| Sprint K — Export Fidelity Integration | Renderer reads preservation snapshot; pre-export advisory in preflight; post-export fidelity report on job result; regression gate `epub_export_fidelity`; atomic export write (`.partial` → rename). | ⬜ pending |
| Sprint L — Candidate Review + Character Text Draft | Translation candidate model + status state machine; grounded candidate generation (no auto-mutation); Character Page text draft (XHTML/text only, no images); provenance on every AI artifact. Schema v5 → v6. | ⬜ pending |
| Sprint M — Image Preview / OCR Security Gate | ADR `012` Gate A (image-bytes policy: MIME allowlist, size cap, path traversal protection, no mutation); Gate B (OCR adapter, credential reuse, cost control); Gate C (optional impl: thumbnail endpoint + OCR-as-Job → drafts). | ⬜ pending |
| Sprint N — Tauri Shell Alpha | `desktop/` subtree (isolated); shell launches FastAPI sidecar on 127.0.0.1; waits `/healthz`; opens WebView; sends session token; pipes sidecar logs; clean shutdown; crash screen on backend failure. No UI rewrite. | ⬜ pending |
| Sprint O — Production Desktop Packaging | Windows + macOS packaging; app icon/name/version; bundle sidecar (PyOxidizer or equivalent — O-stage ADR); smoke-test build; `docs/INSTALL_DESKTOP.md`; debug-bundle export. Auto-updater / code signing / notarization out of scope. | ⬜ pending |
| Deferred (legacy) — npm `@weaver/cli` wrapper | Earlier "Phase Final — Distribution & Installer" target (`npm install -g @weaver/cli → weaver`). **Replaced by Sprints N + O** per ADR `009`. Revisiting requires a new ADR. | 🚫 deferred |

Legend: ✅ complete · 🟡 in progress · ⏳ active · ⬜ pending · 🚫 deferred / blocked.

> MVP per-sprint detail (Sprints 1–13 + RC1) and the Phase A stage log live in **git history**. MVP gap analysis: [docs/MVP_SCOPE.md](docs/MVP_SCOPE.md). Phase/sprint ordering is dependency-driven, not calendar.

### 2.2 Reusable Phase Gate

Before starting any phase or stage, run this gate:

1. Read the active phase/stage scope (§2.3) and its acceptance criteria.
2. List the stage's exit criteria (§2.4) in plain language.
3. Verify each with a concrete command, test, file check, or manual inspection.
4. State what is usable now, what is internal-only, what is not yet user-facing.
5. If every criterion passes, update §2.1 / §2.3 / §2.4 / §2.5.
6. If any fails, do not proceed — mark the row blocked and record the missing proof.

Required reminder before any phase transition: **"Check exit criteria first. No next phase until evidence exists. Explain the detail for manual inspection."**

### 2.3 Active Phase — Sprint I: Persistent Job Core & Realtime Contract

> Sprints G + H are complete. The active sprint is **Sprint I**, governed by ADR [`010`](docs/decisions/010-persistent-job-core-sqlite-in-process.md). Full scope and task order live in [docs/weaver_next_plan.md](docs/weaver_next_plan.md) Sprint I section. Sprint J may **not** start until Sprint I's final gate passes; run the §2.2 phase gate before each sub-stage.

**Sprint I — in-scope summary:**

- **SQLite-backed JobRegistry** — extend `src/weaver/api/jobs.py` (do not rewrite). New tables `jobs` and `job_progress_snapshots`; `job_events.job_id` additive. Schema v3 → v4 with idempotent migration.
- **Standardized status + progress schema** — `running` / `done` / `failed` / `cancelled` preserved; transitional states (`queued` / `processed` / `finalizing`) reserved for J/M downstream.
- **Cold-start recovery** — single recovery pass on FastAPI startup: any `running` row → `failed` with `error_summary='process restart'`. **No auto-resume** (single-process invariant).
- **Write cadence** — terminal status writes synchronous; per-segment progress sampled at 1 s. SQLite is the read-back on refresh; the in-process queue stays the live SSE source.
- **SSE resume** — `GET /jobs/{job_id}/stream` honours `Last-Event-Id`; reconnects skip already-delivered events.
- **One Job Detail UI** — single HTMX page covering translate / batch / export / future parse + OCR jobs.
- **Wired callsites** — `import_source` / `translation` / `batch_translate` / `export_book` all submit through the persistent registry.

**Sprint I — out of scope (deferred to later sprints per ADR `010`):**

- Celery / Redis / RabbitMQ / Kafka / Dramatiq / RQ / external worker daemon / multi-process queue. The `src/weaver/api/jobs.py:8-10` boundary stays in force.
- Multi-process parallelism beyond the existing GIL-bound thread pool.
- Parse-as-Job wiring (Sprint J) and OCR-as-Job wiring (Sprint M).

**Carry-over invariants (unchanged across the Sprint G–O run):**

- `read_epub()` and `DocumentIR` remain the import/export/translation path; Phase F's `ParsedEpub` is the structural layer.
- State writes go through services. CLI/web never touch SQLite directly.
- API keys via env vars or `~/.weaver/secrets.toml` only — never in config, never logged, never rendered.
- Locked stack (CLAUDE.md §3) unchanged. Tauri lives in `desktop/`, not as a Python dependency.
- Volume lifecycle status (Sprint H) stays derived; Sprint I will surface a real `failed` overlay once persistent job state exists.

### 2.4 Exit Criteria

> **MVP acceptance gate: met & LOCKED** (Sprint 9C, 2026-06-02), shipped as `0.7.0-rc.1`; RC1 evidence reports live in **git history**. The MVP checklist lives in [docs/MVP_SCOPE.md](docs/MVP_SCOPE.md). **Phases A–F** complete (Phase F detail in [docs/PHASE_F_PLAN.md](docs/PHASE_F_PLAN.md) and [docs/EPUB_PARSER_AUDIT.md](docs/EPUB_PARSER_AUDIT.md)).

**Sprint I — exit criteria** (governed by ADR `010`; full task order in [docs/weaver_next_plan.md](docs/weaver_next_plan.md)):

- [ ] I1 — Schema v3 → v4 migration ships: `jobs`, `job_progress_snapshots`, `job_events.job_id` additive. Forward-only, idempotent, regression-tested.
- [ ] I2 — `JobRegistry` extended (not rewritten) to write status transitions and 1 s progress snapshots through a transactional storage adapter; existing `JobRunner`/`BatchJobRunner`/`ExportJobRunner` types preserved.
- [ ] I3 — Cold-start recovery: any `running` row at startup → `failed` with `error_summary='process restart'`, `finished_at=now()`. Regression test asserts no auto-resume.
- [ ] I4 — SSE resume: `GET /jobs/{job_id}/stream` honours `Last-Event-Id`; reconnect skips already-delivered events.
- [ ] I5 — Single Job Detail UI page covers translate / batch / export jobs; volume lifecycle `failed` overlay surfaces from the new persistent state (Sprint H derivation extended).
- [ ] I6 — `import_source` / `translation` / `batch_translate` / `export_book` all submit through the persistent registry; `job.log` records every status transition.
- [ ] I7 — Boundary regression: pyproject + import graph forbid Celery / Redis / RQ / external worker; `api/jobs.py:8-10` comment intact.
- [ ] I8 — Final gate: full test suite green, pyright 0, ruff + format clean, clean wheel build, readiness report appended to §2.5.

### 2.5 Phase Log

One row per phase/era; deep detail lives in the linked docs and git history.

| Phase / era | Outcome |
|---|---|
| Foundation (v0.6.0) | CLI complete + Flask web cockpit end-to-end. Detail in git history. |
| Reset Tasks 1–5 | Controlled reset → MVP Web Cockpit Foundation + FastAPI direction; ADRs reset to `001`–`007`; MVP gap finalized + sprint plan locked. |
| MVP Sprints 1–9 | Core cockpit: Novel/Volume/Chapter model + multi-format import (1); FastAPI cockpit foundation (2); workspace read/save/history (3); provider AI translate + safe-retranslate modes (4); glossary + character DB with prompt injection (5); translation memory, lookup-before-AI (6); batch chapter/volume/novel + progress/cancel/SSE (7); volume-aware EPUB/TXT/HTML export (8); MVP stabilization + real-EPUB E2E, **baseline LOCKED** (9C). |
| MVP Sprints 10–13 | Flask→FastAPI convergence: parity audit + gap closure — create/browse, config/secret write, glossary candidate review (10); FastAPI UI functional parity, Jinja2+HTMX (11); parity audit + default-`serve` flip to FastAPI (12); **Flask fully decommissioned** — `serve-flask`, `src/weaver/web/**`, `flask` dep removed (13). FastAPI is the sole web cockpit. |
| MVP RC1 | Release-candidate verification: full validation green (653 tests / 4 skipped, pyright 0, ruff+format clean), CLI 15 commands, cockpit soak 25/25, clean-env wheel install. **GO for RC1**; tag `v0.7.0-rc.1`. Report in git history. |
| Phase A — UI/UX Polish | Cockpit UI polish on Jinja2+HTMX: A1 UX audit → A2-1 shell/a11y/responsive · A2-2 feedback/a11y · A2-3 workspace UX · A2-4 dashboard/project clarity · A2-5 admin usability · A2-6 live verification. Presentation/copy only (+ one additive `done_count` field, a small progressive-enhancement script); no backend/provider/stack change. Merged PR #18 (audit detail in git history). |
| Phase B — Translation QA | **Complete.** Read-only, deterministic, report-first QA before export (no auto-fix, no provider, no mutation, no semantic/vector). B1 plan + ADR `008` (reuse `weaver.qa.checks`, keep severity `info\|warning\|critical`) → B2 engine (`services/translation_qa.py` + `qa/{consistency_checks,scope_checks,report}.py`) → B3 JSON API (`api/routers/qa.py`) → B4 UI pages (`api/routers/ui_qa.py`) → B5 advisory pre-export warning (`…/export/preflight`, never blocks) → B6 docs + regression. Legacy `weaver validate` untouched. 703 tests / 4 skipped, pyright 0, ruff + format clean. |
| Phase C — Release hardening | **Complete.** CHANGELOG promoted to `[0.7.0]` (Phase A + B entries); version consistency confirmed; soak 25/25; clean wheel install; annotated tag `v0.7.0` on `main` (2026-06-05). |
| Phase D — multi-item | **Complete (PR #21, `feat/docx-export`).** Five focused commits: (1) DOCX export target — custom minimal OOXML `renderers/docx.py`, no `python-docx`/no new dep, synthesized from the DB (no write-back); (2) configurable QA thresholds via `[qa]` (`qa/thresholds.py`), defaults unchanged when absent, validated, foreign keys ignored; (3) combined ZIP bundle (`services/export_bundle.py`, `bundle` flag, `bundle_path`); (4) opt-in QA tree badges (out-of-band HTMX, zero QA on tree render — Gate B1 preserved); (5) provider config hardening (`providers/config_values.py`, numeric validation + invalid-model mapping, no key leak). Gate: 780 tests / 4 skipped, pyright 0, ruff + format clean, clean wheel build. Merged-omnibus EPUB intentionally deferred. |
| Phase E — Design System & UI overhaul | **Complete (`feat/design-system-implementaion`).** Token migration to `app.css :root` (color/type/space/radius/shadow/z-index) with legacy class aliases kept; 3-mode layout dispatch (`api/ui_context.py`); left-aligned topbar + brand mark + favicon; widened 264px sidebar with inline line icons (`partials/_icons.html`); dashboard project cards + volume progress cards; QA stat tiles; segmented sub-nav; `_page_header` breadcrumb standardized across all pages incl. 404/error; "QA"→"Quality" copy + active-voice errors. Additive: project delete (web `POST …/delete` + CLI `weaver delete` + `services/project.delete_project`, with path guard) and external-browser launch fix (`cli/open_browser.py`). No backend/schema/HTMX-contract change. Design exploration (DESIGN.md/DESIGN_GUIDE.md) distilled to `docs/DESIGN_NOTES.md`. Gate: 796 tests / 4 skipped, pyright 0, ruff + format clean. |
| Phase F — EPUB Light Novel Metadata, Structure & Image Text Completeness | **Complete (feat/epub-metadata-parse).** Additive ParsedEpub package model and parse_epub_structure() for OPF metadata, manifest/resources, spine, NAV/NCX, image classification, validation issues, preservation context, read-only preview API/UI, export fidelity report, and broader synthetic light-novel fixtures. read_epub(), DocumentIR, import, translation, export, SQLite, OCR, and image-byte behavior unchanged. OCR/vision remains adapter/ADR-gated future work. |
| Post-F strategic pivot (2026-06-08) | ADR [`009`](docs/decisions/009-htmx-first-fastapi-stable-tauri-sidecar-ready.md) merged. Replaces "Phase Final — npm `@weaver/cli` wrapper" with the Sprint G–O sequence (HTMX-first, FastAPI-stable, Tauri-sidecar-ready). Companion ADRs `010` (persistent job core, SQLite in-process) and `011` (Project terminology) accepted. Full plan: [docs/weaver_next_plan.md](docs/weaver_next_plan.md). |
| Sprint G — FastAPI Stability & Tauri-Ready Runtime Foundation | **Complete (branch `feat/FastAPI-stability-Tauri-ready`).** Eight stages G1–G8: G1 read-only audit ([docs/SPRINT_G_RUNTIME_AUDIT.md](docs/SPRINT_G_RUNTIME_AUDIT.md)); G2 `services/app_paths.py` (OS-aware root + `WEAVER_DATA_DIR` override) + `WEAVER_BOOKS_DIR` env-var path replaces the `os.chdir` in `serve` + `services/glossary.py` outlier accepts `cwd=`; G3 `api/routers/runtime.py` adds `/healthz` (`{ok, ts}`) and `/runtime/status` alongside the legacy `/health` (preserved bit-identical); G4 random-port integration test + static-grep guard against absolute URLs in `hx-*` attributes; G5 `services/runtime_env.py` env-mode dispatch (`dev`/`desktop`/`test`), desktop refuses non-loopback bind (exit `64`), `/docs` `/redoc` `/openapi.json` 404 in desktop, CORS same-origin, `X-Weaver-Session` middleware (public bypass: `/healthz` `/health` `/version` `/static/*`); G6 `services/logging_setup.py` writes five JSON-lines files (`runtime.log`/`backend.log`/`job.log`/`export.log`/`provider.log`) with `provider.log` field-scrub regression; G7 [docs/SIDECAR_CONTRACT.md](docs/SIDECAR_CONTRACT.md) (lifecycle, launch args, exit codes `0/64/65/66`, stability guarantees) linked from §1. Gate: **879 passed / 4 skipped**, pyright 0, ruff + format clean, clean wheel build (`weaver-0.7.0-py3-none-any.whl` carries all four new modules). No schema migration, no Tauri code, no job persistence — those land in Sprints H, N, I respectively. |
| Sprint H — Project & Volume Lifecycle Contract | **Complete (branch `feat/lifecycle-persistentjob-contract`).** Four stages H1–H4 governed by ADR `011`. **No schema migration.** H1 user-facing copy audit: templates (`base.html`, `dashboard.html`, `project.html`, `new.html`), `ui_qa.py` page label, `import_source.py` error message, three test assertions — all flipped from "Novel"/"novel" container language to "Project"/"project". Wire identifiers (`scope="novel"`, `/export/novel`, `/batch/novel`), class symbols (`NovelTree`, `NovelTreeResponse`, `analyze_novel`, etc.), provider templates (`light-novel`/`web-novel`), and the domain tagline are intentionally preserved per ADR 011 §2. H2 derived-only volume lifecycle status in `services/volume_lifecycle.py` — five states `empty | imported | in_progress | translated | translating`, computed live from segment counts + `JobRegistry.find_running`. Surfaced via `VolumeView.status`/`status_label` (project_tree.py), `VolumeResponse.status`/`status_label` (JSON tree), and a per-volume badge with token-driven colors in `_tree.html` + `app.css`. `failed`/`exported`/`qa_warning` deferred to Sprints I/K (need persistent state). H3 explicit lifecycle controls: new `services/volume.py` + `storage/volumes.py:delete_volume()` clean qa_warnings → translations → segments → chapters → volume in dependency order (project-scoped data preserved); `DELETE /projects/{name}` and `DELETE /projects/{name}/volumes/{volume_id}` JSON endpoints; `POST /ui/projects/{name}/volumes/{volume_id}/delete` HTMX route swapping `#tree`; per-volume **Delete volume** button on the project page. H4 lifecycle event logging via Sprint G `logging_setup`: `project.created`, `volume.imported`, `volume.deleted`, `project.deleted` land in `runtime.log` as JSON lines; secret-shape regression test confirms no provider key/auth/secret/password leakage in any lifecycle payload. Gate: **904 passed / 4 skipped** (was 879/4; +25 new tests, same four skips), pyright 0, ruff + format clean, clean wheel build (`weaver-0.7.0-py3-none-any.whl` carries `services/volume.py` + `services/volume_lifecycle.py`). UI smoke: `/ui`, `/ui/new`, `/ui/projects/{name}`, `/ui/.../chapters/{id}` all 200; lifecycle badge visible; "Delete volume" button rendered. |
| Sprint I — Persistent Job Core & Realtime Contract | **Complete (branch `feat/lifecycle-persistentjob-contract`).** Six stages I1–I6 governed by ADR `010`. **Schema v5 → v6** additive: `jobs`, `job_progress_snapshots`, `job_events.job_id` (nullable, NULL backfill). I1 forward-only migration with idempotency test + tolerant-of-legacy-v1/v2 path. I2 persistent `JobRegistry`: new `services/job_store.py` storage adapter + `JobStorage` per-job mediator on `api/jobs.py` (in-process invariant intact, `api/jobs.py:8-10` boundary preserved). Status transitions write synchronously before terminal SSE; per-event `job_events` writes; 1-second sampled progress flush. I3 cold-start recovery in the FastAPI factory: any `running` row at boot → `failed` with `error_summary='process restart'`, plus a `recovered` event for replay. **No auto-resume.** I4 SSE resume: `format_sse` emits `id:` lines, all three event endpoints honour `Last-Event-Id` header + `?last_event_id=` query, finished jobs replay from SQLite (no queue hang). I5 wired all producers: translate/batch/export now mirror state; `job.submitted` and `job.finished` land in G6 `job.log`. I6 unified Job Detail UI: new `api/routers/jobs.py` JSON list + detail; `jobs_list.html` + `job_detail.html` HTMX pages with status badge, progress, result/error, event log, cancel-when-running (1 s self-poll); "Jobs" entry in project subnav. Gate: **929 passed / 4 skipped** (was 904/4; +25 new tests, same four skips), pyright 0, ruff + format clean, clean wheel build (`weaver-0.7.0-py3-none-any.whl` carries `services/job_store.py`, `api/routers/jobs.py`, `templates/{jobs_list,job_detail}.html`). UI smoke: `/ui`, project page (Jobs in subnav), `/ui/projects/{name}/jobs`, `/ui/.../jobs/{id}/detail`, JSON `/projects/{name}/jobs` all 200. Cold-start smoke: seeded `running` ghost row reborn as `failed/process restart` after factory rebuild. |
| Sprint J — EPUB Preservation Snapshot & Parser Hardening | **Complete (branch `feat/preservation-parser-hardening`).** Six stages J1–J6. **Schema v6 → v7** additive: `epub_snapshots` header (one row per volume) + five list tables (`epub_snapshot_{manifest,spine,navigation,images,validation}`) keyed by `volume_id`, idempotent migration tolerant of legacy v1/v2 paths. J2 `services/epub_snapshot.py` — `store_snapshot` / `read_snapshot` / `snapshot_status(missing\|fresh\|stale)` / `delete_snapshot`. Snapshot keyed on `(source_hash, parser_version)`; Sprint H3 `delete_volume` now cleans the six snapshot tables in dependency order. J3 `services/epub_reparse.py` + new `JOB_KIND_PARSE` + `ParseJob` / `ParseResult` on `api/jobs.py`; reparse runs as a Sprint I persistent job (cold-start marks `running` → `failed/process restart`, no auto-resume). J4 JSON `GET /projects/{name}/volumes/{vid}/snapshot` + `POST .../reparse` (202 → ParseJob); HTMX `_snapshot.html` swap card with Inspect/Reparse/View buttons in `_tree.html`; `/ui/.../structure` reuses the Phase F `epub_preview.html` template against the persisted snapshot. J5 dependency-free image-dimension parser extended from PNG-only to JPEG (SOF0–SOF3 / SOF5–SOF7 / SOF9–SOF11 / SOF13–SOF15), WebP (VP8 lossy / VP8L lossless / VP8X extended), and SVG (width/height with units, viewBox fallback, percent-only rejected). **PNG offset fixed** (was reading the IHDR chunk length, now reads the real width/height bytes). New `PARSER_VERSION = 2` constant feeds the snapshot stale-check. J6 `weaver epub-inspect <project.toml> --volume N [--reparse] [--json]` summarises metadata / counts / parser version / snapshot freshness. Gate: **973 passed / 4 skipped** (was 929/4; +44 new tests, same four skips), pyright 0, ruff + format clean, clean wheel build (`weaver-0.7.0-py3-none-any.whl` carries `services/epub_snapshot.py`, `services/epub_reparse.py`, `templates/partials/_snapshot.html`). UI smoke: missing → POST reparse (202) → parse job done → snapshot fresh → `/ui/.../structure` 200. |

---

## 3. Stack (Locked)

**Use:** Python 3.11+ · uv · pyproject.toml · ruff · pyright (basic) · pytest · typer · rich · pydantic v2 · tomllib · sqlite3 (WAL, no ORM) · ebooklib · openai SDK · google-generativeai · Jinja2.

**Web cockpit:** **FastAPI** (ADR `004`), behind optional extra `weaver[web]` (FastAPI + Uvicorn + python-multipart); core install pulls no web framework. UI is server-rendered **Jinja2 + HTMX**, no Node/build, no SPA (ADR `007`); HTMX vendored as a static asset (no CDN). asyncio unlocked **only** for the FastAPI web layer. The legacy Flask cockpit was removed in Sprint 13B (Flask→FastAPI migration complete; FastAPI is the sole web surface).

**Still rejected (no reintroduction without ADR):** Flask · Django · SQLAlchemy · Celery · RQ · Docker · React/Node build · SPA framework · OpenTelemetry · Sentry. asyncio remains rejected outside the web layer. **External job queue / worker daemon / multi-process worker pool** is also rejected (ADR `010`; `src/weaver/api/jobs.py:8-10` boundary).

**Desktop shell (Sprint N+, ADR `009`):** Tauri lives in `desktop/` as an isolated subtree. It is a packaging shell — not a Python runtime dependency — and adds no entry to `pyproject.toml`. The shell launches FastAPI as a sidecar (`127.0.0.1`, random port, session token) per `docs/SIDECAR_CONTRACT.md`.

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
- Respect the active-phase stage order (§2.3) and stop at each stage gate (§2.2) for inspection.

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

- Build only what the active phase stage (§2.3) lists. Deferred/advanced items get no scaffolding "for later".
- One PR = one concern. No bundled refactor + feature.
- **Sprint I is persistence-only** (ADR `010`): SQLite-backed job state stays in-process. Do not add Celery / Redis / RQ / external worker / multi-process queue — `src/weaver/api/jobs.py:8-10` remains in force. No EPUB snapshot tables (Sprint J), no candidate review schema (Sprint L), no image/OCR endpoints (Sprint M).
- **Sprint M image/OCR boundary** (ADR `012`): no image-bytes endpoint and no OCR call before ADR `012` Gate A + B are merged.

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
