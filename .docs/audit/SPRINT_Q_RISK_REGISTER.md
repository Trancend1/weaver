# Sprint Q — Workspace v2 · Risk Register

> **Scope.** Risks for executing Sprint Q per [SPRINT_Q_EXECUTION_PLAN](SPRINT_Q_EXECUTION_PLAN.md) (stages Q0–Q12), grounded in [SPRINT_Q_DEEP_AUDIT](SPRINT_Q_DEEP_AUDIT.md) evidence (`QF-xx`/`G-xx`/`D-xx`) and the [ISSUE_BACKLOG](ISSUE_BACKLOG.md) (`WV-xxx`).
> **Levels.** Likelihood × Impact, each L/M/H. **Level** = the larger of the two when they disagree by one step, H when both H, L when both L. "Owner stage" = where the mitigation is built or enforced; "Trigger" = the early-warning sign that the risk is materializing.
> **Status.** All risks OPEN at Q0 unless marked *(accepted)* — accepted risks are consciously carried with a monitoring action instead of a fix.

---

## 1. Architecture & data integrity

### R-01 — Read routes using writable DB connections
- **Linked:** QF-03 · blocker 3. **Likelihood/Impact/Level:** H / H / **H**.
- **Description.** `connect_database` is used for pure reads in ~12 router/service paths (`ui.py:1067,1159,1229,1334,1414`, `candidates.py:125,256`, `jobs.py:82,99`, `epub_snapshot.py:222`, `epub_reparse.py:90`, `image_preview.py:155`). Every such open applies migrations, runs `reset_interrupted_segments`, commits, and briefly takes WAL writer locks against live jobs. A cross-project layer copying this pattern would fan write side-effects across **every DB on the machine**.
- **Mitigation.** Q1: the index uses `connect_readonly_database` exclusively + a **no-write test** (db bytes/mtime unchanged after index build). Q2: existing read paths converted to readonly. Permanent grep-gate: no `connect_database(` under `api/routers/`.
- **Trigger.** A test DB's mtime changes after a GET-only test pass; the grep-gate fails in review.

### R-02 — Migrations / `in_progress` reset firing on read opens
- **Linked:** QF-03, QF-09, QF-12 · blocker 4. **L/I/Level:** H / M / **H**.
- **Description.** `storage/db.py:48-79,132-145` couples open-for-write with migrate+reset. Consequences today: a candidates-list render can migrate a schema mid-session and reset a live job's `in_progress` segment to `pending` (mid-job stomp); at boot, `recover_all_projects` silently auto-migrates every project on the machine.
- **Mitigation.** Q2 item 4: relocate `reset_interrupted_segments` to explicit recovery points (serve startup, CLI write-entry); migration application remains only on genuine write paths; regression test for the stomp race; MAINTENANCE documents the boot-time auto-migration as intended behavior.
- **Trigger.** A segment flips `in_progress → pending` while a job is running (observable in the QF-03 race test); user reports a "pending" segment that was mid-translation.

### R-03 — Cross-project index data leakage
- **Linked:** QF-20 · audit §4 "cross-project index leakage". **L/I/Level:** M / M / **M**.
- **Description.** The Q1 index is the first component aggregating every project's identity, counts, paths, and job state. Today's nearest analog already pushes absolute paths into JSON/templates (`projects.py:111-138`, `dashboard.html:6`). A leaked `source_path`/`project_toml` from project A rendered inside project B's page (or a hub) discloses filesystem layout and breaks the mental model of project isolation.
- **Mitigation.** Q1: route-facing index models expose **no absolute paths**; leak-rule unit test. Q3/Q4/Q7: rendered-HTML grep — hub pages contain no absolute path beyond `books_dir` itself; Q7 hub shows project-relative/basename artifact paths. Q12 security smoke re-runs the grep on a live instance.
- **Trigger.** Leak grep finds an absolute path in hub HTML; a `ProjectIndexEntry` field with a `Path` type appears in a template context.

### R-04 — Stale index after project delete / import / export
- **Linked:** audit §5 invalidation row · G-02. **L/I/Level:** M / M / **M**.
- **Description.** A cached index can show a deleted project, miss a just-imported one, or show stale counts after a CLI run in another process. Worst case: a hub action targets a project whose directory is gone (`shutil.rmtree` deletion, `project.py:117`).
- **Mitigation.** Q1: cache keyed on `(project.toml mtime_ns, db mtime_ns, -wal mtime_ns)`; missing paths drop entries; TTL fallback ≤5 s bounds cross-process staleness; deletion test (project vanishes within one TTL window). Hubs render from the index but **act** through per-project routes that re-resolve via discovery (404 path already exists).
- **Trigger.** Deleted-project card persists past TTL in manual testing; a hub deep-link 404s on a project the index still lists.

### R-17 — Duplicate identity after directory copy
- **Linked:** QF-11 · SD-1. **L/I/Level:** M / M / **M**.
- **Description.** `projects.uuid` (v10) travels with the DB file; copying `.weaver/<name>` duplicates the uuid. Auto-regenerating on detection would silently re-identify a project (worse than the collision).
- **Mitigation.** Q1: discovery flags **both** entries `identity_conflict`; hubs render the conflict and disable copy/aggregation actions for them; resolution is a deliberate user action (documented in MAINTENANCE).
- **Trigger.** Two index entries share a uuid in the duplicate-uuid test or a real workspace.

### R-21 — Export ledger drifts from disk artifacts
- **Linked:** Q7 (WV-009). **L/I/Level:** M / L / **M**.
- **Description.** Users delete/move `output/` artifacts; ledger rows outlive files (or vice versa after manual exports through the legacy CLI path, QF-15).
- **Mitigation.** Q7: history rows verify existence via `stat` on render → "missing" state (never an error); the ledger records, it does not own, files; legacy CLI exporter documented as outside the ledger (Q12a item 3).
- **Trigger.** History rows render as errors instead of "missing"; user confusion reports.

### R-15 — Migration sequencing collisions
- **Linked:** v10 (Q1), v11 (Q7), v12 (Q11, conditional). **L/I/Level:** L / H / **M**.
- **Description.** Two in-flight migration branches would race for the same `SCHEMA_VERSION` slot and produce divergent `schema.sql` mirrors.
- **Mitigation.** Plan rule: one migration-bearing stage at a time, in order; each migration PR bumps `storage/db.py:13`, mirrors `schema.sql`, ships forward + idempotency tests + MAINTENANCE note before the next migration stage starts.
- **Trigger.** Two open PRs both touching `storage/migrations.py`.

### R-12 — Global mutable store overreach
- **Linked:** premise rule · SD-3 · G-06. **L/I/Level:** M / H / **H**.
- **Description.** Resources/Analytics/Index pressure tends toward "just add a workspace.db" — a second source of truth that breaks one-DB-per-project, complicates deletion, and reopens every sync question.
- **Mitigation.** Plan rule (§0): the cross-project layer is read-only; Resources = read-only aggregation + explicit copy with skip-on-conflict; user-authored template store explicitly deferred to an ADR (SD-3); any persistent index store requires an ADR (audit §5 cache row pre-decides in-process cache).
- **Trigger.** Any Q PR creating a DB file outside `.weaver/<project>/`; a "workspace settings/resources" table appears in a migration.

---

## 2. Security & privacy

### R-05 — PATH / `source_path` leakage
- **Linked:** QF-20 · audit §4 path rows. **L/I/Level:** M / M / **M**.
- **Description.** `project.toml [project] source_file`, `volumes.source_path`, `project_toml` locations, and `books_dir` are absolute user-machine paths. They already surface in JSON (`/projects` list) and dashboard meta. New hubs multiply the rendering surface; the export ledger adds `artifact_path`.
- **Mitigation.** Same machinery as R-03 (leak-rule test + HTML grep); per-project pages may show the project's **own** paths (user's own data), hubs show relative/basename forms; index keeps paths internal.
- **Trigger.** Leak grep failure; review spots a `Path` rendered raw in a hub template.

### R-06 — App-data / logs privacy
- **Linked:** QF-17 · audit §4 logs row. **L/I/Level:** L / M / **M** *(partially accepted)*.
- **Description.** Five rotating JSON logs + `sidecar.console.log` accumulate activity (project names, event metadata) under `%APPDATA%/Weaver/logs`. The tee writes raw child stdout/stderr — anything ever printed lands on disk. Translations' `raw_response` accumulates provider output in every project DB (QF-07).
- **Mitigation.** Existing scrubber (`logging_setup.py:19-45`) stays mandatory for provider events; Q12a honors `raw_response_logging` (default off stops DB accumulation); Q12 security smoke greps all logs for key values + session token. Accepted residual: event metadata (names/counts) in local logs is by design for a local tool.
- **Trigger.** Any log line containing a configured key value or token (smoke grep); `raw_response` still persisted with the flag false after Q12a.

### R-07 — Provider key leakage
- **Linked:** audit §4 secrets row · Q6. **L/I/Level:** L / H / **M**.
- **Description.** Q6 renders provider config; Q4/Q7 render job errors. A careless template or error string could surface a key (env value or secrets.toml content) in HTML, SSE, or logs.
- **Mitigation.** Names-only pattern (`_secrets.html`, `list_secret_names`) reused verbatim; `error_summary` strings are service-authored and key-free (keys are read from env at call time, never embedded in `WeaverError` messages — invariant stated in plan §0); permanent regression: seed a fake secret, grep rendered hub HTML (Q6 test) + Q12 smoke grep across logs/SSE.
- **Trigger.** The Q6 regression or Q12 grep finds a key fragment anywhere.

### R-13 — Desktop residuals: port bind-release race + PATH-resolved sidecar *(accepted)*
- **Linked:** QF-17. **L/I/Level:** L / M / **M** *(accepted with monitoring)*.
- **Description.** `launch_config.rs:108-118` frees the chosen port before the child binds (a local process could win the race and receive the WebView's session token); `launch_config.rs:57-66` resolves `weaver` via PATH (same-user PATH hijack). Threat model = same-user malware, which could already read the DBs directly.
- **Mitigation (monitoring, no Q code).** Documented in INSTALL_DESKTOP known limitations; PyInstaller-bundled sidecar (post-Q) closes the PATH vector; Q12 smoke confirms the token never appears in logs (limits blast radius of a race win to one session). `desktop/` stays untouched in Q.
- **Trigger.** Sidecar fails to bind its assigned port at launch (the race's benign symptom — crash screen).

---

## 3. Performance

### R-08 — QA scan (or provider call) on dashboard/hub render
- **Linked:** Gate B1 · audit §5 QA row · G-03. **L/I/Level:** M / H / **H**.
- **Description.** The fastest way to "rich" dashboard numbers is calling `analyze_novel` or provider healthchecks on render — O(all segments) per project × N projects, plus real money for cloud providers. Sprint P already enforced Gate B1 per-project; the workspace scale makes a breach an order of magnitude worse.
- **Mitigation.** Plan §0 extends Gate B1 to all hub renders (no QA, no provider calls, no hashing); Q6 healthcheck is an explicit per-project button (R-22); Q8 QA-dependent metrics sit behind an explicit action; spy-based tests assert zero QA/provider invocations on render.
- **Trigger.** A render-path test observes a QA/provider call; dashboard latency jumps with segment counts rather than project counts.

### R-09 — Source EPUB hashing on every render
- **Linked:** QF-05/QF-21 · blocker 5. **L/I/Level:** H (today) / H / **H**.
- **Description.** `project_overview` → `status_for_volume` → `compute_source_hash` reads + SHA-256s every EPUB volume per project-page render (~hundreds of MB for a large series), plus two extra writable opens per volume. Any index/dashboard reusing `status_for_volume` inherits it × N projects.
- **Mitigation.** Q1: index never hashes (rule + spy test); Q2 item 6: overview renders snapshot state from the stored row + `(mtime_ns,size)` fast-path; full hashing only behind explicit reparse/staleness actions. Residual: an mtime-preserving overwrite reads as fresh — accepted, one explicit click verifies.
- **Trigger.** File-read spy fires during overview/dashboard render tests; project page latency scales with EPUB sizes.

### R-10 — N+1 SQLite open cost / uncached fan-out
- **Linked:** QF-19 · audit §5 discovery row. **L/I/Level:** M / M / **M**.
- **Description.** Today every dashboard render re-opens every project DB (~9 queries each, sequential, uncached). Naive hubs would multiply this per page per poll.
- **Mitigation.** Q1: one shared read-through cache (mtime-keyed + TTL ≤5 s); budget test (≤150 ms warm / ≤750 ms cold @ 10 synthetic projects, `@pytest.mark.perf`); hubs consume the cache, never fan out themselves; Q4 poll reuses the existing interval (no tighter loops).
- **Trigger.** Budget test red; dashboard/queue latency grows linearly with N while cached.

### R-18 — WAL read-only open failures on recovery-needed / locked DBs
- **Linked:** QF-12 · audit §5 WAL row. **L/I/Level:** M / L / **M**.
- **Description.** `mode=ro` cannot recover a WAL journal: a DB whose last writer crashed, or one mid-write by a CLI process, can refuse readonly opens; a v8 DB read by v9+ code errors on missing columns.
- **Mitigation.** Q1: per-project `try/except (WeaverError, sqlite3.Error)` → typed `locked`/`error`/`needs_upgrade` entries (schema-version guard read before column access); **never** fall back to a writable open from the read layer; hubs render degraded entries (one bad project never blanks a hub — test).
- **Trigger.** Index test with a held-writer DB raises instead of degrading; a hub page 500s on one bad project.

---

## 4. UX & product honesty

### R-11 — Swallowed approve/apply failures (silent-failure pattern spreads)
- **Linked:** QF-04 · blocker 6 · anti-slop gate 5. **L/I/Level:** H (exists) / M / **H**.
- **Description.** `except WeaverError: pass` and three `suppress(HTTPException)` blocks make failed review actions look like success. Risk is double: the existing defect, and the pattern being copied into six new hubs.
- **Mitigation.** Q2 item 5 fixes the existing sites (error fragments); permanent grep-gate bans the patterns under `api/routers/`; plan §0 makes it a stage-gate rule from Q1.
- **Trigger.** Grep-gate failure; a hub action that fails server-side renders an unchanged fragment.

### R-19 — Ghost `running` jobs in the global queue
- **Linked:** QF-09. **L/I/Level:** M / M / **M**.
- **Description.** Boot-time recovery skips locked/broken DBs (`job_store.py:369-371`), leaving orphaned `running` rows; jobs of other processes (CLI) are invisible to the in-process registry. A naive queue renders both as live forever.
- **Mitigation.** Q1: `stale_running` classification (DB `running` ∧ not in live `JobRegistry`); Q4 renders it distinctly ("stale — will be recovered on next start"); no hub-side "fixing" of rows (recovery stays a startup concern, ADR 010).
- **Trigger.** A `running` row older than the process uptime renders as live.

### R-16 — UI-test churn / HTMX hook breakage in the shell stage
- **Linked:** QF-10 · Sprint P P4 precedent. **L/I/Level:** H / M / **H**.
- **Description.** Q3 (global sidebar + context bar + dashboard blocks) is the largest template diff of the sprint; P4 was the highest-churn stage of Sprint P. Breaking a pinned hook (`#tree`, `#job-panel`, `id="seg-{id}"`, …) silently kills HTMX swaps.
- **Mitigation.** Q2 PR-a (router split) lands first and alone; Q3 is one PR after it settles; pinned tests updated in the same PR; hook list frozen in plan §0; no other template-heavy stage runs concurrently.
- **Trigger.** Pinned-test failures spanning multiple files; an HTMX swap stops working in manual demo.

### R-22 — Provider healthcheck cost abuse
- **Linked:** Q6 · R-08 family. **L/I/Level:** L / M / **M**.
- **Description.** A "check all" affordance or an eager poll would fire real provider calls (cost/quota/latency) across every project.
- **Mitigation.** Q6: per-project explicit button only; no bulk action; no auto-refresh of health fragments; FakeProvider call-counter test asserts zero calls on hub GET.
- **Trigger.** Provider logs show healthchecks the user didn't click; quota complaints.

---

## 5. Process, scope & maintainability

### R-14 — Workspace v2 scope creep
- **Linked:** plan §0 fences · Council deferral history. **L/I/Level:** H / H / **H**.
- **Description.** Sprint Q's surface invites adjacent wishes: cross-project TM lookup during translation, shared glossary store, SSE fan-in, queue priorities, artifact downloads, currency cost estimates, OCR, editor rewrites, route `{id}` migration. Each is individually plausible; together they sink the sprint.
- **Mitigation.** Every stage carries an explicit out-of-scope list; sub-decisions (SD-1..SD-10) pre-commit the default answer; anything requiring a new store/dep/provider/queue → ADR, post-Q; the stage gate fails on undocumented scope.
- **Trigger.** A stage PR touches files outside its "files likely touched" list without a recorded reason; a new table/dep appears without an SD/ADR reference.

### R-20 — ADR-013 governance stall (WV-008 `error` tier)
- **Linked:** Q11 · WV-008. **L/I/Level:** M / L / **M**.
- **Description.** The `error` severity tier contradicts ADR 008; if the ADR decision stalls, WV-008 risks blocking Q11.
- **Mitigation.** Pre-authorized fallback (audit + plan): ship the four checks at existing tiers and drop the tier; the ADR is written first so the decision point is explicit, not implicit.
- **Trigger.** Q11 PR open >1 review cycle on the tier question — invoke the fallback.

### R-23 — Router/module size and merge conflicts
- **Linked:** QF-10. **L/I/Level:** M / M / **M**.
- **Description.** `api/routers/ui.py` ≥1414 lines; six later stages add routes. Without the split, every stage PR conflicts with every other in one file.
- **Mitigation.** Q2 PR-a mechanical split (zero behavior change, pinned tests unmodified as proof); later stages add routes only to their domain module.
- **Trigger.** Two stage PRs conflict in `ui.py`; a module crosses 400 lines again.

---

## 6. Coverage map (required-risk checklist)

| Required risk (Q0 instruction) | Register id |
|---|---|
| Read routes using writable DB connections | R-01 |
| Migrations/reset on read | R-02 |
| Cross-project index data leakage | R-03 |
| Stale index after project delete/import/export | R-04 |
| PATH/source_path leakage | R-05 (paths) + R-13 (desktop PATH resolution) |
| App-data/logs privacy | R-06 |
| Provider key leakage | R-07 |
| QA scan on dashboard render | R-08 |
| Source EPUB hashing on every render | R-09 |
| N+1 SQLite open cost | R-10 |
| Swallowed approve/apply failures | R-11 |
| Global mutable store overreach | R-12 |
| Workspace v2 scope creep | R-14 |

**Additional risks carried:** R-15 (migration sequencing), R-16 (UI-test churn), R-17 (duplicate identity), R-18 (WAL readonly failures), R-19 (ghost running jobs), R-20 (ADR-013 stall), R-21 (ledger/disk drift), R-22 (healthcheck cost), R-23 (router size/conflicts).

**Review cadence.** Re-walk this register at every stage gate; close or re-level risks with evidence (test name / grep / smoke result) in the stage PR. New risks discovered mid-sprint get `R-24+` ids here, not ad-hoc notes.
