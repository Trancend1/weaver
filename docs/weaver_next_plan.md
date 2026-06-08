# Weaver Next Roadmap — HTMX-first, FastAPI-stable, Tauri-sidecar-ready

> **Status:** Active forward-looking roadmap (Phase F shipped on `feat/epub-metadata-parse`).
> **Supersedes:** the "Phase Final — npm `@weaver/cli` wrapper" entry in `CLAUDE.md §2.1`.
> npm wrapper is **deferred legacy** — not a parallel track; revisiting it requires a new ADR.
> **Governs:** Sprint G through Sprint O (the post-Phase-F sequence).
> **Reference ADRs:** ADR `009` (strategic pivot Tauri-sidecar-ready), ADR `010` (persistent job core, SQLite in-process), ADR `011` (Project terminology consolidation). ADR `012` (image preview/OCR security gate) lands inside Sprint M (gate B).

---

## 0. Strategic Baseline

Current state:

```text
HTMX-first         = done
FastAPI-stable     = partial   (no health/version, dev-path assumptions, in-process jobs only)
Tauri-sidecar-ready = not started
```

Locked direction:

```text
Keep:
  FastAPI · Jinja2 + HTMX · Tailwind tokens (DESIGN_NOTES.md) · SQLite (WAL, no ORM)
  CLI surface (typer + rich)

Prepare:
  Tauri sidecar compatibility (FastAPI as a local 127.0.0.1 service the shell launches)

Reject (unchanged from CLAUDE.md §3):
  NiceGUI · UI rewrite to Vue/React/Svelte · SPA bundler · Celery/Redis/RQ · external worker
  npm `@weaver/cli` wrapper (deferred legacy — was the prior plan; replaced by Tauri sidecar)
```

Strategy:

```text
HTMX-first  →  FastAPI-stable  →  Tauri-sidecar-ready  →  Tauri shell alpha  →  Desktop packaging
```

Five hard rules carried into every sprint below:

1. HTMX remains the UI; no SPA migration, no UI rewrite.
2. FastAPI is the **only** boundary for runtime, project, job, export, and future desktop shell.
3. Tauri is a **packaging shell** wrapping the existing local FastAPI cockpit — not a reason to rewrite anything.
4. All long-running tasks are **backend-owned, persistent, and refresh-safe** (ADR `010`).
5. State writes go through services; UI templates carry no business logic (CLAUDE.md §4.2).

---

## 1. Dependency Map

Execution order is dependency-driven, not calendar-driven:

```text
Sprint G  Runtime Contract
  → Sprint H  Project / Volume UX & Lifecycle (rename Novel → Project; ADR 011)
    → Sprint I  Persistent Job Core (SQLite-backed in-process; ADR 010)
      → Sprint J  EPUB Preservation Snapshot (persist Phase F ParsedEpub)
        → Sprint K  Export Fidelity Wiring (consume Phase F + snapshot)
          → Sprint L  Candidate Review + Character Text Draft
            → Sprint M  Image Preview / OCR Gate (ADR 012, then optional impl)
              → Sprint N  Tauri Shell Alpha
                → Sprint O  Production Desktop Packaging
```

Rationale for the ordering:

- Tauri needs a FastAPI that starts deterministically, exposes health, uses an app-data path, and shuts down cleanly.
- The Project / Volume contract is the anchor every other sprint binds to (snapshots, jobs, exports, reviews).
- Persistent jobs must precede parse-as-job, export-as-job, OCR-as-job; otherwise each workflow re-invents progress.
- Export fidelity is only safe once the preservation snapshot it consumes is stable.
- OCR and image preview block on a security ADR (path traversal, MIME allowlist, byte exposure policy).
- Tauri shell itself comes last so we package a stable backend, not a moving target.

---

## 2. Roadmap — Sprint G through Sprint O

Each sprint declares: Goal · Why-now · In-scope · Out-of-scope · Output · Acceptance Criteria · Risks.

---

### Sprint G — FastAPI Stability & Tauri-Ready Runtime Foundation

**Goal.** Stabilize FastAPI as the runtime spine of Weaver and ship the contracts a Tauri sidecar will eventually rely on. **Not** a Tauri migration — a blocker sprint that prevents rework in Sprints H–O.

**Why first.** Without it, every later sprint will re-invent app-data paths, hardcoded ports, missing health checks, missing structured logs, and informal startup/shutdown behavior.

**In-scope.**

1. Runtime endpoints:
   ```text
   GET /healthz          — liveness, returns {ok, ts}
   GET /version          — package version + git sha (if available)
   GET /runtime/status   — env mode, port, app-data dir, log dir
   ```
2. Runtime config (env vars; CLI flags override):
   ```text
   WEAVER_HOST    default 127.0.0.1
   WEAVER_PORT    default 8765 (auto when 0)
   WEAVER_ENV     dev | desktop | test
   WEAVER_DOCS    true | false  (auto false in desktop)
   ```
3. App-data directory abstraction (`services/app_paths.py`):
   ```text
   workspace_dir   database_dir   cache_dir
   export_dir      logs_dir       temp_dir       config_dir
   ```
   All resolved from one root: `~/.weaver/` (POSIX), `%APPDATA%/Weaver/` (Windows), `~/Library/Application Support/Weaver/` (macOS). Override via `WEAVER_DATA_DIR`. Existing `~/.weaver/secrets.toml` location preserved.
4. Remove dev-path assumptions from production code paths (audit logged in G1).
5. HTMX assets and template URLs use **relative** paths (already mostly true; verify `hx-get`, `hx-post`, static asset `<link>` / `<script>`).
6. Structured logging baseline (`services/logging_setup.py`), files in `logs_dir`:
   ```text
   runtime.log  backend.log  job.log  export.log  provider.log
   ```
   JSON lines, rotation 10 MiB × 5 files. No secrets/keys.
7. Desktop security baseline (auto-applied when `WEAVER_ENV=desktop`):
   ```text
   bind 127.0.0.1 only (refuse 0.0.0.0 startup)
   /docs and /redoc disabled
   CORS: same-origin only
   session token draft (header `X-Weaver-Session`, optional in dev, required in desktop)
   ```
8. Sidecar contract document `docs/SIDECAR_CONTRACT.md`:
   ```text
   start backend → poll /healthz → open webview → send session token → graceful shutdown
   stdout/stderr conventions (one structured log line per event, no ANSI in desktop mode)
   exit code map (0 clean, 64 config error, 65 port-in-use, 66 data-dir error)
   ```

**Out-of-scope.**

- Tauri app itself · `.msi`/`.dmg` installer · auto-updater · code signing · Rust command bridge · any UI rewrite.

**Output.** A FastAPI runtime that boots deterministically, exposes health/version, writes logs to a known place, refuses unsafe binds in desktop mode, and ships a sidecar contract Tauri can implement against in Sprint N.

**Acceptance Criteria.**

- `weaver serve` (dev) and `weaver serve --env desktop` both start; desktop refuses `--host 0.0.0.0`.
- `curl 127.0.0.1:<port>/healthz` returns `{"ok": true, ...}` within 2 s of start.
- `curl /version` returns the wheel version; `curl /runtime/status` reports the resolved data dir.
- App-data dir is created on first start; **no** workflow writes outside it (covered by a path-leak test).
- HTMX UI works when port is changed via `WEAVER_PORT` (manual + test client).
- `logs_dir/runtime.log` contains one structured start line; `provider.log` contains zero API keys (regression test).
- `docs/SIDECAR_CONTRACT.md` exists and is referenced from `CLAUDE.md §1`.
- Gate green: tests pass + 0 pyright + ruff clean + clean wheel build.

**Risks & mitigations.**

- *Risk:* logging breaks soak script. *Mitigation:* keep stdout summary; structured JSON only to file.
- *Risk:* app-data move breaks existing local DBs. *Mitigation:* detect legacy `.weaver/` in CWD and emit a one-time `runtime.log` warning + CLI hint; do **not** auto-migrate in G.

#### Sprint G Task Order

| Step | Output | Gate |
|------|--------|------|
| G1 — Runtime audit | List of dev-only assumptions: hardcoded paths, host strings, port assumptions, missing health, scattered loggers. | All assumptions identified, file:line referenced. |
| G2 — App-data contract | `services/app_paths.py` + tests; integration in DB open / export / logs / cache. | No workflow writes outside `app_paths.*`. |
| G3 — Health / version / status | `api/routers/runtime.py`. | Endpoints respond < 50 ms cold. |
| G4 — Relative-route + asset hardening | Audit + fixes in templates and `app.css`. | UI works on `WEAVER_PORT=0` (random). |
| G5 — Desktop security baseline | Env mode dispatch, bind guard, CORS rule, docs toggle, session-token middleware (optional). | Desktop mode test refuses 0.0.0.0 + serves no `/docs`. |
| G6 — Structured logging | `services/logging_setup.py` + 5 named files. | Failure traceable from logs alone. |
| G7 — Sidecar contract doc | `docs/SIDECAR_CONTRACT.md`. | Doc references actual endpoints + exit codes. |
| G8 — Final gate | Runtime readiness report appended to phase log. | Sprint H may start. |

---

### Sprint H — Project & Volume Lifecycle Contract (Novel → Project rename)

**Goal.** Lock the hierarchy `Project → Volume → Chapter → Segment` end-to-end, finish the **Novel → Project** terminology consolidation, and give every Volume an explicit lifecycle status the UI and downstream sprints can rely on.

**Why after G.** Project / Volume is the anchor every downstream sprint binds to (snapshots in J, fidelity in K, candidates in L, image scope in M). If the contract drifts later, all those sprints need migrations.

**Existing baseline (do not re-invent).**

- Schema already uses `projects` and `volumes` tables (`storage/schema.sql`), not `novels`. **No table rename needed.**
- ADR 006 named the top tier "Novel" in copy; ADR `011` retires that label.
- `weaver init <epub>` already creates project + first volume in one transaction; `weaver import <project.toml> <source>` adds more volumes (ADR `006`).
- Volume delete exists in the CLI (`weaver delete`) and Phase E added `services/project.delete_project` with a path guard.

**In-scope.**

1. **Terminology consolidation** — replace "Novel" with "Project" across user-facing copy, route helpers, template strings, CLI help text, and docs. Schema column names stay (`projects.id`, `volumes.project_id`). Code symbols may keep `project` already in use; rename happens only where a stray `novel` survives (audit in H1).
2. **Volume lifecycle status** — add `volumes.status TEXT NOT NULL DEFAULT 'imported'` (schema v3 → v4 migration), with constraint:
   ```text
   created · imported · parsed · ready_for_translation ·
   translation_in_progress · translated · ready_for_export · exported · failed
   ```
   Status is derived/updated by the existing services (import, parse, translate, export); no new background job introduced here.
3. **Endpoint contract** (use existing routes; **add only what's missing**, do not re-design URLs):
   ```text
   GET    /projects                                    (exists)
   GET    /projects/{project}                          (exists)
   POST   /projects                                    — explicit create (without import); new
   PATCH  /projects/{project}                          — rename / metadata; new
   DELETE /projects/{project}                          (exists via UI; expose JSON parity)
   GET    /projects/{project}/volumes                  — list with status; new (was implicit)
   POST   /projects/{project}/volumes                  — wraps `import_source`; new
   GET    /projects/{project}/volumes/{volume_id}      — detail; new
   DELETE /projects/{project}/volumes/{volume_id}      — new
   ```
4. **UI** — project list, project detail (volume cards already shipped in Phase E), volume detail, add volume, delete volume, inspect volume. Every volume card surfaces its lifecycle status.
5. **Status propagation hooks** in existing services: `import_source.py`, `translation.py`, `batch_translate.py`, `export_book.py` set status transitions inside their existing transactions.

**Out-of-scope.**

- Full export redesign (Sprint K).
- AI candidate review (Sprint L).
- OCR / image preview (Sprint M).
- Tauri shell (Sprint N).

**Output.** Weaver has one consistent term ("Project"), every volume carries a queryable lifecycle status, and the volume CRUD surface is explicit JSON + HTMX — ready to be consumed by snapshot, fidelity, review, and OCR workflows.

**Acceptance Criteria.**

- `grep -RIn "Novel\|novel" src/weaver` returns only intentional residue (schema/ADR history); audit doc records each survivor.
- User can create an empty project without an import; import then attaches a Volume.
- User can delete a volume without deleting the project (covered by existing test + new path-guard test).
- Volume detail page shows lifecycle status; status changes when import / translate / export complete.
- `GET /projects/{project}/volumes/{volume_id}` returns volume + chapter count + status + last activity ts.
- Schema migration v3 → v4 ships with: forward migration test, idempotency test, rollback note in `docs/MAINTENANCE.md`.
- Gate green.

**Risks & mitigations.**

- *Risk:* status fields drift from real workflow state. *Mitigation:* status transitions live inside the same SQLite transaction as the service that changes the underlying data; never a separate "status updater".
- *Risk:* rename breaks bookmarks / CLI scripts. *Mitigation:* CLI keeps `weaver init` / `weaver inspect` names; only output copy changes.

---

### Sprint I — Persistent Job Core & Realtime Contract

**Goal.** Promote every long-running task to a **persistent, refresh-safe, single-process** job model: SQLite-backed registry, standardized status + progress schema, SSE live stream, polling fallback, and one Job Detail UI used by all workflows.

**Why before J/K/L/M.** Parse, export, OCR, AI candidate generation are all long-running. If we land them before the job model, each workflow grows its own progress handling.

**Hard architectural boundary (ADR `010`).** `src/weaver/api/jobs.py:8-10` stays in force:

```text
Allowed:    FastAPI process → in-process JobRegistry → worker threads → SQLite persistence
Forbidden:  Celery · Redis · RQ · external worker daemon · multi-process/multi-node queue
```

SQLite is the **durability layer**, not a queue. Workers remain `threading.Thread`. The locked stack (CLAUDE.md §3) is untouched.

**In-scope.**

1. **Schema (v4 → v5).** Three additive tables; foreign-keys reference `projects(id)` and `volumes(id)`:
   ```text
   jobs (
     id TEXT PRIMARY KEY,            -- uuid4 hex (matches current JobRegistry ids)
     kind TEXT NOT NULL,             -- import | parse | translate_chapter | batch_translate | export | ocr
     project_id INTEGER REFERENCES projects(id),
     volume_id INTEGER REFERENCES volumes(id),
     chapter_id TEXT REFERENCES chapters(id),
     status TEXT NOT NULL CHECK (status IN (
       'queued','running','processed','finalizing','completed','failed','cancelled'
     )),
     total_units INTEGER NOT NULL DEFAULT 0,
     done_units INTEGER NOT NULL DEFAULT 0,
     failed_units INTEGER NOT NULL DEFAULT 0,
     skipped_units INTEGER NOT NULL DEFAULT 0,
     current_label TEXT,
     error_summary TEXT,
     started_at TEXT NOT NULL,
     finished_at TEXT,
     created_by TEXT
   );

   job_events (                       -- already exists; extend rather than re-create
     id INTEGER PRIMARY KEY,
     job_id TEXT REFERENCES jobs(id), -- new column; migrate existing rows to NULL
     event TEXT NOT NULL,
     data_json TEXT,
     created_at TEXT NOT NULL
   );

   job_progress_snapshots (
     job_id TEXT REFERENCES jobs(id),
     snapshot_at TEXT NOT NULL,
     done_units INTEGER NOT NULL,
     total_units INTEGER NOT NULL,
     PRIMARY KEY (job_id, snapshot_at)
   );
   ```
2. **Registry refactor.** `api/jobs.py` JobRegistry persists `TranslationJob`, `BatchJob`, `ExportJob` to `jobs` on submit, on terminal event, and on cancel. In-memory state stays for live SSE; SQLite is the read-back on refresh / cold start.
3. **Cold-start recovery.** On FastAPI startup: mark any `running` row as `failed` with `error_summary = "process restart"`; this is the **only** recovery action (no auto-resume — single-process invariant).
4. **Endpoints.**
   ```text
   GET  /jobs                       — list (filters: project, kind, status)
   GET  /jobs/{job_id}              — detail (counters + last snapshot)
   GET  /jobs/{job_id}/events       — recent events (paged)
   GET  /jobs/{job_id}/stream       — SSE; resumes from last persisted event
   POST /jobs/{job_id}/cancel       — sets cancel flag (existing semantics)
   ```
5. **UI.** One **Job Detail** template + one **Active Jobs** sidebar widget. All current per-workflow progress panes (`_job.html`, `_workspace_grid.html`) read from `/jobs/{id}` instead of holding state.
6. **Service wiring.** `import_source`, `translation`, `batch_translate`, `export_book` submit through the registry and update job rows inside their existing transactions.

**Out-of-scope.**

- Distributed queue / external worker.
- Cron scheduler / auto-retry policies (a single manual "retry" button is fine; auto-retry needs its own ADR).
- Multi-tenant / multi-user job views.

**Output.** One persistent job model, used by every workflow, surviving refresh and process restart, exposed via SSE + polling.

**Acceptance Criteria.**

- Refresh during a translate job preserves progress (read from SQLite).
- Cold-restart marks orphan `running` rows as `failed` with the documented error; UI shows them in history.
- Cancel sets `cancelled` and persists `finished_at`.
- `GET /jobs?status=running` returns active jobs within 50 ms on a 10k-row table.
- SSE stream resumes from the last persisted event id (no duplicate events on reconnect).
- No new third-party dep added; `pyproject.toml` unchanged.
- Gate green; regression: existing 843+ tests still pass.

**Risks & mitigations.**

- *Risk:* SQLite write contention under fast SSE updates. *Mitigation:* persist progress on **snapshot interval** (default 1 s) and on terminal events, not per event; events stay in the in-process queue for live SSE.
- *Risk:* migration touches the existing `job_events` table. *Mitigation:* additive column (`job_id` nullable, backfill = NULL), forward + idempotency test.

---

### Sprint J — EPUB Preservation Snapshot & Parser Hardening

**Goal.** Turn Phase F's in-memory `ParsedEpub` into a **persisted, versioned, invalidatable** snapshot keyed by Volume — the canonical source for readiness, export fidelity, debugging, and future Tauri preview.

**Why after H/I.** Snapshots need a stable `volume_id` (H) and a job-based reparse pathway (I). Doing this before either forces a schema migration later.

**Existing baseline (Phase F, do not rebuild).**

- `core/epub_structure.py` (`ParsedEpub` contract) ✅
- `readers/epub.parse_epub_structure()` + `read_chapter_excerpt()` ✅
- `readers/epub_validation.py` (deterministic engine) ✅
- `services/epub_structure_preview.py` (read-only serializer) ✅
- `services/epub_export_fidelity.py` (source-vs-export report) ✅
- Phase F is **not persisted** to SQLite. Sprint J adds persistence; the in-memory path stays for ad-hoc preview.

**In-scope.**

1. **Schema (v5 → v6).** Six additive tables, all keyed by `volume_id`:
   ```text
   epub_sources              — source_hash, parser_version, schema_version, created_at
   epub_parse_snapshots      — header: counts, readiness_status, metadata_summary
   epub_manifest_items
   epub_spine_items
   epub_nav_entries
   epub_image_inventory      — role, role_confidence, dims, mime, is_cover
   epub_validation_warnings  — scope, severity, code, message
   ```
2. **Snapshot service** (`services/epub_snapshot.py`): `build_snapshot(volume_id)` runs `parse_epub_structure()` then writes the tables atomically; `load_snapshot(volume_id)` reads them back as a `ParsedEpub` equivalent.
3. **Invalidation rules.**
   ```text
   source_hash changed       → snapshot marked stale
   parser_version  changed   → snapshot stale (reparse recommended)
   schema_version  changed   → migration-or-reparse required
   ```
   `readiness_status` derived from validation warnings (no new code path).
4. **Reparse as a Job (consumes Sprint I).** `POST /projects/{p}/volumes/{v}/reparse` submits a `kind=parse` job; UI surfaces progress like any other job.
5. **Parser hardening (additive, behind unit tests).**
   ```text
   JPEG / WebP / SVG dimension parsing (current: PNG-only fast path)
   alt/title role detection
   image role confidence score (already drafted in Phase F)
   canonical cover selection (NAV cover-image > guide > spine[0] manifest)
   NAV as canonical TOC; NCX fallback; NAV/NCX mismatch warning (already in Phase F engine — extend)
   reading-order label (chapter href + display title)
   duplicate manifest id warning
   orphan resource warning
   media-type mismatch warning
   cover ambiguity warning
   ```
6. **CLI.** `weaver epub-inspect <path>` → JSON snapshot to stdout; same contract as `epub_structure_preview` so Web and CLI never diverge.

**Out-of-scope.**

- OCR.
- Full image viewer (Sprint M gate decides).
- Export rewrite (Sprint K).
- Reader mode.

**Output.** EPUB structure is no longer ephemeral; downstream sprints query a single, versioned snapshot instead of re-parsing.

**Acceptance Criteria.**

- Re-opening an unchanged EPUB preview returns the persisted snapshot (no reparse).
- Snapshot is marked stale when `source_hash` changes; UI shows a reparse CTA.
- `parser_version` is recorded; bumping it forces stale on next open.
- Reading order shows `href + label`.
- NAV/NCX divergence creates one warning (not duplicate TOC).
- Image inventory covers JPEG/PNG/WebP/SVG dimensions.
- `weaver epub-inspect` and `GET /ui/epub-preview` return structurally identical data.
- Gate green; Phase F preview routes still work for ad-hoc upload-and-inspect.

**Risks & mitigations.**

- *Risk:* schema churn if J ships before H. *Mitigation:* prerequisite — H complete.
- *Risk:* SVG dimension parsing is fragile. *Mitigation:* viewBox-first, width/height fallback, warning on parse fail (not error).

---

### Sprint K — Export Fidelity Integration

**Goal.** Wire export to the preservation snapshot so output stays faithful to the source EPUB's structure, with pre-export advisory + post-export report + a regression gate.

**Why after J.** Fidelity needs the snapshot. Phase F shipped `services/epub_export_fidelity.py`; Sprint K **consumes** it from inside the export pipeline (it is currently invocable but not on the hot path).

**In-scope.**

1. **Renderer consumes preservation context.** `renderers/epub.py` reads the snapshot for the volume and preserves:
   ```text
   OPF metadata · manifest · spine order · NAV/NCX · cover ·
   image assets · CSS/fonts when safe · structural hierarchy
   ```
2. **Pre-export advisory** (extends the existing `/ui/.../export/preflight`): warns when the snapshot has critical validation issues; never blocks (parity with Phase B advisory rule).
3. **Post-export fidelity report.** Job result includes the existing `EpubFidelityReport`; UI surfaces passed checks, warnings, critical gaps, missing assets.
4. **Regression gate.** New test target `epub_export_fidelity` in CI: round-trip a fixture, assert manifest/spine/NAV match within tolerance.
5. **Atomic export.**
   ```text
   write to <export_dir>/.tmp/<name>.epub.partial → validate → rename to final
   ```
   Failure leaves no partial final artifact.

**Out-of-scope.**

- Visual reader mode.
- OCR-driven translation.
- Auto-fix malformed source EPUBs.
- Full CSS rewrite engine.

**Output.** Exported EPUBs stay structurally close to the source; users see warnings before final write; failed exports never leave half-written files.

**Acceptance Criteria.**

- Spine order preserved (regression-gated).
- OPF metadata, cover, NAV/NCX preserved (regression-gated).
- Important image assets preserved; missing assets reported.
- Pre-export preflight surfaces snapshot warnings; checkbox to acknowledge.
- Atomic write proven by a failure-injection test.
- Gate green.

**Risks & mitigations.**

- *Risk:* snapshot drift between H/J and renderer. *Mitigation:* renderer always calls `load_snapshot(volume_id)` — never re-parses.

---

### Sprint L — Candidate Review + Character Text Draft

**Goal.** Reduce manual review effort on translation candidates without opening the OCR/image surface yet. Every AI-produced artifact stays auditable; final translations never mutate without explicit approval.

**Why before M.** Review schema is the contract OCR drafts will plug into in M. Building OCR before the review model forces a rewrite.

**In-scope.**

1. **Schema (v6 → v7).**
   ```text
   translation_candidates
   translation_candidate_reviews
   character_page_drafts
   character_page_draft_items
   ```
2. **Candidate status.** `generated · edited · approved · rejected · needs_recheck · stale`.
3. **Actions.**
   ```text
   Approve as current        Edit then approve
   Generate from Source      Improve from Source
   Compare candidate vs Source
   Reject                    Mark as needs recheck
   ```
4. **Grounding inputs** (passed through existing prompt builder; no provider change):
   ```text
   source segment · existing candidate · chapter context · glossary ·
   character DB · previous approved translations · style/tone instruction
   ```
5. **Invariant:** generating a candidate never overwrites the current translation; only "Approve" promotes it.
6. **Character Page — XHTML/text only.** Parser extracts headings, name list, description, aliases from XHTML pages and maps to draft Character DB entries.
7. **Provenance.** Every AI artifact records `source · provider · model · prompt_version · context_version · created_at`.

**Out-of-scope.**

- OCR / image character pages.
- Auto-approve.
- Automatic Character DB mutation.
- Image reader mode.
- Relationship graphs.

**Output.** Weaver actively assists review; the human stays the decision maker.

**Acceptance Criteria.**

- New candidates can be generated from Source without mutating the current translation.
- Candidate history is persisted and visible.
- Approve / edit / reject moves status correctly; UI reflects within one HTMX swap.
- Character Page text parser produces drafts; drafts are approve/edit/reject before they touch Character DB.
- Every AI row carries the full provenance record.
- Gate green.

---

### Sprint M — Image Preview & OCR / Vision Decision Gate

**Goal.** Open the image-aware surface **safely**. Gate A is an ADR (`012`); only when accepted do Gate B and Gate C ship code.

**Why after J/L.** Image preview needs a stable image inventory (J). OCR needs persistent jobs (I), candidate/draft review (L), provenance, and cost control. Doing this earlier risks security holes and silent data mutation.

**Gate A — ADR `012` (must precede any image-bytes endpoint).**

```text
Decide:
  may image bytes be exposed?     allowed image categories
  size cap                         MIME allowlist
  path traversal protection        cache policy
  no-mutation guarantee            endpoint design
```

Initial allowed categories (subject to ADR): `cover · color illustration · insert illustration · character page`.

**Gate B — ADR for OCR/vision.**

```text
Decide:
  provider adapter (built behind the existing providers/registry pattern)
  credential handling (must reuse ~/.weaver/secrets.toml; no new secret store)
  cost control (per-job budget, hard cap, dry-run mode)
  output data model (rows persisted; never mutate translations directly)
  JP OCR support · confidence score · manual review
```

**Gate C — Limited implementation (only after A + B accepted).**

1. Thumbnail endpoint, read-only:
   ```text
   GET /projects/{project}/volumes/{volume_id}/images/{image_id}/thumbnail
   ```
2. Size-capped response; MIME allowlist enforced; no arbitrary path.
3. Optional OCR job (`kind=ocr` in Sprint I's registry) for Character Page images.
4. OCR results land as drafts (consumes Sprint L's draft schema).

**Out-of-scope.**

- Full manga / comic OCR workflow.
- Full image reader.
- Auto-translation mutation from OCR.
- Auto-save to Character DB.

**Output.** A safe path to image preview + OCR without breaking the review or security model.

**Acceptance Criteria.**

- ADR `012` merged before any image-bytes endpoint.
- Thumbnail endpoint refuses arbitrary paths (path-traversal regression test).
- MIME allowlist enforced (415 on disallowed).
- OCR jobs use Sprint I's job model + Sprint L's draft schema.
- OCR results carry confidence + provenance.
- Gate green.

---

### Sprint N — Tauri Shell Alpha

**Goal.** Prove Weaver runs as a Tauri desktop shell over the existing FastAPI sidecar, **without UI rewrite**.

**Why last.** Needs G's runtime stability, I's persistent jobs, J's snapshot, K's atomic export, and Sprint G's `docs/SIDECAR_CONTRACT.md`. Building Tauri before these forces shell-side workarounds that become tech debt.

**In-scope.**

1. Minimal Tauri workspace (in `desktop/` — new subtree, isolated from `src/weaver/`).
2. Tauri starts FastAPI as a sidecar process (`weaver serve --env desktop --host 127.0.0.1 --port 0`).
3. Waits on `/healthz`; opens WebView when ready.
4. Sends session token via `X-Weaver-Session` header.
5. Pipes sidecar stdout/stderr into `logs_dir/runtime.log`.
6. Clean shutdown: SIGTERM the sidecar on window close; wait up to 5 s; SIGKILL if needed.
7. Crash screen if backend fails to start (shows last 50 log lines).

**Out-of-scope.**

- Signed installers · auto-updater · `.msi`/`.dmg` production builds · cross-platform release pipeline · deep Rust bridge · any UI rewrite.

**Output.** Weaver launches as a Tauri desktop shell with the existing HTMX UI.

**Acceptance Criteria.**

- Double-click launch starts backend + UI within 5 s on the maintainer's machine.
- `/healthz` polled before window opens.
- Window close kills the sidecar; no orphan `weaver` process in OS process list.
- Backend failure surfaces a readable crash screen.
- Sidecar logs land in `logs_dir/runtime.log`.
- No external browser dependency.
- HTMX UI unchanged (template diff = 0 between Sprint M end and Sprint N end).

---

### Sprint O — Production Desktop Packaging

**Goal.** Promote the Tauri shell alpha to a candidate distribution build.

**In-scope.**

1. Windows packaging (`.msi` or `.exe` installer; pick one — ADR if both).
2. macOS packaging (`.dmg` or `.app`).
3. App icon, name, version, config storage location (reuses G's app-data dir).
4. Bundle sidecar binary (Python + wheel) using PyOxidizer or equivalent — decided in an O-stage ADR.
5. Basic smoke-test build per OS.
6. Installer documentation in `docs/INSTALL_DESKTOP.md`.
7. Debug-bundle export (`weaver doctor --bundle` zips logs + version + config).
8. Release checklist appended to `docs/MAINTENANCE.md`.

**Out-of-scope (unless explicitly opened later).**

- Auto-updater · code signing · notarization · cloud sync · multi-user/SaaS mode.

**Output.** A reproducible desktop packaging path; core workflow unchanged.

---

## 3. Revised Priority Table

```text
P0 — Blocker / Must Do First (Sprint G + H + I)
  FastAPI runtime stability         App-data directory abstraction
  Project/Volume lifecycle + rename Persistent job core (SQLite, in-process)
  Relative HTMX route compatibility Structured logs
  Health / version / status

P1 — Product Workflow Foundation (Sprint J + K)
  EPUB preservation snapshot        Parser hardening
  Volume readiness                  Export fidelity baseline
  Job-based parse / export

P2 — User Productivity (Sprint L)
  Candidate review workflow         Source-grounded candidate generation
  Character Page XHTML/text draft   Review provenance

P3 — Image-aware Expansion (Sprint M, ADR-gated)
  Image preview ADR (012)           Thumbnail endpoint
  OCR / Vision ADR                  Character Page image OCR draft

P4 — Desktop Distribution (Sprint N + O)
  Tauri shell alpha                 Sidecar lifecycle
  Packaging smoke test              Installer path
```

---

## 4. Parallelism Rules

**Do not run in parallel** (conflict-prone):

```text
1. Tauri shell actual vs FastAPI runtime stabilization        (Sprint N vs G)
2. OCR implementation vs Image/OCR ADR                        (Sprint M Gate C vs A/B)
3. Export fidelity vs preservation snapshot                   (Sprint K vs J)
4. Candidate review AI vs candidate/review schema             (parts of L)
5. UI rewrite vs HTMX hardening                               (never — locked)
6. Image-bytes endpoint vs path traversal / MIME ADR          (Sprint M Gate C vs A)
7. Full packaging vs sidecar lifecycle                        (Sprint O vs N)
```

**Safe to run in parallel:**

```text
1. Test fixture hardening alongside parser hardening (Sprint J).
2. Design copy / empty state alongside backend work, if it touches no route contract.
3. Documentation updates after each sprint gate.
4. CLI `epub-inspect` alongside Sprint J snapshot, sharing the same contract.
```

---

## 5. Cross-cutting Invariants

These hold across every sprint and the §2.2 phase gate:

- `read_epub()` and `DocumentIR` remain the import/export/translation path. Phase F's `ParsedEpub` is the **structural** layer; do not merge the two.
- `weaver` CLI surface stays functional; new web behavior gets a CLI counterpart when feasible (e.g., `weaver epub-inspect` in J).
- API keys via env or `~/.weaver/secrets.toml` only — never in config, never logged, never rendered (CLAUDE.md §4.2).
- All state writes go through services. No SQLite access from CLI/web layers.
- Schema migrations are forward-only + tested for idempotency; rollback notes go to `docs/MAINTENANCE.md`.
- No new third-party runtime dependency without ADR — including in Sprint N (Tauri lives in its own subtree, not as a Python dep).
- `~/.weaver/secrets.toml` location and mode (`0o600`) are not relocated by G's app-data abstraction; secrets are a stable contract.

---

## 6. Next Sprint Recommendation

**Active sprint after Phase F:** `Sprint G — FastAPI Stability & Tauri-Ready Runtime Foundation`.

Not:

```text
Sprint G — Tauri Migration
Sprint G — NiceGUI Migration
Sprint G — Full Desktop Rewrite
Sprint G — npm `@weaver/cli` Wrapper           (deferred legacy; see §0)
```

Sprint G removes the blockers every later sprint depends on. Sprint H may start only after the G8 gate passes.

---

## 7. Final Roadmap Sequence

```text
Sprint G — FastAPI Stability & Tauri-Ready Runtime Foundation       (ADR 009)
Sprint H — Project & Volume Lifecycle Contract (Novel → Project)    (ADR 011)
Sprint I — Persistent Job Core & Realtime Contract                  (ADR 010)
Sprint J — EPUB Preservation Snapshot & Parser Hardening            (extends Phase F)
Sprint K — Export Fidelity Integration                              (consumes J)
Sprint L — Candidate Review + Character Text Draft
Sprint M — Image Preview & OCR / Vision Gate                        (ADR 012, then optional impl)
Sprint N — Tauri Shell Alpha                                        (consumes G + I + K)
Sprint O — Production Desktop Packaging
```

---

## 8. Final Decision

Weaver does **not** rewrite its UI. The most efficient path is:

```text
HTMX-first
  → FastAPI-stable
    → Tauri-sidecar-ready
      → Tauri shell alpha
        → Production desktop packaging
```

Each sprint produces a foundation the next sprint consumes. No sprint produces a feature that needs to be torn down for the next sprint to land.
