# Weaver

Offline-capable, glossary-aware **JP→EN** light-novel translation workbench. Two surfaces: a **CLI** and a local **web cockpit**. Web-cockpit-first development focus; CLI stays functional.

**Not:** SaaS, consumer product, hosted service, complex SPA.

> **Status (2026-06-05):** MVP shipped as release candidate **`v0.7.0-rc.1`** (FastAPI is the sole web cockpit; Flask fully removed). **Phase A — UI/UX Polish** is complete. **Active: Phase B — Translation QA & Consistency Checks** (read-only, report-first; see §2.3). Detailed MVP/Phase-A history is archived in [docs/archive/MVP_PHASE_LOG.md](docs/archive/MVP_PHASE_LOG.md) and git history.

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
| **[docs/PHASE_B_QA_PLAN.md](docs/PHASE_B_QA_PLAN.md)** | **Active phase** — Translation QA & consistency checks: rules, severity model, report schema, stage breakdown (Stage B1 deliverable; to be written) |
| [docs/PHASE_A_UI_AUDIT.md](docs/PHASE_A_UI_AUDIT.md) | Phase A UX audit + polish slices (A1 audit, A2-1…A2-6) |
| [docs/RC1_REPORT.md](docs/RC1_REPORT.md) | **MVP RC1**: validation/soak/clean-install evidence, release notes, known issues, deferred roadmap, recommended version tag |
| [docs/MVP_STABILIZATION_REPORT.md](docs/MVP_STABILIZATION_REPORT.md) | Sprint 9 baseline: validation matrix, acceptance audit, **consolidated deferred/known-gaps list** |
| [docs/MAINTENANCE.md](docs/MAINTENANCE.md) | Cleanup, testing, regression, release, migration discipline |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Active ADR index (`001`–`008`) |
| [docs/decisions/](docs/decisions/) | Active ADRs `001`–`008` |
| [ENGINEERING_STANDARDS.md](docs/ENGINEERING_STANDARDS.md) · [PROMPT_DESIGN.md](docs/PROMPT_DESIGN.md) · [SECURITY_AND_PERFORMANCE.md](docs/SECURITY_AND_PERFORMANCE.md) · [AI_SLOP_PREVENTION.md](docs/AI_SLOP_PREVENTION.md) | Supplementary reference specs (still active) |
| [docs/archive/MVP_PHASE_LOG.md](docs/archive/MVP_PHASE_LOG.md) | **Archived** detailed per-sprint MVP log (Sprints 1–13 + RC1) and the Phase A stage log |
| Sprint reports (historical) | [SPRINT10_PARITY_AUDIT](docs/SPRINT10_PARITY_AUDIT.md) · [SPRINT12_UI_PARITY_AUDIT](docs/SPRINT12_UI_PARITY_AUDIT.md) · [SPRINT13A_DECOMMISSION_READINESS](docs/SPRINT13A_DECOMMISSION_READINESS.md) · [SPRINT13A5_SOAK_RESULT](docs/SPRINT13A5_SOAK_RESULT.md) · [SPRINT11A_UI_PLAN](docs/SPRINT11A_UI_PLAN.md) — Flask→FastAPI parity, decommission, soak |
| [docs/archive/](docs/archive/) | Archived ADRs `0001`–`0020`, pre-reset specs (PRD_v2, SYSTEM_ARCHITECTURE), strategy docs — historical |

---

## 2. Progress

### 2.1 Roadmap

Forward-looking phase roadmap. MVP is shipped; the per-sprint MVP detail is archived (see below).

```txt
Foundation (v0.6.0) ✅
  → MVP Web Cockpit Foundation — Sprints 1–13 ✅  (release candidate v0.7.0-rc.1)
  → Phase A — UI/UX Polish ✅
  → Phase B — Translation QA & Consistency Checks   ⬅ ACTIVE
  → Phase C — Release hardening / maintenance        ⬜ next
```

| Phase | Scope | Status |
| ----- | ----- | ------ |
| MVP (Sprints 1–13) | Core JP→EN cockpit: Novel/Volume/Chapter structure & import; two-column workspace; provider AI translate + safe retranslate; glossary + character DB (prompt injection); translation memory; batch; EPUB/TXT/HTML export. FastAPI made the sole web surface (Flask removed, Sprint 13B). | ✅ `v0.7.0-rc.1` |
| Phase A — UI/UX Polish | Cockpit UI polish on Jinja2 + HTMX (ADR `007`): shared shell / a11y / responsive @390px, workspace UX, dashboard + admin clarity. Presentation/copy only; no backend/provider/stack change. | ✅ |
| **Phase B — Translation QA & Consistency Checks** | **Read-only, deterministic QA reports before export (report-first, no auto-fix): QA engine → JSON API → UI report/badges → pre-export warning. No provider calls, no mutation, no semantic/vector. Stages B1–B6 (§2.3).** | 🟡 active |
| Phase C — Release hardening | Promote `v0.7.0-rc.1` → stable; address deferred-roadmap items per [RC1_REPORT](docs/RC1_REPORT.md). | ⬜ pending |

Legend: ✅ complete · 🟡 in progress · ⏳ next · ⬜ pending · 🚫 blocked.

> MVP per-sprint detail (Sprints 1–13 + RC1) and the Phase A stage log are archived in [docs/archive/MVP_PHASE_LOG.md](docs/archive/MVP_PHASE_LOG.md). MVP gap analysis: [docs/MVP_SCOPE.md](docs/MVP_SCOPE.md). Phase/sprint ordering is dependency-driven, not calendar.

### 2.2 Reusable Phase Gate

Before starting any phase or stage, run this gate:

1. Read the active phase/stage scope (§2.3) and its acceptance criteria.
2. List the stage's exit criteria (§2.4) in plain language.
3. Verify each with a concrete command, test, file check, or manual inspection.
4. State what is usable now, what is internal-only, what is not yet user-facing.
5. If every criterion passes, update §2.1 / §2.3 / §2.4 / §2.5.
6. If any fails, do not proceed — mark the row blocked and record the missing proof.

Required reminder before any phase transition: **"Check exit criteria first. No next phase until evidence exists. Explain the detail for manual inspection."**

### 2.3 Active Phase — Phase B: Translation QA & Consistency Checks

**Goal:** help the user check translation quality and consistency **before export**, without auto-fix.

**Core principle — _report first, fix later._** Phase B only **reads** data and produces a QA report. It must **not** mutate any translation, call a provider/LLM, or do semantic/vector analysis. Findings are surfaced; the user decides what to do.

**Stages & gates** (one stage per slice; stop at each gate for inspection — §2.2):

| Stage | Focus | Output | Gate |
| ----- | ----- | ------ | ---- |
| B1 | QA audit & rule design | `docs/PHASE_B_QA_PLAN.md` + report-schema proposal + stage breakdown | Stop after **docs/design only** — no code. |
| B2 | QA engine foundation | framework-agnostic read-only `services/translation_qa.py` (`analyze_chapter/volume/novel`) + tests | Stop after engine + tests clean — no API/UI. |
| B3 | FastAPI QA API | JSON endpoints (novel/volume/chapter) as a thin adapter over B2 | Stop after API + tests clean — no UI. |
| B4 | FastAPI UI QA report | QA report pages + severity/category filters + tree/project/chapter badges | Stop after usable UI — no export integration. |
| B5 | Export QA warning | pre-export QA summary; **export remains allowed by default** (no hard block) | Stop after warning works. |
| B6 | Docs & stabilization | updated docs + full regression clean | Phase complete when all of B1–B5 stable. |

**Deterministic checks (initial set, to be finalized in B1):** untranslated segment · failed segment · stale segment · empty translation · suspiciously short translation · repeated identical translation · glossary source term present but target term missing · character JP name present but EN name missing · fallback-heavy chapter · mixed-status chapter.

**Severity model:** `info` · `warning` · `error`. **Issue scopes:** chapter / volume / novel report. **Data model (B2):** `QAReport`, `QAIssue`, `QASeverity`, `QACategory`, `QAScopeSummary`.

**Phase rules (non-negotiable, for every stage):**
- **Read-only.** No provider/LLM calls, no DB mutation, no auto-fix, no semantic/vector search.
- QA engine is **framework-agnostic** (ADR `002`): no FastAPI/Jinja/HTMX import, no Pydantic, no CLI/web output. API and UI are thin adapters that reuse it.
- Deterministic by default (ADR `003` / AI_SLOP). UI stays **Jinja2 + HTMX** (ADR `007`) — no React/Vue/Node, no visual polish beyond a usable layout.
- Export behavior must not change: source fallback stays valid; the B5 warning is advisory, not a gate.
- Standard code rules still apply (§4.2): typed public funcs, one concept per file, `WeaverError` hierarchy, state via services.

**B1 must reconcile with existing QA, not duplicate it.** A deterministic QA layer already exists: `weaver.qa.checks` (`SegmentInput`/`QAWarning`, `Severity = info|warning|critical`, e.g. `check_empty_translation`, `check_untranslated_japanese`) consumed by the `weaver validate` CLI ("six deterministic QA checks"). B1 must audit it and decide reuse vs. extend — **no parallel QA system** (§4.3). Note the naming gap to resolve in B1: existing severity uses `critical`, this plan proposes `error`; pick one and document it. The new `services/translation_qa.py` should build on `weaver.qa.checks` where possible rather than re-implement the per-segment checks.

**Carry-over invariants (unchanged this phase):**
- **Web is FastAPI-only** (ADR `004`). `weaver serve` = FastAPI cockpit (UI + API), `weaver serve-api` = headless. Flask is fully removed — no `serve-flask`, no `src/weaver/web/**`, no `flask` dependency.
- **Legacy CLI** `weaver translate` and `services/export.py` are **single-volume**; multi-volume translate/export is the cockpit's job (batch + `export_book`).

**Baseline entering Phase B:** `v0.7.0-rc.1` (RC1) + Phase A UI polish, all merged to `main`. Last full-suite validation was green at RC1 (**653 tests / 4 skipped**, pyright 0, ruff + format clean, CLI 15 commands, FastAPI UI smoke, cockpit soak 25/25); Phase A added presentation-only UI tests on top. **Re-confirm the current baseline via the §2.2 gate before B1 exits** (test count drifts with each added test).

### 2.4 Exit Criteria

> **MVP acceptance gate: met & LOCKED** (Sprint 9C, 2026-06-02), shipped as `v0.7.0-rc.1`; evidence in [docs/MVP_STABILIZATION_REPORT.md](docs/MVP_STABILIZATION_REPORT.md) and [docs/RC1_REPORT.md](docs/RC1_REPORT.md). The MVP checklist lives in [docs/MVP_SCOPE.md](docs/MVP_SCOPE.md). **Phase A — UI/UX Polish: complete** ([docs/PHASE_A_UI_AUDIT.md](docs/PHASE_A_UI_AUDIT.md)).

**Phase B exits only when:**

- **B1** — `docs/PHASE_B_QA_PLAN.md` exists: QA rule list, severity model (`info`/`warning`/`error`), categories, report schema (chapter/volume/novel), and a stage breakdown; reconciliation with existing `weaver.qa.checks` + `weaver validate` documented. (Design only — no code.)
- **B2** — `services/translation_qa.py` is framework-agnostic, **read-only**, deterministic; `analyze_chapter/volume/novel` produce `QAReport`/`QAIssue`. Tests prove detection of every initial check (untranslated, failed/stale, empty/short, repeated, glossary, character-name, fallback-heavy, mixed-status). No provider call, no mutation, no semantic/vector.
- **B3** — JSON endpoints `GET /projects/{name}/qa`, `…/volumes/{id}/qa`, `…/chapters/{id}/qa` return a valid report (`scope`, counts, `issues[]`, `summary_by_category`, `summary_by_chapter|volume`); unknown project/volume/chapter handled cleanly; thin adapter over B2 only.
- **B4** — QA report pages (`/ui/projects/{name}/qa`, `…/chapters/{id}/qa`) + severity badges, category filter, links where available; project/chapter/tree badge states (`clean`/`warnings`/`errors`); empty + "review before export" states. Jinja2 + HTMX, no auto-fix.
- **B5** — pre-export QA warning shows the issue summary; **export still allowed by default** ("Export anyway" vs "Review QA first"); existing export behavior + source fallback unchanged.
- **B6** — docs updated (TRANSLATION_PIPELINE, COCKPIT_WORKFLOW, ARCHITECTURE, QUICKSTART, CLAUDE.md); full regression green (`pytest`, `pyright`, `ruff`); FastAPI UI + QA API smoke; export flow still works; **no accidental translation mutation, no provider call during QA**.
- **Quality gate (every stage):** CLI not broken; web not broken; docs match code; one PR = one concern; no premature visual polish.

### 2.5 Phase Log

One row per phase/era; deep detail lives in the linked docs, [docs/archive/MVP_PHASE_LOG.md](docs/archive/MVP_PHASE_LOG.md), and git history.

| Phase / era | Outcome |
|---|---|
| Foundation (v0.6.0) | CLI complete + Flask web cockpit end-to-end. Detail in git history + `docs/archive/`. |
| Reset Tasks 1–5 | Controlled reset → MVP Web Cockpit Foundation + FastAPI direction; ADRs reset to `001`–`007`; MVP gap finalized + sprint plan locked. |
| MVP Sprints 1–9 | Core cockpit: Novel/Volume/Chapter model + multi-format import (1); FastAPI cockpit foundation (2); workspace read/save/history (3); provider AI translate + safe-retranslate modes (4); glossary + character DB with prompt injection (5); translation memory, lookup-before-AI (6); batch chapter/volume/novel + progress/cancel/SSE (7); volume-aware EPUB/TXT/HTML export (8); MVP stabilization + real-EPUB E2E, **baseline LOCKED** (9C). |
| MVP Sprints 10–13 | Flask→FastAPI convergence: parity audit + gap closure — create/browse, config/secret write, glossary candidate review (10); FastAPI UI functional parity, Jinja2+HTMX (11); parity audit + default-`serve` flip to FastAPI (12); **Flask fully decommissioned** — `serve-flask`, `src/weaver/web/**`, `flask` dep removed (13). FastAPI is the sole web cockpit. |
| MVP RC1 | Release-candidate verification: full validation green (653 tests / 4 skipped, pyright 0, ruff+format clean), CLI 15 commands, cockpit soak 25/25, clean-env wheel install. **GO for RC1**; tag `v0.7.0-rc.1`. Report: [docs/RC1_REPORT.md](docs/RC1_REPORT.md). |
| Phase A — UI/UX Polish | Cockpit UI polish on Jinja2+HTMX: A1 UX audit ([docs/PHASE_A_UI_AUDIT.md](docs/PHASE_A_UI_AUDIT.md)) → A2-1 shell/a11y/responsive · A2-2 feedback/a11y · A2-3 workspace UX · A2-4 dashboard/project clarity · A2-5 admin usability · A2-6 live verification. Presentation/copy only (+ one additive `done_count` field, a small progressive-enhancement script); no backend/provider/stack change. Merged PR #18. |
| **Phase B — Translation QA** | **Active.** Read-only, deterministic QA reports before export (report-first, no auto-fix; no provider calls, no mutation, no semantic/vector). Stages B1–B6 (§2.3). **Next: B1 — QA rule design & audit (docs/design only).** |

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
