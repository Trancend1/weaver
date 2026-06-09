# Roadmap Replan — Path to Coherent Desktop (N → P → O → Q)

> **Status:** Accepted (maintainer, 2026-06-09). Supersedes the sequencing tail of the prior Sprint G–O plan (`docs/weaver_next_plan.md`, now retired to git history) from **Sprint N onward**. Sprints G–M are complete and unchanged.
> **Decision (user-confirmed, 2026-06-09):** **strict sequence N → P → O → Q** (not parallel). Sprint N (Tauri shell alpha) → Sprint P (Workflow Coherence) → Sprint O (production packaging) → Sprint Q (Workspace v2). **`N → O` directly is forbidden.** **Hard O-gate:** **WV-001 (Generate Candidate UI)** and **WV-002 (Reading Preview)** MUST be complete before Sprint O begins. Sprint P ≠ Workspace remake; Sprint P = workflow coherence. **Sprint Q stays high-level** until O is complete, WV-010 exists, and real desktop feedback is collected. Detailed Sprint P execution: [SPRINT_P_EXECUTION.md](SPRINT_P_EXECUTION.md).
> **Governing inputs:** [THE_COUNCIL_WEAVER_AUDIT](THE_COUNCIL_WEAVER_AUDIT.md), [WORKFLOW_BLUEPRINT](WORKFLOW_BLUEPRINT.md), [PAGE_LAYOUT_BLUEPRINT](PAGE_LAYOUT_BLUEPRINT.md), [ISSUE_BACKLOG](ISSUE_BACKLOG.md), [SOURCEOFARCHITECTURE](SOURCEOFARCHITECTURE.md). Reference ADRs `009`–`012`.
> **Reconciliation note:** `docs/weaver_next_plan.md` (HEAD) still reads "Sprint L active"; `CLAUDE.md` reads "Sprint M complete / Sprint N active." This replan treats **Sprint M as complete and Sprint N as next** — the `CLAUDE.md` state is authoritative.

---

## 1. Strategic direction

Weaver's most efficient path remains the locked strategy:

```text
HTMX-first → FastAPI-stable → Tauri-sidecar-ready → Tauri shell alpha → coherent workflow → production desktop
```

The audit adds one inserted step. Today the **backend is ready to package** but the **workflow is not coherent enough to package well** (no candidate generation in UI, no output preview, Review/Validation conflated, navigation triplicated). Packaging straight after the Tauri alpha (`N → O`) would ship those gaps to a distributable — so it is **forbidden**. The sequence spends **one focused sprint (P)** to close the workflow gaps *after* the low-risk Tauri alpha (N) and *before* production packaging (O).

**Five hard rules carried forward (unchanged):**
1. HTMX remains the UI — no SPA, no UI rewrite.
2. FastAPI is the only runtime/project/job/export boundary.
3. Tauri is a packaging shell over the existing cockpit — not a rewrite reason.
4. Long-running tasks stay backend-owned, persistent, refresh-safe (ADR 010, in-process SQLite — no external queue).
5. State writes go through services; templates carry no business logic; secrets via env/`secrets.toml` only.

---

## 2. Dependency map

```text
Sprint G  Runtime Contract                       ✅
Sprint H  Project/Volume Lifecycle (rename)       ✅
Sprint I  Persistent Job Core                     ✅
Sprint J  EPUB Preservation Snapshot              ✅
Sprint K  Export Fidelity Integration             ✅
Sprint L  Candidate Review + Character Draft       ✅ (schema+apply+list UI; generation UI deferred → P)
Sprint M  Image Preview / OCR Gate (ADR 012)       ✅ (preview+gate; OCR contract only)
  → Sprint N  Tauri Shell Alpha            (packaging-only; desktop/; template-diff = 0)
  → Sprint P  Workflow Coherence           (audit P0/P1; ★ WV-001 + WV-002 are the O-gate)
  → Sprint O  Production Desktop Packaging (BLOCKED until P's O-gate passes; N→O forbidden)
  → Sprint Q  Workspace v2 (cross-project) (post-O; high-level only until O + WV-010 + desktop feedback)
```

**Strict order, not parallel.** Execute one sprint at a time: N, then P, then O, then Q. Sprint N is a `desktop/` subtree that consumes the *existing* runtime contract and keeps **template diff = 0**; Sprint P then changes templates/routes inside `src/weaver/`. Doing N first de-risks the desktop path with zero cockpit churn, then P makes the cockpit coherent on a stable base.

**The hard O-gate.** Sprint O (which bundles a sidecar binary into a packaged build) **must not start** until **WV-001 (Generate Candidate UI)** and **WV-002 (Reading Preview)** are complete and gate-green. `N → O` directly is forbidden: packaging a desktop build whose review loop cannot generate candidates and cannot preview translated output ships a broken product. Re-cutting a packaged build later to absorb these is the expensive path — land them in P, package once.

---

## 3. Sprint breakdown

Each sprint: **Goal · In-scope · Out-of-scope · Deliverables · Acceptance · Validation checkpoint.** Sprints N/O carry the intent of the retired plan (the audit does not alter them); P and Q are new. **Sprint P has a full task-level execution breakdown for agent handoff in [SPRINT_P_EXECUTION.md](SPRINT_P_EXECUTION.md).**

### Sprint N — Tauri Shell Alpha *(first; runs now)*
- **Goal.** Prove Weaver runs as a Tauri desktop shell over the existing FastAPI sidecar, no UI rewrite.
- **In-scope.** Minimal Tauri workspace in `desktop/`; start sidecar (`weaver serve --env desktop --host 127.0.0.1 --port 0`); poll `/healthz`; open WebView; send `X-Weaver-Session`; pipe sidecar logs to `logs_dir/runtime.log`; clean shutdown (SIGTERM→5s→SIGKILL); crash screen on backend-start failure.
- **Out-of-scope.** Installers, signing, auto-update, Rust bridge, any UI change.
- **Deliverables.** `desktop/` Tauri project + `docs/SIDECAR_CONTRACT.md` conformance.
- **Acceptance.** Double-click launch < 5 s; `/healthz` polled before window; window-close kills the sidecar (no orphan process); backend failure → readable crash screen; **template diff = 0** vs Sprint M end.
- **Validation checkpoint.** Manual launch on the maintainer's machine + process-table check; existing test suite still green.

### Sprint P — Workflow Coherence *(new; the audit's core)*
- **Goal.** Make the cockpit workflow coherent end-to-end so the production desktop wraps a complete product. Closes the audit's P0 + the highest P1/P2 issues.
- **Execution detail:** [SPRINT_P_EXECUTION.md](SPRINT_P_EXECUTION.md) — task-level breakdown for agent handoff (build order, reuse map, constraints, insights, per-item acceptance).
- **★ O-gate (mandatory before Sprint O):** **WV-001** (Generate Candidate UI) + **WV-002** (Reading Preview) MUST be complete and gate-green. The remaining items are strongly recommended before O but may trail into a P.2 follow-up; WV-001/002 are non-negotiable.
- **In-scope (issue → blueprint):**
  - **WV-001 (P0)** Candidate + character-draft **generation in the cockpit** (segment row + Candidates/Drafts pages). [WORKFLOW §5, PAGE §4–5]
  - **WV-002 (P1)** **Reading Preview** (translated flow + Before/After) reusing export renderers, no file write. [WORKFLOW §7, PAGE §7]
  - **WV-003 (P1)** Persisted per-segment **review status** + a **Review Queue**; keep Validation distinct. [WORKFLOW §5–6, PAGE §5–6]
  - **WV-004 (P1)** **Navigation unification** (global Workspace sidebar shell + contextual panel; fix Dashboard/Projects label; drop subnav duplication). [PAGE §0]
  - **WV-005 (P1)** **Project Overview** (summary/progress/health/quick-actions). [PAGE §2]
  - **WV-006 (P1)** Single **status taxonomy** across DB/API/UI; remove dead status branches. [SOURCEOFARCHITECTURE §Status]
  - **WV-007 (P2)** Join **structure validation** into the QA report. [WORKFLOW §6]
  - **WV-008 (P2)** Missing checks + `error` tier. [WORKFLOW §6]
  - **WV-013 (P3)** Editor **context panel** (rides WV-001 + WV-006). [PAGE §4]
- **Out-of-scope.** Cross-project Workspace hubs (Queue/Resources/Providers/Exports/Analytics — Sprint Q); OCR implementation (ADR 012 gate C); project-id refactor (WV-010, Sprint Q); export-history ledger (WV-009 → split: gate toggle here, ledger in Q); any UI framework change.
- **Deliverables.** Generation UI; Reading Preview + Before/After surfaces; `review status` migration + Review Queue; reconciled navigation shell + Project Overview; status taxonomy doc + label alignment; QA structure category + new checks.
- **Acceptance (per issue, see [ISSUE_BACKLOG](ISSUE_BACKLOG.md)).** Plus the **§2.2 phase gate**: full suite green, pyright 0, ruff + format clean, clean wheel build; **no new runtime dependency**; **all migrations forward + idempotency tested**; secrets never logged/rendered (regression test stays green).
- **Validation checkpoints (staged).**
  - P1: generate→list→approve→apply works through UI routes (test).
  - P2: Reading Preview renders translated output with zero disk writes (test asserts no file created).
  - P3: review-status migration forward+idempotent; Review Queue reflects status within one HTMX swap.
  - P4: navigation has no duplicated entry; label/title agree (UI test).
  - P5: status taxonomy mapping documented; no template references an impossible status (grep test).
  - P6: QA report includes a `structure` category at novel scope without re-parsing (reads snapshot).
  - P7: final gate (above) → Sprint O may package.

### Sprint O — Production Desktop Packaging *(entry BLOCKED until Sprint P's O-gate passes; `N → O` forbidden)*
- **Goal.** Promote the Tauri alpha to a candidate distribution build wrapping the coherent (post-P) cockpit.
- **Entry condition (hard).** WV-001 + WV-002 complete and gate-green; Sprint N acceptance met; Sprint P final gate green. Do not begin O before this.
- **In-scope.** Windows + macOS packaging; app icon/name/version; bundle sidecar (PyOxidizer-or-equivalent, O-stage ADR); per-OS smoke build; `docs/INSTALL_DESKTOP.md`; `weaver doctor --bundle` (logs+version+config zip); release checklist in `docs/MAINTENANCE.md`.
- **Out-of-scope (unless opened by ADR).** Auto-updater, code signing, notarization, cloud sync, multi-user/SaaS.
- **Acceptance.** Reproducible per-OS build; core workflow unchanged; smoke test passes on each OS.
- **Validation checkpoint.** Install + launch + run one import→translate→preview→export loop on each target OS.

### Sprint Q — Workspace v2 (cross-project) *(new; post-O)*
- **Goal.** Deliver the source-of-truth Workspace command-center and the remaining knowledge/output hubs.
- **In-scope.** **WV-010** stable project id + cross-project read layer (pre-req); Dashboard command-center (Translation Queue, Provider Health, Recent Activity); Workspace-level Resources (shared glossary/character/TM/templates/style guides); Providers hub (routing/cost/history/health); Exports hub + **WV-009** export-history ledger; **Analytics** (`sourceofarchitecture.md §19`); full **Content Explorer** (segment list + asset browser); **WV-011/WV-012/WV-014** cleanups + LN-fidelity spike.
- **Out-of-scope.** External queue/worker (locked); multi-user/SaaS; OCR beyond ADR 012 gates.
- **Acceptance.** Cross-project reads back the hubs within budget; no SQLite access added to CLI/web layers; ADR 010 unviolated; §2.2 gate green.
- **Validation checkpoint.** Dashboard shows live cross-project queue/health/activity on ≥3 projects; Analytics metrics reconcile against per-project DBs.

---

## 4. Core architecture decisions (carried + new)

| Decision | Choice | Rationale | ADR/issue |
|---|---|---|---|
| UI stack | Jinja2 + HTMX, no SPA | Locked; all new surfaces are partial swaps | ADR 004/007 |
| Job model | In-process SQLite-backed, single process | No external queue; refresh-safe | ADR 010 |
| Structure layer | `ParsedEpub` snapshot stays separate from `DocumentIR` | Don't merge translation + structure paths | weaver_next_plan §5 |
| Export gate | Advisory by default; **opt-in** Final block-on-critical | Honor "never silently block" + give a real Final gate | WV-009, ADR 008 |
| Review state | **New persisted axis** on segments | Human review must be trackable | WV-003 |
| Status model | **One taxonomy**, five axes (translation/review/validation/export/job) | Kill drift; one vocabulary DB→API→UI | WV-006, [SOURCEOFARCHITECTURE](SOURCEOFARCHITECTURE.md) |
| Validation | Deterministic only; **join structure into QA** | No LLM-judge; one report | WV-007/008, ADR 008 |
| Preview | **Reuse export renderer**, no file write | Cheapest path to output preview | WV-002 |
| Project identity | Introduce stable id + cross-project read layer **before** Workspace hubs | Per-project DB can't cheaply serve cross-project views | WV-010 |
| Desktop | Tauri sidecar shell; package after coherence | Package a stable, coherent product once | ADR 009 |

---

## 5. Sequencing summary

```text
1. Sprint N  Tauri alpha (desktop/, template-diff-0)             ← runs now
2. Sprint P  Workflow Coherence (src/weaver/ UI + API + storage)
   ★ O-GATE: WV-001 (Generate Candidate UI) + WV-002 (Reading Preview) MUST be complete
3. Sprint O  Production packaging          (BLOCKED until the O-gate passes; N → O forbidden)
4. Sprint Q  Workspace v2 (cross-project)  (high-level only until O + WV-010 + desktop feedback)
```

**Entry condition for O:** WV-001 + WV-002 complete and gate-green **and** Sprint N acceptance met **and** Sprint P final gate green.
**Entry condition for Q:** Sprint O shipped **and** WV-010 (cross-project read layer) designed **and** real desktop feedback collected. (Do not detail Sprint Q before this.)

---

## 6. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Skipping P and packaging straight after N (`N → O`) | Forbidden by the hard O-gate: Sprint O entry requires WV-001 + WV-002 complete and gate-green. N runs first in `desktop/` (template-diff-0); P then owns `src/weaver/` templates on a stable base. |
| Review-status migration drifts from real state | Status transitions live inside the same transaction as the service that changes the data (the H pattern); never a separate updater. |
| Status taxonomy churn breaks badges/tests | Land the taxonomy doc first; change UI labels via a presentation mapping where DB values are stable; grep-test for impossible statuses. |
| Reading Preview accidentally writes files | Renderer reuse must take an in-memory path; test asserts no artifact created. |
| Scope creep pulling Workspace hubs into P | Hubs are explicitly Sprint Q and depend on WV-010; P ships per-project surfaces only. |
| Roadmap docs keep disagreeing on active sprint | Phase-2 doc reconciliation makes `CLAUDE.md` + this replan the single active-sprint authority; the prior `weaver_next_plan.md` is retired to git history. |

---

## 7. Handoff notes

- **Build order (full detail in [SPRINT_P_EXECUTION §1](SPRINT_P_EXECUTION.md)):** WV-006 → **WV-001** → **WV-002** → WV-013 → WV-003 → WV-005 → WV-004 → WV-007/008. WV-006 first because Review/Preview/nav consume the status taxonomy; WV-001/002 early because they are the hard O-gate.
- **Reuse, don't rebuild:** generation services exist (`candidate_generation`, `character_draft`); preview can reuse `renderers/rendered_document`; QA can read the persisted snapshot for structure findings.
- **Don't touch:** the job model (ADR 010), the `ParsedEpub`/`DocumentIR` split, secret handling, the export atomic-write path — all are validated and out of P's scope except where an issue names them.
- **Every sprint exits via the §2.2 phase gate** with evidence appended to `CLAUDE.md §2.5`.
- **Source of truth for the target product:** [SOURCEOFARCHITECTURE](SOURCEOFARCHITECTURE.md) (build-state-annotated). Use it, not the original `docs/sourceofarchitecture.md` draft, for P/Q specs.
