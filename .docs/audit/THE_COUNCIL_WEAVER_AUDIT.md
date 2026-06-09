# THE COUNCIL — Weaver Audit

> **Type:** Read-only audit. No source, test, or runtime changes were made to produce this document.
> **Date:** 2026-06-09 · **Branch:** `chore/audit-gate` · **Build state (per `CLAUDE.md`):** v0.7.0 · Sprints A–M complete · 1043 tests / 4 skipped · pyright 0 · ruff clean.
> **Source of truth audited:** [`docs/sourceofarchitecture.md`](../../docs/sourceofarchitecture.md) (the target IA/UX spec) measured against the actual repository.
> **Companion deliverables:** [WORKFLOW_BLUEPRINT](WORKFLOW_BLUEPRINT.md) · [PAGE_LAYOUT_BLUEPRINT](PAGE_LAYOUT_BLUEPRINT.md) · [ISSUE_BACKLOG](ISSUE_BACKLOG.md) · [ROADMAP_REPLAN](ROADMAP_REPLAN.md) · [SOURCEOFARCHITECTURE](SOURCEOFARCHITECTURE.md)

---

## 0. Executive Summary

Weaver today is a **working translation pipeline** wrapped in a **flat cockpit**. The backend is strong: clean layering (ADR 002/004), a single-process persistent job core (ADR 010), a versioned EPUB preservation snapshot, fidelity-checked export, and a well-tested deterministic QA engine. The pipeline `import → translate → QA → export` works end-to-end.

The **gap** is between that pipeline and the product the source-of-truth describes: a **scalable, series-aware workspace** with a command-center Dashboard, a global Workspace sidebar, a Project Overview, a unified Content Explorer, a 3-column Translation Editor, a clean **Review (human) vs Validation (automatic)** split, an output **reading Preview**, and a stable five-axis status taxonomy.

Three findings dominate:

1. **The human-review loop is a dead-end in the cockpit.** Candidate and character-draft *review* surfaces exist, but **candidate/draft *generation* is not wired into any UI** — only the JSON API can create them ([evidence](#p-01)). A reviewer opening the Candidates page sees nothing to review unless someone hit the API by hand.
2. **There is no output Preview.** What the UI calls "EPUB Preview" is a **structure inspector that shows untranslated source excerpts** ([evidence](#p-02)). The only way to see the translated book is to export it. The source-of-truth's "Reading Preview / Before-After" is unbuilt.
3. **"Review" and "Validation" are conflated, and there is no persistent review state.** "Quality" = automated QA only; QA is recomputed on every page load and never persisted; segments carry no `approved / needs-revision / reviewed` axis ([evidence](#p-03)).

None of this is decay — it is **scope**: the implemented MVP deliberately built the pipeline first. This audit maps the distance to the source-of-truth and sequences the work to close it.

---

## 1. Current-State Map

For each area: **Current behavior → Evidence → Works → Problems → Root-cause hypothesis.**

### 1.1 Import / Parse / Reparse

- **Current.** `weaver init`/`import` and the cockpit New-project / Import-volume forms read a source (`read_epub` → `DocumentIR`), scope it to a volume (`core/ir.scope_document_to_volume`), and persist chapters+segments. EPUB structure is parsed separately into `ParsedEpub` and persisted as a versioned snapshot; reparse runs as a job.
- **Evidence.** Import routes `api/routers/ui.py:600` (`/ui/new`), `api/routers/ui.py:643` (`/import`); snapshot tables `storage/schema.sql:187-234`; reparse-as-job `api/routers/ui.py:424`; snapshot/parse services `services/epub_snapshot.py`, `services/epub_reparse.py`; data-flow note `docs/ARCHITECTURE.md:43-52`.
- **Works.** Deterministic parse; snapshot invalidation by `source_hash` + `parser_version`; reparse is refresh-safe (job model); import is sandboxed (`source_browser`, `source_intake`).
- **Problems.** Two structural paths coexist (`read_epub`/`DocumentIR` for translation vs `parse_epub_structure`/`ParsedEpub` for inspection) — intentional (ADR/roadmap §5) but a divergence surface a new contributor must learn. Import requires a source file; **sourceless project creation is unsupported** (`docs/WEB_WORKFLOW.md:154`), which blocks the source-of-truth "create empty project, then attach volume" flow.
- **Root-cause hypothesis.** Phase F added structure parsing *parallel* to the translation reader to avoid destabilizing the import path; the duplication is the cost of that safety.

### 1.2 Project Flow

- **Current.** One `project.toml` + one SQLite DB = one Project (a series). A Project holds many Volumes. The project page is a tree (Volume → Chapter) + import panel + export panel + a "Load quality badges" button.
- **Evidence.** `_single_project_id` = `SELECT id FROM projects ORDER BY id LIMIT 1` (`services/project_tree.py:149`, `services/translation_qa.py:384`, repeated in candidates/drafts list routes); project page `api/templates/project.html`; tree `services/project_tree.py`.
- **Works.** The series→volume→chapter→segment hierarchy is real and consistent end-to-end (ADR 011 finished the Novel→Project rename). The tree is cheap (QA is opt-in, never on render — Gate B1).
- **Problems.** No **Project Overview** surface (summary / progress / health / current activity / quick actions from `sourceofarchitecture.md §11`). The project page mixes navigation, import, export, and badges in one scroll. Routes key on project **name**, not a stable id.
- **Root-cause hypothesis.** The page grew feature-by-feature (Sprints 11→L) without an overview layer ever being specced.

### 1.3 Workspace / Navigation

- **Current.** Three layout modes (`global` / `project` / `workspace`, `api/ui_context.py`). Topbar = Dashboard / New project / Config (`base.html:21-25`). Per-project sidebar = Project / Quality / Glossary / Characters / Memory / Candidates / Drafts + a chapter tree (`partials/_sidebar.html`). Project page also has its own subnav (Quality / Jobs / Glossary / Characters / Memory, `project.html:21-27`).
- **Evidence.** `base.html`, `partials/_sidebar.html`, `api/ui_context.py:29-66`, `project.html:21-27`.
- **Works.** HTMX server-rendered, no SPA; sidebar chapter tree shows per-chapter progress.
- **Problems.** **No global Workspace sidebar** (`sourceofarchitecture.md §8`: Projects / Queue / Resources / Providers / Exports / Settings). Navigation is **triplicated and inconsistent**: Quality/Glossary/Characters appear in *both* the sidebar and the project subnav; "Dashboard" in the topbar opens a page titled "Projects" (`dashboard.html:7`) and breadcrumbs label `/ui` as "Dashboard" (`project.html:5`). Volume is barely a navigation target — the editor route omits it entirely.
- **Root-cause hypothesis.** Navigation was added per-feature; no single IA owner reconciled topbar vs sidebar vs subnav.

### 1.4 Preview

- **Current.** "EPUB Preview" (`/ui/epub-preview`, `/ui/projects/{n}/volumes/{id}/structure`) renders **structure**: metadata, TOC, spine reading order, **untranslated chapter excerpts**, image inventory (with image-bytes preview links), and structural validation issues. A separate CLI `services/preview.py` prints source/translation text pairs.
- **Evidence.** `api/templates/epub_preview.html:153-169` ("Untranslated source text, trimmed for inspection only"); route `api/routers/ui.py:132`,`:483`; CLI preview `services/preview.py` (text pairs, read-only).
- **Works.** Structure inspection is thorough and LN-aware (cover/illustration/insert/character-page roles); image bytes are gated (manifest-backed, MIME allowlist, 8 MiB cap, path-traversal rejection — `api/routers/projects.py:569`, ADR 012).
- **Problems.** **No reading/output preview.** The user cannot see the *translated* book laid out before export — no reading simulation, no before/after, no image-in-context (`sourceofarchitecture.md §15`). Two unrelated things share the word "preview."
- **Root-cause hypothesis.** Preview was scoped as *import-time structure readiness* (Phase F), not *pre-export output review*; the output-preview need was never on a sprint.

### 1.5 Translation

- **Current.** Two-column JP/EN chapter editor (`workspace.html`) with per-segment save (→ `manual`), on-demand history, Translate / Retranslate (modes `skip_existing` / `retranslate_non_manual` / `force_selected`), live job panel (SSE + poll), filters, keyboard shortcuts. Translation memory lookup precedes the provider call; glossary + character DB inject into the prompt.
- **Evidence.** `workspace.html`, `partials/_segment.html`, translate routes `api/routers/ui.py:825-879`, TM/glossary injection `docs/WEB_WORKFLOW.md:308-319`.
- **Works.** Solid segment-level control; manual edits protected; non-destructive retranslate (append-only attempts); reuse surfaced.
- **Problems.** **No context panel** — glossary, characters, AI candidates, and history are separate pages, not inline beside the editor (`sourceofarchitecture.md §13.1` wants 3 columns). **Candidate generation is unreachable from the editor** (the segment toolbar links to *review* candidates, but nothing generates one — see [1.6](#16-review)). Dead status branches (`reused`/`tm`/`memory`) appear in `_segment.html:3,17` and `workspace.html:11` but can never match the DB `segments.status` CHECK set.
- **Root-cause hypothesis.** The editor predates candidates (Sprint 11B vs Sprint L); the two were never merged into one workspace.

### 1.6 Review {#16-review}

- **Current.** Translation **candidates** (AI suggestions) and **character page drafts** are persisted with provenance and reviewed on dedicated pages (approve / reject / apply). Glossary **candidate review** is a separate, more complete flow (approve/edit/reject writes `glossary_terms`).
- **Evidence.** Candidate review pages `api/routers/ui.py:935-1133`; candidate API `api/routers/candidates.py`; glossary review `api/routers/glossary_review.py`. **Generation has no UI:** `grep` for `candidates/generate`/`drafts/generate`/"Generate" in `api/templates/` → **no matches**; the Candidates page only loads `/candidates/list` (`api/templates/candidates.html:14`).
- **Works.** Apply is correctly non-destructive (creates a translation attempt; status → `translated`/`manual`); provenance is captured; glossary review loop is end-to-end.
- **Problems.** **The translation-candidate and character-draft review loop is incomplete in the cockpit** — you can list/approve/apply but cannot *generate* without the JSON API. **No per-segment human-review status** (`Approved` / `Needs Revision` / `Reviewed`) exists in the schema; "Review" as the source-of-truth defines it (editorial human checkpoint with persistent state) is not modeled.
- **Root-cause hypothesis.** Sprint L shipped the review *schema + apply* path and the *list/act* UI but stopped before the *generate-from-editor* trigger; the per-segment review axis was never specced.

### 1.7 Validation

- **Current.** Deterministic, read-only QA over the Novel/Volume/Chapter scopes (`services/translation_qa.py`), reusing shared checks (`qa/checks.py`, `qa/consistency_checks.py`, `qa/scope_checks.py`). Severity `info | warning | critical`; badge `clean | warnings | errors`; categories `completeness / staleness / consistency / quality / export_readiness`. Surfaced on `/qa` pages and an advisory export preflight.
- **Evidence.** `services/translation_qa.py`, `qa/checks.py:12` (`Severity = info|warning|critical`), `api/routers/ui_qa.py`, preflight `api/routers/ui_qa.py:180`.
- **Works.** Clean, well-tested, no LLM, no mutation; scope roll-ups; opt-in badges keep the tree cheap.
- **Problems.** **Structural EPUB validation lives in a *separate* engine** (`readers/epub_validation.py`, surfaced only in the structure preview) and is **not joined into the QA report** — so a user checking "quality" sees translation issues but not structural ones in the same place. Missing checks vs `sourceofarchitecture.md §14.2`: max-length ratio, honorific mismatch, punctuation mismatch, broken line breaks. No `error` tier (only `critical`). The vestigial `qa_warnings` table is written by nothing (`grep`: schema + volume-delete cleanup + tests only) yet is cleaned on volume delete.
- **Root-cause hypothesis.** Translation QA (Phase B / ADR 008) and EPUB structure validation (Phase F) were built in different sprints with different report shapes and never unified.

### 1.8 Export

- **Current.** Volume-aware export to EPUB / TXT / HTML / DOCX (one artifact per volume), optional ZIP bundle, advisory preflight, atomic write, post-export fidelity report. EPUB export consumes the preservation snapshot. A legacy single-project CLI exporter (`services/export.py`) still exists.
- **Evidence.** `services/export_book.py`, `renderers/{epub,epub_synthesis,txt,html,docx}.py`, `services/epub_export_fidelity.py`, preflight `api/routers/ui_qa.py:180-282`, export UI `project.html:65-82` + `api/routers/ui.py:896`.
- **Works.** Faithful structure preservation; never blocks/blanks/drops (source fallback for unpublishable segments); atomic (no half-written finals); per-volume artifacts + bundle.
- **Problems.** **No `error` / `Final` gate** — export is *always* advisory (`api/routers/ui_qa.py:185-189`), which conflicts with `sourceofarchitecture.md §16.4` ("require clean validation for final export"). **No persisted export status / history** (volume lifecycle explicitly defers `exported` — `services/volume_lifecycle.py:18-23`); `sourceofarchitecture.md §16.5` wants export history. **Two export paths** (legacy CLI vs volume-aware) — documented as an accepted MVP boundary but still a divergence.
- **Root-cause hypothesis.** The advisory-only rule is a deliberate Phase B/D decision (never silently block); export history was never specced because the job table covers the run but not a per-artifact ledger.

### 1.9 State / API / Storage

- **Current.** SQLite (WAL, no ORM), schema v8, additive tested migrations. State writes go through services; CLI/web never touch SQLite directly. One DB per project; project identity in routes is the **name**. Persistent job core (jobs / job_events / job_progress_snapshots) with cold-start recovery.
- **Evidence.** `storage/db.py:13` (`SCHEMA_VERSION = 8`), `storage/migrations.py`, `storage/schema.sql`, job recovery `api/app.py:91`, layer rule `docs/ARCHITECTURE.md:24`.
- **Works.** Clean boundaries; migrations are forward-only + idempotent + tested; jobs survive refresh and restart; secrets never in config/logs/render.
- **Problems.** **Per-project-DB isolation is an architectural ceiling** for the source-of-truth Workspace command-center: cross-project features (Translation Queue across projects, Provider Health, Recent Activity, shared Resources) have **no cross-project read layer** — `discover_projects` scans the filesystem and opens each DB independently. Project identity = name (rename/duplication fragility; source-of-truth wants `:projectId`). Five status concepts are modeled inconsistently (see [§2](#2-status-model-the-core-inconsistency)).
- **Root-cause hypothesis.** "One project = one DB" was the right MVP simplification; the Workspace vision raises requirements the per-project DB was never designed to serve.

---

## 2. Status Model — the core inconsistency {#2-status-model-the-core-inconsistency}

The source-of-truth (`§20`) mandates **five independent status axes** with stable vocabulary. The codebase implements a *subset*, with naming drift and missing axes:

| Axis (target) | Target states | Actual implementation | Verdict |
|---|---|---|---|
| **Translation** | Untranslated, Translating, Translated, Manually Edited, Failed, Locked | `segments.status`: `pending, in_progress, translated, failed, stale, skipped, manual` (`schema.sql:42-51`) | Close, but **no `Locked`**; adds `stale`/`skipped` the target omits; names differ (`pending`≠`Untranslated`). |
| **Review** (human) | Not Reviewed, Needs Review, Needs Revision, Approved, Rejected | **Not modeled.** Only *candidate*/*draft* tables have `approved/rejected` (a different concept). | **Missing axis.** |
| **Validation** (auto) | Not Checked, Passed, Warning, Failed, Critical | QA computed on demand (`info/warning/critical`, badge `clean/warnings/errors`); **never persisted**; `qa_warnings` table unused. | Partial; **no `error` tier; not persisted; no per-segment state**. |
| **Export** | Not Ready, Draft Ready, Ready, Exporting, Exported, Failed | **Not persisted.** Volume lifecycle defers `exported` (`volume_lifecycle.py:18-23`). | **Missing axis.** |
| **Job** | Waiting, Processing, Cancelling, Cancelled, Completed, Failed | `jobs.status`: `queued, running, done, failed, cancelled` (+ reserved `processed, finalizing`) | Present; **naming drift** (`queued`≠`Waiting`, `done`≠`Completed`); no persisted `Cancelling`. |

Plus a **derived volume lifecycle** (`empty / imported / in_progress / translated / translating`) that is a sixth, parallel vocabulary the target doesn't name.

**Consequence:** the UI shows raw DB strings as badges (`_segment.html:18`), volume words elsewhere, and QA badge words in a third place — there is no single status taxonomy across DB/API/UI, which is exactly the P0 finding the source-of-truth opens with (`sourceofarchitecture.md §1.1`, §7).

---

## 3. Pain Verification

Each pain point: **Verified? · Evidence · Severity · Root cause · Recommended direction · Change type.**

<a id="p-01"></a>
### P-01 — Candidate/draft generation is not in the UI (review dead-end)
- **Verified:** Yes. `grep` for `candidates/generate|drafts/generate|Generate` across `api/templates/` returns **no matches**; the Candidates page only `hx-get`s `/candidates/list` (`candidates.html:14`); the segment toolbar links to *review* only (`_segment.html:32`). Generation endpoints exist but are JSON-only (`api/routers/candidates.py:146`,`:269`).
- **Severity:** P0 (workflow blocker — the Review surface has no content path).
- **Root cause:** Sprint L shipped schema + apply + list UI; the generate trigger was never added to the editor/review pages.
- **Recommendation:** Add "Generate candidate" to the segment row + a "Generate for chapter/selection" action on the Candidates page; add "Generate character draft" on the Drafts page. **Change type:** UI (+ thin route wiring; services already exist).

<a id="p-02"></a>
### P-02 — No translated reading/output preview
- **Verified:** Yes. The only "preview" surfaces show **source** structure/excerpts (`epub_preview.html:156` "Untranslated source text"); the translated book is visible only by exporting.
- **Severity:** P1 (major UX blocker for the review→export loop).
- **Root cause:** Preview was scoped to import-time structure readiness, not pre-export output.
- **Recommendation:** Add a read-only **Reading Preview** that renders the *translated* chapter flow (reuse the export renderer's `RenderChapter`/`block_to_html` without writing files) + a **Before/After** source↔translation view. **Change type:** API + UI (renderer reuse; no new write path).

<a id="p-03"></a>
### P-03 — Review and Validation are conflated; no persistent review state
- **Verified:** Yes. "Quality" = automated QA only (`ui_qa.py`); QA is recomputed each load and never persisted; `segments` has no review column (`schema.sql:35-51`); the project workflow rail labels step 4 "Review = Candidates + glossary" (`project.html:17`).
- **Severity:** P1.
- **Root cause:** Translation QA (Phase B) and candidate review (Sprint L) were built separately; the human-review axis was never modeled.
- **Recommendation:** Define **Review** (human, persistent per-segment: `not_reviewed/needs_revision/approved`) vs **Validation** (automatic QA) per the status taxonomy; surface them as distinct concerns within one "Review & Validation" module. **Change type:** Storage (new review column/table) + API + UI.

<a id="p-04"></a>
### P-04 — Navigation is triplicated and labels are inconsistent
- **Verified:** Yes. Topbar "Dashboard" → page titled "Projects" (`dashboard.html:7`); breadcrumb labels `/ui` "Dashboard" (`project.html:5`); Quality/Glossary/Characters appear in both sidebar (`_sidebar.html:16-27`) and project subnav (`project.html:21-27`). No global Workspace sidebar.
- **Severity:** P1.
- **Root cause:** Navigation accreted per feature; no IA reconciliation.
- **Recommendation:** One global Workspace nav + one contextual project panel; fix the Dashboard/Projects label; remove sidebar/subnav duplication. **Change type:** UI.

<a id="p-05"></a>
### P-05 — No Project Overview surface
- **Verified:** Yes. `/ui/projects/{name}` renders a tree + import + export, not a summary/progress/health/quick-actions overview (`project.html`). The dashboard is a flat project grid (`dashboard.html`).
- **Severity:** P1.
- **Root cause:** No overview layer was ever specced (`sourceofarchitecture.md §11`).
- **Recommendation:** Add a Project Overview tab (summary, translation progress, project health, current activity, quick actions). **Change type:** API (aggregate read) + UI.

<a id="p-06"></a>
### P-06 — Structural validation not joined into the QA report
- **Verified:** Yes. `readers/epub_validation.py` issues surface only in the structure preview; `services/translation_qa.py` builds the QA report from translation checks only.
- **Severity:** P2.
- **Root cause:** Two report shapes from two sprints.
- **Recommendation:** Add structure findings (from the persisted snapshot) as a QA category so one report spans translation + structure. **Change type:** Service + UI.

<a id="p-07"></a>
### P-07 — Export is always advisory; no Final gate; no export history
- **Verified:** Yes. Preflight never blocks (`ui_qa.py:185-189`); no `exported` status persisted (`volume_lifecycle.py:18-23`); no export ledger.
- **Severity:** P2 (design decision vs target).
- **Root cause:** Deliberate "never silently block" rule (ADR 008) + no per-artifact ledger spec.
- **Recommendation:** Keep advisory default; add **opt-in** "block final export on unresolved critical" with a draft-export escape hatch; persist an export-history ledger. **Change type:** Service + Storage + UI.

<a id="p-08"></a>
### P-08 — Status taxonomy drift across DB/API/UI
- **Verified:** Yes (see [§2](#2-status-model-the-core-inconsistency)).
- **Severity:** P1 (cross-cutting; the source-of-truth's opening P0).
- **Root cause:** Five axes modeled inconsistently across sprints.
- **Recommendation:** Author one canonical status taxonomy (this audit's [SOURCEOFARCHITECTURE §Status Model](SOURCEOFARCHITECTURE.md)) and align labels in DB/API/templates; remove dead status branches. **Change type:** Storage + API + UI (+ doc).

<a id="p-09"></a>
### P-09 — Project identity is name-based; per-project DB ceiling for Workspace features
- **Verified:** Yes. Routes use `{name}` (`api/routers/ui.py` passim); cross-project data requires scanning + opening each DB (`project_discovery`).
- **Severity:** P2 (architectural pre-req for Workspace command-center).
- **Root cause:** "One project = one DB" MVP simplification.
- **Recommendation:** Introduce a stable project id at the discovery layer; define a cross-project read layer before building Queue/Provider-Health/Activity/Resources hubs. **Change type:** Storage/Service (+ API).

<a id="p-10"></a>
### P-10 — Vestigial `qa_warnings` table + dead status branches + two preview/export paths
- **Verified:** Yes. `qa_warnings` written by nothing (grep: schema + volume-delete + tests); `reused/tm/memory` status branches unreachable (`schema.sql:42-51`); two preview concepts; two export paths.
- **Severity:** P3 (clarity / debt).
- **Root cause:** Legacy carry-over from pre-reset CLI validate + parallel sprints.
- **Recommendation:** Remove or wire `qa_warnings`; delete dead status branches; document (or converge) the preview/export duplications. **Change type:** Storage cleanup + UI cleanup + doc.

---

## 4. Council Review

### 4.1 Product Lead
- **Findings.** The vertical slice (import→translate→QA→export) is genuinely usable and the strongest asset. The product *information architecture*, however, is "flat project + chapter editor," well below the series-workspace the source-of-truth specs. The most valuable missing capabilities are, in order: candidate-generation-in-UI (P-01), output Preview (P-02), Review/Validation separation (P-03), Project Overview (P-05).
- **Top risks.** Shipping a Tauri desktop shell (Sprint N→O) around the current flat workflow would package the gaps into a distributable product; the rich workspace then becomes a costly post-distribution retrofit.
- **Recommendations.** Adopt the **strict N → P → O → Q** sequencing (chosen): Sprint N (packaging-only, low-risk, validates the sidecar) first, then a **Workflow Coherence** sprint (P) before Sprint O so the production desktop wraps a coherent workflow. **WV-001 + WV-002 are the hard gate for O; `N → O` is forbidden.**
- **Deferrals.** Analytics, cross-project Workspace hubs (Queue/Provider-Health/Resources), and OCR stay post-coherence; they depend on P-09 (cross-project read layer) and ADR-gated work.

### 4.2 UX Architect
- **Findings.** Three overlapping navigation systems with duplicated entries and an inconsistent "Dashboard/Projects" label (P-04). The editor lacks a context panel; users leave the editor to consult glossary/characters/candidates. Status vocabulary differs per surface (P-08). Microcopy on the workflow rail is good but "Review" is vague. Dead status branches in templates.
- **Top risks.** Adding pages without an IA owner will deepen the duplication; users can't form a stable mental model ("where am I, what's next").
- **Recommendations.** One global Workspace sidebar + one contextual project panel (per `sourceofarchitecture.md §7–10`); a 3-column editor with an inline context panel; a single status taxonomy with consistent badges; every primary page answers *context / progress / next action* (`§23`).
- **Deferrals.** Visual design polish and motion are out of scope until IA is reconciled.

### 4.3 EPUB / Light-Novel Expert
- **Findings.** Parsing + preservation + fidelity are strong and LN-aware (cover/color/insert/character-page roles, image inventory, snapshot, fidelity report). The decisive gap is the **absence of a translated reading preview** (P-02) — the one thing an LN translator needs before export. Image bytes are well-gated but not surfaced *in a reading context*. Honorifics are supported via glossary; **ruby/furigana and vertical-text handling are not evidenced** and are likely flattened in the TXT/HTML synthesis path.
- **Top risks.** Translators validate output by exporting and opening in a reader — slow, and divorced from the in-app review loop. Furigana/vertical-text loss would be discovered only post-export.
- **Recommendations.** Reading Preview + Before/After + in-context illustration view; add a structural-fidelity category to QA (P-06); spike furigana/ruby + page-image placement fidelity as a tracked investigation.
- **Deferrals.** OCR / image-text translation stay ADR-gated (ADR 012 gate B/C).

### 4.4 Backend Architect
- **Findings.** Layering, job model, migrations, and secret handling are exemplary. The constraints are: per-project-DB isolation as a ceiling for cross-project Workspace features (P-09); name-based project identity; the five-axis status drift (P-08); vestigial `qa_warnings` and two preview/export paths (P-10); review state unmodeled (P-03).
- **Top risks.** Building Workspace command-center features on per-project DBs without a cross-project read layer invites N-open-DB scans or a premature global store.
- **Recommendations.** Introduce a stable project id + a thin cross-project read/index layer *before* Queue/Provider-Health/Activity; model Review + Export status as persisted axes; remove dead schema. Keep SQLite-in-process (ADR 010) — no external queue.
- **Deferrals.** No global multi-project DB until a concrete Workspace sprint requires it.

### 4.5 Review & Validation Engineer
- **Findings.** Validation (deterministic QA) is robust and well-tested. Review is incomplete in the cockpit (P-01) and has no persistent state (P-03). Structural validation is unjoined (P-06). Missing checks: max-length ratio, honorific mismatch, punctuation mismatch, broken line breaks; no `error` tier. Export is advisory-only with no Final gate or history (P-07). Test coverage is broad (QA, migrations, jobs, export fidelity, readers, renderers) but has **no test for the candidate-generation UI flow** (because it's unbuilt) and **no reading-preview tests** (feature absent).
- **Top risks.** Reviewers can't run the loop the product implies; "looks reviewed" is unverifiable because review state isn't stored.
- **Recommendations.** Wire generation into the UI; add a persistent review axis; join structure into QA; add the four missing checks + the `error` tier; add an opt-in Final-export gate + export history; add coverage for generate→review→apply and reading-preview once they exist.
- **Deferrals.** Semantic/vector QA stays out (ADR 008 — deterministic only).

### 4.6 Delivery Manager
- **Findings.** The Sprint G–O roadmap is sound and dependency-driven; G–M are done; the recovered `weaver_next_plan.md` is itself **stale** (says "Sprint L active" while `CLAUDE.md` says Sprint M complete / N active). The source-of-truth introduces a UX/IA ambition absent from G–O.
- **Top risks.** Roadmap docs disagree on the active sprint; the IA ambition has no home in the sequence.
- **Recommendations.** Adopt the strict plan ([ROADMAP_REPLAN](ROADMAP_REPLAN.md)): **Sprint N (Tauri alpha)** first, then **Sprint P (Workflow Coherence)** — task breakdown in [SPRINT_P_EXECUTION](SPRINT_P_EXECUTION.md) — before **Sprint O (packaging)**; `N → O` forbidden, WV-001 + WV-002 gate O. Reconcile all roadmap docs to one active-sprint statement.
- **Deferrals.** Cross-project Workspace hubs + Analytics become **Sprint Q (Workspace v2)**, post-O.

---

## 5. Synthesis

### 5.1 Disagreements
- **Export gating.** Engineer wants a Final-export gate (source-of-truth §16.4); current design (ADR 008) is advisory-only. **Resolved:** keep advisory default, add *opt-in* block-on-critical with draft escape hatch.
- **Sequencing.** Roadmap says Tauri-next; audit says workflow debt is high. **Resolved (user-confirmed):** strict **N → P → O → Q** — N first, then P (Workflow Coherence) before O; `N → O` forbidden (WV-001 + WV-002 gate O).
- **Workspace command-center.** Product wants it; Backend warns the per-project DB can't serve it cheaply. **Resolved:** defer to Sprint Q behind a cross-project read layer (P-09).

### 5.2 Trade-offs
- **Coherence vs speed-to-desktop:** the sequence spends one extra sprint (P) to avoid shipping a flat workflow to desktop.
- **Reuse vs new surfaces:** Reading Preview reuses export renderers (cheap); Review-state + Workspace hubs need new storage (costed in P/Q).
- **Determinism:** All QA stays deterministic (ADR 008); no LLM-judge creep.

### 5.3 Consensus
1. The backend is ready to be packaged; the **workflow is not yet coherent enough to package well**.
2. The three highest-leverage fixes are **P-01 (generation in UI)**, **P-02 (reading Preview)**, **P-03 (Review/Validation split + status taxonomy)** — all land in **Sprint P**.
3. Tauri **N** is safe to run now (packaging-only, template-diff-zero); **O** waits for **P**.
4. The source-of-truth is the spec for **P** and **Q**; this audit's [SOURCEOFARCHITECTURE](SOURCEOFARCHITECTURE.md) is the reconciled, build-state-annotated version.

### 5.4 Top 10 Fixes (ranked)

| # | Fix | Pain | Priority | Lands in |
|---|---|---|---|---|
| 1 | Surface candidate + character-draft **generation** in the cockpit | P-01 | **P0** | Sprint P |
| 2 | Add a **reading/output Preview** (translated flow + before/after) | P-02 | P1 | Sprint P |
| 3 | Separate **Review** (persistent human state) from **Validation** | P-03 | P1 | Sprint P |
| 4 | Add a **Project Overview** (summary/progress/health/actions) | P-05 | P1 | Sprint P |
| 5 | Unify **navigation** (global Workspace nav + contextual panel; fix labels) | P-04 | P1 | Sprint P |
| 6 | Implement one **status taxonomy** across DB/API/UI; kill dead branches | P-08 | P1 | Sprint P |
| 7 | Join **structure validation** into the QA report | P-06 | P2 | Sprint P |
| 8 | Add missing checks + `error` tier + **opt-in Final-export gate** + export history | P-07, P-03 | P2 | Sprint P/Q |
| 9 | Stabilize **project identity** + cross-project read layer (Workspace pre-req) | P-09 | P2 | Sprint Q |
| 10 | Remove **vestigial `qa_warnings`** + resolve preview/export duplications | P-10 | P3 | Sprint P/Q |

---

## 6. Evidence Index (file:line anchors)

- Navigation: `src/weaver/api/templates/base.html:21`, `partials/_sidebar.html:16`, `templates/project.html:5,21`, `templates/dashboard.html:7`, `api/ui_context.py:29`.
- Routes: `src/weaver/api/routers/ui.py` (UI), `ui_qa.py` (QA + preflight), `ui_admin.py` (glossary/characters/memory/config), `candidates.py` (review API), `projects.py:569` (image bytes), `app.py:159` (`/`→`/ui`).
- Editor / review: `templates/workspace.html`, `partials/_segment.html:3,17,32`, `templates/candidates.html:14`.
- Preview: `templates/epub_preview.html:156`, `services/preview.py`, `routers/ui.py:132,483`.
- QA / validation: `services/translation_qa.py`, `qa/checks.py:12`, `qa/consistency_checks.py`, `qa/scope_checks.py`, `readers/epub_validation.py`.
- Status / storage: `storage/schema.sql:42,118,150,251`, `storage/migrations.py`, `services/volume_lifecycle.py:18-23,37`, `services/project_tree.py:149`.
- Export: `services/export_book.py`, `services/epub_export_fidelity.py`, `renderers/epub.py`, `routers/ui.py:896`.
- Roadmap: `docs/weaver_next_plan.md` (HEAD), ADRs `009`–`012` (`docs/decisions/`).
