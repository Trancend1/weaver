# Sprint P — Workflow Coherence · Execution Breakdown

> **Audience.** A fresh agentic AI (or human) executing Sprint P with **no memory of the audit conversation**. This document is self-contained: it carries the goal, the current build state with evidence, the exact code to reuse, step-by-step work, the constraints you must not violate, and the acceptance gates — for each task.
> **Position in roadmap.** Strict sequence **N → P → O → Q** ([ROADMAP_REPLAN](ROADMAP_REPLAN.md)). Sprint N (Tauri shell alpha, in `desktop/`) lands first. **Sprint P is this document.** Sprint O (production packaging) **must not start until Sprint P's O-gate passes** (see §1). Sprint Q stays high-level until O ships.
> **Spec of record.** Target product = [SOURCEOFARCHITECTURE.md](SOURCEOFARCHITECTURE.md). Issue acceptance = [ISSUE_BACKLOG.md](ISSUE_BACKLOG.md). Page targets = [PAGE_LAYOUT_BLUEPRINT.md](PAGE_LAYOUT_BLUEPRINT.md). Process targets = [WORKFLOW_BLUEPRINT.md](WORKFLOW_BLUEPRINT.md).
> **What Sprint P is NOT.** It is **not** the cross-project Workspace remake (Dashboard hubs / Queue / Resources / Providers / Analytics / project-id layer). That is Sprint Q. Sprint P is **per-project workflow coherence** only.

---

## 0. Operating constraints (read before writing any code)

These are non-negotiable. Violating one fails the sprint gate even if the feature "works."

**Stack & dependencies**
- Server-rendered **Jinja2 + HTMX only**. No SPA, no client framework, no build step, no web fonts. HTMX is vendored (`api/static/htmx.min.js`); no CDN.
- **No new runtime dependency.** `pyproject.toml` runtime deps stay frozen. A new dep requires an ADR (do not write one inside Sprint P).
- SQLite (WAL, **no ORM**). Long tasks use the in-process `JobRegistry` (`api/jobs.py`) — **no Celery/Redis/RQ/external worker** (ADR `010`).

**Layer boundaries (ADR 002/004)**
- `api/routers/ui*.py` are **thin adapters**: they call a `services/*` function and render a template. **No business logic, no SQLite access** in the UI layer.
- Shared/core (`services/`, `storage/`, `core/`, `qa/`, `readers/`, `renderers/`) is **framework-agnostic**: no `Request`/`Response`, no templates, no CLI output. Pydantic lives only at the web boundary (`api/schemas.py`).
- **All state writes go through services**, inside a single transaction. One segment write = one transaction. A status transition lives in the **same transaction** as the data it describes (never a separate "status updater" pass).

**Cockpit invariants**
- **Do not rename or remove these HTMX hooks** (swaps + UI tests depend on them): `#tree`, `#ws-grid`, `#job-panel`, `#export-panel`, `#browser`, `#selected_source`, `#source_path`, `#qa-badge-status`, `#qa-issues`, `id="seg-{id}"`, `qa-badge-vol-*`, `qa-badge-ch-*`.
- Design tokens have a **single source**: `api/static/app.css` `:root`. No magic numbers in templates.
- Layout modes are dispatched in `api/ui_context.py` (`global` / `project` / `workspace`). Reuse `global_layout` / `project_layout` / `workspace_layout`.
- **Gate B1:** the project tree must **never** run QA on render. QA is opt-in (a button), computed on demand. Do not add an auto-QA call to any list/tree render.
- UI copy/structure is pinned by tests: `tests/unit/api/test_ui_shell.py`, `test_ui_layout.py`, `test_ui_qa.py`, `test_ui_delete.py`. When you intentionally change a user-facing string or layout marker, **update the test in the same PR**.

**Safety & correctness**
- API keys: env vars or `~/.weaver/secrets.toml` only — never in config, never logged, never rendered, never in an SSE event.
- **Deterministic by default.** The only LLM call in Sprint P is candidate/draft *generation* (a feature that already exists as a service). No new LLM-driven QA, no "smart" anything.
- Migrations are **forward-only, additive, idempotent, and tested** (forward test + idempotency test). Rollback note goes in `docs/MAINTENANCE.md`.
- Tests use `FakeProvider`, never live LLMs. Fixtures are public-domain only.
- Errors via the `WeaverError` hierarchy (`src/weaver/errors.py`); user-facing message = what failed / likely cause / next command.
- **Contribution identity:** no `Co-Authored-By: Claude`, no "Generated with Claude Code", no AI/bot author metadata (CLAUDE.md §4.6).

**Workflow**
- One PR = one concern. Prefer one WV-item per PR.
- Run the §2.2 phase gate (CLAUDE.md) before declaring any item done: tests green, pyright 0, ruff + format clean, clean wheel build.

---

## 1. Build order & the O-gate

Execute in this order. The rationale is dependency-driven: the status taxonomy underpins Review/Preview/nav badges, so it goes first; the two O-gate items go early so they are provably done before packaging.

```text
1. WV-006  Status taxonomy + remove dead status branches      (foundation; others consume it)
2. WV-001  Generate Candidate / Draft in the cockpit          ★ O-GATE (MUST complete before Sprint O)
3. WV-002  Reading / output Preview                            ★ O-GATE (MUST complete before Sprint O)
4. WV-013  Translation Editor context panel                   (rides WV-001 + WV-006)
5. WV-003  Review status (persisted) + Review Queue
6. WV-005  Project Overview
7. WV-004  Navigation unification (reconcile only — no new hubs)
8. WV-007  Join structure validation into the QA report
9. WV-008  Missing validation checks + `error` tier           (needs an ADR — see task)
   (secondary) WV-009 export gate toggle (Draft/Final) · WV-011 qa_warnings cleanup
```

**★ HARD O-GATE (enforced).** Sprint O (production packaging) **must not begin** until **WV-001 (Generate Candidate UI)** and **WV-002 (Reading Preview)** are complete and gate-green. **`N → O` directly is forbidden.** Rationale: packaging a desktop build whose review loop cannot generate candidates (P0 dead-end) and which cannot preview translated output ships a broken product to distribution.

The remaining P items (WV-003/004/005/007/008/013) are **strongly recommended** before O but are not the hard gate — they may, at the maintainer's discretion, trail into a P.2 follow-up if O is time-pressured. WV-001 and WV-002 are not negotiable.

---

## 2. Task execution blocks

Each block: **Goal · Why · Build-state today (evidence) · Reuse · Steps · Constraints · Insight/Gotchas · Acceptance & tests.**

---

### WV-006 — Single status taxonomy + remove dead branches  *(do first)*

**Goal.** One canonical status vocabulary mapped consistently DB → API → UI; remove status strings the DB can never produce.

**Why first.** Review (WV-003), Reading Preview (WV-002), nav badges (WV-004), and the editor (WV-013) all render status. Land the vocabulary before they consume it, or you will retrofit labels three times.

**Build-state today.**
- Canonical taxonomy is already written: [SOURCEOFARCHITECTURE.md §5](SOURCEOFARCHITECTURE.md) (five axes: translation / review / validation / export / job).
- DB segment statuses (the only valid set): `pending, in_progress, translated, failed, stale, skipped, manual` — `src/weaver/storage/schema.sql:42-51` (CHECK constraint).
- **Dead branches** referencing non-existent statuses `reused` / `tm` / `memory`: `src/weaver/api/templates/partials/_segment.html:3,17` and `src/weaver/api/templates/workspace.html:11`. (TM reuse stores a `memory`-tagged *attempt* in `translations`; the *segment* status becomes `translated`. So these branches never fire.)
- Job status naming drift: `jobs.status` = `queued/running/done/failed/cancelled` vs canonical `Waiting/Processing/Cancelled/Completed/Failed` (`schema.sql:150-158`).

**Reuse.** No new code path — this is a presentation-mapping + cleanup task.

**Steps.**
1. Add a small presentation helper (e.g. `api/status_labels.py`, framework-agnostic pure dict/function) mapping DB enum → human label per axis, sourced verbatim from SOURCEOFARCHITECTURE §5. Keep DB enum values **unchanged** (no migration, no churn).
2. Replace inline status-label logic in `_segment.html` and `workspace.html` with the helper; **delete** the `reused/tm/memory` branches.
3. Sweep templates for any other raw-status rendering and route through the helper.

**Constraints.**
- **Do not rename DB enum values.** That would force a migration and break history/tests. Map only at presentation.
- No logic in templates — the mapping is a pure helper.

**Insight / gotchas.**
- The `manual` status is "source of truth — protected from normal retranslate" (`_segment.html:19`). Preserve that nuance in the label/help text.
- Job label mapping is presentation-only too; don't touch `jobs.status` values (SSE/registry depend on them).

**Acceptance & tests.**
- A grep test asserts no template references a status outside the DB CHECK set (`reused|tm|memory` → zero matches).
- `test_ui_shell.py` / `test_ui_layout.py` updated for any changed status copy.

---

### WV-001 — Generate Candidate & Character-Draft in the cockpit  ★ O-GATE

**Goal.** Let a user **generate** a translation candidate (and a character-page draft) from the cockpit. Today they can only review/approve/apply candidates that were created via the JSON API — the review loop has no in-UI content source.

**Why (P0).** The Candidates/Drafts review pages are dead-ends: nothing to review unless someone hit the API by hand. This is the single highest-leverage fix and a hard gate for Sprint O.

**Build-state today.**
- Generation exists as **services + JSON endpoints only**:
  - `services/candidate_generation.generate_candidate(project_toml, chapter_id, segment_id, *, cwd, provider_override)` → stored `pending`, **never auto-applied** (grounded in glossary + character DB + chapter context).
  - JSON route: `POST /projects/{name}/candidates/generate` — `src/weaver/api/routers/candidates.py:146`.
  - `services/character_draft.generate_character_draft(project_toml, chapter_id, *, cwd)` (text/XHTML only; no OCR). JSON route: `POST /projects/{name}/drafts/generate` — `candidates.py:269`.
- **No UI trigger anywhere:** `grep -r "candidates/generate\|drafts/generate\|Generate" src/weaver/api/templates` → no matches. The Candidates page only loads the list: `templates/candidates.html:14`. The segment row links to *review* only: `templates/partials/_segment.html:32`.
- Existing UI review routes (approve/reject/apply, list re-render) are the pattern to copy: `api/routers/ui.py:935-1133`; card re-render `ui_candidates_rerender_card` (`ui.py:1001`); list partial `templates/partials/_candidates_list.html`.

**Reuse.**
- Call the existing services — **do not** reimplement generation.
- Copy the HTMX adapter shape from `ui_candidate_approve` (`ui.py:971`) and `ui_candidates_rerender_card` (`ui.py:1001`).
- Error fragment pattern: `_job_error` (`ui.py:791`) / the existing `_import_error` / per-segment error render.

**Steps.**
1. **Per-segment generate (in the editor).** Add UI route `POST /ui/projects/{name}/chapters/{chapter_id}/segments/{segment_id}/candidates/generate` that calls `generate_candidate(...)` and returns the re-rendered candidate card (reuse `_candidates_list.html` for one candidate, like `ui_candidates_rerender_card`). On `ProviderError`/`SegmentNotFoundError` → render the existing error fragment (HTMX swap), never a 500.
2. **Editor button.** In `partials/_segment.html`, add a "Generate candidate" control next to the existing "Review candidates" link (`:32`), `hx-post` to the route above, `hx-target` a candidate slot, with an `htmx-indicator` (generation calls a provider — it is slow; show the calm-loader pattern already used in `workspace.html`).
3. **Candidates page generate.** On `templates/candidates.html`, add a "Generate for chapter" affordance (choose chapter) → a UI route that loops `generate_candidate` over the chapter's untranslated/needs-review segments **synchronously is NOT acceptable for a whole chapter** (see gotcha) — scope this to a single segment from the page, OR submit a job. For Sprint P, ship **per-segment generation only** (step 1–2) and leave chapter/selection batch generation as a documented follow-up (it needs the job model — see Insight).
4. **Character-draft generate.** Add `POST /ui/projects/{name}/chapters/{chapter_id}/drafts/generate` calling `generate_character_draft(...)`; add a "Generate character draft" button on `templates/character_drafts.html`; re-render the drafts list (reuse `_drafts_list.html`). Handle the "no character content detected" case (the service returns `None`) with a clear empty message.

**Constraints.**
- Thin adapter only — **no generation logic in the UI route.**
- **Non-destructive invariant:** generation creates a `pending` candidate and **must not** mutate the current translation. The service already guarantees this; do not add an "apply on generate" shortcut.
- Provider errors surface as an HTMX error fragment, not an exception page. Reuse `WeaverError` messages (what/cause/next).
- Secrets/keys never rendered (the provider call uses env/secret store as usual).

**Insight / gotchas.**
- **Generation is synchronous and provider-bound.** A single-segment generate inside one HTTP request is fine with an `htmx-indicator`. **Chapter/selection batch generation can exceed a request timeout** and must run through the `JobRegistry` (like batch translate) — that is **out of Sprint P scope**; ship per-segment now, file batch-generate as a follow-up that reuses the job model.
- `apply_candidate` (when the user later applies) already creates a `translations` attempt and sets segment status `translated`/`manual` (`candidates.py:214`). Generation and apply are cleanly separated — keep them so.
- The candidate card template already renders provenance; generation just produces another `pending` row the existing list will show.

**Acceptance & tests.**
- From the editor, a user generates a candidate for a segment without leaving the page; it appears as `pending`; approve → apply promotes it; the current translation is unchanged until apply.
- Character drafts can be generated from the Drafts page; "no content" is handled.
- New UI test: generate → list → approve → apply through the **UI routes** (using `FakeProvider`). This is the test that proves the loop is closed.

---

### WV-002 — Reading / output Preview  ★ O-GATE

**Goal.** A read-only **Reading Preview** that renders the **translated** chapter/volume as it will read after export, plus a **Before/After** (source ↔ translation) view. Today the only "preview" shows *source* structure, so the translated book is visible only by exporting.

**Why.** The translate → review → export loop has no in-app way to see the result. This is the EPUB/LN reviewer's core need and a hard gate for Sprint O.

**Build-state today.**
- "EPUB Preview" is a **structure inspector** showing source excerpts: `templates/epub_preview.html:156` ("Untranslated source text, trimmed for inspection only"); routes `api/routers/ui.py:132,483`.
- A CLI-only service computes source/translation **pairs**: `services/preview.preview_project(...)` → `PreviewBlock(segment_id, chapter_index, chapter_title, source_text, translation, status)` (`src/weaver/services/preview.py`). This is the data for Before/After.
- The export renderer building blocks exist: `renderers/rendered_document` (`RenderChapter`, `block_to_html`) and `renderers/html.py` (`docs/ARCHITECTURE.md` module inventory). The **volume-aware orchestrator `services/export_book.py` WRITES FILES** — do not call it for preview.

**Reuse.**
- **Before/After:** reuse `services/preview.preview_project` (or a thin sibling) for the source/translation pairs — it already applies the "latest translation where status ∈ {translated, manual} and source_hash matches" rule.
- **Reading view:** reuse `renderers/rendered_document` (`RenderChapter` / `block_to_html`) to build chapter HTML **in memory**. Mirror the export **publishable rule** (translated/manual + hash match, else source fallback) so *preview == export*.

**Steps.**
1. Add a **read-only service** (e.g. `services/reading_preview.py`) that, given a project + volume (or chapter), returns rendered translated chapter HTML **as a string/value object** — building on `rendered_document` blocks. **It writes nothing to disk.**
2. Add UI routes: `GET /ui/projects/{name}/volumes/{volume_id}/preview` (and a per-chapter variant) rendering a new `templates/reading_preview.html` with three modes: **Reading** (translated flow), **Before/After** (source ↔ translation, from `preview_project`), **Structure** (link/reuse the existing structure preview).
3. Render translated HTML inside a **sandboxed, styled container** (see constraints). Cover/illustration placement may reuse the snapshot image inventory for ordering, but **do not** expose new image-byte endpoints (the gated one from Sprint M already exists if needed).

**Constraints.**
- **No file writes.** Add a test that asserts no artifact is created under `output/` during preview. Do **not** call `export_book` / `export_bundle`.
- Read-only; no provider call; no mutation.
- **HTML safety:** translated text and source markup may contain HTML. Render through the controlled `block_to_html` path; if you must mark content `|safe`, ensure it passed the renderer (do not `|safe` raw DB text). Prefer a constrained container/iframe with a tight style scope so preview CSS cannot leak into the cockpit shell.
- Service stays framework-agnostic (returns data/HTML string; the route renders the page).

**Insight / gotchas.**
- The point of mirroring the export publishable rule is that the preview must not show a segment as translated that export would source-fallback. Reuse the same predicate (`status ∈ {translated, manual}` AND `source_hash` matches the latest attempt) — see `services/export_book` / `qa` `list_export_segment_states` for the canonical rule.
- TXT/HTML-sourced volumes are *synthesized* on export (`renderers/epub_synthesis.py`); for those, the reading preview renders from DB content just like export — there is no source EPUB layout to mirror. State this in the UI ("synthesized layout").
- Furigana/ruby and vertical text fidelity are **unverified** (WV-014, Sprint Q). Do not promise it; render what the blocks contain.

**Acceptance & tests.**
- A user previews the translated chapter/volume flow in-app; a Before/After toggle shows source↔translation per segment.
- Test asserts **zero files written** during a preview request.
- Test asserts the preview's published-vs-fallback decision matches the exporter's for a fixture.
- `prefers-reduced-motion` honored; reading container is keyboard-scrollable.

---

### WV-013 — Translation Editor context panel  *(rides WV-001 + WV-006)*

**Goal.** Add the third column to the editor: an inline **context panel** (detected glossary terms, characters in the segment, AI candidates with the **Generate** button from WV-001, history, consistency warnings) so the translator never leaves the editor to consult resources.

**Build-state today.** Editor is 2-column (`templates/workspace.html`); glossary/characters/candidates/history are separate pages; history is an on-demand fragment (`ui.py:769`). Target layout: [PAGE_LAYOUT_BLUEPRINT §4](PAGE_LAYOUT_BLUEPRINT.md).

**Reuse.** Glossary terms (`storage/glossary.list_glossary_terms`), characters (`storage/characters.list_characters`), candidates list (WV-001 routes), history (`services/segment_history`), consistency hints (`qa/consistency_checks`). All as HTMX fragments loaded into the panel.

**Steps.**
1. Add a right-column region to `workspace.html` (respect the `workspace` layout mode / icon-rail; keep responsive ≤900/720px behavior).
2. Populate via HTMX fragments per active segment: detected glossary terms (match against `segment.source_text`), characters present, candidates (with Generate), history-on-demand, consistency warnings.

**Constraints.** No new dep; presentation only; reuse existing services; do not duplicate logic. Update `test_ui_layout.py` for the new layout marker.

**Insight / gotchas.** Keep the panel **lazy** — fragments load per segment focus, not eagerly for every segment (avoid N provider/db calls on render). "Detected glossary terms" is a deterministic substring match (same logic as `qa.checks.check_glossary_mismatch`), not an LLM call.

**Acceptance.** A translator consults glossary/characters/candidates/history and generates a candidate without leaving the editor; the panel updates on segment focus.

---

### WV-003 — Persisted review status + Review Queue

**Goal.** Model the **human review** axis (distinct from automatic Validation) and give it a queue. Today "Reviewed/Approved" is not trackable; QA is recomputed each load and never persisted.

**Build-state today.** `segments` has no review column (`schema.sql:35-51`). Candidate/draft `approved/rejected` is a *different* concept (the suggestion's state, not the final translation's review state). Schema is at v8 (`storage/db.py:13`). Canonical review states: [SOURCEOFARCHITECTURE §5.2](SOURCEOFARCHITECTURE.md) — `not_reviewed / needs_review / needs_revision / approved / rejected`.

**Reuse.** Migration pattern: `storage/migrations.py` (`_migrate_to_vN` + register in `_MIGRATIONS`); bump `SCHEMA_VERSION` in `storage/db.py`; mirror `schema.sql`. Service-through-transaction pattern: `services/workspace_edit.save_segment_translation`.

**Steps.**
1. **Migration v8 → v9 (additive).** Add `segments.review_status TEXT NOT NULL DEFAULT 'not_reviewed'` with a CHECK over the five canonical values (column is simplest; a `segment_reviews` table is over-modeling for Sprint P). Update `schema.sql` to match for fresh DBs. Write a forward-migration test + an idempotency test. Add a rollback note to `docs/MAINTENANCE.md`.
2. **Service.** `services/segment_review.set_review_status(project_toml, chapter_id, segment_id, status, *, cwd)` — writes through a transaction; validates the status; raises `WeaverError` on bad input.
3. **Editor surface.** In `partials/_segment.html`, show the review status (via the WV-006 helper) + buttons (Mark reviewed / Needs revision); HTMX re-render the segment row.
4. **Review Queue page.** `GET /ui/projects/{name}/volumes/{volume_id}/review` listing segments filtered by review status + issue type, with the resolution actions from [WORKFLOW_BLUEPRINT §5](WORKFLOW_BLUEPRINT.md). For Sprint P, ship the queue + the core actions (Open in Editor / Mark reviewed / Needs revision / Generate candidate); the fuller resolution set is acceptable to trail.

**Constraints.** Migration additive + tested; transitions in-transaction; review status is **independent** of translation status and of candidate state. Keep Validation (QA) a separate concern/page.

**Insight / gotchas.** **Design sub-decision (document it):** does applying a candidate auto-set `review_status = approved`? Recommended **no** — applying a candidate sets the *translation*; a human still reviews. Keep them orthogonal so "approved" always means a human signed off. Record the choice in the PR description.

**Acceptance & tests.** Marking a segment reviewed/needs-revision persists across reloads; the Review Queue reflects status within one HTMX swap; migration forward + idempotency tests pass.

---

### WV-005 — Project Overview

**Goal.** A Project Overview surface (summary · translation progress · project health · current activity · quick actions), replacing the current tree-first project page as the landing tab.

**Build-state today.** `/ui/projects/{name}` renders tree + import + export (`templates/project.html`). Target: [PAGE_LAYOUT_BLUEPRINT §2](PAGE_LAYOUT_BLUEPRINT.md), spec [SOURCEOFARCHITECTURE §8.2](SOURCEOFARCHITECTURE.md).

**Reuse.** `services/project_tree.project_tree` (volumes/chapters/counts + derived volume status), segment counts already in the tree, `services/translation_qa` for health **(opt-in only)**.

**Steps.**
1. Add an Overview section/tab computed from cheap reads: title/author/volume-chapter-segment counts, translated/manual/pending tallies (already in `project_tree`), current activity (last job from `services/job_store.list_jobs_for_project`), quick-action links.
2. Move the existing tree / import / export panels to their own tabs under the project.

**Constraints.** **Project Health that needs QA must stay opt-in** (Gate B1 — do not auto-run a novel-wide QA scan on Overview render). Summary/progress come from counts (cheap); a "Check health" button triggers QA like the existing "Load quality badges" pattern (`project.html:30`).

**Insight / gotchas.** Reuse the lazy-QA OOB-badge mechanism (`ui_qa.py:285` `qa_tree_badges`) for any health number that needs QA. Counts are free; QA is not.

**Acceptance.** Opening a project shows the overview first; tallies reconcile against the DB; tree/import/export still reachable as tabs.

---

### WV-004 — Navigation unification  *(reconcile only — do NOT build new hubs)*

**Goal.** Remove the triplicated/inconsistent navigation: one global Workspace nav shell + one contextual project panel; fix the "Dashboard" label that opens a page titled "Projects"; drop the project-page subnav that duplicates the sidebar.

**Build-state today.** Topbar = Dashboard / New project / Config (`base.html:21-25`). Per-project sidebar = Project / Quality / Glossary / Characters / Memory / Candidates / Drafts + chapter tree (`partials/_sidebar.html`). Project page **also** has a subnav duplicating Quality/Glossary/Characters/Memory (`project.html:21-27`). Dashboard topbar label vs page title "Projects" mismatch (`dashboard.html:7`); breadcrumb labels `/ui` "Dashboard" (`project.html:5`).

**Steps.**
1. Reconcile labels: make the Dashboard topbar entry and the `/ui` page title agree (pick "Dashboard" or "Projects" and use it everywhere; the audit suggests "Dashboard" as the command-center name).
2. Remove the project-page subnav duplication (`project.html:21-27`) — keep those entries only in the contextual sidebar.
3. Scaffold the global Workspace sidebar **structure** (Projects / Queue / Resources / Providers / Exports / Settings) per [SOURCEOFARCHITECTURE §4.1](SOURCEOFARCHITECTURE.md), but **the cross-project hubs (Queue/Resources/Providers/Exports/Analytics) are Sprint Q** — in Sprint P they may be present as disabled/"coming in Workspace v2" placeholders or link to the existing per-project equivalents. **Do not build cross-project hub content in Sprint P.**

**Constraints.**
- **Scope fence:** Sprint P reconciles existing navigation and scaffolds the shell. It does **not** implement Queue/Resources/Providers/Exports/Analytics (no cross-project read layer exists yet — that is WV-010, Sprint Q).
- Do not rename HTMX hooks. Update `test_ui_shell.py` / `test_ui_layout.py` for the reconciled nav.
- Keep the three layout modes working (`ui_context.py`).

**Insight / gotchas.** This is the highest template-diff item and the one most likely to break UI tests — do it **after** WV-006 (so badges use the taxonomy) and after the O-gate items, so a slip here cannot delay WV-001/002.

**Acceptance.** No nav entry appears in two places; Dashboard label and page title agree; the global sidebar structure is identical across pages (only content/contextual-panel change); keyboard navigable, focus visible.

---

### WV-007 — Join structure validation into the QA report

**Goal.** One QA report covering translation **and** EPUB structure. Today structural findings live only in the structure preview.

**Build-state today.** `readers/epub_validation.py` produces structure issues surfaced only in `epub_preview.html:205`; `services/translation_qa.py` builds translation-only reports; the persisted snapshot stores validation rows (`epub_snapshot_validation`, `schema.sql:229`).

**Reuse.** `services/epub_snapshot.read_snapshot(db_path, volume_id)` → `ParsedEpub` with `.validation_issues`. Fold these into the `QAReport` as a new category.

**Steps.**
1. Add a `structure` category to the QA report (`qa/report.py` category set) and have `services/translation_qa` (or a thin composer) read the **persisted snapshot** validation rows for in-scope volumes and emit them as `QAIssue`s.
2. Surface in `templates/qa.html` under the existing severity/category filters; roll counts into the badge.

**Constraints.** **Read the snapshot — do not re-parse** the EPUB on QA render (Gate B1 / cheap). Deterministic. Severity mapping must align with WV-008's tiers if both land.

**Insight / gotchas.** Structure issues are per-volume; map them to the volume/novel scope of the report (they have no `chapter_id`/`segment_id`). Use the existing `_issue_from_scope` pattern (`translation_qa.py:324`).

**Acceptance.** The QA report shows structural findings (missing cover/image, NAV/spine mismatch, etc.) under a `structure` category at novel/volume scope; counts roll into the badge; no re-parse on render.

---

### WV-008 — Missing validation checks + `error` severity tier  *(requires an ADR)*

**Goal.** Add the missing deterministic checks (max-length ratio, honorific mismatch, punctuation mismatch, broken line breaks) and an `error` tier between `warning` and `critical`.

**Build-state today.** `qa/checks.py:12` defines `Severity = info|warning|critical` (only a **minimum** length-ratio check, `check_length_ratio`). Target check list + 4 tiers: [SOURCEOFARCHITECTURE §5.3](SOURCEOFARCHITECTURE.md) / [WORKFLOW_BLUEPRINT §6](WORKFLOW_BLUEPRINT.md).

**Reuse.** Add checks as pure functions alongside `qa/checks.py` / `qa/consistency_checks.py`, wired through `run_all_checks` and `services/translation_qa`.

**Steps.**
1. **ADR FIRST.** Adding an `error` tier **contradicts ADR `008`**, which deliberately pins severity to `info|warning|critical` ("No `error` severity is emitted"). Write a short ADR (`docs/decisions/013-qa-error-severity-tier.md`) superseding that part of ADR 008 before changing the `Severity` type. **Do not silently add the tier.** (Writing this ADR is in-scope for WV-008 — it is the decision the feature requires, not a new dependency.)
2. Once accepted: extend `Severity` to `info|warning|error|critical`; update badge mapping (`badge_for` in `qa/report.py`) and the UI badge classes (`ui_qa.py:31`).
3. Add the four checks as deterministic functions with thresholds (extend `qa/thresholds.py` where a knob is needed); unit-test each (passing + failing case).

**Constraints.** **Deterministic only** — no LLM (ADR 008's core stays). Each check is pure and read-only. If the ADR is **not** written/accepted, ship the new *checks* at existing severities and **drop the `error` tier** rather than violate ADR 008.

**Insight / gotchas.** This is the only Sprint P item that needs a governance decision. Keep it last so it cannot block the O-gate. If time-pressured, the four checks alone (at `warning`/`critical`) deliver most of the value; the `error` tier is a refinement.

**Acceptance.** ADR `013` merged (or the tier dropped); each new check has passing/failing unit tests; severities are `info/warning/error/critical` (or documented 3-tier if deferred); no LLM use.

---

### Secondary (do only if O-gate + above are green)

- **WV-009 (export gate toggle).** Keep advisory default (`ui_qa.py:185-189`); add an **opt-in** "block Final export on unresolved critical" with a Draft escape hatch (Draft always succeeds). The **export-history ledger is Sprint Q** — do not build it here. Constraint: never make advisory the default; the block is opt-in.
- **WV-011 (`qa_warnings` cleanup).** The table is written by nothing (`grep qa_warnings` → schema + volume-delete cleanup + tests only). Either wire QA persistence into it (supports a "last validated" timestamp) or remove it + its delete-cleanup (`storage/volumes.py`, `services/volume.py`). Decide alongside whether Validation persists; migration note in `docs/MAINTENANCE.md`.

---

## 3. Sprint P exit gate

Sprint P is complete when **all** hold:

- [ ] **O-GATE:** WV-001 (generate candidate + draft in UI) and WV-002 (reading preview, no file writes) complete and gate-green. *(These two unblock Sprint O.)*
- [ ] WV-006 status taxonomy applied; no template references an impossible status (grep test).
- [ ] WV-003 review-status migration (v8→v9) forward + idempotency tested; Review Queue functional.
- [ ] WV-005 Project Overview shipped; WV-004 navigation reconciled (no duplicated entries; labels agree); WV-013 editor context panel shipped.
- [ ] WV-007 structure findings in the QA report; WV-008 checks shipped (with ADR `013` if the `error` tier is included, else 3-tier).
- [ ] **Phase gate:** full suite green, pyright 0, ruff + format clean, clean wheel build; **no new runtime dependency**; all migrations forward + idempotent + tested; secrets never logged/rendered (regression test green); UI tests updated for intentional copy/layout changes.
- [ ] Readiness note appended to `CLAUDE.md §2.5`.

**Only then may Sprint O begin.** `N → O` directly remains forbidden.

---

## 4. Open sub-decisions (resolve in-PR, record the choice)

1. **`error` severity tier** → needs ADR `013` superseding ADR 008's 3-tier rule, or drop the tier (WV-008).
2. **Apply-candidate vs review-status** → recommended orthogonal (apply sets translation; human sets review). Document in the WV-003 PR.
3. **Batch candidate generation** (chapter/selection) → out of Sprint P; needs the `JobRegistry` (like batch translate). File as a follow-up; Sprint P ships per-segment generation.
4. **Validation persistence** (`qa_warnings`) → decide wire-vs-remove in WV-011.

---

## 5. Map of touch points (quick index)

| Concern | Primary files |
|---|---|
| Candidate/draft generation (service) | `services/candidate_generation.py`, `services/character_draft.py` |
| Candidate/draft UI | `api/routers/ui.py` (candidate/draft routes), `templates/candidates.html`, `character_drafts.html`, `partials/_segment.html`, `_candidates_list.html`, `_drafts_list.html` |
| Reading preview | new `services/reading_preview.py`, `renderers/rendered_document.py`, `services/preview.py`, new `templates/reading_preview.html` |
| Review status | `storage/migrations.py`, `storage/schema.sql`, `storage/db.py`, new `services/segment_review.py`, `partials/_segment.html`, new review-queue route/template |
| Status taxonomy | new `api/status_labels.py`, `partials/_segment.html`, `workspace.html` |
| Project Overview | `api/routers/ui.py` (`project_view`), `templates/project.html`, `services/project_tree.py`, `services/job_store.py` |
| Navigation | `templates/base.html`, `partials/_sidebar.html`, `templates/project.html`, `api/ui_context.py` |
| QA structure join | `services/translation_qa.py`, `qa/report.py`, `services/epub_snapshot.py`, `templates/qa.html` |
| QA checks + tier | `qa/checks.py`, `qa/thresholds.py`, `qa/report.py`, `api/routers/ui_qa.py`, `docs/decisions/013-*.md` |
| Tests to update | `tests/unit/api/test_ui_shell.py`, `test_ui_layout.py`, `test_ui_qa.py`; new tests per item |
