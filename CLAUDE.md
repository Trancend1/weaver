# Weaver

Offline-capable, glossary-aware **JP→EN** light-novel translation workbench with a **CLI** and local **web cockpit** (web-cockpit-first development). **Not:** SaaS, consumer product, hosted service, complex SPA.

> **Status (2026-06-08):** v0.7.0 stable · Sprints A–K complete · **Sprint L complete** · Active sprint: **Sprint M** (Image / OCR Security Gate) · Last gate: **1017 tests / 4 skipped**, pyright 0, ruff + format clean, clean wheel build · [Full plan](docs/weaver_next_plan.md) · ADRs `009` (strategic pivot), `010` (persistent job core), `011` (Project terminology)

---

## 1. Documentation Map

Docs are the spec. Code follows docs. If code contradicts docs, ask first.

| Doc | Purpose |
|-----|---------|
| [README.md](README.md) | User-facing: install, quickstart, commands |
| [docs/README.md](docs/README.md) | Project overview, CLI/web split, where to start |
| [docs/QUICKSTART.md](docs/QUICKSTART.md) | End-to-end install + walkthrough |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Module map, layer boundaries, data flow |
| [docs/CLI_WORKFLOW.md](docs/CLI_WORKFLOW.md) | CLI daily workflow, limitations, rules |
| [docs/COCKPIT_WORKFLOW.md](docs/COCKPIT_WORKFLOW.md) | Web cockpit usage (FastAPI, Jinja2 + HTMX, JSON API) |
| [docs/DESIGN_NOTES.md](docs/DESIGN_NOTES.md) | UI design system: tokens, layout, components, a11y constraints |
| [docs/PROVIDER_AND_MODEL_CONFIG.md](docs/PROVIDER_AND_MODEL_CONFIG.md) | Provider setup, models, secret store |
| [docs/TRANSLATION_PIPELINE.md](docs/TRANSLATION_PIPELINE.md) | Import → segment → translate → QA → export flow |
| [docs/weaver_next_plan.md](docs/weaver_next_plan.md) | **Active roadmap:** Sprint G–O sequence |
| [docs/SIDECAR_CONTRACT.md](docs/SIDECAR_CONTRACT.md) | Runtime contract for Tauri (or any) host shell |
| [docs/MAINTENANCE.md](docs/MAINTENANCE.md) | Testing, regression, release, migration discipline |
| [docs/DECISIONS.md](docs/DECISIONS.md) | ADR index (`001`–`011`) |
| [docs/decisions/](docs/decisions/) | Full ADR texts |
| Supplementary: [ENGINEERING_STANDARDS.md](docs/ENGINEERING_STANDARDS.md) · [PROMPT_DESIGN.md](docs/PROMPT_DESIGN.md) · [SECURITY_AND_PERFORMANCE.md](docs/SECURITY_AND_PERFORMANCE.md) · [AI_SLOP_PREVENTION.md](docs/AI_SLOP_PREVENTION.md) | Reference specs (still active) |

> Retired docs (pre-reset specs, Phase A UI audit, MVP sprint logs, Flask→FastAPI audits, completed phase plans B/D/E, RC1 reports, design exploration) are in **git history** only.

---

## 2. Progress

### 2.1 Roadmap

Phases A–F shipped (v0.7.0). The post-Phase-F roadmap is Sprint G–O ([docs/weaver_next_plan.md](docs/weaver_next_plan.md)), governed by ADR `009`.

```txt
Foundation (v0.6.0) ✅
  → MVP Web Cockpit — Sprints 1–13        ✅  (v0.7.0-rc.1)
  → Phase A — UI/UX Polish                 ✅
  → Phase B — Translation QA               ✅
  → Phase C — Release hardening            ✅  (v0.7.0)
  → Phase D — DOCX, ZIP, QA config         ✅
  → Phase E — Design system & UI overhaul  ✅
  → Phase F — EPUB metadata & structure    ✅
  → Sprint G — FastAPI stability           ✅
  → Sprint H — Project & volume lifecycle  ✅
  → Sprint I — Persistent job core         ✅
  → Sprint J — EPUB preservation           ✅
  → Sprint K — Export fidelity             ✅
  → Sprint L — Candidate review            ✅
  → Sprint M — Image / OCR security gate   ⬜
  → Sprint N — Tauri shell alpha           ⬜
  → Sprint O — Production desktop          ⬜
```

Legend: ✅ complete · ⬜ pending · 🚫 deferred/blocked

> Phase ordering is dependency-driven, not calendar. MVP detail: [docs/MVP_SCOPE.md](docs/MVP_SCOPE.md). Sprint detail per row in §2.5.

### 2.2 Reusable Phase Gate

Before starting any phase or stage:

1. **Read** the active phase scope (§2.3) and its acceptance criteria.
2. **List** the stage's exit criteria (§2.4) in plain language.
3. **Verify** each with a concrete command, test, file check, or manual inspection.
4. **State** what is usable now, what is internal-only, what is not yet user-facing.
5. **If all pass** — update §2.1 / §2.3 / §2.4 / §2.5.
6. **If any fails** — mark the row blocked, record the missing proof. Do not proceed.

> Required reminder: **"Check exit criteria first. No next phase until evidence exists. Explain the detail for manual inspection."**

### 2.3 Active Phase — Sprint M: Image / OCR Security Gate

> [Full scope and task order](docs/weaver_next_plan.md). Sprint M may **not** start until Sprint L's final gate passes. Run the §2.2 phase gate before each sub-stage.

**Sprint L Complete ✅** — Candidate Review + Character Text Draft:

- Translation candidate model with status state machine (`pending` / `approved` / `rejected` / `applied` / `superseded` / `failed`)
- Grounded candidate generation with diff context; no auto-mutation of active translations
- Character Page text draft: XHTML/text-only (no images/OCR); provenance on every AI artifact (provider, model, prompt_version, timestamps, source segments)
- Schema v7 → v8: additive tables for candidates and drafts (forward-only, idempotent)
- JSON API + HTMX UI for candidate review and draft approval
- Safety: apply creates normal translation history entry; rejected candidates retained for audit

**Sprint M In scope (ADR `012`):**
- Image bytes endpoint (read-only, sandboxed)
- OCR pipeline with security gate (Gates A + B must pass before OCR calls)
- No external queue — `api/jobs.py:8-10` boundary stays in force

**Carry-over invariants (unchanged across Sprint G–O):**
- `read_epub()` and `DocumentIR` remain the import/export/translation path; `ParsedEpub` is the structural layer
- State writes go through services; CLI/web never touch SQLite directly
- API keys via env vars or `~/.weaver/secrets.toml` only — never in config, never logged, never rendered
- Locked stack (§3) unchanged; Tauri lives in `desktop/`, not a Python dependency

### 2.4 Exit Criteria

> **MVP acceptance:** met & LOCKED (Sprint 9C, 2026-06-02), shipped as v0.7.0-rc.1. Phases A–F complete. Sprints G–K complete.

**Sprint L exit criteria** (full task order in [docs/weaver_next_plan.md](docs/weaver_next_plan.md)):

- [x] L1 — Schema v7 → v8 migration: additive tables for candidates and drafts. Forward-only, idempotent, regression-tested.
- [x] L2 — Translation candidate model with status state machine; grounded generation with diff context; no auto-mutation.
- [x] L3 — Character Page text draft: XHTML/text-only; provenance on every AI artifact.
- [x] L4 — Follows Sprint I job pattern; cold-start recovery marks `running` → `failed/process restart`; no auto-resume.
- [x] L5 — Final gate: full test suite green, pyright 0, ruff + format clean, clean wheel build, readiness report in §2.5.

### 2.5 Phase Log

Deep detail per entry lives in git history and linked docs.

| Phase / Sprint | Key ref | Tests | Status |
|---|---|---|---|
| Foundation (v0.6.0) | Git history | — | ✅ CLI complete + Flask web |
| Reset Tasks 1–5 | Git history | — | ✅ MVP direction, FastAPI, ADRs 001–007 |
| MVP Sprints 1–9 | Git history | — | ✅ Core cockpit; baseline locked (9C) |
| MVP Sprints 10–13 | Git history | — | ✅ Flask→FastAPI convergence; Flask removed |
| MVP RC1 | Git history | 653 / 4 | ✅ v0.7.0-rc.1 tagged |
| Phase A — UI Polish | PR #18 | — | ✅ Jinja2+HTMX polish, a11y, responsive |
| Phase B — Translation QA | — | 703 / 4 | ✅ Report-first QA engine |
| Phase C — Release Hardening | — | — | ✅ v0.7.0 tagged |
| Phase D — Multi-item | `feat/docx-export` (PR #21) | 780 / 4 | ✅ DOCX, ZIP, QA config, provider hardening |
| Phase E — Design System | `feat/design-system-implementaion` | 796 / 4 | ✅ Token system, hybrid layout, project delete |
| Phase F — EPUB Metadata | `feat/epub-metadata-parse` | — | ✅ ParsedEpub, OPF, manifest, spine, NAV |
| Post-F Pivot (ADR 009–011) | [docs/weaver_next_plan.md](docs/weaver_next_plan.md) | — | ✅ Sprint G–O roadmap replaces npm wrapper |
| Sprint G — Runtime | `feat/FastAPI-stability-Tauri-ready` | 879 / 4 | ✅ Endpoints, env modes, logging, sidecar contract |
| Sprint H — Lifecycle | `feat/lifecycle-persistentjob-contract` | 904 / 4 | ✅ Volume lifecycle, delete controls, event logging |
| Sprint I — Persistent Jobs | `feat/lifecycle-persistentjob-contract` | 929 / 4 | ✅ JobRegistry, cold-start recovery, SSE resume |
| Sprint J — EPUB Snapshots | `feat/preservation-parser-hardening` | 973 / 4 | ✅ 6 snapshot tables, reparse job, epub-inspect CLI |
| Sprint K — Export Fidelity | `feat/export-fidelity` | 981 / 4 | ✅ Preflight, atomic write, fidelity report |
| **Sprint L — Candidate Review** | — | 1017 / 4 | ✅ Complete |

---

## 3. Stack (Locked)

**Core:** Python 3.11+ · uv · pyproject.toml · ruff · pyright (basic) · pytest · typer · rich · pydantic v2 · tomllib · sqlite3 (WAL, no ORM) · ebooklib · openai SDK · google-generativeai · Jinja2

**Web cockpit:** FastAPI (ADR `004`) behind optional `weaver[web]` extra. UI is server-rendered Jinja2 + HTMX (ADR `007`), no Node/build, no SPA. HTMX vendored as static asset (no CDN). asyncio unlocked **only** for the FastAPI web layer.

**Desktop shell (Sprint N+, ADR `009`):** Tauri in `desktop/` — isolated subtree, not a Python dependency. Launches FastAPI as sidecar (`127.0.0.1`, random port, session token) per [docs/SIDECAR_CONTRACT.md](docs/SIDECAR_CONTRACT.md).

**Providers:**

| Provider | Role | Auth |
|---|---|---|
| `deepseek` | Default cloud | `DEEPSEEK_API_KEY` |
| `gemini` | Free-tier cloud | `GEMINI_API_KEY` |
| `ollama` | Local, optional | None |
| `custom` | OpenAI-compatible endpoint | env var named by `api_key_env` |
| `fake` | CI/dev default | None |

Provider registry: `providers/registry.py`. API keys resolve from env vars or `~/.weaver/secrets.toml` (mode `0o600`, env wins) — never in config, never logged, never rendered.

**Rejected (no reintroduction without ADR):** Flask · Django · SQLAlchemy · Celery · RQ · Docker · React/Node build · SPA framework · OpenTelemetry · Sentry. asyncio rejected outside the web layer. External job queue / worker daemon / multi-process worker pool also rejected (ADR `010`; `api/jobs.py:8-10`).

---

## 4. AI Instructions

### 4.1 Before Coding

- Read the relevant doc/ADR section first. Docs are authoritative.
- Respect sprint order. Run the §2.2 phase gate before starting a new sprint.
- Use exact names/values from docs for types, schemas, exit codes. Do not improvise.
- When unsure: ask. Do not invent fields, prompts, commands, or exit codes.
- Respect the active-phase stage order (§2.3). Stop at each stage gate (§2.2) for inspection.
- Before committing: scan the diff for AI attribution trailers, bot author metadata, or leaked credentials.

### 4.2 Code Rules (Non-Negotiable)

Source: [ENGINEERING_STANDARDS.md](docs/ENGINEERING_STANDARDS.md), ADR `002`.

- **Types:** Type hints on every public function. Pyright basic must pass.
- **Modularity:** One concept per file. Split if >400 lines or >5 public functions.
- **Naming:** Forbidden filenames: `utils.py`, `helpers.py`, `manager.py`. Name modules for their purpose.
- **No `**kwargs`** in public APIs. No bare `except:` or `except Exception:` outside the CLI/web boundary.
- **Errors:** All via `WeaverError` hierarchy (`src/weaver/errors.py`). User-facing errors include: what failed / likely cause / next command.
- **State discipline:** State writes go through services. CLI/web never touch SQLite directly. One segment translation = one transaction.
- **Layer boundaries:** Shared/core is framework-agnostic (no web `Request`/`Response`, no DI wiring, no template/CLI output). Pydantic only at the web boundary. UI templates/routes carry no business logic.
- **API keys:** Env vars or `~/.weaver/secrets.toml` only — never in config, never logged, never rendered. Shell env wins.
- **Value types:** `@dataclass(frozen=True)` for value types. `pathlib.Path` for paths. Atomic writes (`tempfile` + `replace`) for valuable state.
- **Tests:** Mirror source tree. Use `FakeProvider`, never live LLMs in CI. Fixtures = public-domain only.
- **Githooks:** `.githooks/` are mandatory local guardrails. Keep `git config core.hooksPath .githooks` enabled.

### 4.3 Anti-Slop

Source: [AI_SLOP_PREVENTION.md](docs/AI_SLOP_PREVENTION.md).

- No "smart"/"AI-powered"/"magical"/"intelligent" feature names. No chat UIs, avatars, sparkles, fortune-cookie loaders.
- Deterministic by default. LLM only when determinism is impossible AND output is verifiable AND user can override.
- No config flags for unbuilt features. No stub functions. No commented-out code. No abstractions with one caller.

### 4.4 Scope Discipline

- Build only what the active phase (§2.3) lists. Deferred/advanced items get no scaffolding "for later".
- One PR = one concern. No bundled refactor + feature.
- **Sprint L:** candidate-review + character-draft only. No image/OCR endpoints, no EPUB preservation/export changes, no external queue.
- **Sprint M boundary (ADR `012`):** no image-bytes endpoint and no OCR call before ADR `012` Gates A + B are merged.

### 4.5 Communication

- Terse, technical. No filler, no apology, no marketing language.
- Reference files as `[name](path/file.md)` or `src/weaver/foo.py:42`. State decisions directly.

### 4.6 Contribution Identity

> **Copy this section verbatim into every project CLAUDE.md. Do not modify.**

AI is a ghostwriter. Repository accountability remains with the human owner.

- Do not add `Co-Authored-By: Claude` or any AI/model co-author trailer to commits.
- Do not add "Generated with Claude Code" or equivalent tags to commit messages or PR bodies.
- Do not push commits with AI or bot author identity.
- Do not make AI appear in the GitHub contributor graph.
- Author and committer identity must be the repo owner's human identity configured for the project.
- If AI assistance needs to be disclosed, mention it only in normal prose in a PR description or changelog, never in git metadata.
