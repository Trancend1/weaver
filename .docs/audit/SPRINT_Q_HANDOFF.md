# Sprint Q — Workspace v2 · Agent Handoff (Q0 → Q1)

> **Audience.** A fresh agent (or human) with **no memory of any prior conversation**, picking up Sprint Q cold. Everything needed to start safely is here or one link away. Do not begin coding before finishing §1–§6.
> **Produced by Sprint Q0** (2026-06-10, docs-only — no code was changed).

---

## 1. Current sprint status (as of 2026-06-10)

| Fact | Value |
|---|---|
| Version | v0.7.0 · schema **v9** (`storage/db.py:13`) |
| Completed sprints | A–M, **N** (Tauri shell alpha), **P** (Workflow Coherence, WV-001..006), **O** (production desktop, portable exe path) |
| Test baseline | **1102 passed / 4 skipped** · pyright 0 · ruff clean (Sprint P/O exit gates, recorded in `CLAUDE.md` §2.4–2.5) |
| Active sprint | **Q — Workspace v2 (cross-project command center)** · stage **Q0 (planning) complete** → next is **Q1** |
| Open WV items inherited by Q | WV-007, WV-008, WV-009 (both halves), **WV-010 (entry item)**, WV-011, WV-012, WV-013, WV-014 + the WV-004 global-shell remainder + WV-001 batch-generation follow-up |
| Sprint Q structure | Q0 planning → **Q1 identity+read layer** → **Q2 hardening** → Q3 shell/dashboard → Q4 queue → Q5 resources → Q6 providers → Q7 export gate+ledger → Q8 analytics → Q9 explorer → Q10 editor panel → Q11 validation → Q12 cleanup+final gate |
| Migrations planned | v10 (Q1, `projects.uuid`) → v11 (Q7, `export_history`) → v12 (Q11, only if `qa_warnings` removal chosen). **One at a time.** |

**What Sprint Q is:** the cross-project Workspace layer (stable identity, read-only index, Dashboard command center, global Queue, Resources/Providers/Exports hubs, Analytics, Content Explorer v2, editor context panel, validation completion, cleanup). **What it is not:** SaaS/multi-user, external queue, SPA/Node, OCR, provider expansion, route rewrite, or a global mutable store.

---

## 2. Source-of-truth files (read in this order)

| # | File | Why |
|---|---|---|
| 1 | `CLAUDE.md` | Project rules (§4.2 code rules, §4.3 anti-slop, §4.6 contribution identity), progress state, locked stack |
| 2 | [.docs/audit/SPRINT_Q_DEEP_AUDIT.md](SPRINT_Q_DEEP_AUDIT.md) | **Evidence base**: inheritance map, gap matrix G-01..G-15, findings QF-01..QF-22, security/perf/UX audits, file:line anchors |
| 3 | [.docs/audit/SPRINT_Q_EXECUTION_PLAN.md](SPRINT_Q_EXECUTION_PLAN.md) | The staged plan Q0–Q12: ground rules, per-stage scope/tests/acceptance/rollback |
| 4 | [.docs/audit/SPRINT_Q_RISK_REGISTER.md](SPRINT_Q_RISK_REGISTER.md) | R-01..R-23 with mitigations + the per-stage-gate review rule |
| 5 | [.docs/audit/SOURCEOFARCHITECTURE.md](SOURCEOFARCHITECTURE.md) | Target product spec (build-state annotated) — the spec Q builds against |
| 6 | [.docs/audit/ROADMAP_REPLAN.md](ROADMAP_REPLAN.md) §3 "Sprint Q" | Sprint-level acceptance: hubs within budget, no SQLite in CLI/web layers, ADR 010 unviolated |
| 7 | [.docs/audit/ISSUE_BACKLOG.md](ISSUE_BACKLOG.md) | WV-001..014 acceptance criteria (WV-010 especially) |
| 8 | [.docs/audit/PAGE_LAYOUT_BLUEPRINT.md](PAGE_LAYOUT_BLUEPRINT.md) §0/§1/§10 | Target layouts for shell/dashboard/hubs (do not invent new layouts) |
| 9 | `docs/SPRINT_P_EXECUTION_PLAN.md` | How the previous sprint was staged/gated — match its discipline |
| 10 | `docs/ARCHITECTURE.md`, `docs/MAINTENANCE.md`, `docs/SIDECAR_CONTRACT.md` | Layer map, migration/release discipline, desktop contract |

Precedence: when docs disagree, **code is evidence** and the deep audit records the discrepancy (D-01..D-07); for planning intent, the execution plan wins inside Sprint Q.

---

## 3. Exact next recommended stage

**Q1 — WV-010: stable project identity + cross-project read layer** ([plan §Q1](SPRINT_Q_EXECUTION_PLAN.md)).

One sentence: add `projects.uuid` (migration v9→v10) + expose identity through discovery with duplicate detection, and build `services/workspace_index.py` — a **read-only**, cached, error-isolated, budget-tested index of project/volume/job summaries — shipped dark (no UI consumes it until Q3).

Why not something else first: every hub depends on it; the audit's blockers 2–6 are fixed in Q2 *using the patterns Q1 defines*; building any hub first would re-create the ad-hoc fan-out the audit condemns (R-01, R-10, R-12).

---

## 4. Branch recommendation

- Q0 docs were authored on **`feat/full-complete-workspace`**. Commit them there as a **docs-only** commit (suggested message: `docs(planning): add Sprint Q workspace v2 deep audit and execution plan`) and merge via PR.
- **Q1 starts on a fresh branch from `main`** after that merge: `feat/workspace-v2-q1`. One branch + one PR per stage thereafter (`feat/workspace-v2-q2`, …). Q2 is two PRs from one branch (PR-a split, PR-b fixes) — see the plan.
- Never force-push `main`; conventional commits with scope (`feat(workspace): …`, `fix(api): …`, `docs(planning): …`).
- Keep `git config core.hooksPath .githooks` enabled.

---

## 5. Commands to inspect repo state (run these first, before any edit)

```bash
rtk git status --short --branch          # expect clean tree (or only .docs/audit Q0 files if pre-commit)
rtk git log --oneline -8                 # confirm you are on/after the Q0 docs commit
uv run pytest -q                         # expect 1102 passed / 4 skipped (baseline)
uv run pyright                           # expect 0 errors
uv run ruff check .                      # expect clean
uv run weaver --help                     # CLI loads
```

Re-verify the audit's key anchors (cheap greps — if any drifted, update the audit before coding):

```bash
rtk grep -n "SCHEMA_VERSION = " src/weaver/storage/db.py                  # expect 9
rtk grep --context-only -m 30 "SELECT id FROM projects ORDER BY id LIMIT 1" src   # expect ~28 hits (QF-01)
rtk grep -n "connect_database" src/weaver/api                             # writable-in-router sites (QF-03)
rtk grep -n "suppress(HTTPException)" src/weaver/api/routers/ui.py        # 3 sites (QF-04)
rtk grep -n "compute_source_hash" src/weaver/services/epub_reparse.py     # QF-05 anchor
rtk grep -n "review_status" src/weaver/storage/schema.sql                 # v9 column present
```

---

## 6. What must NOT be touched (hard fences)

- **Locked stack:** FastAPI + Jinja2 + HTMX (vendored), SQLite WAL no-ORM, typer/rich, pydantic-at-web-boundary. No SPA/Node/build step/web fonts. **No new runtime dependency.**
- **ADR 010:** in-process single-process `JobRegistry`; no external queue/worker; no SSE fan-in.
- **`desktop/` subtree:** read-only for all of Q (smoke only at Q12).
- **`read_epub()`/`DocumentIR` vs `ParsedEpub`:** separate paths — never merge.
- **HTMX hooks (pinned by tests):** `#tree`, `#ws-grid`, `#job-panel`, `#export-panel`, `#browser`, `#selected_source`, `#source_path`, `#qa-badge-status`, `#qa-issues`, `id="seg-{id}"`, `qa-badge-vol-*`, `qa-badge-ch-*`.
- **Secrets:** env / `~/.weaver/secrets.toml` only; never in config/logs/render/SSE; session token header-only.
- **Gate B1 (extended):** no QA scan, no provider call, **no source-file hashing** on any render path.
- **DB enum values** (`segments.status`, `jobs.status`, `review_status`): presentation-mapped only — never renamed.
- **Export advisory default:** the Final gate (Q7) is opt-in; advisory stays the default (ADR 008 resolution).
- **One project DB = the source of truth for that project.** No global mutable store of any kind without an ADR.
- **Contribution identity (CLAUDE.md §4.6):** no AI co-author trailers, no "Generated with" tags, human author identity only.

---

## 7. Top 10 findings to keep in working memory (full detail: audit §3)

1. **QF-01** — `SELECT id FROM projects ORDER BY id LIMIT 1` in **28 call sites** (17 files, 5 in routers): the single-project assumption Q1 must centralize, not chase.
2. **QF-03 / R-01/R-02** — routers open **writable** connections for reads; every open migrates + resets `in_progress` (mid-job stomp race). Read layer = `connect_readonly_database` only.
3. **QF-02 / D-01** — raw SQL inside UI routers while docs claim "CLI/web never touch SQLite." Q2 extracts; grep-gate forever after.
4. **QF-04 / R-11** — approve/reject/apply failures swallowed (`suppress(HTTPException)`, `except WeaverError: pass`) — silent-failure pattern must not reach the hubs.
5. **QF-05 / R-09** — Project Overview SHA-256-hashes **every source EPUB on every render** (+2 writable opens per volume) despite a "no file access" docstring. The index must never hash.
6. **QF-11 / R-17** — identity = directory name, duplicated in three drift-able places; jobs keyed by name; dir-copy duplicates identity → Q1 uuid + conflict entries.
7. **QF-12 / R-18** — readonly connections never migrate; v8 DBs surface the moment the read layer exists → schema-version guard + `needs_upgrade` entries.
8. **QF-09 / R-19** — boot recovery write-opens every project DB and silently skips locked ones → ghost `running` rows; queue must render `stale_running` distinctly.
9. **WV-007/008/009/011/013 are open** (Sprint P shipped only WV-001..006): structure-QA join, 4 checks + ADR-013-gated `error` tier, export gate + ledger, `qa_warnings` verdict, editor context panel → stages Q7/Q10/Q11.
10. **G-04 / blocker 8** — the global Workspace sidebar was never scaffolded (`base.html:21-25` = Dashboard/New project/Config); hubs have no home until Q3.

---

## 8. Q1 first-task checklist (execute in order)

1. [ ] Run §5 inspection commands; confirm baseline green and anchors unmoved (if moved → update audit first).
2. [ ] Create `feat/workspace-v2-q1` from `main` (post-Q0-merge).
3. [ ] Read [plan §Q1](SPRINT_Q_EXECUTION_PLAN.md) fully, including sub-decisions **SD-1** (duplicate-uuid policy) and **SD-2** (no route migration).
4. [ ] **Migration v10:** add `projects.uuid` in `storage/migrations.py` (register in `_MIGRATIONS`), bump `SCHEMA_VERSION` to 10 in `storage/db.py`, mirror in `storage/schema.sql`, set uuid in `storage/projects.create_project`. Backfill with `uuid.uuid4()` (stdlib).
5. [ ] **Tests first for the migration:** forward test (v9 fixture → v10 has unique uuids) + idempotency test (re-apply is a no-op), in `tests/unit/storage/test_migrations.py`.
6. [ ] Extend `services/project_discovery.py`: `uuid` on `DiscoveredProject` (readonly read; `None` for needs-upgrade DBs), `find_project_by_uuid`, duplicate-uuid → `identity_conflict` flagging on both entries.
7. [ ] Build `services/workspace_index.py` exactly per plan §Q1 in-scope items 3–5: readonly opens only · per-project error isolation (`ready|needs_upgrade|locked|error|identity_conflict`) · schema-version guard before column access · counts + `job_counts` (incl. `stale_running` via the live `JobRegistry`) + `last_activity` · mtime-keyed cache + ≤5 s TTL · **paths internal only**.
8. [ ] Tests per plan §Q1: broken-project isolation set (healthy/locked/v8/corrupt/deleted), cache invalidation on mtime change, **no-write assertion**, leak rule, duplicate-uuid, perf smoke (`@pytest.mark.perf`, 10 synthetic projects, ≤150 ms warm / ≤750 ms cold).
9. [ ] Add the permanent **grep-gate test**: no `conn.execute(` / `connect_database(` / `suppress(HTTPException)` / `except WeaverError: pass` under `api/routers/` *beyond the existing audited sites* (exact-count pin until Q2 removes them; then zero).
10. [ ] Migration rollback note in `docs/MAINTENANCE.md` (additive column; inert if unused).
11. [ ] Stage gate: `uv run pytest -q tests/unit/storage/test_migrations.py tests/unit/services/test_workspace_index*.py` → then `uv run pytest -q` (full), `uv run pyright`, `uv run ruff check .`, `uv run ruff format --check .`.
12. [ ] PR (one concern: Q1). Update `CLAUDE.md` §2.3 active-stage line in the same PR. **No UI change, no route change, no hub work** — the index ships dark.

**Definition of done for Q1:** plan §Q1 acceptance criteria all check; the index is consumed by zero routes; every test in step 8 exists and passes.

---

## 9. Final validation commands (the Sprint Q exit — Q12b; also the pre-release matrix)

```text
uv run pytest -q                      # full suite green
uv run pyright                        # 0 errors
uv run ruff check .                   # clean
uv run ruff format --check .          # clean
uv run weaver --help                  # CLI loads
cd desktop && cargo check             # host compiles
cd desktop && cargo tauri build       # portable exe builds (Sprint O path intact)
```

Plus, per [plan §Q12](SPRINT_Q_EXECUTION_PLAN.md):
- **Desktop smoke** (Windows, ≥3 projects): launch → `/healthz` 200 → `/ui` → dashboard within budget → cross-project queue live → close → no orphan `weaver` process → both logs in `%APPDATA%\Weaver\logs\`.
- **Security smoke:** traversal probes rejected; zero key/token hits grepping all logs + rendered config/providers HTML; desktop 401 without session header; no cross-project absolute-path leakage in hub HTML.
- **Performance smoke:** perf-marked index test within budget @10 projects; zero source-hashing on dashboard/overview renders.

Record all evidence in the Q12 PR and `CLAUDE.md` §2.4/§2.5 — Sprint Q closes only with that note written.
