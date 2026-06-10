# Sprint Q — Workspace v2 · Staged Execution Plan (Q0–Q12)

> **Audience.** A fresh agent (or human) executing Sprint Q with no memory of the planning conversation. Read [SPRINT_Q_DEEP_AUDIT](SPRINT_Q_DEEP_AUDIT.md) first — every `QF-xx` / `G-xx` / `WV-xxx` / `U-xx` / `D-xx` id below resolves there or in [ISSUE_BACKLOG](ISSUE_BACKLOG.md). Risk ids `R-xx` resolve in [SPRINT_Q_RISK_REGISTER](SPRINT_Q_RISK_REGISTER.md).
> **This is a plan, not an implementation.** Producing it changed no code. Sprint Q executes stage by stage; **do not advance a stage with a red gate.**
> **Restructure note.** The stage order is deliberately built around the audit's locked blockers: (1) the single-project-per-DB assumption hard-coded in 28 call sites, (2) raw SQL inside UI routers, (3) routers opening writable connections for reads, (4) read paths triggering migrations / `in_progress` resets, (5) Project Overview hashing source EPUBs on every render, (6) silently swallowed approve/apply failures, (7) WV-007/008/009/011/013 still open, (8) the global Workspace sidebar never scaffolded. Consequence: **Q1 = identity + read layer (WV-010), Q2 = read-path & failure-visibility hardening** — both land **before** any hub UI. Hubs follow (Q3–Q8), per-project surfaces after (Q9–Q11), residual cleanup + gate close the sprint (Q12).
> **Spec of record.** [SOURCEOFARCHITECTURE](SOURCEOFARCHITECTURE.md) (build-state annotated) · [ROADMAP_REPLAN](ROADMAP_REPLAN.md) §3 (Sprint Q acceptance) · [PAGE_LAYOUT_BLUEPRINT](PAGE_LAYOUT_BLUEPRINT.md) §0/§1/§10 · [WORKFLOW_BLUEPRINT](WORKFLOW_BLUEPRINT.md).
> **Cold-start companion.** [SPRINT_Q_HANDOFF](SPRINT_Q_HANDOFF.md).

---

## 0. Ground rules (apply to every stage — violating one fails the stage gate)

**Stack & scope (locked):**
- Jinja2 + HTMX only; HTMX vendored. No React/Vue/Node/build step, no SPA, no web fonts.
- **No new runtime dependency** (`uuid`, `hashlib` etc. are stdlib and fine). A new dep needs an ADR — none is planned inside Sprint Q.
- SQLite WAL, no ORM. In-process `JobRegistry` only (ADR 010) — no Celery/Redis/RQ/external queue/worker.
- No provider expansion. No OCR (ADR 012 gates stay closed). No cloud/SaaS/multi-user scope.
- `desktop/` untouched except Q12 smoke + audit notes.

**Layer & data rules:**
- One project DB stays the **only source of truth** for that project. **No new global mutable store.** The cross-project layer is **read-only**.
- The read layer uses `connect_readonly_database` (`storage/db.py:82`) **exclusively**. Never `connect_database` from any index/hub path (R-01).
- UI routers stay thin: call a `services/*` function, render a template. **Zero new raw SQL in `api/routers/`** (QF-02) — the existing violations are Q2 cleanup targets, not precedents. Grep-gate enforced from Q1 onward.
- State writes go through services in one transaction; status transitions live with their data.
- Secrets: env / `~/.weaver/secrets.toml` only — never in config, logs, render, or SSE. The session token never appears in URLs or logs (R-07).
- Migrations: forward-only, additive, idempotent, tested (forward + idempotency), mirrored in `schema.sql`, rollback note in `docs/MAINTENANCE.md`. **One migration-bearing stage in flight at a time** (R-15): v10 (Q1) → v11 (Q7) → v12 (Q11, only if chosen).

**Cockpit invariants:**
- Do not rename/remove HTMX hooks: `#tree`, `#ws-grid`, `#job-panel`, `#export-panel`, `#browser`, `#selected_source`, `#source_path`, `#qa-badge-status`, `#qa-issues`, `id="seg-{id}"`, `qa-badge-vol-*`, `qa-badge-ch-*` (R-16).
- Design tokens single source: `api/static/app.css` `:root`.
- **Gate B1, extended for Q:** no QA scan, no provider call, **and no source-file hashing** (QF-05) on any list/tree/overview/dashboard/hub render (R-08, R-09).
- UI copy/layout pinned by `tests/unit/api/test_ui_shell.py`, `test_ui_layout.py`, `test_ui_qa.py`, `test_ui_delete.py` — intentional changes update the test in the same PR.
- Errors via `WeaverError` (what failed / likely cause / next command). **No `except: pass`, no `suppress(HTTPException)` in new code** (QF-04, R-11).
- Contribution identity per CLAUDE.md §4.6 — no AI author metadata, no AI attribution trailers.

**Workflow:**
- One PR ≈ one stage (Q2 and Q12 are explicitly multi-commit; see there). Branch per stage from `main` after the previous stage merges (recommendation in [SPRINT_Q_HANDOFF](SPRINT_Q_HANDOFF.md)).
- Targeted validation per stage; the **full matrix only at Q12** and before any release-facing claim.

---

## 1. Stage map

```text
Q0   Audit & planning (this package)                                   ✅ docs-only
Q1   WV-010 — stable project id + cross-project read layer  [mig v10]  ★ entry; blockers 1
Q2   Read-path & failure-visibility hardening                          ★ blockers 2,3,4,5,6 (+ ui.py split)
Q3   Global Workspace shell + Dashboard command center                 blocker 8 (G-03/G-04)
Q4   Global Translation Queue                                          G-05
Q5   Workspace Resources hub                                           G-06
Q6   Provider hub                                                      G-07
Q7   Export gate (Draft/Final) + export-history ledger      [mig v11]  WV-009 (blocker 7)
Q8   Analytics (deterministic)                                         G-09
Q9   Content Explorer v2                                               G-10, QF-14
Q10  Translation Editor context panel                                  WV-013 (blocker 7)
Q11  Validation improvements                              [mig v12?*]  WV-007/008/011/014 (blocker 7)
Q12  Residual cleanup + docs reconciliation + FINAL GATE               QF-07/08/15, D-01..D-07
```
\* v12 only if the `qa_warnings` removal is chosen (SD-8).

**Hard sequencing rules.**
- **Q1 before any hub** (Q3–Q8 all consume the index). Do not build Dashboard/Queue/Resources/Providers/Analytics against ad-hoc `discover_projects` fan-outs.
- **Q2 before any new UI stage** — the hubs must be built on the hardened patterns, not alongside the broken ones.
- Migration stages are exclusive (R-15).
- Q9/Q10/Q11 are per-project and index-independent; they may be re-ordered after Q2 if priorities shift, but **never run two template-heavy stages at once** (`base.html`/`_sidebar.html` collisions — Q3 vs Q9/Q10).
- Q12 last, always.

**Q1 vs Q2 ordering note.** Q2 is technically independent of Q1 (it is per-project hygiene). Q1 stays first because WV-010 is the mandated Sprint Q entry item ([ROADMAP_REPLAN §3](ROADMAP_REPLAN.md)) and because Q1 *defines* the readonly/no-write patterns Q2 then retrofits. If the maintainer prefers to swap Q1↔Q2, nothing breaks — record the swap in CLAUDE.md §2.3.

---

## Q0 — Audit & planning *(complete)*

- **Goal.** Produce the handoff-safe planning package.
- **Deliverables.** [SPRINT_Q_DEEP_AUDIT](SPRINT_Q_DEEP_AUDIT.md) · this plan · [SPRINT_Q_RISK_REGISTER](SPRINT_Q_RISK_REGISTER.md) · [SPRINT_Q_HANDOFF](SPRINT_Q_HANDOFF.md).
- **Validation.** Docs-only diff (no `src/`, `tests/`, `desktop/` changes). **Acceptance:** ✅ on commit of this package.

---

## Q1 — WV-010: stable project identity + cross-project read layer  ★ ENTRY  [migration v10]

**Goal.** A stable, rename-safe project identity and a read-only, cached, error-isolated cross-project index that every later hub consumes — without violating one-DB-per-project, ADR 010, or the layer rules.

**Why this stage exists.** Blocker 1: the single-project assumption is hard-coded in **28 call sites** (QF-01) and identity has three drift-able sources with jobs keyed by name (QF-11). Every Q hub needs cross-project reads; without one shared, read-only, budgeted layer, each hub would fan out its own DB opens and inherit the write side-effects of QF-03. The Council called this the architectural ceiling (P-09); ROADMAP_REPLAN makes it the Q prerequisite.

**Dependencies.** None (first implementation stage). Defines patterns Q2 retrofits.

**In-scope.**
1. **Migration v9 → v10 (additive):** `projects.uuid TEXT` — `ALTER TABLE projects ADD COLUMN uuid TEXT`, backfill `uuid4()` per row, `CREATE UNIQUE INDEX IF NOT EXISTS idx_projects_uuid ON projects(uuid)`. Mirror in `schema.sql` (fresh DBs set uuid in `create_project`). Bump `SCHEMA_VERSION` to 10 (`storage/db.py:13`). Forward + idempotency tests.
2. **Identity exposure:** `DiscoveredProject` gains `uuid: str | None` (None = needs-upgrade DB); resolver `find_project_by_uuid(books_dir, uuid)`. **Duplicate-uuid detection** (directory-copy case): both entries flagged `identity_conflict` — never auto-regenerate (SD-1, R-17).
3. **Read layer:** new `services/workspace_index.py` (framework-agnostic):
   - `ProjectIndexEntry` (frozen dataclass): `uuid`, `name`, `schema_version`, `state` (`ready | needs_upgrade | locked | error | identity_conflict`), `error: str | None`, counts (volumes/chapters/segments/pending/translated/failed/stale + review buckets), `job_counts: dict[str, int]` (incl. `stale_running`), `last_activity: str | None`. Filesystem paths stay **internal** — route-facing models expose none (QF-20, R-03/R-05).
   - `build_workspace_index(books_dir, *, jobs, cache) -> WorkspaceIndex` — **readonly opens only**; per-project `try/except (WeaverError, sqlite3.Error)` → error entry (pattern: `project_discovery.py:53-61`); **schema-version guard** read the same way `apply_migrations` tracks it, *before* touching v9+ columns (QF-12, R-18) → `needs_upgrade` entry; **never auto-migrates**.
   - **No source-file hashing, no QA, no provider calls** (Gate B1 extension; QF-05). Snapshot status, if surfaced, comes from the stored `epub_snapshots` row only.
4. **Cache + invalidation (designed before any UI):** in-process read-through cache on `app.state`, keyed per project by `(project.toml mtime_ns, weaver.db mtime_ns, weaver.db-wal mtime_ns or 0)`, TTL fallback 5 s; missing paths drop entries (project delete → gone within one TTL window; R-04). No persistence, no global DB (R-12).
5. **Stale-running reconciliation rule:** a DB `running` row absent from the live `JobRegistry` is classified `stale_running` (QF-09, R-19); Q4 renders it as such.
6. **Perf budget + smoke:** `@pytest.mark.perf` test with 10 synthetic projects asserting warm index < 150 ms / cold < 750 ms (non-CI-gating; rerun at Q12; R-10).
7. **Leak-rule test:** route-facing summaries expose no absolute path (QF-20).

**Out-of-scope.** Any route/URL change (routes stay `{name}`; optional `/ui/p/{uuid}` → redirect alias only if trivial — SD-2); rewriting the 28 `_single_project_id` call sites (Q2 takes the router ones, Q12 the opportunistic rest); any hub UI; any writable index store; CLI changes.

**Files likely touched.** `storage/migrations.py` · `storage/schema.sql` · `storage/db.py` · `storage/projects.py` · `services/project_discovery.py` · **new** `services/workspace_index.py` · `tests/unit/storage/test_migrations.py` · **new** `tests/unit/services/test_workspace_index*.py` · `docs/MAINTENANCE.md`.

**Service/storage/API/UI impact.** New read-only service module; discovery dataclass extension; `create_project` gains uuid. **No API/UI change** (deliberately — the layer ships dark and proven before anything renders it).

**Data model impact.** +1 column, +1 unique index (v10). No enum changes, no new tables.

**Security risks.** R-03/R-05 (the index is the one place aggregating every project path on the machine — leak rule + internal-path discipline); R-17 (identity conflict mishandling could silently merge two projects' summaries). Mitigations in-stage: leak test, conflict entries.

**Performance risks.** R-10 (fan-out cost — mitigated by cache + budget test); R-18 (WAL readonly open failure on recovery-needed DBs — mitigated by per-project error isolation); R-09 (guarded by the no-hashing rule + test).

**Tests required.** Migration forward + idempotency; uuid backfill uniqueness; duplicate-uuid conflict entry; index over a books dir containing {healthy, locked (simulated via held writer), v8-schema fixture, corrupt file, deleted-mid-scan} → error isolation; cache invalidation on db mtime change; **no-write assertion** (db bytes/mtime unchanged after index build); leak rule; perf smoke (marked).

**Acceptance criteria** (mirrors WV-010 + ROADMAP Q):
- A stable id resolves a project independent of its display name (resolver test).
- Cross-project read returns project/volume/job summaries within budget on ≥3 real + 10 synthetic projects.
- **No SQLite access added to CLI/web layers**; ADR 010 unviolated; the index never writes (test-proven).
- One broken project never blanks the index (error-entry test).

**Validation checkpoint.** `uv run pytest -q tests/unit/storage/test_migrations.py tests/unit/services/test_workspace_index*.py` · `uv run pyright` · `uv run ruff check .`.

**Rollback/escape plan.** Migration is additive → rollback = ship nothing that reads `uuid` (column is inert). The index module has zero consumers until Q3 → deleting `services/workspace_index.py` reverts the stage. Record both in the PR + MAINTENANCE.

**Handoff notes.** Copy the readonly/error-entry patterns from `services/project_overview.py:80-86` and `services/project_discovery.py:53-61`. Do **not** copy `services/job_store.py:367` (`connect_database` in a loop — that is the recovery path, not a read path). The schema-version marker is owned by `storage/migrations.apply_migrations` — read it the same way that module does; do not invent a second mechanism.

---

## Q2 — Read-path & failure-visibility hardening  ★ BLOCKERS 2–6

**Goal.** Retire the audit's correctness blockers in existing code **before** any new surface is built on top of them: readonly reads, no migrations/resets on read, no silent failures, no per-render hashing, and a router layout that can absorb Q3–Q10 without merge chaos.

**Why this stage exists.** Blockers 2–6 are live defects, not style debt: every candidates-list render runs a schema migration and resets `in_progress` segments (QF-03 — a mid-job stomp); approve/reject/apply failures are invisible (QF-04 — anti-slop gate 5); the Project Overview hashes every source EPUB per render (QF-05); routers contain raw SQL the docs claim cannot exist (QF-02, D-01). Building six hubs on these patterns multiplies them by N projects. Hardening now also makes Q3–Q10 PRs smaller and reviewable.

**Dependencies.** Q1 merged (policy order; see the Q1↔Q2 swap note in §1). The grep-gates defined here become permanent.

**In-scope** (each item its own commit; one PR, or two split as a+b below):
- **PR-a — mechanical, zero behavior change:**
  1. **Split `api/routers/ui.py`** (≥1414 lines, QF-10, R-23) into focused routers — suggestion: `ui.py` (dashboard/project/import) · `ui_workspace.py` (editor/translate) · `ui_candidates.py` (candidates/drafts) · `ui_review.py` (review/preview) · `ui_jobs.py` (jobs) — re-included in `api/app.py:136-157`. No route path, name, or template change; **pinned UI tests must pass unmodified** (that is the proof of "mechanical").
- **PR-b — behavior fixes:**
  2. **Router SQL → services (QF-02):** extract the raw-SQL/list logic from `ui*.py:1067,1159,1229,1334,1414`-areas, `candidates.py:125-126,256-257`, `jobs.py:82,99`, `ui_qa.py:232-236` into `services/` read functions (e.g. `services/candidate_listing.py` or extensions of existing services). Routers become thin calls.
  3. **Readonly reads (QF-03/R-01):** every extracted read path uses `connect_readonly_database`. `snapshot_status` / `status_for_volume` / `image_preview._volume_source_path` reads (`epub_snapshot.py:222`, `epub_reparse.py:90`, `image_preview.py:155`) move to readonly or accept an injected connection.
  4. **Reset/migration relocation (R-02):** move `reset_interrupted_segments` out of `connect_database` (`db.py:48-79,132-145`) to explicit recovery points — serve startup (`recover_all_projects` already covers it) and CLI write-entry commands. Migration application stays in `connect_database` (write paths only, which is where it belongs). Document the behavior change in `docs/MAINTENANCE.md`. Add a regression test for the QF-03 race: a segment `in_progress` under a live job is **not** reset by a concurrent UI read.
  5. **Failure visibility (QF-04/R-11):** replace `except WeaverError: pass` (`ui.py:1074`) and the three `suppress(HTTPException)` blocks (`ui.py:1088,1098,1108`) with error fragments (reuse the `_job_error` pattern) so a failed approve/reject/apply renders an inline error. Update the pinned tests in the same commit.
  6. **Overview hashing fix (QF-05/QF-21/R-09):** `project_overview` stops calling `status_for_volume` per volume. Snapshot state renders from the stored `epub_snapshots` row + an `(mtime_ns, size)` fast-path; the full hash runs only behind the existing explicit reparse/staleness actions. Fix the module docstring (D-04). Reuse the already-open readonly connection (drop the extra per-volume opens).
  7. **Stale-source image preview (QF-06):** `image_preview.py` catches `OSError` → `WeaverError` ("source file moved; reattach or reparse"); test with a deleted source fixture.
  8. **Grep-gates (permanent, added to the test suite):** zero `conn.execute(`/`connect_database(` under `api/routers/`; zero `suppress(HTTPException)` / `except WeaverError: pass` under `api/routers/`.

**Out-of-scope.** Splitting `cli/main.py` / `readers/epub.py` / `api/jobs.py` (noted debt, not Q's concern); consolidating all 28 `_single_project_id` copies (only those the extractions touch — the rest is Q12-opportunistic); any new route, template, or feature; `raw_response_logging` (Q12); upload cap (Q12).

**Files likely touched.** `api/routers/ui*.py` (split + thinning) · `api/app.py` · new/extended `services/` read modules · `storage/db.py` · `services/{epub_snapshot,epub_reparse,image_preview,project_overview}.py` · `cli/main.py` (only the reset call-site relocation) · pinned UI tests · new regression tests · `docs/MAINTENANCE.md`.

**Service/storage/API/UI impact.** Services gain read functions; `storage/db.py` semantic change (no reset-on-open); routers shrink to adapters. UI behavior change is limited to **new error fragments** where failures were silent.

**Data model impact.** None.

**Security risks.** Low — this stage *reduces* attack/aggravation surface (no writable handles on read paths). Watch: error fragments must not leak file paths beyond the existing `WeaverError` message style (R-05).

**Performance risks.** Positive: removes per-render hashing (R-09) and redundant opens (R-10). Watch: the `(mtime_ns,size)` fast-path must not report "fresh" for an mtime-preserving overwrite — acceptable residual (full verification stays one explicit click away; documented).

**Tests required.** Pinned suites pass PR-a unmodified; QF-03 race regression; reset-relocation test (CLI entry still recovers crashed `in_progress`); approve-failure renders an error fragment (no silent path); overview render does zero source-file reads (spy/instrumented); deleted-source image preview → 422 not 500; both grep-gates.

**Acceptance criteria.** All grep-gates green; pinned UI tests green (updated only for intentional error-fragment copy); overview of a 10-volume project performs no source hashing (test-proven); a failed approve is visibly reported; full suite green (this stage touches wide surface — run it all).

**Validation checkpoint.** **Full** `uv run pytest -q` + pyright + both ruff modes (wide blast radius justifies the full run here, mid-sprint).

**Rollback/escape plan.** PR-a is revert-safe by construction. PR-b commits are item-scoped and individually revertible; item 4 (reset relocation) carries the MAINTENANCE note naming the single revert commit if a recovery regression surfaces.

**Handoff notes.** Item 4 is the only subtle one: `reset_interrupted_segments` currently doubles as crash recovery for **CLI** runs. Keep the reset at CLI write-entry commands and serve startup; drop it only from read opens. Item 1's split is the merge-conflict shield for the whole sprint — do it first, alone, and let it sit green before PR-b.

---

## Q3 — Global Workspace shell + Dashboard command center  ★ BLOCKER 8

**Goal.** The global chrome from [PAGE_LAYOUT §0](PAGE_LAYOUT_BLUEPRINT.md) — persistent Workspace sidebar (Projects · Queue · Resources · Providers · Exports · Settings), context bar, topbar **Active jobs** chip — and the Dashboard command-center blocks the Q1 index can already feed (Current Project · In Progress · Recently Completed · Recent Activity).

**Why this stage exists.** Blocker 8: Sprint P reconciled labels but never scaffolded the global shell (`base.html:21-25` is still Dashboard/New project/Config; audit G-04, U-01/U-02/U-12). Every later hub needs a home in stable navigation **before** it ships, or Q4–Q8 each re-touch `base.html` (R-16).

**Dependencies.** Q1 (index feeds the dashboard blocks) + Q2 (router split; hardened patterns).

**In-scope.**
1. Global sidebar (`base.html` + new `partials/_workspace_sidebar.html`): six entries; hubs not yet shipped render as **disabled** entries labeled "Workspace v2 — stage Qn" (no dead links, no fake pages). Sidebar structure identical on every page (SOURCEOFARCHITECTURE §4.1 rule); the per-project contextual panel (`partials/_sidebar.html`) stays.
2. Context bar (`partials/_context_bar.html`): Project › Volume › Chapter + stage + next action, fed from existing per-page context via `api/ui_context.py` (extend `global_layout`/`project_layout`/`workspace_layout` minimally).
3. Topbar **Active jobs** chip from the in-process `JobRegistry` only (zero DB; QF-22, U-03/U-04); links to the project jobs page until Q4's global queue exists.
4. Dashboard blocks from the index: Current Project (latest `last_activity` + continue link), In Progress, Recently Completed, Recent Activity; existing project grid stays as the Projects block; error-entry projects render as degraded cards (existing pattern, `dashboard.html:17-21`).
5. Extend `api/status_labels.py` to the **review axis** (QF-13) — labels only, enums unchanged.

**Out-of-scope.** Queue page (Q4) and all hub content (Q5–Q8); route renames; per-project tree changes; layout-mode redesign (the three `ui_context.py` modes stay); Queue/Provider Health dashboard tiles (arrive with Q4/Q6).

**Files likely touched.** `templates/base.html` · new `partials/_workspace_sidebar.html`, `_context_bar.html` · `templates/dashboard.html` · `api/ui_context.py` · `api/status_labels.py` · dashboard route in the split `ui.py` · `api/static/app.css` (tokens only) · `tests/unit/api/test_ui_shell.py`, `test_ui_layout.py`.

**Service/storage/API/UI impact.** Dashboard route consumes `workspace_index` through one service call; no storage change; biggest template diff of the sprint.

**Data model impact.** None.

**Security risks.** R-03/R-05: dashboard blocks render index summaries — leak-rule test from Q1 re-asserted against the rendered HTML (no absolute paths beyond `books_dir` itself). Disabled hub entries must not expose unimplemented routes.

**Performance risks.** R-08/R-09/R-10: the dashboard must render from the cached index only — no QA, no hashing, no per-render fan-out beyond the index call. Budget check rides the Q1 perf smoke.

**Tests required.** Updated shell/layout pinning tests (same PR); "sidebar identical across pages" assertion; disabled-hub entries have no `href` to nonexistent routes; chip renders 0/N from a seeded registry; dashboard degraded-state cards; rendered-HTML leak grep; permanent grep-gates still green.

**Acceptance criteria.** Every page shows the same global sidebar + context bar; the chip reflects a running job within one poll; the Dashboard answers "what was I doing" with a working continue link; no nav item duplicated (WV-004 holds); keyboard navigable, focus visible; usable at 390 px.

**Validation checkpoint.** `uv run pytest -q tests/unit/api/` + pyright + ruff; manual demo-to-self at 390 px.

**Rollback/escape plan.** Shell partials are include-gated — reverting two includes in `base.html` restores the old chrome; dashboard blocks degrade to the existing grid if the index call is reverted.

**Handoff notes.** This is the UI-test-churn magnet (Sprint P's P4 precedent — R-16). Keep it one PR, after Q2's split has settled. Do not grow hub placeholders into content "while you're in there" — each hub has its own gate.

---

## Q4 — Global Translation Queue

**Goal.** One read-only page answering "what is running / queued / failed / done across all projects" ([PAGE_LAYOUT §10](PAGE_LAYOUT_BLUEPRINT.md) Queue row), with the topbar chip linking to it.

**Why this stage exists.** U-03/U-04: concurrent work across a series is untrackable; jobs are visible only inside the owning project (`ui.py:250` route). G-05; ROADMAP Q names the cross-project queue explicitly.

**Dependencies.** Q1 (index job summaries + `stale_running` rule) + Q3 (shell entry + chip).

**In-scope.**
1. Index extension: per-project recent jobs (id, kind, status incl. `stale_running`, scope label, progress units, started/finished), bounded (last ~20 per project), readonly.
2. New route `GET /ui/jobs` (global layout) + `templates/jobs_hub.html`: grouped by state (Processing / Waiting / Stale / Failed / Recently completed), filters by project/kind; rows deep-link to the existing per-project job detail (`/ui/projects/{name}/jobs/{job_id}/detail`).
3. Activate the Queue sidebar entry; point the topbar chip here.
4. Live-ness via the existing HTMX poll pattern — **no SSE fan-in**; per-job SSE stays on the job detail page (ADR 010 single-process intact).

**Out-of-scope.** Cross-project job **submission**; cancel-from-hub (deep-link to the existing cancel — avoids a second cancel path; revisit post-Q); SSE multiplexing; priorities (none exist).

**Files likely touched.** `services/workspace_index.py` · the split `ui_jobs.py` · new `templates/jobs_hub.html` · `partials/_workspace_sidebar.html` · tests.

**Service/storage/API/UI impact.** Index read extension; +1 GET route; one template.

**Data model impact.** None.

**Security risks.** R-03: job rows carry `current_label`/`error_summary` strings — they are service-authored and key-free today; the leak grep extends to this page. No job mutation endpoints added.

**Performance risks.** R-10: bounded per-project job reads ride the cached index; poll interval reuses the existing pattern (no tighter loops). R-19: stale-running mislabeling — covered by the Q1 reconciliation rule + test.

**Tests required.** Hub lists jobs from ≥3 seeded projects; `stale_running` rendered distinctly from `running` (QF-09); an error-entry project degrades to a row, page still renders; poll fragment swaps preserve filters; no-write assertion holds with job reads.

**Acceptance criteria.** Cross-project queue visible on ≥3 projects (ROADMAP Q validation line); a job started in project A is visible from project B's context within one poll; stale-running is never shown as live.

**Validation checkpoint.** Targeted pytest (new hub tests + `test_ui_shell.py`); manual: start a batch translate in one project, watch hub + chip from another page.

**Rollback/escape plan.** Route + template + sidebar entry deletable as a unit; the index extension is inert without the page.

**Handoff notes.** Truth hierarchy for "running": in-memory `JobRegistry` first, DB rows second. Do not "fix" stale rows from the hub — recovery stays a startup concern (ADR 010).

---

## Q5 — Workspace Resources hub

**Goal.** Make per-project knowledge (glossaries, character DBs, translation memories, prompt templates, style guides) discoverable across the workspace and copyable between projects — **without** a shared mutable store.

**Why this stage exists.** G-06/U-06: a series split across projects re-enters the same canon per project; SOURCEOFARCHITECTURE §8.9→§17 names the hub. The premise rule (one DB per project, no global store) forces the copy-not-share design (R-12).

**Dependencies.** Q1 (counts via index) + Q3 (sidebar entry).

**In-scope.**
1. Index extension: per-project resource counts (glossary terms/candidates, characters, TM entries) — readonly counts only.
2. New route `GET /ui/resources` + `templates/resources_hub.html`: projects × resource counts, linking to the existing per-project pages.
3. **Copy service** `services/resource_copy.py` (framework-agnostic): glossary terms / characters / TM entries from project A → B. Explicit user action; **skip-on-conflict** (the UNIQUE constraints already enforce it — `schema.sql:96,107,122`) returning a copied/skipped report; one transaction on the **destination** DB; source opened readonly. (A project-DB write through a service is allowed — it is not a global store.)
4. Hub copy UI: source project → resource type → destination project → report fragment. No copy control renders for `needs_upgrade`/`error`/`identity_conflict` destinations.
5. Prompt templates & style guides: the built-in presets (`core/templates.get_template` — `light-novel`, `web-novel`, `aozora-classic`) listed **read-only** with descriptions. No user-authored template store (SD-3 — that would be a new mutable store → ADR, out of Q).

**Out-of-scope.** Shared/global stores; auto-sync; resource editing in the hub; template authoring; cross-project TM lookup during translation (changes the translation data flow — post-Q ADR if wanted).

**Files likely touched.** `services/workspace_index.py` · new `services/resource_copy.py` · new `api/routers/ui_resources.py` · new `templates/resources_hub.html` · sidebar partial · tests.

**Service/storage/API/UI impact.** New copy service (destination-write through existing storage accessors); +1 route + template.

**Data model impact.** None (existing tables/uniques).

**Security risks.** R-12 (the chief risk — scope fence is the mitigation); copy must not leak source paths into the destination (resources carry no paths today — keep it so).

**Performance risks.** R-10: counts ride the index. Copy of a large TM is O(entries) inside one transaction — bound the UI copy to resource-type granularity (no "copy everything" button) and report counts.

**Tests required.** Copy happy-path + conflict-skip report + destination rollback on mid-copy error; readonly-source assertion (source db mtime unchanged); hub renders ≥3 projects incl. an error entry; disabled-copy state for non-ready destinations; `protect_manual` TM semantics preserved (`services/translation_memory.py`).

**Acceptance criteria.** Every project's resource counts visible in one place; a glossary copy A→B yields an exact copied/skipped report; source bytes unchanged; no global store introduced.

**Validation checkpoint.** Targeted pytest (`test_resource_copy*`, hub tests) + pyright + ruff.

**Rollback/escape plan.** Hub route/template deletable; the copy service has no callers outside the hub.

**Handoff notes.** Reuse `storage/glossary.py` / `storage/characters.py` / `storage/translation_memory.py` accessors — no hand-written INSERTs where an accessor exists.

---

## Q6 — Provider hub

**Goal.** One surface answering: which provider/model does each project use, is it healthy (on demand), what failed recently, what has it consumed — with config safety preserved.

**Why this stage exists.** G-07/U-05: provider state is invisible (config form only); failures live inside job errors; token usage is persisted (`translations.input_tokens/output_tokens`, `schema.sql:68-70`) but never surfaced. SOURCEOFARCHITECTURE §8.9→§18.

**Dependencies.** Q1 (index) + Q3 (sidebar entry).

**In-scope.**
1. Index extension: per-project provider type + model (from `project.toml`, already parsed by `inspect_project`), failed-job count, token totals (`SUM(input_tokens), SUM(output_tokens)` readonly, cached with the entry).
2. New route `GET /ui/providers` + `templates/providers_hub.html`: routing table (project → provider/model); secret env-var **names** + set/unset state (reuse `core/secret_store.list_secret_names` + the `_secrets.html` pattern — values never rendered); recent failures (`jobs` rows `status='failed'` + `error_summary`); token usage per project/provider.
3. **Explicit health check:** per-project button → POST → `inspect_project(run_healthcheck=True)` (`services/project.py:243-266`) → `ProviderStatus` fragment (healthy/latency/message). **Never on render** (R-22; Gate B1 extension — provider calls cost money/quota).
4. Activate the Providers sidebar entry; `/ui/config` stays the editing surface (hub reads; config edits).

**Out-of-scope.** Currency cost estimates (tokens only — SD-4; anti-slop gate 6); provider failover/routing rules (no such engine exists; would need an ADR); editing provider config from the hub; new providers; bulk health checks.

**Files likely touched.** `services/workspace_index.py` · new `api/routers/ui_providers.py` · new `templates/providers_hub.html` · sidebar partial · tests.

**Service/storage/API/UI impact.** Read extensions + one POST (healthcheck) that reuses an existing service.

**Data model impact.** None.

**Security risks.** R-07 (the chief risk): the page renders provider config — values never rendered, names only; the rendered-HTML secrets grep becomes a permanent regression test here. `error_summary` strings are key-free (keys are read from env at call time and never embedded in `WeaverError` messages — keep it so).

**Performance risks.** R-22 (healthcheck = live provider call — explicit button only, one project per click); token SUM is O(translations) per project — cached with the index entry; no aggregate table (premature).

**Tests required.** Hub renders with `FakeProvider` projects; health button → status fragment (healthy + failing-config cases); **rendered page contains no secret value** (seed a fake secret, grep HTML); token sums match seeded attempts; zero provider calls on hub GET (FakeProvider call counter).

**Acceptance criteria.** All providers/models visible at a glance; health on demand; failures and token consumption per project visible; secrets names-only; zero provider calls on render.

**Validation checkpoint.** Targeted pytest + the secrets-grep regression + pyright + ruff.

**Rollback/escape plan.** Route/template/sidebar entry deletable; index extension inert.

**Handoff notes.** `ProviderStatus` already models healthy/latency/message — render it, don't re-derive.

---

## Q7 — Export gate (Draft/Final) + export-history ledger + Exports hub  *(WV-009, full)*  [migration v11]

**Goal.** Close WV-009: keep advisory-by-default export, add the **opt-in** "Final requires clean validation" gate, persist an **export-history ledger**, surface per-project history + a global Exports hub.

**Why this stage exists.** Blocker 7 (WV-009 open): preflight never blocks (`ui_qa.py:184-189`), no export status exists (`volume_lifecycle.py:18-23`), artifacts are findable only on disk (U-07, G-08). SOURCEOFARCHITECTURE §8.8 requires the gate + history; the Council resolution keeps advisory as default.

**Dependencies.** Q1 (hub reads via index) + Q3 (sidebar entry). Migration slot: v11 — **after** Q1's v10, exclusive (R-15).

**In-scope.**
1. **Migration v10 → v11 (additive):** `export_history` table — `id TEXT PK, volume_id INTEGER REFERENCES volumes(id), format TEXT, kind TEXT CHECK (kind IN ('draft','final')), status TEXT CHECK (status IN ('succeeded','failed')), qa_badge TEXT, artifact_path TEXT, byte_size INTEGER, job_id TEXT, version_label TEXT, created_at TEXT NOT NULL`. Mirror schema.sql; forward + idempotency tests; MAINTENANCE note.
2. **Ledger writer in the export service path** (`services/export_book.py` / export job completion): one row per artifact on success **and** failure, written by the service — never from a router.
3. **Draft/Final gate:** export UI gains Draft (default, always allowed) / Final; Final with the opt-in toggle refuses while unresolved `critical` QA issues exist, with an explanation + Draft escape hatch. Gate evaluation in a service reusing the preflight report; **advisory default unchanged** (ADR 008 honored; SD-5: per-run checkbox + optional `[export] final_requires_clean` project default).
4. Per-project Export history list from the ledger; rows show exists/missing via `stat` — **never serving artifact bytes** (downloads stay out of scope).
5. **Exports hub** `GET /ui/exports`: cross-project recent exports via index extension (readonly ledger reads). Activate sidebar entry.
6. Derived volume lifecycle may now surface `exported` **as a derived read of the ledger** — not a new persisted axis on volumes (`volume_lifecycle.py` deferral closes honestly).

**Out-of-scope.** Export settings beyond existing options; artifact downloads through the cockpit; retention/cleanup policies (post-Q note); changing the advisory default; bundling changes; CLI exporter changes (QF-15 is Q12 doc work).

**Files likely touched.** `storage/migrations.py` · `storage/schema.sql` · `storage/db.py` (v11) · new `storage/export_history.py` · `services/export_book.py` (+ job completion glue — prefer the service over `api/jobs.py`) · `api/routers/ui_qa.py` (preflight gains gate state) · export panel template(s) · new `templates/exports_hub.html` · new `api/routers/ui_exports.py` · `services/workspace_index.py` · `services/volume_lifecycle.py` · tests.

**Service/storage/API/UI impact.** New storage module + service writer + gate predicate; +1 hub route; export panel changes.

**Data model impact.** +1 table (v11).

**Security risks.** R-03/R-05: `artifact_path` is an absolute path — per-project pages may show it (it is the user's own output dir), the **global hub shows project-relative/basename forms** (leak rule). No byte serving (R-21 stays a data-integrity, not security, concern).

**Performance risks.** Ledger reads are tiny and indexed by insertion; `stat` per row is cheap; hub rides the cached index (R-10).

**Tests required.** Migration forward/idempotent; ledger row on success and failure; Draft always succeeds with criticals present; Final+toggle refuses with criticals, succeeds clean; ledger row carries the gating `qa_badge`; missing-artifact rendering; hub lists ≥3 projects; existing export fidelity suite stays green (atomic write untouched).

**Acceptance criteria** (mirrors WV-009): Draft export always succeeds; gated Final refuses with an explanation; history lists past artifacts with validation result; migration tested; export remains advisory by default.

**Validation checkpoint.** Targeted pytest (`test_migrations`, new export-history/gate tests, existing `test_export*`) + pyright + ruff.

**Rollback/escape plan.** Additive table is inert if the writer is reverted; the gate is opt-in, so default behavior is unchanged by construction.

**Handoff notes.** The preflight already computes everything the gate needs (`ui_qa.py:180-220`) — move the decision into a service; do not duplicate the report. Keep ADR 002 intact: the ledger writer lives in the service, not in `api/jobs.py` callbacks.

---

## Q8 — Analytics (deterministic)

**Goal.** Per-project and workspace-level **current-state** analytics from data that already exists: progress, review state, QA state (on demand only), provider/token usage, export readiness — no LLM, no invented numbers.

**Why this stage exists.** G-09: SOURCEOFARCHITECTURE §8.9→§19 names Analytics; the data is already persisted (status counts, `review_status`, token columns, Q7's ledger) but never aggregated.

**Dependencies.** Q1 (rollups via index) + Q7 (export readiness reads the ledger). QA-dependent metrics stay opt-in (Gate B1).

**In-scope.**
1. `services/project_analytics.py`: per-project aggregates — translation status breakdown; review-status breakdown; token usage per provider/model (`COALESCE` sums — old rows may be NULL); candidate/draft funnel (counts by status); export readiness (ledger + publishable-rule counts via `list_export_segment_states`); recent activity (jobs). **QA-dependent numbers only behind an explicit "Run validation" action.**
2. Per-project Analytics page/tab `GET /ui/projects/{name}/analytics` (project layout).
3. Workspace rollup as a Dashboard section (SD-6 — no new sidebar entry) from index extensions.
4. Honest framing: tokens not currency (SD-4); **current-state, not time-series** (no metrics history exists; `job_events` is an activity feed — the page says so).

**Out-of-scope.** Time-series/metrics persistence (new store → ADR territory); JS chart libraries (HTML/CSS bars only); QA-on-render; currency.

**Files likely touched.** New `services/project_analytics.py` · new template(s) · router addition (per the Q2 split layout) · `services/workspace_index.py` · tests.

**Service/storage/API/UI impact.** Pure read service + one page + a dashboard section.

**Data model impact.** None.

**Security risks.** Low; rollups are counts. Leak rule applies to any rendered project listing (R-03).

**Performance risks.** R-08 (no QA on render — test-enforced); token sums cached with index entries; per-project page computes on demand (acceptable: single project scope).

**Tests required.** Aggregates reconcile against seeded DB fixtures (ROADMAP Q acceptance: "metrics reconcile against per-project DBs"); zero QA/provider calls on render (spy); rollup degrades per error-entry project.

**Acceptance criteria.** Analytics numbers match direct DB queries on a fixture; zero provider/QA calls on render; rollup visible across ≥3 projects.

**Validation checkpoint.** Targeted pytest + pyright + ruff.

**Rollback/escape plan.** Pure read surfaces — deletable as a unit.

**Handoff notes.** Export readiness must reuse the exporter's publishable predicate (same rule reading preview mirrors — `services/reading_preview.py` docstring) — do not invent a third "publishable" definition.

---

## Q9 — Content Explorer v2

**Goal.** Promote the structure surface to the Content Explorer of [PAGE_LAYOUT §3](PAGE_LAYOUT_BLUEPRINT.md): volume tree + chapter list + **segment list** + asset browser + metadata + warnings as tabs; resolve the three-"preview" naming (QF-14).

**Why this stage exists.** G-10/U-09: jump-to-problem-segment requires detours; three surfaces share the word "preview" (`/ui/epub-preview`, `/structure`, `/preview` — `ui.py:142,498,594`). The snapshot already carries the data.

**Dependencies.** Q2 (router split; hardened read patterns). Index-independent — may be re-ordered among Q9–Q11.

**In-scope.**
1. Reframe the structure page (route `/ui/projects/{name}/volumes/{id}/structure`, template `epub_preview.html` — keep the filename, change titles/labels to limit churn) as **Content Explorer** with tabs: Structure (existing) · Segments (new) · Assets (existing inventory + gated previews) · Metadata (existing) · Warnings (existing).
2. **Segment list tab:** paginated per chapter; columns: order, kind, status badge, review badge, jump links (`Open in editor` → `workspace.html#seg-{id}`, `Preview` → reading preview chapter). Filters: status, review status, kind. Thin read service (`services/segment_listing.py` or an extension of `chapter_workspace`).
3. Per-node status badges in the volume tree (taxonomy labels — counts only).
4. Naming cleanup (SD-7): the global `/ui/epub-preview` re-titles as pre-import "Inspect a source" reachable from `/ui/new` (no global nav entry) — the word "preview" stops meaning three things.
5. Reading-preview cross-link ("View as reader").

**Out-of-scope.** New byte endpoints (the Sprint M gate is the only image server); editing from the explorer; furigana rendering promises (WV-014 is Q11's spike); OPF/manifest editing.

**Files likely touched.** `templates/epub_preview.html` · split router module · new `services/segment_listing.py` · new `partials/_segment_list.html` · tests (`test_ui_layout.py` + new).

**Service/storage/API/UI impact.** One read service; tab-level template work; no new routes beyond fragments.

**Data model impact.** None.

**Security risks.** Asset tab must reuse the ADR 012 image gate untouched (`projects.py:570`); no raw archive-path access (the gate already rejects it — keep manifest-id keying).

**Performance risks.** Tabs render from the snapshot — assert **no re-parse on render** (spy on `parse_epub_structure`); segment list is paginated (no full-volume segment dumps).

**Tests required.** Segment tab pagination + filters; jump links resolve; no-reparse spy; legacy-route title/redirect test; pinned layout tests updated same PR.

**Acceptance criteria.** From one surface a user can: see reading order, list a chapter's segments with status/review badges, jump to a problem segment in the editor, browse assets safely, read metadata and warnings. Reading preview remains a distinct, linked surface.

**Validation checkpoint.** Targeted pytest + manual demo at 390 px.

**Rollback/escape plan.** Tab additions are template-scoped; the segment service has one caller.

**Handoff notes.** Snapshot (`read_snapshot`) feeds structure/assets/warnings; segments come from the project DB. `ParsedEpub` vs `DocumentIR` stay separate (locked invariant) — do not mix the paths.

---

## Q10 — Translation Editor context panel  *(WV-013)*

**Goal.** The editor's third column: detected glossary terms, characters present, AI candidates **with Generate** (WV-001 routes), history on demand, consistency warnings — lazy per segment focus ([PAGE_LAYOUT §4](PAGE_LAYOUT_BLUEPRINT.md)).

**Why this stage exists.** Blocker 7 (WV-013 open): the editor is still 2-column (`workspace.html`); translators leave it for every resource lookup (U-10). All data sources already exist as services; Sprint P's plan explicitly excluded this item from its core.

**Dependencies.** Q2 (split + patterns). Index-independent — re-orderable among Q9–Q11. Avoid running concurrently with Q3 (template collisions).

**In-scope.**
1. Right-column region in `workspace.html` (respect the `workspace` layout mode + ≤900/720 px responsive behavior; new layout marker pinned in `test_ui_layout.py`).
2. HTMX fragments per **active segment** (loaded on focus, never eagerly): glossary terms (deterministic substring/normalized match — same family as `qa.checks.check_glossary_mismatch`); characters in segment; candidates list (reuse `_candidates_list.html` + the WV-001 generate route); history (`services/segment_history`, existing on-demand fragment); consistency warnings (`qa/consistency_checks` scoped to the one segment).
3. **Batch candidate generation (SD-10, optional):** "Generate for chapter" as a `JobRegistry` job looping `generate_candidate` over untranslated/needs-review segments. Include only if the panel lands early; otherwise it stays the named follow-up it already is (blocker if skipped: job-kind wiring in `api/jobs.py` — named, not "later").
4. Keyboard reachability; `prefers-reduced-motion` respected.

**Out-of-scope.** New deps; eager N-fragment loads; provider calls on panel render (candidates list is a DB read; generation is the explicit button); editing glossary/characters in-panel (links out).

**Files likely touched.** `templates/workspace.html` · new `partials/_context_panel*.html` · split workspace router module · thin `services/` reads where needed · `tests/unit/api/test_ui_layout.py` + new fragment tests · (batch: `api/jobs.py`, batch route, job tests).

**Service/storage/API/UI impact.** Fragment routes + template column; optional one job kind.

**Data model impact.** None.

**Security risks.** None new (fragments render existing data); keep raw DB text out of `|safe` (the WV-002 HTML-safety rule applies to any rendered translation text).

**Performance risks.** Lazy-load is the rule — a panel that fires N fragment requests on page GET fails the stage (test-enforced). Glossary detection is a deterministic in-process match, not an LLM call (anti-slop).

**Tests required.** Panel fragments render per segment with FakeProvider fixtures; lazy-load proven (zero fragment requests on page GET); generate-from-panel reuses the WV-001 test path; consistency fragment read-only.

**Acceptance criteria** (mirrors WV-013): a translator consults glossary/characters/candidates/history and generates a candidate without leaving the editor; the panel updates on segment focus; no new dependency.

**Validation checkpoint.** Targeted pytest (`test_ui_layout.py`, `test_ui_candidates*.py`, new panel tests).

**Rollback/escape plan.** The panel is an include + fragment routes with single callers.

**Handoff notes.** The job panel (`#job-panel`) and segment hooks (`id="seg-{id}"`) are pinned — build around them.

---

## Q11 — Validation improvements  *(WV-007 + WV-008 + WV-011 + WV-014)*  [migration v12 only if removal chosen]

**Goal.** One QA report spanning translation **and** structure; the four missing deterministic checks; the `error` tier decision via ADR; the `qa_warnings` verdict; the furigana fidelity spike.

**Why this stage exists.** Blocker 7: WV-007/008/011 were Sprint P's "strongly recommended" tail and never landed (`qa/checks.py:12` is still 3-tier; structure findings live only on the structure page; `qa_warnings` is dead schema whose 3-tier CHECK would fight a 4-tier severity — QF-16). WV-014 is the Council's LN-fidelity spike assigned to Q.

**Dependencies.** Q2 (read patterns). Index-independent. Migration slot v12 (if removal chosen) — after Q7's v11 (R-15). ADR 013 is the one governance gate of the sprint (R-20).

**In-scope.**
1. **WV-007:** a `structure` category in the QA report — `services/translation_qa` (or a thin composer) reads **persisted snapshot validation rows** (`epub_snapshot_validation` via `read_snapshot`) for in-scope volumes → `QAIssue`s at volume/novel scope (`_issue_from_scope` pattern, `translation_qa.py:324`-area); surfaced in `templates/qa.html` filters; counts roll into badges. **No re-parse on render.**
2. **WV-008 step 1 — ADR 013 first:** the `error` tier contradicts ADR 008 ("no error severity") — write `docs/decisions/013-qa-error-severity-tier.md` **before** touching `Severity`. If rejected/deferred → ship the checks at existing tiers and drop the tier (fallback pre-authorized by the audit).
3. **WV-008 step 2:** four deterministic checks — max-length ratio, honorific mismatch, punctuation mismatch, broken line breaks — pure functions in `qa/checks.py`/`qa/consistency_checks.py`, thresholds in `qa/thresholds.py`, each with passing+failing unit tests; severity mapping + badge classes updated (`qa/report.py:84-90`, `ui_qa.py` badge map) if the tier lands.
4. **WV-011 verdict (recommended: REMOVE — SD-8):** drop `qa_warnings` + its delete-cleanup (`storage/volumes.py:145-155`, `services/volume.py`) via migration v12 (`DROP TABLE`) + schema.sql mirror + MAINTENANCE note. If "last validated" visibility is wanted instead, add a lean `validation_runs(scope, scope_id, badge, counts_json, finished_at)` — **decide in-PR, build exactly one**.
5. **WV-014 spike (time-boxed, investigation-only):** fixture EPUB with ruby (`<ruby><rt>`) + vertical text (`writing-mode`) → document survive/flatten through import→preview→export; outcome = a written finding + (if lost) a scoped follow-up issue. No preservation implementation inside Q.

**Out-of-scope.** LLM-based checks (ADR 008 core stands); per-segment validation persistence; OCR-adjacent checks; export gate changes (Q7 owns the gate).

**Files likely touched.** `qa/checks.py` · `qa/thresholds.py` · `qa/report.py` · `services/translation_qa.py` · `api/routers/ui_qa.py` · `templates/qa.html` · `docs/decisions/013-*.md` · (`storage/migrations.py` + `schema.sql` + `storage/volumes.py` + `services/volume.py` if v12) · `tests/unit/qa/*` · `tests/unit/storage/test_migrations.py` · spike fixture EPUB.

**Service/storage/API/UI impact.** QA service composition + check additions; QA page filter/badge updates; possible one-table drop.

**Data model impact.** v12 drop (or nothing).

**Security risks.** None new (read-only checks over already-stored data).

**Performance risks.** Structure category must read the snapshot, never re-parse (spy-tested); the four checks are O(segment) pure functions inside the existing on-demand scan.

**Tests required.** Per-check unit pairs; structure-category report test reading a stored snapshot (no parser call — spy); badge mapping; migration tests incl. a pre-drop `SELECT COUNT(*) == 0` assertion if v12; spike fixture finding documented.

**Acceptance criteria.** QA report shows structural findings under `structure` at volume/novel scope without re-parsing; each new check has unit pairs; severity set is 4-tier **with** ADR 013 merged or documented 3-tier without; `qa_warnings` is gone-or-wired (exactly one, not both, not neither); WV-014 finding written.

**Validation checkpoint.** `uv run pytest -q tests/unit/qa tests/unit/storage/test_migrations.py tests/unit/api/test_ui_qa.py`.

**Rollback/escape plan.** Checks are pure additions; the tier is ADR-gated; the table drop is gated on the full suite + a MAINTENANCE rollback note (restore = re-add DDL; the table was provably empty).

**Handoff notes.** `Severity` is imported by `qa/report.py:13` (`QASeverity = Severity`) — one Literal to extend, two badge maps to update. Structure issues carry no chapter/segment id — volume/novel scope only.

---

## Q12 — Residual cleanup + docs reconciliation + FINAL INTEGRATION GATE

**Goal.** Retire the remaining audited debt, reconcile every stale doc, then prove Sprint Q holds together as one product. Two phases: **Q12a residual fixes**, **Q12b the gate**. No new features.

**Why this stage exists.** The audit's smaller findings (QF-07/08/15/18, D-01..D-07, the QF-01 remainder) don't justify their own stages but must not survive the sprint; and ROADMAP/CLAUDE.md culture requires an evidence-backed exit gate.

**Dependencies.** Everything (last stage, always).

**In-scope — Q12a (each its own commit):**
1. **QF-07 (SD-9):** honor `raw_response_logging` — gate `raw_response=` persistence in `services/translation.py:504-513` on the flag (default false stops persisting) — or delete the flag line; recommended: **honor**. MAINTENANCE note (behavior change).
2. **QF-08:** upload byte cap (constant in `services/source_intake.py`, recommend 256 MiB) → `WeaverError`; update WORKFLOW_BLUEPRINT's "upload-capped" claim to true.
3. **QF-15 (WV-012 export half):** one doc section declares `export_book` canonical for UI surfaces, `services/export.py` CLI-only (or schedules its deletion post-Q). Doc-led; no behavior change.
4. **QF-01 remainder:** consolidate `_single_project_id` copies that Q2's extractions didn't touch into one storage accessor — opportunistic, stop at diminishing returns.
5. **Docs pass (D-01..D-07 + QF-18):** ARCHITECTURE layer claim (true again after Q2); WORKFLOW_BLUEPRINT stale deltas (sourceless create ✅; upload cap ✅ after item 2); `project_overview` docstring (fixed in Q2 — verify); MAINTENANCE migration notes complete (v10/v11/v12); CLAUDE.md §2.1/§2.3/§2.4/§2.5 sync with evidence.

**In-scope — Q12b (the gate; fix-only changes allowed):**

```text
uv run pytest -q                      # full suite green (≥1102 baseline + Q additions / 4 skipped)
uv run pyright                        # 0 errors
uv run ruff check .                   # clean
uv run ruff format --check .          # clean
uv run weaver --help                  # CLI loads
cd desktop && cargo check             # host compiles
cd desktop && cargo tauri build       # portable exe builds (Sprint O path intact)
```

**Desktop smoke (Windows, real desktop, ≥3 projects in the books dir):** launch → `/healthz` 200 → `/ui` renders → Dashboard command center within budget → global queue shows a live batch job started in another project; chip count matches → hubs render with degraded entries for a deliberately broken project → window close → no orphan `weaver` process → `%APPDATA%\Weaver\logs\` contains `runtime.log` + `sidecar.console.log`.

**Security smoke:** path traversal probes rejected (`/projects/browse?dir=..%2F..`, image preview with traversal manifest path); grep all five logs + `sidecar.console.log` + rendered `/ui/config` + `/ui/providers` HTML for any configured key value → zero hits; session token absent from logs/URLs; desktop-mode `/ui` without `X-Weaver-Session` → 401 while `/healthz` stays 200; dashboard/queue/hub HTML contains no absolute path from another project (QF-20 leak rule).

**Performance smoke:** `@pytest.mark.perf` index test @10 synthetic projects within budget (≤150 ms warm / ≤750 ms cold); manual dashboard first paint subjectively <1 s with 10+ projects; instrumentation/spy confirms zero source-file hashing on dashboard + overview renders.

**Out-of-scope.** Any feature work; anything not fixing a failure surfaced by the gate.

**Files likely touched.** Q12a: `services/{translation,source_intake}.py`, docs (`ARCHITECTURE`, `WORKFLOW_BLUEPRINT`, `MAINTENANCE`, `CLAUDE.md`, `WEB_WORKFLOW`). Q12b: none (evidence only), or targeted fixes.

**Service/storage/API/UI impact.** Two small service guards (flag + cap); rest is docs.

**Data model impact.** None.

**Security risks.** Item 1 *improves* privacy posture (raw responses stop accumulating by default). The gate's security smoke is the sprint's final leak check (R-03/R-05/R-06/R-07).

**Performance risks.** None added; the gate verifies the budgets (R-08/R-09/R-10).

**Tests required.** Flag-honored test (no `raw_response` persisted when false; persisted when true); upload-cap test (over-cap → friendly error, no memory blow); all grep-gates; the full matrix.

**Acceptance criteria.** All Q12a items closed or explicitly re-scoped with a named blocker; full matrix green; all three smokes pass with recorded evidence; CLAUDE.md §2 updated (Sprint Q row with test count + date).

**Validation checkpoint.** The full matrix above — this **is** the sprint exit.

**Rollback/escape plan.** Q12a commits are independent and individually revertible. If the gate fails on a hub, the hub's stage rollback applies (each hub is deletable as a unit by design).

**Handoff notes.** Do not start Q12b until Q12a's commits are in. Record gate evidence verbatim (counts, timings) in the PR and CLAUDE.md §2.5 — the next sprint's planner reads it the way this plan read Sprint P's.

---

## 2. Open sub-decisions (resolve in the named stage's PR; record the choice)

| ID | Decision | Default recommendation | Stage |
|---|---|---|---|
| SD-1 | Duplicate-uuid policy on dir copy | Flag both as `identity_conflict`; user resolves (no auto-regenerate — silent identity change is worse) | Q1 |
| SD-2 | Route identity migration | Defer; optional `/ui/p/{uuid}` redirect alias only; name-routes stay canonical through Q | Q1 |
| SD-3 | User-authored prompt-template/style-guide store | Out of Q (new mutable store → ADR); read-only presets shown | Q5 |
| SD-4 | Cost display | Tokens only; currency needs user-entered rates → post-Q if requested | Q6/Q8 |
| SD-5 | Final-gate toggle location | Per-export-run checkbox + optional `[export] final_requires_clean` project default (advisory stays default) | Q7 |
| SD-6 | Workspace analytics placement | Dashboard section (no new sidebar entry) | Q8 |
| SD-7 | `/ui/epub-preview` legacy route | Re-title as pre-import "Inspect a source" reachable from `/ui/new`; no global nav entry | Q9 |
| SD-8 | `qa_warnings` | Remove (migration v12); build `validation_runs` only if "last validated" is explicitly demanded — exactly one of the two | Q11 |
| SD-9 | `raw_response_logging` | Honor the flag (default false stops persisting raw responses) | Q12 |
| SD-10 | Batch candidate generation | Include in Q10 only if the panel lands early; else it stays the named follow-up (blocker: job-kind wiring in `api/jobs.py`) | Q10 |

---

## 3. Targeted validation index (quick reference)

| Stage | Minimum proving commands |
|---|---|
| Q1 | `uv run pytest -q tests/unit/storage/test_migrations.py tests/unit/services/test_workspace_index*.py` |
| Q2 | **full** `uv run pytest -q` (wide blast radius) + grep-gates |
| Q3 | `uv run pytest -q tests/unit/api/` + manual 390 px demo |
| Q4 | hub tests + `test_ui_shell.py` + manual cross-project job watch |
| Q5 | `test_resource_copy*` + hub tests |
| Q6 | hub tests + rendered-HTML secrets grep regression |
| Q7 | `test_migrations` + export-history/gate tests + existing `test_export*` |
| Q8 | analytics reconciliation fixtures |
| Q9 | explorer tab tests + no-reparse spy + `test_ui_layout.py` |
| Q10 | panel fragment tests + `test_ui_candidates*.py` + lazy-load proof |
| Q11 | `tests/unit/qa` + `test_ui_qa.py` (+ migrations if v12) |
| Q12 | the full matrix (§Q12b) |
