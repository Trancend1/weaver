# Weaver

Offline-capable, glossary-aware **JP→EN** light-novel translation workbench with a **CLI** and local **web cockpit** (web-cockpit-first development). **Not:** SaaS, consumer product, hosted service, complex SPA.

> **Operating manual:** This file follows the global agent template `@WORKFLOW.md`. It cites and coordinates the docs in §1; it does not duplicate full strategy content. §5–§10 define how work is split across specialized agents/subagents and gated.
>
> **Current Orchestrator:** repo owner (Trancend1) + Claude as Lead Technical Orchestrator.
> **Active Sprint/Phase:** **none active** — Sprint Q (Workspace v2) and **Sprint R (AI glossary-target suggestion)** are both **COMPLETE and merged to `main`**. Next sprint scope TBD by the orchestrator.
>

---

## 1. Documentation Map

Docs are the spec. Code follows docs. If code contradicts docs, ask first.

| Topic | Source of truth |
| --- | --- |
| User-facing: install, quickstart, commands | [README.md](README.md) |
| Navigation supplement — module map, CLI/web flow, data, deps | [docs/CODEMAPS/architecture.md](docs/CODEMAPS/architecture.md) · [backend](docs/CODEMAPS/backend.md) · [frontend](docs/CODEMAPS/frontend.md) · [data](docs/CODEMAPS/data.md) · [dependencies](docs/CODEMAPS/dependencies.md) |
| Runtime contract for Tauri (or any) host shell | [docs/SIDECAR_CONTRACT.md](docs/SIDECAR_CONTRACT.md) |
| Testing, regression, release, migration discipline | [docs/MAINTENANCE.md](docs/MAINTENANCE.md) |
| Architecture decisions (ADR `001`–`014`) | [docs/DECISIONS.md](docs/DECISIONS.md) · [docs/decisions/](docs/decisions/) |
| Active reference specs | [docs/PROMPT_DESIGN.md](docs/PROMPT_DESIGN.md) · [docs/SECURITY_AND_PERFORMANCE.md](docs/SECURITY_AND_PERFORMANCE.md) |
| RTK shell tooling rule | `C:\Users\transcend\.claude\RTK.md` |
| Global workflow template (this file follows it) | `C:\Users\transcend\.claude\WORKFLOW.md` |

**Hierarchy:** `docs/CODEMAPS/` is the primary navigation supplement (module map, CLI/web workflows, data flow, dependencies). ADRs and active sprint docs are source of truth for decisions. `SIDECAR_CONTRACT.md`, `MAINTENANCE.md`, `PROMPT_DESIGN.md`, and `SECURITY_AND_PERFORMANCE.md` remain as detailed reference docs for their respective domains. `.reports/` is an audit/report artifact area; do not treat it as product or architecture authority.

---

## 2. Progress — Phase Schedule

### 2.1 Roadmap Snapshot

Current status: **no active sprint**. Sprints through **R** are complete and merged to `main`; next sprint scope is TBD by the orchestrator.

```txt
Historical baseline ✅
  Foundation → MVP Web Cockpit → Phases A–F → Sprints G–M
Post-pivot desktop/workflow line ✅
  Sprint N (Tauri shell alpha) → Sprint P (workflow coherence) → Sprint O (production desktop)
Workspace + AI suggestion line ✅
  Sprint Q (Workspace v2, PR #41/#42/#43/#44) → Sprint R (AI glossary-target suggestion, PR #46/#47)
Next ⬜
  Open a scoped sprint from current carried follow-ups; do not continue historical sprint scaffolding by default.
```

Legend: ✅ complete · 🟡 active · ⬜ pending · 🚫 deferred/blocked

**Progress wrapper — completed work:** `Foundation → Sprint R` is historical. Keep details in git history and linked source docs, not in this operating file:
- Sprint Q historical refs: [SPRINT_Q_EXECUTION_PLAN.md](.docs/audit/SPRINT_Q_EXECUTION_PLAN.md), [SPRINT_Q_FINAL_VALIDATION.md](.docs/audit/SPRINT_Q_FINAL_VALIDATION.md), [SPRINT_Q_HANDOFF.md](.docs/audit/SPRINT_Q_HANDOFF.md).
- Sprint R refs: [ADR 014](docs/decisions/014-provider-complete-primitive-and-glossary-suggestion.md), [spec](docs/superpowers/specs/2026-06-12-glossary-ai-target-suggestion-design.md), [plan](docs/superpowers/plans/2026-06-12-sprint-r-glossary-ai-suggestion.md).
- Roadmap/audit refs: [ROADMAP_REPLAN.md](.docs/audit/ROADMAP_REPLAN.md), [SOURCEOFARCHITECTURE.md](.docs/audit/SOURCEOFARCHITECTURE.md), [ISSUE_BACKLOG.md](.docs/audit/ISSUE_BACKLOG.md).

### 2.2 Reusable Phase Gate

Before starting any new sprint or stage:

1. **Define scope** in §2.3, including acceptance criteria and explicit non-goals.
2. **List exit criteria** in §2.4 in plain language.
3. **Verify each criterion** with a concrete command, test, file check, or manual inspection.
4. **State user-facing status:** usable now, internal-only, not yet user-facing.
5. **If all pass** — update §2.1 / §2.3 / §2.4 / §2.5 + write a handoff note (§8).
6. **If any fails** — mark blocked, record missing proof, and stop.

> Required reminder: **"Check exit criteria first. No next stage until evidence exists. Explain the detail for manual inspection."**

### 2.3 Active Phase — none

**Track(s) active:** none. Next sprint scope is TBD by the orchestrator.

**Recommended next-sprint inputs:** use [docs/MAINTENANCE.md](docs/MAINTENANCE.md) carried issues plus current user priority. Known forward-relevant candidates:
- WV-014 ruby import flatten follow-up: importer currently flattens `<ruby>` via `itertext()`, leaking furigana into `source_text`; renderer preservation is not the defect.
- Legacy project upgrade UX: v10 projects can show `needs_upgrade` until a writable open migrates them.
- Export ledger semantics: `export_history.job_id` remains `NULL` because the registry id is known only after job closure.
- `volume_lifecycle` exported overlay remains deferred; the export ledger is the source of truth.

**Carry-forward architecture invariants from closed sprints:**
- One project DB remains the source of truth for that project. **No global mutable cross-project store without an ADR.**
- Cross-project reads use the read-only `workspace_index` / workspace services pattern; read paths must not migrate, reset `in_progress`, call providers, run QA scans, or hash source files on render/list/hub paths.
- Provider `complete()` is a domain-agnostic transport primitive only. Feature prompts/parsing stay in services; adding provider domain methods requires an ADR.
- AI artifacts must be explicit, editable/dismissable, failure-visible, and cost-visible.

**Workspace UI invariants still active:**
- `#seg-{id}` = full segment row swap target; `#seg-statusline-{id}` is **not** an HTMX swap target.
- Review pills update optimistically in `workspace.html` and POST with `hx-swap="none"`; failed POST surfaces via `review-save-failed`.
- Review labels/colours are single-sourced in `api/status_labels.py`.
- Keep `#seg-{id}-history`, `#seg-{id}-candidates`, `#seg-{id}-gen-loader`, `.seg-row--review`, `.seg-row--edit`, `.seg-row--tools` stable.
- Do not recreate deleted preview modal routes/buttons or removed workspace header/sidebar clutter.

### 2.4 Exit Criteria

No active sprint means no sprint-specific exit criteria are open.

When opening the next sprint, add only the criteria for that sprint here. Keep closed-sprint evidence in linked docs, not inline. Minimum gate:

- [ ] Scope and non-goals documented in §2.3.
- [ ] Relevant tests/lint/typecheck/build/browser checks identified before implementation.
- [ ] Gate B1 impact stated for any web/render/list/hub path.
- [ ] Security/reliability review required for I/O, secrets, filesystem, subprocess, network, or provider work.
- [ ] Handoff note written with validation evidence before marking complete.

### 2.5 Phase Log

Deep detail lives in git history and linked docs. This table preserves only operational lessons still useful for future work.

| Phase / Sprint wrapper | Key ref | Last verified gate | Operational lesson / carry-forward |
|---|---|---|---|
| Foundation → Sprint M | Git history + ADRs `001`–`012` | 1043 / 4 | Core CLI/cockpit/persistent-job/export/candidate/image-gate baseline is stable; prefer existing architecture over new layers. |
| N → P → O | [ROADMAP_REPLAN.md](.docs/audit/ROADMAP_REPLAN.md), `desktop/`, [INSTALL_DESKTOP.md](docs/INSTALL_DESKTOP.md) | 1102 / 4 | Workflow coherence preceded production desktop; Tauri remains isolated in `desktop/` and follows [SIDECAR_CONTRACT.md](docs/SIDECAR_CONTRACT.md). |
| Sprint Q — Workspace v2 | [SPRINT_Q_FINAL_VALIDATION.md](.docs/audit/SPRINT_Q_FINAL_VALIDATION.md), [SPRINT_Q_HANDOFF.md](.docs/audit/SPRINT_Q_HANDOFF.md) | 1351 / 4, pyright 0, ruff clean, cargo check 0 | Gate B1 audits pay off. Preserve read-only workspace services, no render-path hashing/provider/QA, and no global mutable store. |
| Sprint R — AI glossary-target suggestion | [ADR 014](docs/decisions/014-provider-complete-primitive-and-glossary-suggestion.md), [spec](docs/superpowers/specs/2026-06-12-glossary-ai-target-suggestion-design.md) | 1401 / 4, pyright 0, ruff+format clean | Abstract provider changes have broad blast radius; keep provider methods domain-agnostic and put validation in services. |

> Test counts are historical evidence. Re-run relevant verification for the current sprint; do not assume counts without running them.

---

## 3. Stack (Locked)

**Core:** Python 3.11+ · uv · pyproject.toml · ruff · pyright (basic) · pytest · typer · rich · pydantic v2 · tomllib · sqlite3 (WAL, no ORM) · ebooklib · openai SDK · google-generativeai · Jinja2

**Web cockpit:** FastAPI (ADR `004`) behind optional `weaver[web]` extra. Server-rendered Jinja2 + HTMX (ADR `007`), no Node/build, no SPA. HTMX vendored as static asset (no CDN). asyncio unlocked **only** for the FastAPI web layer.

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

**Deferred (not in Sprint Q scope):** OCR implementation, provider expansion, route rewrite, SPA/Node, external queue.

**Banned unless explicitly overridden (ADR required):** Flask · Django · SQLAlchemy · Celery · RQ · Docker · React/Node build · SPA framework · OpenTelemetry · Sentry. asyncio rejected outside the web layer. External job queue / worker daemon / multi-process worker pool rejected (ADR `010`; `api/jobs.py:8-10`). **No global mutable cross-project store without an ADR.**

---

## 4. AI Instructions

### 4.1 Before Coding

1. Read this file first, then the relevant doc/ADR from §1. No sprint is currently active (Sprint Q + R closed); when a new sprint opens, follow its execution plan/spec + the staging discipline modelled by [SPRINT_Q_EXECUTION_PLAN.md](.docs/audit/SPRINT_Q_EXECUTION_PLAN.md), against [SOURCEOFARCHITECTURE.md](.docs/audit/SOURCEOFARCHITECTURE.md) + [ROADMAP_REPLAN.md](.docs/audit/ROADMAP_REPLAN.md).
2. Check the active stage in §2.3 before starting any work. Respect stage order; stop at each stage gate (§2.2) for inspection.
3. Run `rtk git status --short --branch`. If WIP overlaps the relevant area, tell the orchestrator before editing.
4. Confirm scaffolding is actually requested. Docs/strategy request ≠ build code.
5. Check the file tree before creating new files or folders. Use exact names/values from docs for types, schemas, exit codes — do not improvise. When unsure: ask.
6. Before committing: scan the diff for AI attribution trailers, bot author metadata, or leaked credentials.

### 4.2 Code Rules (Non-Negotiable)

ADR `002`. (Absorbs the former `ENGINEERING_STANDARDS.md`.)

- **Types:** Type hints on every public function. Pyright basic must pass.
- **Modularity:** One concept per file. Split if >400 lines or >5 public functions. Functions >50 lines or >4 params need justification.
- **Naming:** Forbidden filenames: `utils.py`, `helpers.py`, `manager.py`. Avoid class names ending `Manager`/`Helper`/`Handler` unless they truly are that pattern. Name modules for purpose.
- **No `**kwargs`** in public APIs. No bare `except:` or `except Exception:` outside the CLI/web boundary; never `except: pass`.
- **Errors:** All via `WeaverError` hierarchy (`src/weaver/errors.py`). User-facing errors include: what failed / likely cause / next command. Process-exit errors use the documented exit-code table (README / [SIDECAR_CONTRACT.md](docs/SIDECAR_CONTRACT.md)).
- **State discipline:** State writes go through services. CLI/web never touch SQLite directly. One segment translation = one transaction. Status transitions live in the same transaction as the data they describe.
- **Layer boundaries:** Shared/core is framework-agnostic (no web `Request`/`Response`, no DI wiring, no template/CLI output). Pydantic only at the web boundary. UI templates/routes carry no business logic.
- **API keys:** Env vars or `~/.weaver/secrets.toml` only — never in config, logged, rendered, or in an SSE event. Shell env wins. CI greps `provider.log` for zero keys.
- **Value types:** `@dataclass(frozen=True)` for value types. `pathlib.Path` for paths (never string-concat). Atomic writes (`tempfile` + `replace`) for valuable state.
- **Cockpit UI hooks (do not rename/remove):** `#tree`, `#ws-grid`, `#job-panel`, `#export-panel`, `#browser`, `#selected_source`, `#source_path`, `#qa-badge-status`, `#qa-issues`, `id="seg-{id}"`, and the `qa-badge-vol-*` / `qa-badge-ch-*` slots. Design tokens have a single source: `api/static/app.css` `:root`. Details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
- **Tests:** Mirror source tree. Use `FakeProvider`, never live LLMs in CI. Fixtures = public-domain only (e.g. Aozora Bunko). Mock external boundaries only, never your own code.
- **Security (any PR touching I/O):** input parsed via pydantic (not raw dict chains); no user string to `os.system`/`subprocess(shell=True)`/`eval`/`exec`; cloud HTTPS only; malformed input handled without crashing. Performance budgets (init <30 s/200-ch; resume <5 s/10k seg; export <30 s/10k seg; <1 GB peak) — regressions >20% need justification.
- **Tech-debt prevention:** No stub functions "for later", no commented-out code, no single-caller abstractions, no config flag to defer a decision. Dead code deleted on sight. TODO/FIXME carries an issue + cleanup plan.
- **Git/PR:** Conventional Commits with scope (`feat(translate): …`); branches `feat|fix|docs|chore/<name>`; one PR = one concern; no force-push to `main`. ADRs (`docs/decisions/NNNN-*.md`): Context / Decision / Consequences, one page.
- **Githooks:** `.githooks/` are mandatory. Keep `git config core.hooksPath .githooks` enabled.

### 4.3 Anti-Slop

(Absorbs the former `AI_SLOP_PREVENTION.md`.) The LLM must be load-bearing infrastructure, never decoration.

- **No** "smart"/"AI-powered"/"magical"/"intelligent" feature names. No chat UIs, avatars, sparkles, fortune-cookie loaders, marketing language, telemetry/phone-home.
- **No prompt-wrapper features:** a new "mode" that only changes the system prompt is not a feature. Real features change the data flow, state machine, or workflow.
- A feature ships only if all six gates pass: **(1) real pain** (evidenced, not "would be cool") · **(2) falsifiable spec** · **(3) deterministic where possible** (LLM only when determinism is impossible AND output is verifiable) · **(4) user can override** (every AI artifact editable/dismissable) · **(5) failure visible** (failed output marked + surfaced, never silently substituted or retried-forever) · **(6) cost visible**.
- No config flags for unbuilt features. No stub functions. No commented-out code. No abstractions with one caller.

### 4.4 Scope Discipline

Build vertically, not horizontally. One polished slice beats several half-finished ones. When in doubt between spectacle and correctness, prioritize correctness.

- Build only what the active stage (§2.3) lists. Deferred items get no scaffolding "for later".
- One PR = one concern. No bundled refactor + feature. **One closed-sprint stage = one branch + one PR.**
- **Cross-project read layer** is **read-only**; **no global mutable store without an ADR**; **no source-file hashing on any render path** (Gate B1 extended). Add a **Non-Goals** line per stage (§2.3) to fence scope.
- When no sprint is active, open a new scope by writing a Sprint-X execution plan (modelled on [SPRINT_Q_EXECUTION_PLAN.md](.docs/audit/SPRINT_Q_EXECUTION_PLAN.md)) and an entry in §2.3 / §2.4. Do not continue the previous sprint's scaffolding by default.

Build order (when a new sprint opens): **T6/T7/T8 validation gates for any prior carry-over** → **stage implementation in execution-plan order** → **T0 docs + handoff** → **T9 final gate**.

### 4.5 Communication

- Terse, technical. No filler, no apology, no marketing language.
- Reference files as `[name](path/file.md)` or `src/weaver/foo.py:42`. State decisions directly.
- Use concise Indonesian when the user writes in Indonesian.
- When uncertain, present 2–3 concrete options with trade-offs. Flag conflicts early: locked-stack changes, phase jumps, scope creep, direction regressions. During debugging: state what is happening, what was expected, what evidence supports the conclusion.

### 4.6 Contribution Identity

> **Copy this section verbatim into every project CLAUDE.md. Do not modify.**

AI is a ghostwriter. Repository accountability remains with the human owner.

- Do not add `Co-Authored-By: Claude` or any AI/model co-author trailer to commits.
- Do not add "Generated with Claude Code" or equivalent tags to commit messages or PR bodies.
- Do not push commits with AI or bot author identity.
- Do not make AI appear in the GitHub contributor graph.
- Author and committer identity must be the repo owner's human identity configured for the project.
- If AI assistance needs to be disclosed, mention it only in normal prose in a PR description or changelog, never in git metadata.

---

## 5. Implementation Agent Team

Weaver is built by the repo owner with Claude as Lead Technical Orchestrator, who splits work across specialist roles. Each role maps to a Weaver layer and is **realized** either by the orchestrator working inline or by a named Claude subagent/skill (spawn only when the owner asks, per the harness rule).

| # | Role | Weaver domain | Must not do | Realized by |
| --- | --- | --- | --- | --- |
| 1 | **Lead Orchestrator** | Stage sequencing, scope control, merge readiness, final gate | Skip final validation; assign ambiguous work; build a hub on the un-hardened foundation | Orchestrator (inline) · `Plan` |
| 2 | **Product / Workflow Architect** | User journey, page hierarchy, workflow coherence (cockpit) | Add pages without a user-journey path; design features that bypass the core pipeline | Orchestrator · `feature-dev:code-architect` |
| 3 | **Frontend Engineer** | Jinja2 + HTMX templates, partials, navigation, a11y, 390px+ states | Add a frontend build step; rename HTMX hooks (§4.2); noisy UI outside the design system | Orchestrator · `frontend-design` |
| 4 | **Backend Engineer** | API routers, `services/`, CLI commands, provider boundaries, validation | Put business logic in routers; touch SQLite from CLI/web; bypass services | Orchestrator · `feature-dev:code-architect`/`code-explorer` |
| 5 | **Data / Storage Engineer** | `storage/migrations.py`, `schema.sql`, persistence, backward compat | Schema churn without approval; break compat without ADR; mutate on a read path | Orchestrator · `pr-review-toolkit:type-design-analyzer` |
| 6 | **QA / Validation Engineer** | pytest suite, regression, edge cases, acceptance | Validate unit-only; skip user-facing workflow paths | `pr-review-toolkit:pr-test-analyzer` · `verify` |
| 7 | **Security / Safety Engineer** | I/O surfaces, secrets, path traversal, EPUB/image handling | Unsafe file/subprocess patterns; secrets in config/logs/render; cross-project path leak | `security-review` · `pr-review-toolkit:silent-failure-hunter` |
| 8 | **Performance / Reliability Engineer** | Render-path cost (Gate B1), job recovery, budgets | Ship blocking UX; hide errors with silent retries; hash source files on render | Orchestrator (budget checks) · `pr-review-toolkit:silent-failure-hunter` |
| 9 | **Documentation / Handoff Writer** | CLAUDE.md, sprint notes, ADR drafts, §8 handoff | Duplicate source-of-truth docs; write verbose non-operational prose | Orchestrator · `pr-review-toolkit:comment-analyzer` |
| 10 | **Critic / Devil's Advocate** | Challenge assumptions, overengineering, hidden bugs, sequencing | Block without an actionable alternative; complain without evidence | `pr-review-toolkit:code-reviewer` · `feature-dev:code-reviewer` |
| 11 | **Release Captain** | Stage/sprint final gate, "done/not-done", known-gap doc | Mark done without evidence; merge incomplete work | Orchestrator · `code-review` |

**Rule:** No role overrides the orchestrator's scope without documenting reason, risk, and a proposed alternative. **The same agent should not be the sole reviewer of its own work** — builder (Backend/Frontend) → reviewer (Critic/QA/Security). Spawn subagents only when the owner asks (harness rule); otherwise the orchestrator fills the role inline.

---

## 6. Implementation Tracks

A track is owned by exactly one role. Supporting roles review or provide input but do not override the owner.

| Track | Name | Owner | Weaver entry → exit |
| --- | --- | --- | --- |
| T0 | **Docs & Source of Truth** | Doc Writer | Stage scope defined → CLAUDE.md/§2 + handoff (§8) updated; ADRs current |
| T1 | **Product Workflow & UX** | Product Architect | Stage defines/modifies a flow → journey documented; no orphan pages/states |
| T2 | **Frontend (Jinja2 + HTMX)** | Frontend Eng | T1 defines UI; tokens exist → renders at 390px+; keyboard nav; loading/empty/error states; hooks intact |
| T3 | **Backend / API & Services** | Backend Eng | Contracts defined; storage exists → endpoints correct; input validated; services own writes; routers SQL-free |
| T4 | **Data, Storage & Migration** | Storage Eng | Schema/migration required → forward + idempotency tested; existing data preserved; no silent loss |
| T5 | **Provider / Job Integration** | Backend Eng | New provider/model config required → retry/fallback works; secrets confirmed; cost visible; ADR `010` intact |
| T6 | **QA, Testing & Regression** | QA Eng | Implementation complete → full suite passes; regressions + edge cases documented; acceptance verified |
| T7 | **Security & Reliability** | Security Eng | Feature touches I/O/secrets/fs/subprocess/network → surfaces enumerated; risks + mitigations documented |
| T8 | **Performance & Runtime** | Perf Eng | Feature complete → budget met or regression justified; **zero render-path hashing**; no blocking UX; job recovery tested |
| T9 | **Release & Final Gate** | Release Captain | All tracks done; T6/T7/T8 passed → checklist signed; known gaps + next step clear |

**Sprint Q track note:** every Q stage runs T0 (docs) + the build tracks it needs, always gated by T6/T7/T8. Q11 is validation-only (T6/T7/T8 → T0) — no new build tracks. v12 migration is conditional at Q12.

---

## 7. Orchestrator Operating Model

1. Read §1 docs governing the current stage; identify the stage from §2.3.
2. Confirm §3 locked-stack constraints — no new dependency or architecture shift without an ADR/owner approval.
3. Split the stage into tracks (§6); give each track an owner, scope, **acceptance criteria, and explicit non-goals** before implementation.
4. Require a handoff note (§8) at the end of each track.
5. Run Critic review (role #10) before the final gate; run QA + Security + Perf (T6+T7+T8) before merging.
6. Produce a per-track status: **Done** (implemented + validated + documented + handed off) · **Partial** (known gaps documented) · **Blocked** (external dependency) · **Deferred** (reason + trigger) · **Risk Accepted** (mitigation + rollback documented).

**Operating rule:** optimize for sequence, coherence, and risk reduction — not maximum parallel work. **Q1+Q2 hardened the foundation precisely so Q3+ hubs can be built one at a time without re-auditing the read paths.**

---

## 8. Agent Handoff Protocol

Every track ends with a handoff note. Without it, the work is incomplete by definition.

```
## Handoff: [Role]
**Track:** [T0-T9]
**Scope:** [what this track was asked to do]
**Files/Areas Touched:** [created/modified]
**What Changed:** [summary]
**What Was Intentionally Not Changed:** [scope boundaries respected]
**Validation Performed:** [tests run, manual checks, evidence — paste commands/output]
**Known Risks:** [incomplete, fragile, or uncertain]
**Recommended Next Role / Next Step:** [single next action]
```

**Rule:** a handoff must leave enough context to continue **without re-auditing the repo**. Update §2.3/§2.5 at each stage gate. The "next step" line is mandatory.

---

## 9. Review Gates

| Gate | Stage | Checks | Skippable? |
| --- | --- | --- | --- |
| **A — Scope** | Before work | Aligned with active stage (§2.3)? Owner clear? Non-goals stated? Acceptance defined? | No |
| **B — Readiness** | Before coding | Affected files known? §3 constraints respected? Matches existing patterns? **Gate B1: no QA/provider/hashing on render path.** | No for T2–T5 |
| **C — Validation** | After implementation | Tests/manual checks documented? Regressions + edge cases listed? Handoff written? | No for T2–T8 |
| **D — Release** | Before merge | Work complete? Known gaps documented? Critic review done? §2.4 stage criteria green? | No |

**Gate-skip rule:** fewer gates for small changes (single file, <50 lines, no schema change), but **never skip Gate C**. Document any skip in the handoff.

---

## 10. Decision Rules

| # | Rule |
| --- | --- |
| 1 | Prefer **existing architecture** over new patterns. The cross-project read layer is `workspace_index`; do not invent a parallel store. |
| 2 | Prefer **small, sequenced changes** over broad rewrites. One stage, one branch, one PR. |
| 3 | Prefer **user workflow completion** over isolated polish. A working end-to-end cockpit path beats a perfectly refactored unused component. |
| 4 | **Explicit ownership** — every track has a named owner role (§5). |
| 5 | **No new runtime dependency** without an ADR. A new import is an architecture decision. |
| 6 | **No "complete" without validation evidence.** "It compiles" / "tests should pass" is not validation — run them. |
| 7 | **Do not modify roadmap/architecture/stack silently.** Propose changes in a handoff or ADR draft. |
| 8 | **When in doubt, document the uncertainty** and propose the smallest safe next step. A documented question beats an undocumented assumption. |

---

*This file is the operating manual for Weaver. It follows the global template `@WORKFLOW.md`. Read it before any code change. The roadmap (§2.1) is the plan; the active phase (§2.3) is the status — do not conflate them.*
