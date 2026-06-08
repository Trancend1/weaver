# Weaver

Offline-capable, glossary-aware **JP→EN** light-novel translation workbench. Two surfaces: a **CLI** and a local **web cockpit**. Web-cockpit-first development focus; CLI stays functional.

**Not:** SaaS, consumer product, hosted service, complex SPA.

> **Status (2026-06-08):** **`v0.7.0` stable.** Phases A–F complete. **Strategic pivot (ADR `009`): post-Phase-F roadmap is Sprint G–O on the line "HTMX-first, FastAPI-stable, Tauri-sidecar-ready".** The earlier "Phase Final — npm `@weaver/cli` wrapper" target is **deferred legacy** — replaced by a Tauri sidecar path that hardens the FastAPI runtime first. **Active sprint: Sprint G — FastAPI Stability & Tauri-Ready Runtime Foundation.** Full plan: [docs/weaver_next_plan.md](docs/weaver_next_plan.md). New governing ADRs: `009` (strategic pivot), `010` (persistent job core), `011` (Project terminology). Phase F gate (last green): **843 tests / 4 skipped**, pyright 0, ruff + format clean.

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
| [docs/weaver_next_plan.md](docs/weaver_next_plan.md) | **Active post-Phase-F roadmap: Sprint G–O (HTMX-first, FastAPI-stable, Tauri-sidecar-ready). Governed by ADR `009`. Sprint G is the active sprint.** |
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
  → Sprint G — FastAPI Stability & Tauri-Ready Runtime Foundation   ⏳ active
  → Sprint H — Project & Volume Lifecycle Contract (Novel → Project; ADR 011)
  → Sprint I — Persistent Job Core (SQLite-backed, in-process; ADR 010)
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
| **Sprint G — FastAPI Stability & Tauri-Ready Runtime Foundation** | Runtime endpoints (`/healthz`, `/version`, `/runtime/status`); env modes (`dev`/`desktop`/`test`); app-data directory abstraction (`services/app_paths.py`); relative-route + asset hardening; desktop security baseline (127.0.0.1 only, CORS strict, `/docs` off, session-token draft); structured logs (runtime/backend/job/export/provider); `docs/SIDECAR_CONTRACT.md`. No UI rewrite, no Tauri code, no `.msi`/`.dmg`. Governed by ADR `009`. Plan: [docs/weaver_next_plan.md](docs/weaver_next_plan.md). | ⏳ active |
| Sprint H — Project & Volume Lifecycle Contract | Novel → Project copy/CLI/docs consolidation (ADR `011`; schema already uses `projects`); volume lifecycle status field (`created` → `exported` ∪ `failed`); explicit JSON + HTMX CRUD on projects/volumes; status propagation hooks in import/translate/export. Schema v3 → v4 additive. | ⬜ pending |
| Sprint I — Persistent Job Core & Realtime Contract | SQLite-backed JobRegistry (ADR `010`; tables `jobs`, `job_progress_snapshots`; `job_events.job_id` additive); standardized status + progress schema; cold-start recovery (`running` → `failed`); SSE resume via `Last-Event-Id`; one Job Detail UI; wire `import_source`/`translation`/`batch_translate`/`export_book`. **No external queue.** Schema v4 → v5. | ⬜ pending |
| Sprint J — EPUB Preservation Snapshot & Parser Hardening | Persist Phase F `ParsedEpub` into 6 additive tables keyed by `volume_id`; source-hash + parser-version invalidation; reparse-as-Job (consumes Sprint I); image-format dimension coverage (JPEG/WebP/SVG); CLI `weaver epub-inspect`. Schema v5 → v6. | ⬜ pending |
| Sprint K — Export Fidelity Integration | Renderer reads preservation snapshot; pre-export advisory in preflight; post-export fidelity report on job result; regression gate `epub_export_fidelity`; atomic export write (`.partial` → rename). | ⬜ pending |
| Sprint L — Candidate Review + Character Text Draft | Translation candidate model + status state machine; grounded candidate generation (no auto-mutation); Character Page text draft (XHTML/text only, no images); provenance on every AI artifact. Schema v6 → v7. | ⬜ pending |
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

### 2.3 Active Phase — Sprint G: FastAPI Stability & Tauri-Ready Runtime Foundation

> Phase F is complete. The active post-Phase-F sprint is **Sprint G**, governed by ADR [`009`](docs/decisions/009-htmx-first-fastapi-stable-tauri-sidecar-ready.md). Full scope and task order live in [docs/weaver_next_plan.md](docs/weaver_next_plan.md) Sprint G section. Sprint H may **not** start until G8 (the final runtime-readiness gate) passes; run the §2.2 gate before each sub-stage.

**Sprint G — in-scope summary:**

- **Runtime endpoints** — `GET /healthz`, `GET /version`, `GET /runtime/status`. Cold response < 50 ms.
- **Env modes** — `WEAVER_ENV` ∈ `dev | desktop | test`; `WEAVER_HOST` default `127.0.0.1`; `WEAVER_PORT` default `8765` (auto when `0`); `WEAVER_DOCS` toggle (auto `false` in desktop).
- **App-data abstraction** — `services/app_paths.py` resolves `workspace_dir / database_dir / cache_dir / export_dir / logs_dir / temp_dir / config_dir` from one OS-correct root (`~/.weaver/` POSIX, `%APPDATA%/Weaver/` Windows, `~/Library/Application Support/Weaver/` macOS), overridable via `WEAVER_DATA_DIR`. Existing `~/.weaver/secrets.toml` location and `0o600` mode are preserved.
- **Relative HTMX routes + asset hardening** — UI must work under any `WEAVER_PORT`.
- **Desktop security baseline** — bind 127.0.0.1 only (refuse 0.0.0.0 startup in desktop); CORS same-origin; `/docs` and `/redoc` off; session-token draft (header `X-Weaver-Session`, optional dev, required desktop).
- **Structured logging** — JSON-lines files in `logs_dir`: `runtime.log`, `backend.log`, `job.log`, `export.log`, `provider.log`. Rotation 10 MiB × 5. No keys/secrets.
- **Sidecar contract doc** — `docs/SIDECAR_CONTRACT.md` (start → poll `/healthz` → open webview → session token → graceful shutdown; stdout/stderr conventions; exit code map `0/64/65/66`).

**Sprint G — out of scope (deferred to Sprint N+ per ADR `009`):**

- Tauri workspace, `.msi`/`.dmg`, auto-updater, code signing, Rust command bridge, any UI rewrite.
- Job persistence (Sprint I + ADR `010`).
- Project rename copy pass (Sprint H + ADR `011`).

**Carry-over invariants (unchanged across the Sprint G–O run):**

- `read_epub()` and `DocumentIR` remain the import/export/translation path; Phase F's `ParsedEpub` is the structural layer.
- State writes go through services. CLI/web never touch SQLite directly.
- API keys via env vars or `~/.weaver/secrets.toml` only — never in config, never logged, never rendered.
- Locked stack (CLAUDE.md §3) unchanged. Tauri lives in `desktop/`, not as a Python dependency.

### 2.4 Exit Criteria

> **MVP acceptance gate: met & LOCKED** (Sprint 9C, 2026-06-02), shipped as `0.7.0-rc.1`; RC1 evidence reports live in **git history**. The MVP checklist lives in [docs/MVP_SCOPE.md](docs/MVP_SCOPE.md). **Phases A–F** complete (Phase F detail in [docs/PHASE_F_PLAN.md](docs/PHASE_F_PLAN.md) and [docs/EPUB_PARSER_AUDIT.md](docs/EPUB_PARSER_AUDIT.md)).

**Sprint G — exit criteria** (governed by ADR `009`; full task order in [docs/weaver_next_plan.md](docs/weaver_next_plan.md)):

- [x] G1 — Runtime audit doc lists every dev-only assumption with file:line refs. ([docs/SPRINT_G_RUNTIME_AUDIT.md](docs/SPRINT_G_RUNTIME_AUDIT.md))
- [x] G2 — `services/app_paths.py` ships; OS-aware root, `WEAVER_DATA_DIR` override; `serve` stops relying on `os.chdir` (`WEAVER_BOOKS_DIR`); `services/glossary.py` outlier rewired to accept `cwd=`.
- [x] G3 — `/healthz` (`{ok, ts}`), `/version`, `/runtime/status` ship via `api/routers/runtime.py`; cold-response budget covered by `tests/unit/api/test_runtime.py::test_healthz_cold_response_under_50ms`.
- [x] G4 — `tests/integration/test_runtime_random_port.py` boots Uvicorn on `port=0`, asserts `/ui` + an HTMX endpoint; static-grep guard rejects any absolute `http://` URL in `hx-*` attributes.
- [x] G5 — `services/runtime_env.py` + `api/app.py` middleware: desktop refuses `host != 127.0.0.1` (exit `64`), CORS same-origin, `/docs` + `/redoc` + `/openapi.json` 404, `X-Weaver-Session` enforced when set, public-paths bypass kept (`/healthz`, `/health`, `/version`, `/static/*`).
- [x] G6 — `services/logging_setup.py` writes five JSON-lines files in `logs_dir` (rotation 10 MiB × 5); `log_provider_event` scrubs secret-shaped fields; regression test `test_provider_log_contains_no_api_keys_regression`.
- [x] G7 — [docs/SIDECAR_CONTRACT.md](docs/SIDECAR_CONTRACT.md) ships with lifecycle, launch args, endpoint contract, stdout conventions, exit-code map (`0/64/65/66`), stability guarantees; linked from §1.
- [x] G8 — Full gate green: 879 passed / 4 skipped (was 843 / 4), pyright 0, ruff + format clean, clean wheel build (`dist/weaver-0.7.0-py3-none-any.whl` contains all four new modules).

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
| Post-F strategic pivot (2026-06-08) | ADR [`009`](docs/decisions/009-htmx-first-fastapi-stable-tauri-sidecar-ready.md) merged. Replaces "Phase Final — npm `@weaver/cli` wrapper" with the Sprint G–O sequence (HTMX-first, FastAPI-stable, Tauri-sidecar-ready). Companion ADRs `010` (persistent job core, SQLite in-process) and `011` (Project terminology) accepted. Full plan: [docs/weaver_next_plan.md](docs/weaver_next_plan.md). Active sprint: Sprint G. |
| Sprint G — FastAPI Stability & Tauri-Ready Runtime Foundation | **Complete (branch `feat/FastAPI-stability-Tauri-ready`).** Eight stages G1–G8: G1 read-only audit ([docs/SPRINT_G_RUNTIME_AUDIT.md](docs/SPRINT_G_RUNTIME_AUDIT.md)); G2 `services/app_paths.py` (OS-aware root + `WEAVER_DATA_DIR` override) + `WEAVER_BOOKS_DIR` env-var path replaces the `os.chdir` in `serve` + `services/glossary.py` outlier accepts `cwd=`; G3 `api/routers/runtime.py` adds `/healthz` (`{ok, ts}`) and `/runtime/status` alongside the legacy `/health` (preserved bit-identical); G4 random-port integration test + static-grep guard against absolute URLs in `hx-*` attributes; G5 `services/runtime_env.py` env-mode dispatch (`dev`/`desktop`/`test`), desktop refuses non-loopback bind (exit `64`), `/docs` `/redoc` `/openapi.json` 404 in desktop, CORS same-origin, `X-Weaver-Session` middleware (public bypass: `/healthz` `/health` `/version` `/static/*`); G6 `services/logging_setup.py` writes five JSON-lines files (`runtime.log`/`backend.log`/`job.log`/`export.log`/`provider.log`) with `provider.log` field-scrub regression; G7 [docs/SIDECAR_CONTRACT.md](docs/SIDECAR_CONTRACT.md) (lifecycle, launch args, exit codes `0/64/65/66`, stability guarantees) linked from §1. Gate: **879 passed / 4 skipped**, pyright 0, ruff + format clean, clean wheel build (`weaver-0.7.0-py3-none-any.whl` carries all four new modules). No schema migration, no Tauri code, no job persistence — those land in Sprints H, N, I respectively. |

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
- **Sprint G is runtime-only**: no Tauri code, no job persistence (Sprint I), no Project-rename copy pass (Sprint H), no schema migration. Stop at each G-stage gate (G1–G8) for inspection.
- **Sprint I persistence boundary** (ADR `010`): SQLite-backed job state stays in-process. Do not add Celery / Redis / RQ / external worker / multi-process queue — `src/weaver/api/jobs.py:8-10` remains in force.
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
