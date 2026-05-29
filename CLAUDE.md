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

| Sprint | Scope | Status |
|---|---|---|
| 1 | Project structure & novel mgmt (Novel/Volume/Chapter; TXT/EPUB/HTML import) | ⏳ next |
| 2 | Translation workspace (JP/EN two-column, edit, auto-save, revisions) | ⬜ |
| 3 | Provider & AI translation (config, translate chapter/selection, safe retranslate) | ⬜ |
| 4 | Glossary & character database (project-scoped, prompt injection) | ⬜ |
| 5 | Translation memory (source→target store, lookup-before-AI, reuse) | ⬜ |
| 6 | Batch translation & progress (chapter/volume/novel, job status) | ⬜ |
| 7 | Export (EPUB priority, TXT, HTML, DOCX) | ⬜ |
| 8 | MVP stabilization (smoke CLI+web, regression, acceptance checklist, UI/UX plan) | ⬜ |

Legend: ✅ complete · 🟡 in progress · ⏳ next · ⬜ pending · 🚫 blocked.

> Sprint detail + MVP gap analysis finalized in [docs/MVP_SCOPE.md](docs/MVP_SCOPE.md) (reset Task 5, verified against `src/weaver/`). Sprint ordering is dependency-driven, not calendar.

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

Reset status: Tasks 1–5 done (audit · cleanup/ADR reset · docs rewrite · fresh baseline · MVP gap finalize + sprint lock — all checks green; gap table verified against `src/weaver/` in [docs/MVP_SCOPE.md](docs/MVP_SCOPE.md)). **Gate 5 pending maintainer review.** Sprint 1 begins only after Gate 5 passes.

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
