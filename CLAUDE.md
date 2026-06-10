# Weaver

Offline-capable, glossary-aware **JP→EN** light-novel translation workbench with a **CLI** and local **web cockpit** (web-cockpit-first development). **Not:** SaaS, consumer product, hosted service, complex SPA.

> **Status (2026-06-10):** v0.7.0 stable · Sprints A–M + **N, P, O all COMPLETE** (1102 tests / 4 skipped, pyright 0, ruff clean) · **Active: Sprint Q — Workspace v2** (cross-project command center) · **Q0 planning ✅ COMPLETE** (deep audit + execution plan + risk register + handoff) · **Q implementation ⛔ NOT STARTED** · next real stage **Q1 — WV-010** (project identity + cross-project read layer) · Sprint Q source of truth: [.docs/audit/SPRINT_Q_EXECUTION_PLAN.md](.docs/audit/SPRINT_Q_EXECUTION_PLAN.md) + [SPRINT_Q_DEEP_AUDIT.md](.docs/audit/SPRINT_Q_DEEP_AUDIT.md) + [SPRINT_Q_RISK_REGISTER.md](.docs/audit/SPRINT_Q_RISK_REGISTER.md) + [SPRINT_Q_HANDOFF.md](.docs/audit/SPRINT_Q_HANDOFF.md); roadmap of record: [.docs/audit/ROADMAP_REPLAN.md](.docs/audit/ROADMAP_REPLAN.md) · ADRs `009` (strategic pivot), `010` (persistent job core), `011` (Project terminology), `012` (image/OCR security gate)

---

## 1. Documentation Map

Docs are the spec. Code follows docs. If code contradicts docs, ask first.

**Product / reference docs (`docs/`):**

| Doc | Purpose |
|-----|---------|
| [README.md](README.md) | User-facing: install, quickstart, commands |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Module map, layer boundaries, data flow, cockpit UI conventions |
| [docs/CLI_WORKFLOW.md](docs/CLI_WORKFLOW.md) | CLI daily workflow, limitations, rules |
| [docs/WEB_WORKFLOW.md](docs/WEB_WORKFLOW.md) | Web cockpit usage (FastAPI, Jinja2 + HTMX, JSON API) |
| [docs/PROVIDER_AND_MODEL_CONFIG.md](docs/PROVIDER_AND_MODEL_CONFIG.md) | Provider setup, models, secret store |
| [docs/TRANSLATION_PIPELINE.md](docs/TRANSLATION_PIPELINE.md) | Import → segment → translate → QA → export flow |
| [docs/SIDECAR_CONTRACT.md](docs/SIDECAR_CONTRACT.md) | Runtime contract for Tauri (or any) host shell |
| [docs/MAINTENANCE.md](docs/MAINTENANCE.md) | Testing, regression, release, migration discipline |
| [docs/DECISIONS.md](docs/DECISIONS.md) · [docs/decisions/](docs/decisions/) | ADR index (`001`–`012`) + full ADR texts |
| Supplementary: [PROMPT_DESIGN.md](docs/PROMPT_DESIGN.md) · [SECURITY_AND_PERFORMANCE.md](docs/SECURITY_AND_PERFORMANCE.md) | Active reference specs |

**Audit & roadmap of record (`.docs/audit/`)** — the agent-independent planning set (2026-06-09 Council audit). **For the active Sprint Q, the four `SPRINT_Q_*` docs are the primary source of truth** — read them first:

| Doc | Purpose |
|-----|---------|
| [.docs/audit/SPRINT_Q_EXECUTION_PLAN.md](.docs/audit/SPRINT_Q_EXECUTION_PLAN.md) | **★ Active Sprint Q execution plan** — staged Q0–Q12, per-stage scope/deps/files/risks/tests/acceptance/rollback; Q2 = read-path hardening before hubs |
| [.docs/audit/SPRINT_Q_DEEP_AUDIT.md](.docs/audit/SPRINT_Q_DEEP_AUDIT.md) | **★ Sprint Q evidence base** — WV-001..014 inheritance map, gap matrix G-01..G-15, findings QF-01..QF-22 (file:line), security/perf/UX audits, docs-vs-code mismatches D-01..D-07 |
| [.docs/audit/SPRINT_Q_RISK_REGISTER.md](.docs/audit/SPRINT_Q_RISK_REGISTER.md) | **★ Sprint Q risk register** — R-01..R-23 + per-stage-gate review rule |
| [.docs/audit/SPRINT_Q_HANDOFF.md](.docs/audit/SPRINT_Q_HANDOFF.md) | **★ Sprint Q cold-start handoff** — status, read order, branch advice, hard fences, Q1 first-task checklist |
| [.docs/audit/ROADMAP_REPLAN.md](.docs/audit/ROADMAP_REPLAN.md) | Roadmap of record: strict N → P → O → Q (all of N/P/O complete; Q active); Sprint Q acceptance |
| [.docs/audit/SOURCEOFARCHITECTURE.md](.docs/audit/SOURCEOFARCHITECTURE.md) | Reconciled product spec (build-state annotated) — target spec Sprint Q builds against |
| [.docs/audit/ISSUE_BACKLOG.md](.docs/audit/ISSUE_BACKLOG.md) | WV-001..WV-014 with acceptance criteria (WV-010 = Sprint Q entry item) |
| [.docs/audit/PAGE_LAYOUT_BLUEPRINT.md](.docs/audit/PAGE_LAYOUT_BLUEPRINT.md) | Target page layouts (§0 global shell, §1 dashboard, §10 hubs) |
| [.docs/audit/WORKFLOW_BLUEPRINT.md](.docs/audit/WORKFLOW_BLUEPRINT.md) | Per-process Today/Target/Delta |
| [.docs/audit/THE_COUNCIL_WEAVER_AUDIT.md](.docs/audit/THE_COUNCIL_WEAVER_AUDIT.md) | Original current-state map, pain verification, council findings, Top 10 fixes |
| [.docs/audit/SPRINT_P_EXECUTION.md](.docs/audit/SPRINT_P_EXECUTION.md) | Sprint P task-level execution breakdown (closed; reference for staging discipline) |

> Retired docs (pre-reset specs, Phase A UI audit, MVP sprint/scope logs, Flask→FastAPI audits, completed phase plans, RC1 reports, design exploration, the prior `weaver_next_plan.md` Sprint G–O plan, `ENGINEERING_STANDARDS.md`/`AI_SLOP_PREVENTION.md` whose rules are now absorbed into §4.2/§4.3) are in **git history** only. The Sprint G–O detail is captured by the completed phase log (§2.5) + ADRs `009`–`012`; the forward plan is the audit roadmap above.

---

## 2. Progress

### 2.1 Roadmap

Phases A–F + Sprints G–M shipped (v0.7.0). The forward roadmap is the **strict N → P → O → Q replan** ([.docs/audit/ROADMAP_REPLAN.md](.docs/audit/ROADMAP_REPLAN.md)) produced by the 2026-06-09 Council audit, governed by ADR `009` and the audit findings.

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
  → Sprint N — Tauri shell alpha           ✅  (runtime validated, dependency pins fixed, design system integrated)
  → Sprint P — Workflow Coherence          ✅  (WV-001..006 complete; O-gate green)
  → Sprint O — Production desktop          ✅  (portable app path; smoke test green; docs/INSTALL_DESKTOP.md)
  → **Sprint Q — Workspace v2 (cross-project)** 🟡  ACTIVE — Q0 planning ✅; implementation ⛔ not started; next = Q1
       Q0 planning              ✅  (deep audit + execution plan + risk register + handoff)
       Q1 identity + read layer ⬜  ← NEXT (WV-010: projects.uuid migration v10 + read-only workspace_index)
       Q2 read-path hardening   ⬜  (readonly reads, reset/migration relocation, EPUB-hash fix, error fragments, ui.py split)
       Q3 shell + dashboard     ⬜  · Q4 queue · Q5 resources · Q6 providers · Q7 export gate+ledger · Q8 analytics
       Q9 explorer v2           ⬜  · Q10 editor panel · Q11 validation (WV-007/008/011) · Q12 cleanup + final gate
```

Legend: ✅ complete · 🟡 active · ⬜ pending · 🚫 deferred/blocked

> Phase ordering is dependency-driven, not calendar. **N → P → O are all closed; Sprint Q is active.** Sprint Q is the cross-project Workspace layer; it is staged Q0–Q12 (one stage = one branch + one PR, not parallel) per [.docs/audit/SPRINT_Q_EXECUTION_PLAN.md](.docs/audit/SPRINT_Q_EXECUTION_PLAN.md). **Hard ordering inside Q:** Q1 (WV-010 identity + read-only index) defines the correct read patterns; Q2 retrofits them (readonly reads, reset/migration relocation, no per-render EPUB hashing, visible failures); **no cross-project hub (Q3+) may be built on the un-hardened foundation.** Stage detail + acceptance per stage in the execution plan; cold-start orientation in [SPRINT_Q_HANDOFF.md](.docs/audit/SPRINT_Q_HANDOFF.md).

### 2.2 Reusable Phase Gate

Before starting any phase or stage:

1. **Read** the active phase scope (§2.3) and its acceptance criteria.
2. **List** the stage's exit criteria (§2.4) in plain language.
3. **Verify** each with a concrete command, test, file check, or manual inspection.
4. **State** what is usable now, what is internal-only, what is not yet user-facing.
5. **If all pass** — update §2.1 / §2.3 / §2.4 / §2.5.
6. **If any fails** — mark the row blocked, record the missing proof. Do not proceed.

> Required reminder: **"Check exit criteria first. No next phase until evidence exists. Explain the detail for manual inspection."**

### 2.3 Active Phase — Sprint Q (Workspace v2) 🟡 ACTIVE · Q0 planning ✅ · implementation ⛔ not started

> Sprints N → P → O are **all CLOSED**. **Sprint Q is the active phase**: the cross-project Workspace command center. **Stage Q0 (planning) is complete**; **no implementation has begun**. Next real stage is **Q1 (WV-010)**. Primary source of truth: [.docs/audit/SPRINT_Q_EXECUTION_PLAN.md](.docs/audit/SPRINT_Q_EXECUTION_PLAN.md) + [SPRINT_Q_DEEP_AUDIT.md](.docs/audit/SPRINT_Q_DEEP_AUDIT.md); cold-start: [SPRINT_Q_HANDOFF.md](.docs/audit/SPRINT_Q_HANDOFF.md).

**Core premise (why Q is staged the way it is):** one project DB per project is the only source of truth for that project. Cross-project features therefore need a **read-only cross-project read layer first** — there is **no global mutable store** without an ADR. So Q1 builds stable identity (`projects.uuid`) + a read-only, cached, error-isolated `workspace_index`, Q2 hardens the existing read paths to match, and only then (Q3+) are any hubs built.

**Sprint Q — staged scope (per [SPRINT_Q_EXECUTION_PLAN.md](.docs/audit/SPRINT_Q_EXECUTION_PLAN.md)):**
- **Q0 — Planning** ✅ COMPLETE — deep audit (QF-01..22, G-01..15), staged execution plan Q0–Q12, risk register R-01..23, cold-start handoff.
- **Q1 — WV-010 identity + read layer** ⬜ NEXT — migration v9→v10 adds `projects.uuid` (stable, rename-safe); extend `project_discovery` with uuid + duplicate detection; build `services/workspace_index.py` (read-only, mtime-cached, per-project error-isolated, budget-tested). **Ships dark — zero UI consumers.**
- **Q2 — Read-path & failure-visibility hardening** ⬜ — retrofit `connect_readonly_database` for all reads; relocate `reset_interrupted_segments`/migration off the read path; remove per-render EPUB hashing from Project Overview; surface swallowed approve/apply failures; mechanical `ui.py` split (PR-a) then fixes (PR-b). **No hub may be built before this is green.**
- **Q3–Q8 — Hubs** ⬜ — global shell + dashboard, cross-project queue (`stale_running` distinct), Resources, Providers, Export gate + ledger (migration v11; advisory stays default per ADR 008), Analytics.
- **Q9–Q11 — Per-project surfaces** ⬜ — Content Explorer v2, editor context panel, validation completion (WV-007 structure-QA join, WV-008 4 checks + ADR-013-gated `error` tier, WV-011 `qa_warnings` verdict).
- **Q12 — Cleanup + final gate** ⬜ — residual dead code, conditional migration v12, full validation matrix + desktop/security/perf smoke.

**Hard fences for all of Sprint Q (full list in [SPRINT_Q_HANDOFF.md §6](.docs/audit/SPRINT_Q_HANDOFF.md)):**
- **One project DB = the source of truth for that project. No global mutable store without an ADR.**
- **Gate B1 (extended):** no QA scan, no provider call, **and no source-file hashing** on any render/list/hub path.
- Read paths use `connect_readonly_database` only — never trigger migrations or `in_progress` reset on read.
- State writes go through services; CLI/web/UI routers never touch SQLite directly (Q2 enforces a permanent grep-gate).
- `read_epub()`/`DocumentIR` vs `ParsedEpub` — separate paths, never merge.
- Locked stack (§3) unchanged; in-process `JobRegistry` (ADR `010`) — no external queue/worker/SSE-fan-in; **no new runtime dependency.**
- `desktop/` is read-only for all of Q (smoke only at Q12).
- HTMX hooks (§4.2) and DB enum values are never renamed — presentation-mapped only.
- API keys via env vars or `~/.weaver/secrets.toml` only — never in config, logged, rendered, or in an SSE event.
- One stage = one branch + one PR; **PR for the whole sprint stays unopened until Sprint Q is finished** (per maintainer instruction 2026-06-10).

### 2.4 Exit Criteria

> **MVP acceptance:** met & LOCKED (Sprint 9C, 2026-06-02), shipped as v0.7.0-rc.1. Phases A–F + Sprints G–M complete.

**Sprint N exit criteria** (Tauri shell alpha):

> **Gate N status: ✅ CLOSED — runtime validated, build green.**

- [x] N1 — Double-click launch starts backend + UI within 5 s on the maintainer's machine.
- [x] N2 — `/healthz` polled before the window opens.
- [x] N3 — Window close kills the sidecar; no orphan `weaver` process in the OS process list.
- [x] N4 — Backend failure surfaces a readable crash screen; cockpit `runtime.log` + host `sidecar.console.log` land in `logs_dir`.
- [x] N5 — No external browser dependency; **template diff = 0** vs Sprint M end (no UI rewrite).
- [x] N6 — Gate green: full suite **1102 / 4 skipped**.

**Sprint P exit criteria** (Workflow Coherence) — executed per [docs/SPRINT_P_EXECUTION_PLAN.md](docs/SPRINT_P_EXECUTION_PLAN.md):

> **Gate P status: ✅ CLOSED 2026-06-10 — all exit criteria satisfied.**

- [x] P1/WV-001 — Candidate/draft generation in cockpit: `ui_candidate_generate`, `ui_draft_generate` routes; segment-editor + drafts-page buttons; HTMX re-render; non-destructive invariant enforced.
- [x] P2/WV-002 — Reading Preview: `reading_preview_for_chapter/volume` service (no file writes); `reading_preview.html` with Reading + Before/After modes; publishable rule mirrors export.
- [x] P3/WV-003 — Review status + queue: Schema v8→v9 additive migration (`segments.review_status`); `segment_review.py` service; Review Queue UI with filters; orthogonal to translation status.
- [x] P4/WV-004 — Navigation coherence: Dashboard label fix; Jobs sidebar; duplicate subnav removed; Dashboard breadcrumb root on all child pages; back-button consistency.
- [x] P5/WV-005 — Project Overview: `project_overview.py` cheap-count service; overview cards + volume-grid + next-actions + review counts; no QA-on-render (Gate B1).
- [x] P6/WV-006 — Status taxonomy: `status_labels.py` helper; dead `reused/tm/memory` branches removed; canonical labels across editor/tree/QA.
- [x] **O-gate:** WV-001 + WV-002 both tested and passing; no regression in 1102 tests.
- [x] Full suite: **1102 passed / 4 skipped**; pyright 0; ruff check + format clean; `weaver --help` validates; no new runtime dependency.

**Sprint O entry gate (hard):** WV-001 + WV-002 MUST be complete and gate-green before Sprint O begins. `N → O` directly is forbidden. **Sprint P now satisfies this gate.** Sprint O additionally requires Sprint N runtime validation (Rust + MSVC toolchain). **Both gates GREEN — Sprint O is COMPLETE.**

**Sprint O exit criteria** (Production Desktop Packaging):

> **Gate O status: ✅ COMPLETE 2026-06-10 — portable app path validated, smoke test green, docs written.**

- [x] O1 — `cargo tauri build` produces `target/release/weaver-desktop.exe` (portable, ~3.2 MB).
- [x] O2 — Version aligned: `tauri.conf.json` + `Cargo.toml` = 0.7.0 (matches `pyproject.toml`).
- [x] O3 — App identity: product name "Weaver", production icons (ink hand + gold/green fate-web), `dev.weaver.desktop` identifier.
- [x] O4 — Sidecar bundling plan documented: PATH dependency for Sprint O baseline; PyInstaller recommended for single-file distribution; ADR-level evaluation recorded in `docs/INSTALL_DESKTOP.md`.
- [x] O5 — Smoke test: launch → `/healthz` 200 → `/ui` 200 → static assets served → graceful close → no orphans (real desktop environment).
- [x] O6 — Logs: `sidecar.console.log` + `runtime.log` both written to `%APPDATA%\Weaver\logs\`.
- [x] O7 — Documentation: `docs/INSTALL_DESKTOP.md` covers prerequisites, build steps, smoke test, troubleshooting, known limitations.
- [x] O8 — Maintenance: `docs/MAINTENANCE.md` updated with desktop packaging validation section and regression checklist.
- [x] O9 — Full gate: **1102 passed / 4 skipped**; pyright 0; ruff check + format clean; `weaver --help` validates; no new runtime dependency.

**Sprint Q exit criteria** (Workspace v2) — executed per [.docs/audit/SPRINT_Q_EXECUTION_PLAN.md](.docs/audit/SPRINT_Q_EXECUTION_PLAN.md), each stage gated per §2.2:

> **Gate Q status: 🟡 IN PROGRESS — Q0 planning ✅ complete; Q1–Q12 implementation ⛔ not started.**

- [x] Q0 — Planning complete: deep audit, execution plan (Q0–Q12), risk register (R-01..23), cold-start handoff — all four `.docs/audit/SPRINT_Q_*` docs landed.
- [ ] Q1 — WV-010: migration v10 (`projects.uuid`, forward + idempotency tests); `project_discovery` uuid + duplicate detection; `services/workspace_index.py` read-only/mtime-cached/error-isolated/budget-tested; grep-gate test added; **index consumed by zero routes**.
- [ ] Q2 — Read paths use `connect_readonly_database` only; `reset_interrupted_segments`/migration off the read path; zero source-file hashing on any render; approve/apply failures surfaced; `ui.py` split (zero behavior change); router-SQL grep-gate → zero.
- [ ] Q3–Q8 — Hubs built only on the hardened foundation: global shell + dashboard, cross-project queue (`stale_running` distinct), Resources, Providers, Export gate + ledger (migration v11; advisory default preserved), Analytics — each within performance budget, no SQLite in CLI/web layer, ADR 010 unviolated.
- [ ] Q9–Q11 — Content Explorer v2; editor context panel; validation completion (WV-007/008/011; `error` tier only after ADR 013).
- [ ] Q12 — Residual cleanup; conditional migration v12; **final gate green** — full suite + pyright 0 + ruff clean + `weaver --help` + `cargo check`/`cargo tauri build`; desktop smoke (≥3 projects, no orphans, both logs); security smoke (traversal rejected, zero key/token in logs/render, no cross-project path leak); performance smoke (index within budget @10 projects, zero render-time hashing).
- [ ] Throughout: no new runtime dependency; one stage = one branch + one PR; **sprint PR opened only after Sprint Q is finished**.

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
| Post-F Pivot (ADR 009–011) | ADRs `009`–`011` | — | ✅ Sprint G–O roadmap replaces npm wrapper |
| Sprint G — Runtime | `feat/FastAPI-stability-Tauri-ready` | 879 / 4 | ✅ Endpoints, env modes, logging, sidecar contract |
| Sprint H — Lifecycle | `feat/lifecycle-persistentjob-contract` | 904 / 4 | ✅ Volume lifecycle, delete controls, event logging |
| Sprint I — Persistent Jobs | `feat/lifecycle-persistentjob-contract` | 929 / 4 | ✅ JobRegistry, cold-start recovery, SSE resume |
| Sprint J — EPUB Snapshots | `feat/preservation-parser-hardening` | 973 / 4 | ✅ 6 snapshot tables, reparse job, epub-inspect CLI |
| Sprint K — Export Fidelity | `feat/export-fidelity` | 981 / 4 | ✅ Preflight, atomic write, fidelity report |
| Sprint L — Candidate Review | — | 1017 / 4 | ✅ Schema + apply + list UI (generation UI → Sprint P) |
| Sprint M — Image / OCR Gate | `feat/image-ocr-security` (PR #29) | 1043 / 4 | ✅ Preview gate (ADR `012`); OCR contract only |
| Council Audit + replan | [.docs/audit/](.docs/audit/) | — | ✅ Audit + roadmap (strict N → P → O → Q) |
| **Sprint N — Tauri Shell Alpha** | `desktop/` | 1043 / 4 | ✅ CLOSED — runtime validated, build green (dependency pins fixed, design system integrated) |
| **Sprint P — Workflow Coherence** | [SPRINT_P_EXECUTION](.docs/audit/SPRINT_P_EXECUTION.md) + [SPRINT_P_EXECUTION_PLAN](docs/SPRINT_P_EXECUTION_PLAN.md) | 1102 / 4 | ✅ CLOSED 2026-06-10 — all 6 WV items (P1–P6) complete; O-gate WV-001+WV-002 green; pyright 0; ruff clean; no new runtime dependency |
| **Sprint O — Production Desktop** | `desktop/` | 1102 / 4 | ✅ COMPLETE 2026-06-10 — portable app path (cargo tauri build → 3.2 MB exe); production icons; docs/INSTALL_DESKTOP.md; smoke test green; sidecar bundling plan (PyInstaller recommended for single-file); PATH dependency baseline |
| **Sprint Q — Workspace v2** | [SPRINT_Q_EXECUTION_PLAN](.docs/audit/SPRINT_Q_EXECUTION_PLAN.md) + [DEEP_AUDIT](.docs/audit/SPRINT_Q_DEEP_AUDIT.md) + [RISK_REGISTER](.docs/audit/SPRINT_Q_RISK_REGISTER.md) + [HANDOFF](.docs/audit/SPRINT_Q_HANDOFF.md) | 1102 / 4 | 🟡 ACTIVE — **Q0 planning ✅ COMPLETE** 2026-06-10 (deep audit QF-01..22/G-01..15, staged plan Q0–Q12, risk register R-01..23, cold-start handoff); **implementation ⛔ not started**; next = **Q1 (WV-010)** identity + read-only `workspace_index` |

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

- Read the relevant doc/ADR section first. Docs are authoritative. For the **active Sprint Q**, the forward spec is [.docs/audit/SPRINT_Q_EXECUTION_PLAN.md](.docs/audit/SPRINT_Q_EXECUTION_PLAN.md) + [SPRINT_Q_DEEP_AUDIT.md](.docs/audit/SPRINT_Q_DEEP_AUDIT.md) (cold start: [SPRINT_Q_HANDOFF.md](.docs/audit/SPRINT_Q_HANDOFF.md)), against the target [SOURCEOFARCHITECTURE.md](.docs/audit/SOURCEOFARCHITECTURE.md) + [ROADMAP_REPLAN.md](.docs/audit/ROADMAP_REPLAN.md).
- Respect sprint order. Run the §2.2 phase gate before starting a new sprint.
- Use exact names/values from docs for types, schemas, exit codes. Do not improvise.
- When unsure: ask. Do not invent fields, prompts, commands, or exit codes.
- Respect the active-phase stage order (§2.3). Stop at each stage gate (§2.2) for inspection.
- Before committing: scan the diff for AI attribution trailers, bot author metadata, or leaked credentials.

### 4.2 Code Rules (Non-Negotiable)

ADR `002`. (Absorbs the former `ENGINEERING_STANDARDS.md`; still-valid rules below.)

- **Types:** Type hints on every public function. Pyright basic must pass.
- **Modularity:** One concept per file. Split if >400 lines or >5 public functions. Functions >50 lines or >4 params need justification.
- **Naming:** Forbidden filenames: `utils.py`, `helpers.py`, `manager.py`. Avoid class names ending `Manager`/`Helper`/`Handler` unless they truly are that pattern. Name modules for their purpose.
- **No `**kwargs`** in public APIs. No bare `except:` or `except Exception:` outside the CLI/web boundary; never `except: pass`.
- **Errors:** All via `WeaverError` hierarchy (`src/weaver/errors.py`). User-facing errors include: what failed / likely cause / next command. Process-exit errors use the documented exit-code table (README / [SIDECAR_CONTRACT.md](docs/SIDECAR_CONTRACT.md)).
- **State discipline:** State writes go through services. CLI/web never touch SQLite directly. One segment translation = one transaction. Status transitions live in the same transaction as the data they describe (no separate "status updater").
- **Layer boundaries:** Shared/core is framework-agnostic (no web `Request`/`Response`, no DI wiring, no template/CLI output). Pydantic only at the web boundary. UI templates/routes carry no business logic.
- **API keys:** Env vars or `~/.weaver/secrets.toml` only — never in config, never logged, never rendered, never in an SSE event. Shell env wins. CI greps `provider.log` for zero keys.
- **Value types:** `@dataclass(frozen=True)` for value types. `pathlib.Path` for paths (never string-concat paths). Atomic writes (`tempfile` + `replace`) for valuable state.
- **Cockpit UI hooks (do not rename/remove):** `#tree`, `#ws-grid`, `#job-panel`, `#export-panel`, `#browser`, `#selected_source`, `#source_path`, `#qa-badge-status`, `#qa-issues`, `id="seg-{id}"`, and the `qa-badge-vol-*` / `qa-badge-ch-*` slots — HTMX swaps and UI tests depend on them. Design tokens have a single source: `api/static/app.css` `:root`. Details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
- **Tests:** Mirror source tree. Use `FakeProvider`, never live LLMs in CI. Fixtures = public-domain only (e.g. Aozora Bunko). Mock external boundaries only, never your own code.
- **Security (any PR touching I/O):** input parsed via pydantic (not raw dict chains); no user string to `os.system`/`subprocess(shell=True)`/`eval`/`exec`; cloud HTTPS only; malformed input handled without crashing. Performance budgets (init <30 s/200-ch; resume <5 s/10k seg; export <30 s/10k seg; <1 GB peak) — regressions >20% need justification.
- **Tech-debt prevention:** No stub functions "for later", no commented-out code, no single-caller abstractions, no config flag to defer a decision. Dead code deleted on sight (git is the archive). TODO/FIXME carries an issue + cleanup plan.
- **Git/PR:** Conventional Commits with scope (`feat(translate): …`); branches `feat|fix|docs|chore/<name>`; one PR = one concern (no bundled refactor + feature); no force-push to `main`. ADRs (`docs/decisions/NNNN-*.md`) capture decisions when made: Context / Decision / Consequences, one page.
- **Githooks:** `.githooks/` are mandatory local guardrails. Keep `git config core.hooksPath .githooks` enabled.

### 4.3 Anti-Slop

(Absorbs the former `AI_SLOP_PREVENTION.md`.) Weaver is AI-assisted but the LLM must be load-bearing infrastructure, never decoration.

- **No** "smart"/"AI-powered"/"magical"/"intelligent" feature names. No chat UIs, avatars, sparkles, fortune-cookie loaders, marketing language, telemetry/phone-home.
- **No prompt-wrapper features:** a new "mode" that only changes the system prompt is not a feature. Real features change the data flow, state machine, or workflow.
- A feature ships only if all six gates pass:
  1. **Real pain** — addresses a specific, evidenced user need ("would be cool" is not evidence).
  2. **Falsifiable spec** — acceptance criteria that pass or fail.
  3. **Deterministic where possible** — LLM only when determinism is impossible AND output is verifiable.
  4. **User can override** — every AI-produced artifact is editable/dismissable.
  5. **Failure visible** — failed AI output is marked and surfaced, never silently substituted or retried-forever.
  6. **Cost visible** — cloud cost is estimable/trackable, not hidden.
- No config flags for unbuilt features. No stub functions. No commented-out code. No abstractions with one caller.

### 4.4 Scope Discipline

- Build only what the active phase (§2.3) lists. Deferred/advanced items get no scaffolding "for later".
- One PR = one concern. No bundled refactor + feature. **One Sprint Q stage = one branch + one PR.**
- **Sprint Q (active):** build only the stage named in §2.3 / the execution plan, in order. **Q1 (read layer) and Q2 (hardening) precede every hub — no Q3+ surface on the un-hardened foundation.** The cross-project read layer is **read-only**; **no global mutable store without an ADR**; **no source-file hashing on any render path** (Gate B1 extended). Out of scope for Q unless its stage names it: OCR implementation, provider expansion, route rewrite, SPA/Node, external queue, `desktop/` changes (smoke only at Q12). Defer the sprint PR until all of Q is finished (per maintainer instruction 2026-06-10).
- Historical: Sprint N = Tauri shell alpha (sidecar lifecycle, no UI rewrite); Sprint P = per-project Workflow Coherence (WV-001..006); Sprint O = production desktop packaging; Sprint L = candidate-review + character-draft; Sprint M = image/OCR security gate (ADR `012`).

### 4.5 Communication

- Terse, technical. No filler, no apology, no marketing language.
- Reference files as `[name](path/file.md)` or `src/weaver/foo.py:42`. State decisions directly.
- Use concise Indonesian when the user writes in Indonesian.

### 4.6 Contribution Identity

> **Copy this section verbatim into every project CLAUDE.md. Do not modify.**

AI is a ghostwriter. Repository accountability remains with the human owner.

- Do not add `Co-Authored-By: Claude` or any AI/model co-author trailer to commits.
- Do not add "Generated with Claude Code" or equivalent tags to commit messages or PR bodies.
- Do not push commits with AI or bot author identity.
- Do not make AI appear in the GitHub contributor graph.
- Author and committer identity must be the repo owner's human identity configured for the project.
- If AI assistance needs to be disclosed, mention it only in normal prose in a PR description or changelog, never in git metadata.
