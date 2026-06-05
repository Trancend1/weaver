# Weaver

Offline-capable, glossary-aware **JP→EN** light-novel translation workbench. Two surfaces: a **CLI** and a local **web cockpit**. Web-cockpit-first development focus; CLI stays functional.

**Not:** SaaS, consumer product, hosted service, complex SPA.

> **Status (2026-06-05):** **`v0.7.0` stable released** (FastAPI is the sole web cockpit; Flask fully removed). Phases A (UI/UX Polish), B (Translation QA, ADR `008`), and C (Release hardening) are all complete. **Phase D — DOCX export in progress:** the DOCX export target is delivered (`renderers/docx.py`, custom minimal OOXML writer, no `python-docx`, no new dependency); remaining Phase D items (QA thresholds config, combined EPUB/ZIP, QA tree badges, provider hardening) are still open (see §2.3). Detailed MVP/Phase-A/B history lives in git history.

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
| [docs/PHASE_B_QA_PLAN.md](docs/PHASE_B_QA_PLAN.md) | Phase B (complete) — Translation QA & consistency checks: rules, severity model, report schema, stage breakdown. Architecture/severity decision in ADR `008`. |
| [docs/PHASE_D_DOCX_EXPORT_PLAN.md](docs/PHASE_D_DOCX_EXPORT_PLAN.md) | Phase D — DOCX export: architecture audit, dependency decision (custom OOXML writer, no `python-docx`), renderer design, API/UI impact, validation matrix, staged plan (D1–D4). |
| [docs/RC1_REPORT.md](docs/RC1_REPORT.md) | **MVP RC1**: validation/soak/clean-install evidence, release notes, known issues, deferred roadmap, recommended version tag |
| [docs/MVP_STABILIZATION_REPORT.md](docs/MVP_STABILIZATION_REPORT.md) | Sprint 9 baseline: validation matrix, acceptance audit, **consolidated deferred/known-gaps list** |
| [docs/MAINTENANCE.md](docs/MAINTENANCE.md) | Cleanup, testing, regression, release, migration discipline |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Active ADR index (`001`–`008`) |
| [docs/decisions/](docs/decisions/) | Active ADRs `001`–`008` |
| [ENGINEERING_STANDARDS.md](docs/ENGINEERING_STANDARDS.md) · [PROMPT_DESIGN.md](docs/PROMPT_DESIGN.md) · [SECURITY_AND_PERFORMANCE.md](docs/SECURITY_AND_PERFORMANCE.md) · [AI_SLOP_PREVENTION.md](docs/AI_SLOP_PREVENTION.md) | Supplementary reference specs (still active) |

> Completed point-in-time records (Phase A UI audit, MVP per-sprint log, Flask→FastAPI sprint audits, pre-reset specs/strategy/old ADRs) were removed from the tree on 2026-06-05; they remain in **git history**.

---

## 2. Progress

### 2.1 Roadmap

Forward-looking phase roadmap. MVP is shipped; the per-sprint MVP detail is archived (see below).

```txt
Foundation (v0.6.0) ✅
  → MVP Web Cockpit Foundation — Sprints 1–13 ✅  (v0.7.0-rc.1)
  → Phase A — UI/UX Polish ✅
  → Phase B — Translation QA & Consistency Checks ✅
  → Phase C — Release hardening ✅  (v0.7.0 stable)
  → Phase D — DOCX export 🟡 (DOCX target ✅) / QA config / combined ZIP   ⬅ in progress
```

| Phase | Scope | Status |
| ----- | ----- | ------ |
| MVP (Sprints 1–13) | Core JP→EN cockpit: Novel/Volume/Chapter structure & import; two-column workspace; provider AI translate + safe retranslate; glossary + character DB (prompt injection); translation memory; batch; EPUB/TXT/HTML export. FastAPI made the sole web surface (Flask removed, Sprint 13B). | ✅ `v0.7.0-rc.1` |
| Phase A — UI/UX Polish | Cockpit UI polish on Jinja2 + HTMX (ADR `007`): shared shell / a11y / responsive @390px, workspace UX, dashboard + admin clarity. Presentation/copy only; no backend/provider/stack change. | ✅ |
| Phase B — Translation QA & Consistency Checks | Read-only, deterministic QA reports before export (report-first, no auto-fix): QA engine → JSON API → UI report/badges → advisory pre-export warning. No provider calls, no mutation, no semantic/vector. ADR `008`. Stages B1–B6. | ✅ |
| **Phase C — Release hardening** | CHANGELOG `[Unreleased]` → `[0.7.0]` (Phase A + B entries); version consistency; soak 25/25; clean wheel install; annotated tag `v0.7.0`. | ✅ `v0.7.0` |
| **Phase D — DOCX export** | DOCX export **✅** (`renderers/docx.py`, custom OOXML, no `python-docx`) → QA thresholds config → combined EPUB/ZIP → QA tree badges → provider hardening. | 🟡 in progress |
| **Phase E — Design System Implementation** | Implement DESIGN.md token system + DESIGN_GUIDE.md hybrid layout across the cockpit: CSS variable migration (6→19 tokens), sidebar layout (3-mode dispatch), component library extraction, typography scale, color semantics, responsive sidebar, workspace redesign per guide. No backend changes — pure CSS + Jinja2 template + HTMX refactor. Source: `docs/DESIGN.md`, `docs/DESIGN_GUIDE.md`. | ⬜ pending |

Legend: ✅ complete · 🟡 in progress · ⏳ next · ⬜ pending · 🚫 blocked.

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

### 2.3 Active Phase — Phase D: DOCX Export

> **Phase C — Release hardening: complete.** `v0.7.0` tagged on 2026-06-05. **Phase D is in progress** — the DOCX export sub-feature is delivered; the remaining Phase D items are not yet started.

**Phase D — DOCX export delivered (D1–D4):**
- D1 — audit + plan: [docs/PHASE_D_DOCX_EXPORT_PLAN.md](docs/PHASE_D_DOCX_EXPORT_PLAN.md). Decision locked: **custom minimal OOXML writer, no `python-docx`, no new dependency, no ADR.**
- D2 — renderer + target: `renderers/docx.py` (`render_docx`, pure, no DB/no fallback); `"docx"` added to `ExportTarget`/`EXPORT_TARGETS`; `_render_volume` DOCX branch. DOCX is **synthesized** from the DB like TXT/HTML — **no write-back**, source never re-read.
- D3 — API/UI: export job flow already generic over `target` (no schema/route change beyond the `ExportRequest` docstring); cockpit export dropdown gains a **DOCX** option; preflight forwards `target` verbatim.
- D4 — docs + regression: TRANSLATION_PIPELINE, COCKPIT_WORKFLOW, ARCHITECTURE, QUICKSTART, MAINTENANCE, CHANGELOG `[Unreleased]`, this file. Full Gate-D validation green.
- **Formatting baseline:** title + `Heading1` headings + normal paragraphs + built-in `Quote` blockquotes + page break before chapters 2..N. No images/footnotes/advanced styling/merged-omnibus DOCX.

**Remaining Phase D items (not started):** QA thresholds config (`[qa]` table) → combined EPUB/ZIP bundle → QA tree badges → provider hardening.

**Phase C delivered (2026-06-05):**
- C1 — version consistency audit: `pyproject.toml` + `__init__.py` both at `0.7.0`; zero RC1/Flask remnants.
- C2 — CHANGELOG: `[Unreleased]` → `[0.7.0] - 2026-06-05`; Phase A + Phase B entries added; dangling links in `[0.1.0]` fixed.
- C3 — full validation: **703 tests / 4 skipped**, pyright 0, ruff clean, soak 25/25 (Flask fallback NOT used), clean wheel install `weaver 0.7.0`.
- C4 — annotated tag `v0.7.0` on `main`.
- C5 — this file updated; Phase D active.

**Carry-over invariants (unchanged):**
- **Web is FastAPI-only** (ADR `004`). `weaver serve` = FastAPI cockpit (UI + API), `weaver serve-api` = headless. Flask fully removed.
- **Legacy CLI** `weaver translate` / `services/export.py` are **single-volume**; multi-volume is the cockpit's job.
- **Phase B QA** (ADR `008`): read-only, deterministic, report-first. 11 rules across novel/volume/chapter scope. Details in [docs/PHASE_B_QA_PLAN.md](docs/PHASE_B_QA_PLAN.md).

### 2.4 Exit Criteria

> **MVP acceptance gate: met & LOCKED** (Sprint 9C, 2026-06-02), shipped as `v0.7.0-rc.1`; evidence in [docs/MVP_STABILIZATION_REPORT.md](docs/MVP_STABILIZATION_REPORT.md) and [docs/RC1_REPORT.md](docs/RC1_REPORT.md). The MVP checklist lives in [docs/MVP_SCOPE.md](docs/MVP_SCOPE.md). **Phase A** complete (PR #18). **Phase B** complete (PR #19). **Phase C** complete — `v0.7.0` tagged 2026-06-05.

**Phase D exits only when:**

- DOCX export (`target="docx"`) produces a valid `.docx` file; `weaver[web]` extra is sufficient (no new top-level dep without ADR).
- QA threshold constants (`FALLBACK_HEAVY_RATIO`, etc.) are configurable via `project.toml` `[qa]` table; engine defaults unchanged when section absent.
- Combined EPUB/ZIP bundle export available for novel scope.
- Full regression green: `pytest`, `pyright`, `ruff`; CLI not broken; export routes not broken.
- Docs updated: TRANSLATION_PIPELINE, COCKPIT_WORKFLOW, CHANGELOG, CLAUDE.md.
- **Quality gate:** one PR = one concern; no auto-fix, no provider call in new QA paths.

### 2.5 Phase Log

One row per phase/era; deep detail lives in the linked docs and git history.

| Phase / era | Outcome |
|---|---|
| Foundation (v0.6.0) | CLI complete + Flask web cockpit end-to-end. Detail in git history. |
| Reset Tasks 1–5 | Controlled reset → MVP Web Cockpit Foundation + FastAPI direction; ADRs reset to `001`–`007`; MVP gap finalized + sprint plan locked. |
| MVP Sprints 1–9 | Core cockpit: Novel/Volume/Chapter model + multi-format import (1); FastAPI cockpit foundation (2); workspace read/save/history (3); provider AI translate + safe-retranslate modes (4); glossary + character DB with prompt injection (5); translation memory, lookup-before-AI (6); batch chapter/volume/novel + progress/cancel/SSE (7); volume-aware EPUB/TXT/HTML export (8); MVP stabilization + real-EPUB E2E, **baseline LOCKED** (9C). |
| MVP Sprints 10–13 | Flask→FastAPI convergence: parity audit + gap closure — create/browse, config/secret write, glossary candidate review (10); FastAPI UI functional parity, Jinja2+HTMX (11); parity audit + default-`serve` flip to FastAPI (12); **Flask fully decommissioned** — `serve-flask`, `src/weaver/web/**`, `flask` dep removed (13). FastAPI is the sole web cockpit. |
| MVP RC1 | Release-candidate verification: full validation green (653 tests / 4 skipped, pyright 0, ruff+format clean), CLI 15 commands, cockpit soak 25/25, clean-env wheel install. **GO for RC1**; tag `v0.7.0-rc.1`. Report: [docs/RC1_REPORT.md](docs/RC1_REPORT.md). |
| Phase A — UI/UX Polish | Cockpit UI polish on Jinja2+HTMX: A1 UX audit → A2-1 shell/a11y/responsive · A2-2 feedback/a11y · A2-3 workspace UX · A2-4 dashboard/project clarity · A2-5 admin usability · A2-6 live verification. Presentation/copy only (+ one additive `done_count` field, a small progressive-enhancement script); no backend/provider/stack change. Merged PR #18 (audit detail in git history). |
| Phase B — Translation QA | **Complete.** Read-only, deterministic, report-first QA before export (no auto-fix, no provider, no mutation, no semantic/vector). B1 plan + ADR `008` (reuse `weaver.qa.checks`, keep severity `info\|warning\|critical`) → B2 engine (`services/translation_qa.py` + `qa/{consistency_checks,scope_checks,report}.py`) → B3 JSON API (`api/routers/qa.py`) → B4 UI pages (`api/routers/ui_qa.py`) → B5 advisory pre-export warning (`…/export/preflight`, never blocks) → B6 docs + regression. Legacy `weaver validate` untouched. 703 tests / 4 skipped, pyright 0, ruff + format clean. |
| Phase C — Release hardening | **Complete.** CHANGELOG promoted to `[0.7.0]` (Phase A + B entries); version consistency confirmed; soak 25/25; clean wheel install; annotated tag `v0.7.0` on `main` (2026-06-05). |
| Phase D — DOCX export | **DOCX target delivered (D1–D4).** Custom minimal OOXML writer `renderers/docx.py` — no `python-docx`, no new dependency; synthesized from the DB like TXT/HTML (no write-back). `"docx"` added to the export target set + `_render_volume` branch; cockpit export dropdown gains DOCX; job flow/schemas unchanged (generic over `target`). Plan: [docs/PHASE_D_DOCX_EXPORT_PLAN.md](docs/PHASE_D_DOCX_EXPORT_PLAN.md). Remaining Phase D items (QA config, combined EPUB/ZIP, QA tree badges, provider hardening) not started. |

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
- Phase B is **read-only QA**: no auto-fix, no provider/LLM calls, no translation mutation, no semantic/vector search. Each stage stops at its gate; design (B1) ships no code.

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
