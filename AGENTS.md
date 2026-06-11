# Weaver

Offline-capable, glossary-aware **JP→EN** light-novel translation workbench with a **CLI** and local **web cockpit** (web-cockpit-first development). **Not:** SaaS, consumer product, hosted service, complex SPA.

> **Operating manual:** This file follows the global agent template `@WORKFLOW.md`. It cites and coordinates the docs in §1; it does not duplicate full strategy content. §5–§10 define how work is split across specialized agents/subagents and gated.
>
> **Current Orchestrator:** repo owner (Trancend1) + Claude as Lead Technical Orchestrator.
**Active Sprint/Phase:** Sprint Q — Workspace v2 · **stages Q1–Q10 built** (Q1–Q9 merged; Q10 on branch `feat/workspace-context-panel`) · **next stage Q11 — Validation (WV-007/008/011)**.
>
> **Status (2026-06-11):** v0.7.0 stable · Sprints A–M + **N, P, O COMPLETE** · **Sprint Q ACTIVE** — Q0 planning ✅, **Q1 (identity + read layer) ✅, Q2 (read-path hardening) ✅, Q3 (shell + dashboard) ✅, Q4 (queue hub) ✅, Q5 (resources hub) ✅, Q6 (providers hub) ✅, Q7 (export gate + ledger) ✅, Q8 (analytics) ✅, Q9 (Content Explorer v2) ✅, Q10 (Editor context panel) ✅ — all merged to `main`** · **next stage Q11 — Validation (WV-007/008/011)** · Source of truth: [.docs/audit/SPRINT_Q_EXECUTION_PLAN.md](.docs/audit/SPRINT_Q_EXECUTION_PLAN.md) + [SPRINT_Q_DEEP_AUDIT.md](.docs/audit/SPRINT_Q_DEEP_AUDIT.md) + [SPRINT_Q_RISK_REGISTER.md](.docs/audit/SPRINT_Q_RISK_REGISTER.md) + [SPRINT_Q_HANDOFF.md](.docs/audit/SPRINT_Q_HANDOFF.md) · ADRs `009` (strategic pivot), `010` (persistent job core), `011` (Project terminology), `012` (image/OCR security gate)

---

## 1. Documentation Map

Docs are the spec. Code follows docs. If code contradicts docs, ask first.

| Topic | Source of truth |
| --- | --- |
| User-facing: install, quickstart, commands | [README.md](README.md) |
| Module map, layer boundaries, data flow, cockpit UI conventions | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| CLI daily workflow, limitations, rules | [docs/CLI_WORKFLOW.md](docs/CLI_WORKFLOW.md) |
| Web cockpit usage (FastAPI, Jinja2 + HTMX, JSON API) | [docs/WEB_WORKFLOW.md](docs/WEB_WORKFLOW.md) |
| Provider setup, models, secret store | [docs/PROVIDER_AND_MODEL_CONFIG.md](docs/PROVIDER_AND_MODEL_CONFIG.md) |
| Import → segment → translate → QA → export flow | [docs/TRANSLATION_PIPELINE.md](docs/TRANSLATION_PIPELINE.md) |
| Runtime contract for Tauri (or any) host shell | [docs/SIDECAR_CONTRACT.md](docs/SIDECAR_CONTRACT.md) |
| Testing, regression, release, migration discipline | [docs/MAINTENANCE.md](docs/MAINTENANCE.md) |
| Architecture decisions (ADR `001`–`012`) | [docs/DECISIONS.md](docs/DECISIONS.md) · [docs/decisions/](docs/decisions/) |
| Active reference specs | [docs/PROMPT_DESIGN.md](docs/PROMPT_DESIGN.md) · [docs/SECURITY_AND_PERFORMANCE.md](docs/SECURITY_AND_PERFORMANCE.md) |
| RTK shell tooling rule | `C:\Users\transcend\.claude\RTK.md` |
| Global workflow template (this file follows it) | `C:\Users\transcend\.claude\WORKFLOW.md` |

**Audit & roadmap of record (`.docs/audit/`)** — the agent-independent planning set (2026-06-09 Council audit). **For the active Sprint Q, the four `SPRINT_Q_*` docs are the primary source of truth** — read them first:

| Doc | Purpose |
| --- | --- |
| [SPRINT_Q_EXECUTION_PLAN.md](.docs/audit/SPRINT_Q_EXECUTION_PLAN.md) | **★ Active execution plan** — staged Q0–Q12, per-stage scope/deps/files/risks/tests/acceptance/rollback |
| [SPRINT_Q_DEEP_AUDIT.md](.docs/audit/SPRINT_Q_DEEP_AUDIT.md) | **★ Evidence base** — WV-001..014 map, gap matrix G-01..15, findings QF-01..22 (file:line) |
| [SPRINT_Q_RISK_REGISTER.md](.docs/audit/SPRINT_Q_RISK_REGISTER.md) | **★ Risk register** — R-01..23 + per-stage-gate review rule |
| [SPRINT_Q_HANDOFF.md](.docs/audit/SPRINT_Q_HANDOFF.md) | **★ Cold-start handoff** — status, read order, branch advice, hard fences |
| [ROADMAP_REPLAN.md](.docs/audit/ROADMAP_REPLAN.md) | Roadmap of record: strict N → P → O → Q; Sprint Q acceptance |
| [SOURCEOFARCHITECTURE.md](.docs/audit/SOURCEOFARCHITECTURE.md) | Reconciled product spec (build-state annotated) — target Sprint Q builds against |
| [ISSUE_BACKLOG.md](.docs/audit/ISSUE_BACKLOG.md) | WV-001..014 with acceptance criteria |
| [PAGE_LAYOUT_BLUEPRINT.md](.docs/audit/PAGE_LAYOUT_BLUEPRINT.md) | Target page layouts (§0 shell, §1 dashboard, §10 hubs) |
| [WORKFLOW_BLUEPRINT.md](.docs/audit/WORKFLOW_BLUEPRINT.md) | Per-process Today/Target/Delta |
| [THE_COUNCIL_WEAVER_AUDIT.md](.docs/audit/THE_COUNCIL_WEAVER_AUDIT.md) | Original current-state map, pain verification, Top 10 fixes |
| [SPRINT_P_EXECUTION.md](.docs/audit/SPRINT_P_EXECUTION.md) | Sprint P task-level breakdown (closed; staging-discipline reference) |

> Retired docs (pre-reset specs, Phase A UI audit, MVP logs, Flask→FastAPI audits, RC1 reports, the prior `weaver_next_plan.md`, `ENGINEERING_STANDARDS.md`/`AI_SLOP_PREVENTION.md` — now absorbed into §4.2/§4.3) live in **git history** only.

---

## 2. Progress — Phase Schedule

### 2.1 Roadmap

Phases A–F + Sprints G–M shipped (v0.7.0). The forward roadmap is the **strict N → P → O → Q replan** ([ROADMAP_REPLAN.md](.docs/audit/ROADMAP_REPLAN.md)), governed by ADR `009`.

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
  → Sprint M — Image / OCR security gate   ✅
  → Sprint N — Tauri shell alpha           ✅
  → Sprint P — Workflow Coherence          ✅  (WV-001..006; O-gate green)
  → Sprint O — Production desktop          ✅
   → Sprint Q — Workspace v2 (cross-project) 🟡  ACTIVE
       Q0 planning              ✅  (deep audit + execution plan + risk register + handoff)
       Q1 identity + read layer ✅  (WV-010: migration v10 + project_discovery uuid + workspace_index)
       Q2 read-path hardening   ✅  (readonly reads, reset/migration relocation, EPUB-hash fix, error fragments, ui.py split)
       Q3 shell + dashboard     ✅  (global workspace shell + dashboard command center)
       Q4 queue hub             ✅  (global translation queue; stale_running distinct)
        Q5 resources             ✅  (cross-project glossary/character/style resources hub; read-only via workspace_resources)
        Q6 providers             ✅  (cross-project provider/model hub; explicit healthcheck; secrets names-only)
        Q7 export gate+ledger    ✅  (migration v11; Draft/Final gate; exports hub)
        Q8 analytics             ✅  (deterministic per-project analytics + dashboard rollup)
        Q9 explorer v2           ✅  (tabbed Content Explorer; segment listing; render-path hashing removed)
        Q10 editor panel         🟡  NEXT
        Q11 validation (WV-007/008/011) · Q12 cleanup + final gate  ⬜
```

Legend: ✅ complete · 🟡 active · ⬜ pending · 🚫 deferred/blocked

> Phase ordering is dependency-driven, not calendar. **N → P → O closed; Sprint Q active, Q1–Q4 merged.** Sprint Q is staged Q0–Q12 (one stage = one branch + one PR, not parallel) per [SPRINT_Q_EXECUTION_PLAN.md](.docs/audit/SPRINT_Q_EXECUTION_PLAN.md). **Roadmap (§2.1) = the plan; the active phase (§2.3) = the status. Do not conflate them.**

### 2.2 Reusable Phase Gate

Before starting any stage:

1. **Read** the active stage scope (§2.3) and its acceptance criteria.
2. **List** the stage's exit criteria (§2.4) in plain language.
3. **Verify** each with a concrete command, test, file check, or manual inspection.
4. **State** what is usable now, what is internal-only, what is not yet user-facing.
5. **If all pass** — update §2.1 / §2.3 / §2.4 / §2.5 + write a handoff note (§8).
6. **If any fails** — mark the row blocked, record the missing proof. Do not proceed.

> Required reminder: **"Check exit criteria first. No next stage until evidence exists. Explain the detail for manual inspection."**

### 2.3 Active Phase — Sprint Q (Workspace v2) 🟡 · Q1–Q9 ✅ merged · Q10 ✅ built · stage Q11 (Validation) next

**Sprint focus:** the cross-project Workspace command center plus per-project surfaces. The hardened read foundation (Q1+Q2), all hubs (Q3–Q7), deterministic analytics (Q8), **Content Explorer v2 (Q9)**, and **Editor Context Panel (Q10)** are built. **Next: Q11 Validation** (WV-007/008/011).

**Track(s) active:** T0 (docs — this update). Next stage Q11 — validation. Gated by T6/T7/T8 (see §6).

**Next:** Q11 validation → Q12 cleanup + final gate + sprint PR.

**Core premise (why Q is staged the way it is):** one project DB per project is the only source of truth for that project. Cross-project features need a **read-only cross-project read layer** — there is **no global mutable store without an ADR**. Q1 built stable identity (`projects.uuid`) + a read-only, mtime-cached, error-isolated `services/workspace_index.py`; Q2 hardened the existing read paths; Q3+ build hubs on that foundation.

**What is built (merged to `main`):**
- **Q1 — WV-010 identity + read layer** ✅ — migration v9→v10 (`projects.uuid`, rename-safe); `project_discovery` uuid + duplicate detection; `services/workspace_index.py` (read-only, mtime-cached, per-project error-isolated, budget-tested); grep-gate test. Shipped dark.
- **Q2 — Read-path & failure-visibility hardening** ✅ — `connect_readonly_database` on read paths; `reset_interrupted_segments`/migration off the read path; per-render EPUB hashing removed from Project Overview; swallowed approve/apply failures surfaced; `ui.py` split into `ui_admin`/`ui_candidates`/`ui_jobs`/`ui_qa`/`ui_queue`/`ui_review`/`ui_workspace` (PR-a mechanical, PR-b fixes).
- **Q3 — Global shell + dashboard** ✅ — `workspace.html` global shell + `dashboard.html` command center; `_workspace_grid`/`_workspace_sidebar` partials; `ui_workspace` router.
- **Q4 — Queue hub** ✅ — `queue_hub.html` cross-project translation queue (`stale_running` distinct); `ui_queue` router.
- **Q5 — Resources hub** ✅ — `services/workspace_resources.py` cross-project glossary/character/style resource summary; `ui_resources.py` router; `resources_hub.html` template; enabled in sidebar.
- **Q6 — Providers hub** ✅ — `services/workspace_providers.py` + `providers_hub.html` + `ui_providers` router; provider/model routing table, key presence by env-var **name** only, token totals, recent failures; health check is an explicit per-project POST (never on render); secret-leak regression test.
- **Q7 — Export gate + ledger + Exports hub** ✅ — migration v10→v11 (`export_history`, additive); `storage/export_history.py`; `services/export_gate.py` (Draft always allowed; Final + `require_clean` refuses on critical QA issues — advisory default preserved, ADR `008`); `services/export_ledger.py` (one row per artifact/attempt, service-written); `services/workspace_exports.py` + `/ui/exports` hub + `/ui/projects/{name}/exports` history.
- **Q8 — Deterministic analytics** ✅ — `services/project_analytics.py` (status/review/token/candidate/export-readiness/activity aggregates); `/ui/projects/{name}/analytics` page + Analytics sidebar item; dashboard "Workspace at a glance" rollup (pure aggregation over the cached index — zero extra DB reads); `workspace_index` entries carry token totals.
- **Q9 — Content Explorer v2** ✅ — `/ui/projects/{name}/volumes/{id}/structure` reframed as a tabbed Content Explorer (Structure · Segments · Assets · Metadata · Warnings) in `ui_explorer.py` + reworked `epub_preview.html`; new read-only `services/segment_listing.py` (chapter rail with status/review counts; filtered, paginated segment table). Render-path hardening: `status_for_volume` (source hashing) removed from render path — replaced by hash-free `snapshot_info`; `read_snapshot` opens readonly. No schema change.
- **Q10 — Editor Context Panel** ✅ — lazy-loaded per-segment context panel in `workspace.html` (HTMX fragment `partials/_workspace_context.html`); read-only `services/workspace_context.py` (glossary substring matching, character mentions, candidate list, history summary, deterministic warnings); explicit "Context" button per segment row; quick links to candidates/QA/reading preview. Zero provider/QA/hash calls on render. No schema change.

**Non-goals for Q10** (scope fence): no OCR, no provider expansion, no route rewrite, no SPA/Node, no external queue, no `desktop/` changes, no global mutable store, no candidate auto-generation (explicit button only), no auto-apply, no auto-review, no QA scan on workspace render.

**Sprint Q PR strategy:** one stage = one branch + one PR. Q5 branch `feat/workspace-resources-hub`. Q6–Q8 grouped on `feat/provider-export-analytics` (PR #41). Q9 branch `feat/content-explorer` (PR #42). Q10 branch `feat/workspace-context-panel`. **Sprint-level PR to `main` stays unopened until Q12 is green** (maintainer instruction 2026-06-10).

**Hard fences for all of Sprint Q** (full list in [SPRINT_Q_HANDOFF.md §6](.docs/audit/SPRINT_Q_HANDOFF.md)):
- **One project DB = the source of truth for that project. No global mutable store without an ADR.**
- **Gate B1 (extended):** no QA scan, no provider call, **and no source-file hashing** on any render/list/hub path.
- Read paths use `connect_readonly_database` only — never trigger migrations or `in_progress` reset on read.
- State writes go through services; CLI/web/UI routers never touch SQLite directly (permanent grep-gate).
- `read_epub()`/`DocumentIR` vs `ParsedEpub` — separate paths, never merge.
- Locked stack (§3) unchanged; in-process `JobRegistry` (ADR `010`) — no external queue/worker/SSE-fan-in; **no new runtime dependency.**
- `desktop/` is read-only for all of Q (smoke only at Q12).
- HTMX hooks (§4.2) and DB enum values are never renamed — presentation-mapped only.
- API keys via env vars or `~/.weaver/secrets.toml` only — never in config, logged, rendered, or in an SSE event.

### 2.4 Exit Criteria

> **MVP acceptance:** met & LOCKED (Sprint 9C, 2026-06-02), shipped as v0.7.0-rc.1. Phases A–F + Sprints G–M complete.

**Sprint N** (Tauri shell alpha) — **✅ CLOSED:** N1 double-click launch <5 s · N2 `/healthz` polled before window · N3 close kills sidecar, no orphan · N4 readable crash screen + both logs · N5 template diff = 0 · N6 full suite green.

**Sprint P** (Workflow Coherence) — **✅ CLOSED 2026-06-10:** P1/WV-001 candidate+draft generation · P2/WV-002 reading preview · P3/WV-003 review status+queue (schema v9) · P4/WV-004 navigation coherence · P5/WV-005 project overview (no QA-on-render) · P6/WV-006 status taxonomy · O-gate WV-001+WV-002 green.

**Sprint O** (Production Desktop) — **✅ COMPLETE 2026-06-10:** O1 portable `weaver-desktop.exe` · O2 version aligned 0.7.0 · O3 app identity + icons · O4 sidecar bundling plan documented · O5 smoke test green · O6 both logs to `%APPDATA%\Weaver\logs\` · O7 `docs/INSTALL_DESKTOP.md` · O8 `docs/MAINTENANCE.md` updated · O9 full gate green.

**Sprint Q** (Workspace v2) — each stage gated per §2.2:

> **Gate Q status: 🟡 IN PROGRESS — Q0 ✅ · Q1 ✅ · Q2 ✅ · Q3 ✅ · Q4 ✅ · Q5 ✅ · Q6 ✅ · Q7 ✅ · Q8 ✅ · Q9 ✅ · Q10 ✅ (all merged to `main`) · Q11 next · Q11–Q12 ⬜.**

- [x] Q0 — Planning: deep audit, execution plan Q0–Q12, risk register R-01..23, cold-start handoff.
- [x] Q1 — WV-010: migration v10 (`projects.uuid`, forward + idempotency tests); `project_discovery` uuid + duplicate detection; `workspace_index.py` read-only/mtime-cached/error-isolated/budget-tested; grep-gate; index consumed by zero routes (shipped dark).
- [x] Q2 — Read paths use `connect_readonly_database` only; reset/migration off read path; zero source-file hashing on render; approve/apply failures surfaced; `ui.py` split (zero behavior change); router-SQL grep-gate → zero.
- [x] Q3 — Global shell + dashboard command center on the hardened foundation; performance budget met; no SQLite in CLI/web layer.
- [x] Q4 — Cross-project queue hub (`stale_running` distinct); ADR `010` unviolated; no provider call / no hashing on render.
- [x] Q5 — Resources hub: cross-project glossary/character/style surfaced read-only via `workspace_resources`; within performance budget; no global mutable store; no source-file hashing on render; failure-visible per Gate B1.
- [x] Q6 — Providers hub: provider/model visible per project; health on explicit demand only; secrets names-only (rendered-HTML secret-grep regression test); zero provider calls on render (spy-tested); token totals + failure summaries.
- [x] Q7 — Export gate + ledger: migration v11 forward + idempotent; Draft always succeeds with criticals present; Final+require_clean refuses with explanation + Draft escape hatch; ledger row on success and failure; missing artifact renders "missing"; advisory default unchanged (ADR `008`); export fidelity suite green.
- [x] Q8 — Analytics: aggregates reconcile against direct DB queries on fixtures; zero QA/provider calls on render (spy-tested); rollup across ≥3 projects on dashboard; tokens-not-currency, current-state-not-time-series framing.
- [x] Q9 — Content Explorer v2: tabbed explorer (Structure/Segments/Assets/Metadata/Warnings) from one surface; segment list with status/review badges + editor jump links; zero reparse/hash/QA/provider on render (spy-tested); missing snapshot degrades safely (Segments tab DB-fed); image gate intact; "preview" naming resolved (SD-7).
- [x] Q10 — Editor context panel: lazy-loaded per-segment context panel (`partials/_workspace_context.html`); read-only `services/workspace_context.py` (glossary matching, character mentions, candidates, history, deterministic warnings); zero provider/QA/hash calls on render; no schema change.
- [ ] Q11 — Validation completion (WV-007/008/011; `error` tier only after ADR `013`).
- [ ] Q12 — Residual cleanup; conditional migration v12; **final gate green** — full suite + pyright 0 + ruff clean + `weaver --help` + `cargo check`/`cargo tauri build`; desktop smoke (≥3 projects, no orphans, both logs); security smoke (traversal rejected, zero key/token in logs/render, no cross-project path leak); performance smoke (index within budget @10 projects, zero render-time hashing). **Carry-forward decisions (from Q7–Q10):** `export_history.job_id` always NULL (registry generates the id after the runner closure — needs a small ADR-010-adjacent API change); v10 projects show `needs_upgrade` in the Exports hub until a writable open migrates them (release-note line); `volume_lifecycle` `exported` overlay — decide keep-deferred vs derive-from-ledger.
- [ ] Throughout: no new runtime dependency; one stage = one branch + one PR; **sprint PR opened only after Sprint Q is finished**.

### 2.5 Phase Log

Deep detail per entry lives in git history and linked docs.

| Phase / Sprint | Key ref | Tests | Status / Lesson |
|---|---|---|---|
| Foundation → Sprint M | Git history + ADRs `001`–`012` | 1043 / 4 | ✅ CLI + cockpit + persistent jobs + EPUB preservation + export fidelity + candidate review + image/OCR gate |
| Council Audit + replan | [.docs/audit/](.docs/audit/) | — | ✅ Audit + strict N → P → O → Q roadmap |
| Sprint N — Tauri Shell Alpha | `desktop/` | 1043 / 4 | ✅ CLOSED — runtime validated, build green |
| Sprint P — Workflow Coherence | [SPRINT_P_EXECUTION](.docs/audit/SPRINT_P_EXECUTION.md) | 1102 / 4 | ✅ CLOSED — WV-001..006; O-gate green. *Lesson:* per-project coherence precedes cross-project hubs |
| Sprint O — Production Desktop | `desktop/` + [INSTALL_DESKTOP](docs/INSTALL_DESKTOP.md) | 1102 / 4 | ✅ COMPLETE — portable 3.2 MB exe; PATH-dependency baseline; PyInstaller recommended for single-file |
| **Sprint Q — Workspace v2** | [SPRINT_Q_EXECUTION_PLAN](.docs/audit/SPRINT_Q_EXECUTION_PLAN.md) + [DEEP_AUDIT](.docs/audit/SPRINT_Q_DEEP_AUDIT.md) + [RISK_REGISTER](.docs/audit/SPRINT_Q_RISK_REGISTER.md) + [HANDOFF](.docs/audit/SPRINT_Q_HANDOFF.md) | Q9 ≈1317 / 4 | 🟡 ACTIVE — Q0✅ Q1✅ Q2✅ Q3✅ Q4✅ Q5✅ Q6✅ Q7✅ Q8✅ Q9✅ (all merged); **Q10 next**. *Lesson:* Gate B1 audits pay off — Q9 found and removed source hashing still living on the structure render path |

> Test counts are the last full-suite figure verified at each closed stage. Re-run the full suite at each stage gate; do not assume a count without running it.

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

1. Read this file first, then the relevant doc/ADR from §1. For the **active Sprint Q**: [SPRINT_Q_EXECUTION_PLAN.md](.docs/audit/SPRINT_Q_EXECUTION_PLAN.md) + [SPRINT_Q_DEEP_AUDIT.md](.docs/audit/SPRINT_Q_DEEP_AUDIT.md) (cold start: [SPRINT_Q_HANDOFF.md](.docs/audit/SPRINT_Q_HANDOFF.md)), against [SOURCEOFARCHITECTURE.md](.docs/audit/SOURCEOFARCHITECTURE.md) + [ROADMAP_REPLAN.md](.docs/audit/ROADMAP_REPLAN.md).
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
- One PR = one concern. No bundled refactor + feature. **One Sprint Q stage = one branch + one PR.**
- **Sprint Q (active):** build only the stage named in §2.3 / the execution plan, in order. The cross-project read layer is **read-only**; **no global mutable store without an ADR**; **no source-file hashing on any render path** (Gate B1 extended). Add a **Non-Goals** line per stage (see Q5 in §2.3) to fence scope.
- Out of scope for Q5 unless the stage names it: OCR, provider expansion, route rewrite, SPA/Node, external queue, `desktop/` changes, editing cross-project resources. Defer the sprint PR until all of Q is finished.

Build order for Q5: **T1 workflow (read-only resources journey)** → **T3 read-layer extension (`workspace_index`)** → **T2 HTMX hub surface** → **T6/T7/T8 validation** → **T0 docs + handoff**.

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

**Sprint Q track note:** every Q stage runs T0 (docs) + the build tracks it needs, always gated by T6/T7/T8. Q5 = T1 → T3 (read-layer) → T2 (hub UI) → T6/T7/T8 → T0. No T4 (no schema change in Q5); T4 returns at Q7 (migration v11).

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
