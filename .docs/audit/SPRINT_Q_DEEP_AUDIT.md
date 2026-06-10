# Sprint Q — Workspace v2 · Deep Audit (Q0)

> **Type.** Read-only audit. Producing this document changed no source, test, or runtime behavior.
> **Date.** 2026-06-10 · **Branch.** `feat/full-complete-workspace` · **Baseline.** v0.7.0 · Sprints A–O complete · 1102 tests / 4 skipped · pyright 0 · ruff clean · schema **v9**.
> **Purpose.** The Q0 stage of Sprint Q (Workspace v2): measure the post-P/post-O repo against the Sprint Q target ([SOURCEOFARCHITECTURE](SOURCEOFARCHITECTURE.md) §3, §8.9; [ROADMAP_REPLAN](ROADMAP_REPLAN.md) §3 Sprint Q), and surface every flaw, gap, and risk Sprint Q must design around **before** WV-010 is implemented.
> **Companions.** [SPRINT_Q_EXECUTION_PLAN](SPRINT_Q_EXECUTION_PLAN.md) (staged plan Q0–Q12) · [SPRINT_Q_RISK_REGISTER](SPRINT_Q_RISK_REGISTER.md) · [SPRINT_Q_HANDOFF](SPRINT_Q_HANDOFF.md) · prior audit: [THE_COUNCIL_WEAVER_AUDIT](THE_COUNCIL_WEAVER_AUDIT.md) · backlog: [ISSUE_BACKLOG](ISSUE_BACKLOG.md) (WV-001..014).
> **Finding IDs.** Council-era issues keep their `WV-xxx` ids. New findings from this audit are `QF-xx` (Q-finding). Both id sets are referenced by the execution plan and risk register. **Stage numbers** refer to the restructured staging in [SPRINT_Q_EXECUTION_PLAN](SPRINT_Q_EXECUTION_PLAN.md): Q1 identity/read layer · **Q2 read-path & failure-visibility hardening** · Q3–Q8 hubs · Q9–Q11 per-project surfaces · Q12 residual cleanup + final gate.

---

## 0. Executive summary

Sprint P closed the per-project workflow loop (generation in UI, reading preview, review axis, overview, navigation labels, status labels). Sprint O shipped a working Windows portable desktop path. What remains is exactly what the Council deferred: **everything cross-project** — and three structural facts dominate how Sprint Q must be built:

1. **The single-project-per-DB assumption is written into 28 call sites.** `SELECT id FROM projects ORDER BY id LIMIT 1` is duplicated across 17 files — including **inside API/UI routers** (`api/routers/ui.py:1068,1335`, `api/routers/ui_qa.py:233`, `api/routers/candidates.py:126,257`). Project identity is the **directory name**, duplicated in three places that can drift (dir name, `project.toml [project] name`, `projects.name` row), and jobs are keyed by name (`storage/schema.sql:153`). WV-010 is not a feature; it is the load-bearing prerequisite for every Q hub ([QF-01](#qf-01), [QF-11](#qf-11)).
2. **The repo already violates the rules Sprint Q must be built under.** Routers run raw SQL ([QF-02](#qf-02)), open **writable** connections for pure reads — each open applies migrations and resets `in_progress` segments ([QF-03](#qf-03)) — and silently swallow errors (`except WeaverError: pass`, `suppress(HTTPException)` — [QF-04](#qf-04)). If Q copies the existing router patterns, the cross-project layer will inherit write side-effects fanned out across **every** project DB. The read layer must be built on `connect_readonly_database` (the good pattern: `services/project_overview.py:81`), and the existing violations are a scheduled hardening stage (Q2), not an accepted style.
3. **Per-render cost is already mis-budgeted at single-project scale; Q multiplies it by N.** The Project Overview hashes the **entire source EPUB** (SHA-256, full file) for every EPUB volume on **every render** (`services/project_overview.py:125` → `services/epub_reparse.py:110` → `compute_source_hash`) while its own docstring claims "no file access beyond a DB read" (`project_overview.py:3-4`) — plus two extra **writable** DB opens per volume ([QF-05](#qf-05)). A Dashboard command center that repeats this pattern across 10 projects is dead on arrival. Invalidation/caching must be designed **before** any Q UI ships (execution plan Q1).

None of this blocks Sprint Q; all of it shapes the order: **identity + read layer first (Q1), read-path hardening immediately after (Q2), hubs after that, residual cleanup before the final gate (Q12).**

---

## 1. Inheritance map — what P/O actually shipped vs. what Q starts from

The Council backlog (WV-001..014) is the contract. Verified state per item, with evidence from the current tree:

| ID | Title | Council target sprint | **Actual state (2026-06-10)** | Evidence |
|---|---|---|---|---|
| WV-001 | Candidate/draft generation in UI | P | ✅ Shipped — **per-segment only**; chapter/selection **batch generation deferred** (needs `JobRegistry`) | `api/routers/ui.py:1113-1120` (`ui_candidate_generate`), `:1351-1352` (`ui_draft_generate`); deferral: `docs/SPRINT_P_EXECUTION_PLAN.md` P1 out-of-scope |
| WV-002 | Reading/output Preview | P | ✅ Shipped (Reading + Before/After; read-only, no file writes) | `services/reading_preview.py:1-21` (readonly connect, `block_to_html`); routes `api/routers/ui.py:594,641` |
| WV-003 | Review status + Review Queue | P | ✅ Shipped (schema v9 `segments.review_status`; queue UI). Fuller resolution-action set trailed | `storage/schema.sql:51-57`; `services/segment_review.py`; routes `ui.py:1201,1264`; `templates/review_queue.html` |
| WV-004 | Navigation unification | P | ◑ **Partial** — labels/subnav/breadcrumbs reconciled; **global Workspace sidebar shell (Projects/Queue/Resources/Providers/Exports/Settings) was NOT scaffolded** | `templates/base.html:21-25` (topbar still Dashboard/New project/Config only); `partials/_sidebar.html` (per-project only); executed scope: `docs/SPRINT_P_EXECUTION_PLAN.md` P4 |
| WV-005 | Project Overview | P | ✅ Shipped (cheap counts, review counts, volume cards). Deviations: tree/import/export stayed on the same page (not tabs); snapshot status per volume is **not** cheap ([QF-05](#qf-05)) | `services/project_overview.py`; `templates/project.html` |
| WV-006 | Status taxonomy + dead branches | P | ✅ Shipped for **translation + job** axes; review/validation/export label mapping **not** centrally wired ([QF-13](#qf-13)) | `api/status_labels.py`; globals wired `api/templating.py:29-32` (4 globals, 2 axes) |
| WV-007 | Structure validation joined into QA | P | ⬜ **Open** — QA report is still translation-only; structure issues remain preview-only | `services/translation_qa.py` (no structure category); `readers/epub_validation.py` surfaced only via structure page |
| WV-008 | Missing checks + `error` tier | P | ⬜ **Open** — severity is still 3-tier; the four checks absent; **needs ADR 013** (contradicts ADR 008) | `qa/checks.py:12` (`Severity = Literal["info","warning","critical"]`) |
| WV-009 | Final-export gate + export history | P/Q | ⬜ **Open (both halves)** — preflight is advisory-only; no `exported` axis; no ledger | `api/routers/ui_qa.py:184-189` ("Export is **never** blocked"); `services/volume_lifecycle.py:18-23` (`exported` deferred) |
| WV-010 | Stable project id + cross-project read layer | Q | ⬜ **Open — Sprint Q's entry item** | `services/project_discovery.py:32-71` (identity = dir name); [QF-01](#qf-01)/[QF-11](#qf-11) |
| WV-011 | `qa_warnings` wire-or-remove | P/Q | ⬜ **Open** — still vestigial (zero writers; cleaned on volume delete; 3-tier CHECK baked in) | `storage/schema.sql:125-132`; `storage/volumes.py:145-155`; grep: no writer |
| WV-012 | Two preview concepts / two export paths | Q | ⬜ **Open** — now **three** "preview" surfaces (global `/ui/epub-preview`, per-volume `/structure`, reading preview) + legacy markdown exporter | routes `ui.py:142,498,594`; `services/export.py` (legacy) vs `services/export_book.py` |
| WV-013 | Editor context panel | P | ⬜ **Open** — editor is still 2-column; glossary/characters/candidates/history are separate pages | `templates/workspace.html`; `docs/SPRINT_P_EXECUTION_PLAN.md` (P1–P7 core excluded WV-013) |
| WV-014 | Furigana/ruby + vertical-text fidelity spike | Q | ⬜ **Open** (investigation, time-boxed) | no ruby/`writing-mode` handling evidenced in `readers/` or `renderers/` |

**Net Sprint Q inheritance:** WV-007, WV-008, WV-009 (full), WV-010, WV-011, WV-012, WV-013, WV-014 + the WV-004 global-shell remainder + the WV-001 batch-generation follow-up + all-new Q hubs (Dashboard command center, Queue, Resources, Providers, Exports, Analytics, Content Explorer v2).

---

## 2. Gap matrix — Sprint Q target vs. current behavior

Columns: target (with source) · current (with evidence) · severity (P0 blocker / P1 major / P2 improvement / P3 enhancement) · user impact · technical impact · recommended fix · stage (per [SPRINT_Q_EXECUTION_PLAN](SPRINT_Q_EXECUTION_PLAN.md)).

| # | Target behavior | Current behavior | Evidence | Sev | User impact | Technical impact | Fix | Stage |
|---|---|---|---|---|---|---|---|---|
| G-01 | Stable project id; rename-safe; id-addressable (SOURCEOFARCHITECTURE §6, WV-010) | Identity = `.weaver/<dir>` name; three drift-able name sources; jobs keyed by name | `project_discovery.py:49-50`; `schema.sql:153`; `project.py:259-270` | **P0** (for Q) | Rename/copy a project dir → broken bookmarks, orphaned job rows | 28 single-project call sites; no resolver | `projects.uuid` column (migration v10) + discovery exposure + resolver service; routes unchanged (alias only) | Q1 |
| G-02 | Cross-project read layer backing all hubs (WV-010) | None. Per-render `discover_projects` → `inspect_project` per project; no cache; no schema guard | `project_discovery.py:32-71`; `api/routers/ui.py:105-133` | **P0** (for Q) | Dashboard stays flat; no queue/health/activity | Every hub would otherwise fan out ad-hoc DB opens from routes | `services/workspace_index.py`: readonly fan-out + per-project error isolation + mtime/TTL cache + schema-version guard | Q1 |
| G-03 | Dashboard = command center: Current Project · In Progress · Recently Completed · Queue · Provider Health · Recent Activity (SOURCEOFARCHITECTURE §8.1; PAGE_LAYOUT §1) | Flat project-card grid | `templates/dashboard.html:10-39` | P1 | No "continue where I left off"; no global state visibility | Blocks on G-02 | Dashboard blocks fed by the index; Queue/Health tiles land with Q4/Q6 | Q3 |
| G-04 | Global Workspace sidebar (Projects/Queue/Resources/Providers/Exports/Settings) + persistent context bar + topbar Active-jobs (PAGE_LAYOUT §0) | Topbar = Dashboard/New project/Config; sidebar per-project only; no context bar; no jobs affordance outside a project | `base.html:21-25`; `partials/_sidebar.html:1-44` | P1 | Global vs project scope is invisible; hubs have no home | Highest template-diff item; pinned UI tests | Global shell with staged hub activation; context bar; topbar jobs chip (in-memory `JobRegistry`, zero DB) | Q3 |
| G-05 | Global Translation Queue across projects (SOURCEOFARCHITECTURE §3; PAGE_LAYOUT §10) | Jobs page is per-project only (`/ui/projects/{name}/jobs`); SSE per job | `api/routers/ui.py:250`; no `/ui/jobs` route | P1 | Concurrent work across series is untrackable | Needs G-02; jobs are per-DB rows + one in-process registry | Read-only cross-project queue page from index; actions deep-link to per-project job detail | Q4 |
| G-06 | Workspace Resources hub (glossaries/characters/TM/prompt templates/style guides) (SOURCEOFARCHITECTURE §8.9 →§17) | All resources per-project; no cross-project listing; no copy path | `_sidebar.html:24-43`; services are per-project-toml | P2 | Series with shared canon re-enter the same glossary per project | A *shared mutable* store would violate the one-DB-per-project premise | Read-only aggregation + explicit copy-between-projects service (conflict-skipping report); **no global store** | Q5 |
| G-07 | Provider hub: routing/cost/health/failures/config safety (SOURCEOFARCHITECTURE §8.9 →§18) | `/ui/config` = defaults form + secret names CRUD only; health check exists but only as an opt-in flag on `inspect_project` | `api/routers/ui_admin.py:458-530`; `services/project.py:243-266` (`run_healthcheck=False`) | P2 | Which provider each project uses, what fails, and token spend are invisible | Health = live provider call (cost!); must never run on render | Hub page: per-project provider/model (from toml, never keys), explicit health button, failures from `jobs.error_summary`, token totals from `translations.input_tokens/output_tokens` | Q6 |
| G-08 | Export gate (Draft always / Final opt-in clean) + persisted export history (SOURCEOFARCHITECTURE §8.8; WV-009) | Advisory-only preflight; no export status axis; no ledger; artifacts discoverable only on disk | `ui_qa.py:184-189`; `volume_lifecycle.py:18-23` | P1 | "What did I already export, was it clean?" unanswerable | Ledger table (migration v11) written at export-job completion | Gate toggle + `export_history` table + per-project history list + global Exports hub via index | Q7 |
| G-09 | Analytics (progress/review/QA/provider usage/export readiness) (SOURCEOFARCHITECTURE §8.9 →§19) | None. Token counts already persisted per attempt but never aggregated | `schema.sql:68-70` (`input_tokens/output_tokens`) | P2 | No progress/cost insight | Deterministic aggregates only; QA-dependent metrics must stay opt-in (Gate B1) | Per-project analytics from counts + token sums; cross-project rollup via index; **tokens, not currency** | Q8 |
| G-10 | Content Explorer: volume tree · chapter list · **segment list** · asset browser · metadata · warnings (SOURCEOFARCHITECTURE §8.3; PAGE_LAYOUT §3) | Structure page covers metadata/spine/images/validation; **no segment list view; no asset-browser tab framing**; three surfaces share the word "preview" | `templates/epub_preview.html`; routes `ui.py:142,498,594` | P2 | Jump-to-problem-segment requires the editor or QA page detour | Snapshot tables already carry the data | Reframe structure page as Content Explorer (tabs: Structure/Segments/Assets/Metadata/Warnings); retire the global `/ui/epub-preview` entry (redirect) | Q9 |
| G-11 | 3-column editor with context panel (glossary/characters/candidates+Generate/history/consistency) (WV-013; PAGE_LAYOUT §4) | 2-column editor + job panel; resources are separate pages | `templates/workspace.html`; `_sidebar.html:24-43` | P2 | Translator leaves the editor constantly | All data sources exist as services; panel must be lazy per segment focus | HTMX context panel; rides WV-001 + status labels | Q10 |
| G-12 | One QA report spanning translation **and** structure; 4-tier severity; 4 missing checks (WV-007/008) | Translation-only report; 3-tier; structure issues only on the structure page | `translation_qa.py`; `qa/checks.py:12` | P2 | "Is this volume valid?" needs two pages | `error` tier contradicts ADR 008 → **ADR 013 required first** | Join snapshot validation rows as a `structure` category; add checks; ADR 013 or stay 3-tier | Q11 |
| G-13 | Vocabulary/dead-code debt retired: `qa_warnings`, legacy exporter, preview naming, dead config flag (WV-011/012, QF-07) | All still present | §3 findings below | P3 | Confusing duplicate concepts | Dead schema + dead flag + 3 preview surfaces | Decide-and-delete pass | Q11/Q12 |
| G-14 | Layer rules hold everywhere ("UI routers thin, no SQLite in web layer" — ARCHITECTURE.md:24, ADR 002) | **Violated in ~12 router sites** (raw SQL, writable opens, silent failure swallows) | [QF-02](#qf-02)/[QF-03](#qf-03)/[QF-04](#qf-04) | P1 (debt) | Silent failures: clicking Approve can fail with zero feedback | Q hubs must not copy these patterns; hardening scheduled | Router → service extraction; readonly reads; error fragments | Q2 (patterns frozen from Q1) |
| G-15 | Sourceless project creation (WORKFLOW_BLUEPRINT §1 delta) | **Already shipped** — blueprint is stale | `services/project.py:131-177` (source optional); `api/routers/projects.py:166-178` | P3 (doc) | None (works) | Doc drift misleads planning | Annotate blueprint | Q12 (doc) |

---

## 3. New findings (QF-01..QF-22)

Each: evidence · severity · impact · recommended fix · stage. These are **additions** to the Council audit, found by inspecting the post-P/post-O tree.

<a id="qf-01"></a>
### QF-01 — Single-project assumption duplicated in 28 call sites — **P1 (architecture)**
- **Evidence:** `grep "SELECT id FROM projects ORDER BY id LIMIT 1"` → 28 matches in 17 files: services (`project_tree.py:149`, `translation_qa.py:384`, `import_source.py:133`, `glossary*.py`, `characters.py:151`, `manual_edit.py:71`, `translation.py:530`, `translation_memory.py:92`, `workspace_translate.py:448`, `workspace_edit.py:131`, `candidate_generation.py:58`, `character_draft.py:285`) **and routers** (`ui.py:1068,1335`, `ui_qa.py:233`, `candidates.py:126,257`).
- **Impact:** WV-010's stable id has 28 places to miss; any future multi-project-per-DB idea is dead; router copies double as layer violations (QF-02).
- **Fix:** Q1 introduces one identity resolver (`storage/projects.get_project_identity(connection)` or equivalent) and the read layer; **do not** chase all 28 call sites in Q1 (they are correct today, one project per DB) — Q2 extracts the router copies, the remaining service copies consolidate opportunistically by Q12, and new copies are forbidden from Q1 onward.

<a id="qf-02"></a>
### QF-02 — Raw SQL + storage imports inside routers — **P1 (layer violation, documented-rule breach)**
- **Evidence:** `api/routers/ui.py:1060-1073` (`from weaver.storage.candidates import …`; `conn.execute("SELECT id FROM projects …")`), `ui.py:1334`, `ui.py:1414`, `ui_qa.py:232-236`, `candidates.py:125-126,256-257`, `jobs.py:82,99`. `docs/ARCHITECTURE.md:24` and CLAUDE.md §4.2 state "CLI/web never touch SQLite directly."
- **Impact:** The rule Sprint Q is ordered to respect ("no SQLite access added to UI/CLI layers") is already broken; new agents copy what they see.
- **Fix:** Q2 extracts these into `services/` read functions; all stages are forbidden from adding new occurrences (permanent grep-gate in the execution plan).

<a id="qf-03"></a>
### QF-03 — Writable connections for pure reads; every open mutates — **P1 (correctness/concurrency)**
- **Evidence:** `storage/db.py:48-79` — `connect_database` **always** runs `apply_migrations` + `reset_interrupted_segments` (`UPDATE segments SET status='pending' WHERE status='in_progress'`, `db.py:132-145`) and commits. Used for **reads** in `ui.py:186,273,312,1067,1159,1229,1334,1414`, `candidates.py:125,256`, `jobs.py:82,99`, `epub_snapshot.py:222` (`snapshot_status`), `epub_reparse.py:90` (`status_for_volume`), `image_preview.py:155`. Only `ui_qa.py:232` and `project_overview.py:81`/`reading_preview.py:18`/`project.py:263` use `connect_readonly_database`.
- **Impact:** (a) rendering a candidates list can run a schema migration; (b) **mid-job stomp**: while a translate job holds a segment `in_progress` (single process, separate connection), any of these read paths resets it to `pending` mid-flight — the worker's later write wins, but the status transition is corrupted in between and the invariant "status transitions live with their data" is violated; (c) each writable open briefly takes WAL writer locks against the live job.
- **Fix:** Q1 hard rule — the workspace index uses `connect_readonly_database` **only** + a no-write regression test. Q2 migrates existing read paths to readonly and moves `reset_interrupted_segments` to explicit recovery points (serve startup + CLI write-entry commands), not every open.

<a id="qf-04"></a>
### QF-04 — Silent failure swallows in the review loop — **P1 (UX/anti-slop gate 5)**
- **Evidence:** `ui.py:1074-1075` (`except WeaverError: pass` → empty candidates list rendered with no error); `ui.py:1086-1090,1096-1100,1106-1110` (`with suppress(HTTPException): approve/reject/apply` → card re-rendered as if nothing happened on failure).
- **Impact:** A failed approve/apply looks identical to success until the user notices the status didn't change. Violates CLAUDE.md §4.3 gate 5 ("failure visible").
- **Fix:** Q2 — error fragments (the `_job_error` pattern) instead of suppression. Q stages must not copy `suppress` into new hub routes.

<a id="qf-05"></a>
### QF-05 — Project Overview hashes every EPUB volume on every render — **P1 (performance, doc mismatch)**
- **Evidence:** `services/project_overview.py:125` calls `_snapshot_status_safe` per volume → `services/epub_reparse.py:100-116` `status_for_volume` → `compute_source_hash(epub_path)` (`epub_snapshot.py:71-77`, full-file SHA-256) + **two more writable DB opens** per volume (`epub_reparse.py:90`, `epub_snapshot.py:222`). The module docstring claims "no file access beyond a DB read" (`project_overview.py:3-4`).
- **Impact:** A 10-volume project with 30 MB EPUBs reads+hashes ~300 MB per project-page load. Any Q dashboard/index that reuses `status_for_volume` per volume inherits this × N projects.
- **Fix:** Q1 (design): the index **never** hashes sources. Q2 fixes the overview (before any dashboard work reuses the overview service): render snapshot status from the stored row + an `(mtime_ns, size)` fast-path; the full hash runs only behind the existing explicit reparse/staleness actions.

<a id="qf-06"></a>
### QF-06 — Stale `volumes.source_path` crashes image preview with a 500 — **P2 (bug)**
- **Evidence:** `services/image_preview.py:73-94` catches `KeyError`/`BadZipFile` but **not** `FileNotFoundError`/`PermissionError`/`IsADirectoryError` from `ZipFile(source_path)`; route `api/routers/projects.py:570-583` converts only `WeaverError` to 422. Moving/deleting the source EPUB after import → unhandled 500. (Contrast: preflight handles the same situation gracefully — `ui_qa.py:244-255`.)
- **Fix:** Q2 — catch `OSError` → `WeaverError` ("source file moved; reattach or reparse"). Test with a deleted source fixture.

<a id="qf-07"></a>
### QF-07 — `raw_response_logging` is a dead flag; raw responses persist unconditionally — **P2 (privacy expectation, DB bloat, dead-config rule)**
- **Evidence:** flag written into every generated `project.toml` (`services/project.py:386` `raw_response_logging = false`); `grep raw_response_logging src/` → that one line only. Meanwhile `services/translation.py:504-513` persists `response.raw_response` into `translations.raw_response` on **every** segment translation (`schema.sql:68`).
- **Impact:** A user reading their config reasonably believes raw provider output is not retained; it is — in the DB, forever (append-only attempts). Also violates CLAUDE.md §4.3 "no config flags for unbuilt features."
- **Fix:** Q12 sub-decision (SD-9): honor the flag (gate `raw_response=` on it; default false = stop persisting) **or** delete the flag line. Recommendation: **honor it** — it matches what the config already promises; document the behavior change in `docs/MAINTENANCE.md`.

<a id="qf-08"></a>
### QF-08 — No upload size cap; blueprint claims "upload-capped" — **P2 (local DoS, doc mismatch)**
- **Evidence:** `api/routers/projects.py:99` (`await file.read()` into memory, `/projects/epub-preview`), same pattern in `/projects/create` and `/ui/new` (`ui.py:712-753`); `grep -i "max_upload|upload.*cap"` → no cap anywhere. `WORKFLOW_BLUEPRINT.md` §1 says imports are "upload-capped".
- **Impact:** A multi-GB file selected by accident is read fully into RAM. Local-only, single-user — severity is bounded, but it is an honesty gap vs. the blueprint.
- **Fix:** Q12 — byte cap (recommend 256 MiB constant in `source_intake`) → 413-style `WeaverError`; update blueprint.

<a id="qf-09"></a>
### QF-09 — Startup write-opens and auto-migrates every project DB; locked DBs are skipped silently — **P2 (cross-project correctness)**
- **Evidence:** `api/app.py:91` (`recover_all_projects` at factory time) → `services/job_store.py:353-373`: per project `connect_database` (= migrate + reset segments + commit); `except (WeaverError, sqlite3.Error): continue` (`job_store.py:369-371`).
- **Impact:** (a) Boot cost scales with N projects; (b) starting the cockpit silently **migrates every project on the machine**, including ones the user never opens — surprising for backups/sync tools; (c) a DB locked by a concurrent CLI run is skipped → its orphaned `running` rows survive → ghost "running" jobs in any Q queue UI.
- **Fix:** Q1 design note — the index must treat `running` rows as "claimed by the live registry, else stale" (cross-check `JobRegistry`); Q4 queue renders stale-running distinctly. Startup recovery behavior itself is ADR-010-correct; document the migration side effect in `docs/MAINTENANCE.md` (Q2 doc task).

<a id="qf-10"></a>
### QF-10 — Module-size rule violations where Q will work — **P2 (maintainability)**
- **Evidence:** `api/routers/ui.py` ≥ 1414 lines, `cli/main.py` 1329, `readers/epub.py` 1263, `api/jobs.py` 1137 (rule: split >400 — CLAUDE.md §4.2).
- **Impact:** Q3–Q10 all add UI routes; landing them into a 1.4k-line router guarantees merge pain and review blindness.
- **Fix:** Mechanical split of `ui.py` (candidates/review/jobs/preview sub-routers) as **Q2 PR-a (hardening)** — test-pinned, zero behavior change. `cli/main.py`/`epub.py` stay out of Q scope (note only).

<a id="qf-11"></a>
### QF-11 — Identity has three drift-able sources; jobs/TM keyed accordingly — **P1 (architecture, WV-010 input)**
- **Evidence:** directory name (`project_discovery.py:49-50`) vs `project.toml [project] name` (`project.py:268`) vs `projects.name` row (`storage/projects.create_project`). `jobs.project_name` = dir name (`schema.sql:153`, `JobRow` doc `job_store.py:53-55`).
- **Impact:** Renaming the directory breaks routes and orphans job rows' project linkage; copying a project dir duplicates identity wholesale.
- **Fix:** Q1: `projects.uuid` (migration v10) as the stable id; discovery exposes it; duplicate-uuid detection at discovery (dir copy case) surfaces a conflict entry instead of guessing. Route migration explicitly deferred (alias/redirect only) — see execution plan sub-decision SD-2.

<a id="qf-12"></a>
### QF-12 — Read-only connections never migrate; schema drift is only masked by QF-09 — **P2 (read-layer correctness)**
- **Evidence:** `connect_readonly_database` (`db.py:82-105`) opens `mode=ro`, applies nothing. A v8 DB (no `review_status`) read by `review_counts_for_volume` → `sqlite3.OperationalError: no such column`. Today every DB is force-migrated at boot (QF-09) **unless** its recovery open failed (locked/corrupt) — exactly the projects most likely to surface in an error path.
- **Impact:** The Q1 index will read DBs the app has never successfully write-opened (new dirs dropped in while running, locked-at-boot DBs).
- **Fix:** Q1: index reads the schema-version marker first (same marker `apply_migrations` maintains — see `storage/migrations.py`) and yields a typed "needs-upgrade/unreadable" entry instead of raising; never auto-migrates from the read layer.

<a id="qf-13"></a>
### QF-13 — Status-label helper covers 2 of 5 axes — **P3 (taxonomy completeness)**
- **Evidence:** `api/templating.py:29-32` registers `translation_status_label`, `job_status_label` (+ 2 badge-class fns). No `review_status_label` / validation / export label globals; `review_queue.html` and future Q badges hand-roll or render raw values.
- **Fix:** Q3 (when the shell lands): extend `api/status_labels.py` to the review axis now, validation/export axes when Q7/Q11 introduce them. Keep DB enums unchanged.

<a id="qf-14"></a>
### QF-14 — Three "preview" surfaces; global `/ui/epub-preview` is a legacy entry — **P3 (IA debt, WV-012)**
- **Evidence:** `/ui/epub-preview` (global, upload-or-pick structure inspector — `ui.py:142`), `/ui/projects/{name}/volumes/{id}/structure` (`ui.py:498`), `/ui/projects/{name}/volumes/{id}/preview` (reading preview — `ui.py:594`).
- **Fix:** Q9 renames the per-volume surface "Content Explorer"; the global route becomes a redirect (or moves under `/ui/new` as "inspect before import", its actual use — SD-7). Document in WV-012 closure.

<a id="qf-15"></a>
### QF-15 — Legacy single-project markdown exporter still present — **P3 (WV-012)**
- **Evidence:** `services/export.py` (markdown export, `connect_readonly_database`, single-project) vs `services/export_book.py` (volume-aware, the cockpit path). Documented as accepted boundary (`docs/WEB_WORKFLOW.md` ~:270).
- **Fix:** Q12 doc-led closure: declare `export_book` canonical for all UI surfaces, `export.py` CLI-only; or schedule deletion post-Q if CLI parity ships. No behavior change required.

<a id="qf-16"></a>
### QF-16 — `qa_warnings` is dead schema with a 3-tier CHECK that would fight WV-008 — **P3 (WV-011)**
- **Evidence:** `schema.sql:125-132` (CHECK `info|warning|critical`); writers: none (grep: schema, `storage/volumes.py:145-155` delete-cleanup, tests). If WV-008 lands a 4-tier severity **and** someone later "wires" this table, the CHECK rejects `error`.
- **Fix:** Q11 decision point (with WV-008, SD-8): **remove** the table (migration v12) + its delete-cleanup; if a "last validated" timestamp is wanted, add a lean `validation_runs` (scope, badge, counts, finished_at) instead of resurrecting a per-segment warning mirror. Recommendation: remove; do not wire.

<a id="qf-17"></a>
### QF-17 — Desktop residual risks: port bind-release race + PATH-resolved sidecar — **P2 (security, accepted-with-eyes-open)**
- **Evidence:** `desktop/src/launch_config.rs:108-118` (bind 127.0.0.1:0 → read port → **drop listener** → child binds later; race documented as accepted per SIDECAR_CONTRACT §6); `launch_config.rs:57-66` (`weaver` resolved via PATH; override env `WEAVER_DESKTOP_SIDECAR`); `docs/INSTALL_DESKTOP.md:142-156` (PyInstaller recommended next).
- **Impact:** A same-user local process could (a) win the port race and receive the WebView's session token, or (b) shadow `weaver` on PATH. Threat model = same-user malware, which could already read the DBs directly — severity bounded, but Q12's desktop smoke must not weaken it (e.g., never log the token; `sidecar.console.log` tees raw stdout — keep token out of all prints).
- **Fix:** No Q code change required. Record in the risk register (R-13); Q12 security smoke greps `sidecar.console.log` + all five logs for the token value.

<a id="qf-18"></a>
### QF-18 — WORKFLOW_BLUEPRINT §1 "sourceless project creation unsupported" is stale — **P3 (doc)**
- **Evidence:** `services/project.py:131-177` (optional source, `project_name` form field), `api/routers/projects.py:166-216`, `/ui/new` form. Shipped post-blueprint.
- **Fix:** Q12 doc pass annotates the blueprint delta as ✅.

<a id="qf-19"></a>
### QF-19 — Dashboard discovery is uncached, sequential, and unbudgeted — **P2 (performance)**
- **Evidence:** `ui.py:105-133` → `discover_projects` per render → per project: readonly open + 1 `GROUP BY` + 8 `COUNT(*)` (`project.py:399-421`). No cache, no budget test anywhere in `tests/`.
- **Impact:** Fine at N≤10 on SSD (~1–5 ms/project warm); unmeasured at N=50 or with 100k-segment DBs (`COUNT(*)` is a table scan).
- **Fix:** Q1 builds the cached index with an explicit budget + a perf smoke test; the dashboard switches to it in Q3.

<a id="qf-20"></a>
### QF-20 — Absolute filesystem paths flow into render contexts — **P3 (cross-project data hygiene)**
- **Evidence:** `dashboard.html:6` renders `books_dir`; `DiscoveredProject.project_toml` and `InspectSummary.source_file`/`output_dir` carry absolute paths into JSON (`projects.py:111-138`) and templates. Single-user local app, so exposure ≈ informational — but the Q index will be the **one** place that aggregates every path on the machine.
- **Fix:** Q1: the index dataclass carries paths **internally** but the route-facing summary exposes only name/uuid/relative display paths; a test asserts no absolute path of one project appears in another project's rendered page, and the queue/dashboard pages render only `books_dir`-relative or basename forms.

<a id="qf-21"></a>
### QF-21 — `snapshot_status`/`status_for_volume` writable-open pile-up — **P3 (perf detail, folded into QF-03/05)**
- **Evidence:** `epub_snapshot.py:222`, `epub_reparse.py:90` — both open writable per call; overview calls both per volume.
- **Fix:** With QF-05's fix (Q2): one readonly connection passed in, or read the snapshot row through the already-open overview connection.

<a id="qf-22"></a>
### QF-22 — No global "active jobs" affordance — **P2 (UX, queue visibility)**
- **Evidence:** `base.html:16-26` (topbar has no jobs entry); jobs reachable only inside a project (`_sidebar.html:20-23`). PAGE_LAYOUT §0 target topbar includes "Active jobs ◍".
- **Fix:** Q3 ships the topbar chip from the in-memory `JobRegistry` (zero DB cost); Q4 links it to the global queue page.

---

## 4. Security audit (Sprint Q lens)

Status legend: ✅ sound today · ◑ sound with caveat · ⚠ gap. "Q action" = what Sprint Q must do (or must not break).

| Surface | Status | Evidence | Risk & Q action |
|---|---|---|---|
| Source browser sandbox | ✅ | `services/source_browser.py:194-204` (`_safe_join`: resolve-then-containment; symlinks resolved before check); suffix allowlist `:21`; upload name sanitization `:118-149`; atomic store `:152-184` | Keep. Q5 resources hub must reuse `resolve_source`-style helpers if it ever lists files; **no new file-listing endpoints outside the sandbox**. |
| EPUB image preview | ◑ | Manifest-id-keyed only; MIME allowlist; 8 MiB cap pre+post; archive-path normalization rejects `../`+absolute (`image_preview.py:20-151`); `Cache-Control: private, no-store`, `nosniff` (`projects.py:584-592`) | Caveat = QF-06 (uncaught `OSError` on stale source → 500) and writable DB open on a read path (QF-03). Fix in Q2. Q9's asset browser must reuse this gate — **no new byte endpoints**. |
| EPUB upload preview | ⚠ | `/projects/epub-preview` reads the whole upload to RAM (`projects.py:99`), parses synchronously; no byte cap (QF-08) | Local-only DoS surface. Q12: byte cap + keep parse synchronous (zipfile module; no extraction to disk beyond the temp file, which is unlinked `projects.py:106-108`). |
| Path normalization / `source_path` | ◑ | `volumes.source_path` + `project.toml source_file` are absolute, trusted, user-owned; resolution fallback `project.py:424-431`/`epub_reparse.py:119-127` (cwd-relative then toml-relative — ambiguity if both exist) | Stale-path failures are handled in preflight (`ui_qa.py:244-255`), not in image preview (QF-06). Q index must treat `source_path` as *display/diagnostic* data only — never auto-open sources from index/render paths (also the QF-05 fix). |
| Logs vs provider secrets | ✅ | Five rotating JSON logs; `scrub_provider_record` strips `key/token/password/secret/authorization/credential` keys (`logging_setup.py:19-21,45`); provider.log never logs prompt or key; CI greps provider.log | Q6 provider hub renders env-var **names** only (existing `_secrets.html` pattern); failures shown from `jobs.error_summary` — ensure provider error strings never embed keys (they don't today; keys are read from env at call time). Q12 smoke: grep all logs + `sidecar.console.log` for any configured key value and the session token. |
| Session token (desktop) | ✅ | 32-byte random hex per launch (`launch_config.rs:120-128`); injected at the network layer for every WebView request incl. SSE/navigations (`webview_session.rs:16-70`); enforced middleware-side for all but `/healthz,/health,/version,/static` (`app.py:50-51,123-134`) | `/static` is intentionally public (assets only, vendored). Q3's new static assets stay under the same mount (`templating.py:35-38`). Do not add token-bearing URLs (token must stay header-only). |
| CORS / desktop mode | ✅ | Desktop: `allow_origins=[]` same-origin-only middleware (`app.py:112-121`); docs off in desktop (`runtime_env.py:39-53`); serve refuses non-loopback host in desktop with exit 64 (`cli/main.py:1319-1323`) | No Q change. Q12 smoke re-verifies 401-without-header on `/ui` in desktop mode. |
| Static assets | ✅ | Vendored dir mount only (`templating.py:24-38`); no CDN; HTMX pinned | Q adds CSS/partials only — no new origins, no web fonts (locked). |
| Local file access (general) | ◑ | All file reads flow through: sandbox (browse/intake), DB-recorded paths (volumes), snapshot-gated bytes (images), output dir (exports) | The Q1 **index** is a new reader of every `project.toml` + DB on the machine: it must read only `.weaver/*/project.toml` (the existing discovery glob), never walk user content. |
| Generated exports | ✅ | Atomic write (`tempfile`+replace), per-volume artifacts under the project's `output/` (`services/export_book.py`); preflight read-only | Q7 ledger stores path/size/hash; Exports hub must **stat**, never open/serve artifact bytes (download stays a future, explicitly-gated decision — not in Q scope). |
| App-data / logs dir | ✅ | OS-aware root (`app_paths.py:96-111`); secrets at `~/.weaver/secrets.toml` mode-restricted (`core/secret_store.py:145`); test mode skips file handlers (`app.py:99-104`) | Q12 smoke confirms `%APPDATA%\Weaver\logs\` gets both `runtime.log` + `sidecar.console.log` and neither contains the token (QF-17). |
| Cross-project index leakage | ⚠ (new surface) | Does not exist yet; today's nearest analog already leaks absolute paths into JSON/templates (QF-20) | **Design rule for Q1:** index entries expose uuid/name/counts/status; absolute paths kept out of route-facing models except the project's own pages. Test asserts the dashboard/queue HTML contains no absolute path other than `books_dir` itself. |
| Stale project references | ◑ | Discovery yields error entries instead of dropping projects (`project_discovery.py:39-42`) — good pattern; image preview 500s on stale source (QF-06) | Q1 index must mirror the error-entry pattern for unreadable/needs-upgrade DBs (QF-12). |
| Project deletion vs index | ◑ | Deletion = `shutil.rmtree` with layout guard (`project.py:88-118`); no index to clean today | Q1: cache invalidation keyed by toml/db path mtime+existence — a deleted project must vanish from the index within one TTL window; test required. Jobs of a deleted project disappear with its DB (acceptable; note in queue UI). |
| Job/result persistence | ✅ | SQLite-durable rows + events + snapshots (Sprint I); cold-start recovery idempotent (`job_store.py:316-373`); locked-DB skip caveat (QF-09) | Q4 queue: render `running` rows not confirmed by the live `JobRegistry` as "stale (recovered next start)" instead of "running". |

---

## 5. Performance audit (Sprint Q lens)

Measured shape of every cost the Q hubs will touch; budgets land in the execution plan (Q1/Q12).

| Cost | Today | Evidence | Q implication |
|---|---|---|---|
| N-project discovery | Per dashboard render: glob `.weaver/*/project.toml` + per project: toml parse + readonly open + 1 `GROUP BY` + 8 `COUNT(*)` (sequential, uncached) | `project_discovery.py:32-71`; `project.py:399-421`; `ui.py:105-133` | ~1–5 ms/project warm on SSD; `COUNT(*)` scans scale with segment count. Q1 index caches per project keyed on (db mtime_ns, -wal mtime_ns, toml mtime_ns); budget: **≤150 ms warm / ≤750 ms cold @ 10 projects** (smoke-tested, non-gating). |
| Opening many SQLite DBs | Open ≈ µs–ms; but `connect_database` adds migration check + UPDATE + commit per open (QF-03); readonly open is clean | `db.py:48-79,82-105` | Index: readonly only; one open per project per refresh; never hold connections across requests (threads must not share — `job_store.py` docstring). |
| WAL read-only caveat | `mode=ro` cannot recover a WAL journal; a DB whose last writer crashed mid-WAL can refuse readonly opens; `-wal`/`-shm` must be readable | `db.py:95-99` (URI ro) | Index catches `sqlite3.Error` per project → error entry (pattern: `DiscoveredProject.error`). Never fall back to a writable open from the read layer. |
| Job summary reads | Per project: `SELECT … FROM jobs` indexed `(project_name,status)`; tiny | `schema.sql:179-180`; `job_store.py:301-314` | Cheap to fan out. Live truth for `running` = in-process `JobRegistry` (`api/jobs.py`); DB rows are history. Queue page = index rows + registry overlay. |
| QA scan | `analyze_novel` loads all segments + latest attempts; O(segments); on-demand only (Gate B1 holds — tree/overview never auto-QA) | `translation_qa.py`; gate respected in `project_overview.py` (counts only) | Analytics (Q8) and dashboard must **never** run QA on render; "validation freshness" comes from Q11's decision (timestamp), not a scan. |
| Snapshot reads | `read_snapshot` = 6 small table reads per volume; cheap. **But** `status_for_volume` = full-file SHA-256 + 2 writable opens (QF-05) | `epub_snapshot.py:214-242`; `epub_reparse.py:85-116` | Index must use stored snapshot rows only. Staleness verification becomes an explicit user action or an mtime+size fast-path. |
| Dashboard render budget | Unbudgeted; no perf test exists | `tests/` (none) | Q1 adds a marked perf smoke (`@pytest.mark.perf`, skipped in CI by default, run in Q12) generating 10 synthetic projects. |
| Cache / read-through / index choice | Nothing cached today | — | **Choose: in-process read-through cache** (dict on `app.state`, per-project entries, invalidated by file mtimes + 2–5 s TTL fallback). **No** persistent global index DB — avoids a second source of truth, honors "no new global mutable store"; revisit via ADR only if N>50 portfolios materialize. |
| Invalidation strategy | n/a | — | Key: `(db_path mtime_ns, db-wal mtime_ns or 0, project.toml mtime_ns)`. Any change → re-read that project only. Deletion → entry dropped (path missing). TTL guards clock-skew/mtime-granularity edge cases. |
| Stale index behavior | n/a | — | Staleness window = TTL (≤5 s) for cross-process writes (CLI translating while cockpit open). Acceptable for dashboards; per-project pages keep reading live (they already do). Document on the page ("updated Ns ago" optional). |
| Safe degraded states | Discovery error entries render as error cards (`dashboard.html:17-21`) | `project_discovery.py:53-61` | Index reuses this: per-project `error`/`needs-upgrade`/`locked` entries; hubs render them; **one bad project never blanks a hub** (test). |

---

## 6. UX audit — residual confusion after Sprint P

Walking the target loop **Import → Inspect → Translate → Review → Validate → Preview → Export → Iterate** against the current cockpit:

| # | Confusion point | Current behavior (evidence) | Q answer (stage) |
|---|---|---|---|
| U-01 | **Global vs project scope** | The only global surfaces are Dashboard/`/ui/new`/Config (`base.html:21-25`); everything else lives behind a project. No visual distinction of scope | Global Workspace sidebar + persistent context bar (Q3) |
| U-02 | **Dashboard vs Project Overview** | Dashboard = flat grid (`dashboard.html`); Overview answers "where am I in *this* project" but nothing answers "where was I across projects" | Dashboard command center: Current Project + In Progress + Recently Completed from the index (Q3) |
| U-03 | **Queue visibility** | Jobs page per project (`ui.py:250`); no global queue; no topbar indicator (QF-22) | Topbar active-jobs chip (Q3) + global queue page (Q4) |
| U-04 | **Active job visibility while elsewhere** | SSE job panel exists only on the page that started the job; elsewhere nothing pulses | Topbar chip (in-memory registry) (Q3) |
| U-05 | **Provider/config visibility** | `/ui/config` edits defaults + secrets; per-project provider visible only inside project.toml; failures only inside job errors | Provider hub: per-project routing table, explicit health check, failure feed, token usage (Q6) |
| U-06 | **Resource discoverability** | Glossary/Characters/Memory are per-project sidebar items (`_sidebar.html:24-35`); nothing says "you have 4 glossaries across this series' projects" | Resources hub (read-only aggregation + copy) (Q5) |
| U-07 | **Export history visibility** | After export, artifacts exist on disk only; the UI forgets them (`volume_lifecycle.py:18-23`) | Export ledger + per-project history + Exports hub (Q7) |
| U-08 | **Review vs Validation clarity** | Much better post-P (Review Queue vs QA pages) — but structure validation still lives on a third page (WV-007), and review labels aren't centrally mapped (QF-13) | QA structure category (Q11); label completion (Q3) |
| U-09 | **Content explorer vs reading preview** | Three "preview" words: global EPUB Preview, per-volume Structure, per-volume Reading Preview (QF-14) | Rename structure surface → Content Explorer; redirect legacy route (Q9) |
| U-10 | **Editor context absence** | Translator leaves the editor for glossary/characters/candidates/history (`workspace.html` 2-col) | Context panel (Q10) |
| U-11 | **Failure invisibility in review actions** | Approve/reject/apply failures are swallowed (QF-04) | Error fragments (Q2; pattern frozen from Q1) |
| U-12 | **Three-question contract** ("what am I working on / progress / next") | Holds on project pages post-P5; absent at workspace level | Context bar + dashboard Current Project card (Q3) |

---

## 7. Docs-vs-code mismatches (fix in Q12 doc pass unless noted)

| # | Doc claim | Reality | Evidence |
|---|---|---|---|
| D-01 | `docs/ARCHITECTURE.md:24` "CLI/web never touch SQLite directly" | ~12 router sites do (QF-02/03) — true again only after Q2 | `ui.py:1067-1075` et al. |
| D-02 | `WORKFLOW_BLUEPRINT.md §1` "sourceless project creation unsupported" | Shipped (QF-18) | `project.py:131-177` |
| D-03 | `WORKFLOW_BLUEPRINT.md §1` "upload-capped" | No cap exists (QF-08; cap lands Q12) | grep |
| D-04 | `project_overview.py:3-4` "no file access beyond a DB read" | Hashes every EPUB volume per render (QF-05; fixed in Q2) | `project_overview.py:125` |
| D-05 | `project.toml [logging] raw_response_logging` implies raw responses are opt-in | Persisted unconditionally (QF-07) | `translation.py:511` |
| D-06 | SOURCEOFARCHITECTURE §6 route targets use `{id}` | Routes use `{name}`; id introduction deferred to Q1 alias + post-Q migration (sub-decision SD-2) | `ui.py` passim |
| D-07 | CLAUDE.md §2.3/§2.5 say Sprint Q "high-level only" | Q0 planning now exists (this package) — CLAUDE.md updated in the Q0 commit | this commit |

---

## 8. Dependency analysis

**Must come first.** Q1 (WV-010: uuid + read layer + cache/invalidation + budgets + leak rules) — every hub (Q3 dashboard blocks, Q4 queue, Q5 resources list, Q6 provider list, Q7 exports hub, Q8 rollups) consumes it. Q2 (read-path & failure-visibility hardening, including the mechanical `ui.py` split — QF-10) precedes all later UI stages.

**Strictly ordered.** Q1 → Q2 → Q3 → Q4 (queue needs the shell + index). Q7's ledger migration (v11) after Q1's uuid migration (v10) — one migration in flight at a time. Q11's `qa_warnings` removal (v12, if chosen) after Q7. Q12 last.

**Parallel-safe in principle** (if the maintainer ever relaxes strict sequence): Q9 (content explorer), Q10 (editor panel), Q11 (validation) are per-project and independent of the index; they could interleave after Q2. The plan still **recommends strict sequence** — it matches the project's one-sprint-at-a-time culture and avoids template collisions.

**Must never be parallel.** Two migration-bearing stages (Q1/Q7/Q11-removal); any two stages editing `base.html`/`_sidebar.html` (Q3 vs Q9/Q10); anything during Q12.

**External dependencies.** None new: uuid (stdlib), no new runtime deps anywhere in Q. ADR 013 is the only governance gate (Q11, `error` tier).

---

## 9. Evidence index (primary anchors)

- Identity/discovery: `services/project_discovery.py:32-102` · `services/project.py:63-117,239-284` · `storage/schema.sql:3-11,153`
- DB layer: `storage/db.py:13,48-105,132-145` · `storage/migrations.py:60,472`
- Read-layer exemplars: `services/project_overview.py:80-86` (readonly) vs `api/routers/ui.py:1067` (writable in router)
- Router violations: `api/routers/ui.py:1057-1110,1159,1229,1334,1414` · `api/routers/candidates.py:125,256` · `api/routers/jobs.py:82,99`
- Overview hashing: `services/project_overview.py:111-140` · `services/epub_reparse.py:85-116` · `services/epub_snapshot.py:71-77,214-242`
- Jobs: `api/app.py:85-97` · `services/job_store.py:88-97,301-373` · `api/jobs.py` (registry)
- Security: `services/source_browser.py:194-204` · `services/image_preview.py:20-164` · `api/app.py:50-51,112-134` · `services/runtime_env.py` · `core/secret_store.py` · `services/logging_setup.py:19-45` · `desktop/src/{launch_config,webview_session,sidecar}.rs`
- QA/export: `qa/checks.py:12` · `qa/report.py:84-90` · `api/routers/ui_qa.py:180-282` · `services/volume_lifecycle.py:18-23` · `services/export_book.py` · `services/export.py`
- Sprint P deliverables: `api/status_labels.py` · `api/templating.py:29-32` · `services/{segment_review,reading_preview,project_overview}.py` · `storage/schema.sql:51-57`
- Templates/nav: `templates/base.html:16-33` · `partials/_sidebar.html` · `templates/dashboard.html` · routes grep of `api/routers/*`
