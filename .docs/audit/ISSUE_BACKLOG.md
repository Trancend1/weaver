# Issue Backlog

> **Source.** Derived from [THE_COUNCIL_WEAVER_AUDIT](THE_COUNCIL_WEAVER_AUDIT.md) §3–5. Each issue is independently actionable and carries acceptance criteria.
> **Priorities.** P0 = workflow/output blocker · P1 = major UX blocker · P2 = improvement · P3 = enhancement.
> **Type.** UI · API · Parser · Storage · Test (an issue may span several; the leading type is listed first).
> **Sprint.** Target sprint from [ROADMAP_REPLAN](ROADMAP_REPLAN.md).

---

## P0 — Workflow / Output blockers

### WV-001 — Candidate & character-draft generation absent from the cockpit
- **Area:** Review / Translation Editor
- **Type:** UI (+ thin route wiring; services exist)
- **Evidence:** `grep candidates/generate|drafts/generate|Generate` in `src/weaver/api/templates/` → no matches. Candidates page only `hx-get`s `/candidates/list` (`candidates.html:14`). Generation is JSON-only (`api/routers/candidates.py:146`, `:269`). Services ready: `services/candidate_generation.generate_candidate`, `services/character_draft.generate_character_draft`.
- **Root cause:** Sprint L shipped schema + apply + list UI; the generate trigger was never added.
- **Fix direction:** Add "Generate candidate" to the segment row (`_segment.html`) → `POST /ui/projects/{name}/candidates/generate` (new thin UI route over the existing service). Add "Generate for chapter / selection" on `candidates.html`. Add "Generate character draft" on `character_drafts.html`. Re-render the affected card/list via HTMX.
- **Acceptance:** From the editor, a user generates a candidate for a segment without leaving the page; it appears as `pending` and never mutates the current translation; approve→apply promotes it (existing behavior). Drafts can be generated from the Drafts page. A test exercises generate→list→approve→apply through the UI routes.

---

## P1 — Major UX blockers

### WV-002 — No translated reading/output Preview
- **Area:** Preview
- **Type:** API + UI (renderer reuse)
- **Evidence:** `epub_preview.html:156` renders "Untranslated source text"; no route renders translated output; `services/preview.py` is CLI text-pairs only.
- **Root cause:** Preview scoped to import-time structure, not pre-export output.
- **Fix direction:** New read-only Reading Preview reusing `renderers/rendered_document.RenderChapter` / `block_to_html` (no file write). Add a Before/After view from `services/preview.py` pairs. Route `/ui/projects/{name}/volumes/{id}/preview`.
- **Acceptance:** A user previews the *translated* chapter flow (cover → illustrations → text → afterword) in-app; a Before/After toggle shows source↔translation per segment; nothing is written to disk; reduced-motion respected.

### WV-003 — Review and Validation conflated; no persistent per-segment review state
- **Area:** Review / Validation / State
- **Type:** Storage + API + UI
- **Evidence:** "Quality" = automated QA only (`ui_qa.py`); `segments` has no review column (`schema.sql:35-51`); QA recomputed each load, never persisted; rail labels step 4 "Review = Candidates + glossary" (`project.html:17`).
- **Root cause:** Translation QA (Phase B) and candidate review (Sprint L) built separately; human-review axis never modeled.
- **Fix direction:** Add a persisted review status (`not_reviewed / needs_review / needs_revision / approved / rejected`) — new column on `segments` or a `segment_reviews` table (migration, additive, tested). Build a Review Queue page + resolution actions. Keep Validation (auto) distinct.
- **Acceptance:** A segment can be marked reviewed/needs-revision and the state persists across reloads; a Review Queue lists segments by review/issue status with filters; migration has forward + idempotency tests; Validation pages are unchanged in behavior.

### WV-004 — Navigation triplicated; inconsistent Dashboard/Projects labels
- **Area:** Workspace / Navigation
- **Type:** UI
- **Evidence:** Topbar "Dashboard" → page titled "Projects" (`dashboard.html:7`); breadcrumb labels `/ui` "Dashboard" (`project.html:5`); Quality/Glossary/Characters in both sidebar (`_sidebar.html:16-27`) and project subnav (`project.html:21-27`); no global Workspace sidebar.
- **Root cause:** Navigation accreted per feature; no IA reconciliation.
- **Fix direction:** One global Workspace sidebar (Projects/Queue/Resources/Providers/Exports/Settings) + one contextual project panel; remove the project subnav duplication; standardize the Dashboard label; persistent context bar showing Project › Volume › Chapter + stage + next action.
- **Acceptance:** No nav item appears in two places; "Dashboard" label and page title agree; the global sidebar structure is identical across all pages (only content/contextual-panel change, per `sourceofarchitecture.md §8`); keyboard navigable, focus visible.

### WV-005 — No Project Overview surface
- **Area:** Project Flow
- **Type:** API (aggregate read) + UI
- **Evidence:** `/ui/projects/{name}` renders tree + import + export (`project.html`); no summary/progress/health/quick-actions overview.
- **Root cause:** Overview layer never specced.
- **Fix direction:** Add a Project Overview tab: summary, translation progress, project health, current activity, quick actions (`sourceofarchitecture.md §11`). Move tree/import/export to their own tabs.
- **Acceptance:** Opening a project shows the overview first; metrics (translated/reviewed/validated/failed/pending) are accurate against the DB; quick actions route correctly; the tree/import/export still reachable as tabs.

### WV-006 — No single status taxonomy across DB/API/UI; dead status branches
- **Area:** State / API / UI
- **Type:** Storage + API + UI
- **Evidence:** Five-axis drift table in [audit §2](THE_COUNCIL_WEAVER_AUDIT.md#2-status-model-the-core-inconsistency); dead branches `reused/tm/memory` in `_segment.html:3,17` & `workspace.html:11` (not in `schema.sql:42-51` CHECK set); job names drift (`queued`≠Waiting, `done`≠Completed).
- **Root cause:** Five status concepts modeled inconsistently across sprints.
- **Fix direction:** Adopt the canonical taxonomy in [SOURCEOFARCHITECTURE §Status Model](SOURCEOFARCHITECTURE.md); align UI labels to it (presentation mapping where DB values stay); remove dead branches.
- **Acceptance:** A documented mapping exists DB→API→UI for all five axes; no template references a status the DB cannot produce; badges read consistently across editor/tree/QA.

---

## P2 — Improvements

### WV-007 — Structural EPUB validation not joined into the QA report
- **Area:** Validation
- **Type:** Service + UI
- **Evidence:** `readers/epub_validation.py` issues appear only in the structure preview; `services/translation_qa.py` builds translation-only reports.
- **Root cause:** Two report shapes from two sprints.
- **Fix direction:** Add a `structure` QA category sourced from the persisted snapshot's validation rows; surface in `qa.html` with the existing filters.
- **Acceptance:** The QA report shows structural findings (missing cover/image, NAV/spine mismatch, etc.) under a `structure` category at novel/volume scope; counts roll into the badge; no re-parse on render (reads the snapshot).

### WV-008 — Missing validation checks + no `error` severity tier
- **Area:** Validation
- **Type:** API (checks) + Test
- **Evidence:** `qa/checks.py:12` severities = `info|warning|critical`; only a *minimum* length-ratio check (`check_length_ratio`); no honorific/punctuation/line-break/max-length checks vs `sourceofarchitecture.md §14.2`.
- **Root cause:** Phase B shipped a focused check set.
- **Fix direction:** Add max-length-ratio, honorific-mismatch, punctuation-mismatch, broken-line-break checks; introduce an `error` tier between `warning` and `critical`; unit-test each.
- **Acceptance:** Each new check has a passing/failing unit test; severities are `info/warning/error/critical`; badge mapping updated; no LLM use (deterministic only, ADR 008).

### WV-009 — Export always advisory; no Final gate, no export history
- **Area:** Export
- **Type:** Service + Storage + UI
- **Evidence:** Preflight never blocks (`ui_qa.py:185-189`); no `exported` status (`volume_lifecycle.py:18-23`); no per-artifact ledger.
- **Root cause:** Deliberate "never silently block" (ADR 008) + no export-history spec.
- **Fix direction:** Keep advisory default; add an **opt-in** "block Final on unresolved critical" toggle with a Draft escape hatch; persist an export-history ledger (date/format/status/validation/path/size/version) + a persisted export status axis.
- **Acceptance:** Draft export always succeeds; Final export with the toggle on refuses when criticals remain and explains why; an export history list shows past artifacts with their validation result; migration tested.

### WV-010 — Project identity is name-based; no cross-project read layer
- **Area:** Storage / Architecture
- **Type:** Storage + Service + API
- **Evidence:** Routes use `{name}` (`api/routers/ui.py` passim); cross-project data needs per-DB scans (`project_discovery`); `_single_project_id` assumes one project per DB (`project_tree.py:149`).
- **Root cause:** "One project = one DB" MVP simplification.
- **Fix direction:** Introduce a stable project id at the discovery/index layer; add a thin cross-project read layer (read-only index of projects/volumes/jobs) to back Workspace hubs without a global mutable store.
- **Acceptance:** A stable id resolves a project independent of its display name; a cross-project read returns project/volume/job summaries within budget on N projects; no SQLite access added to CLI/web layers; ADR 010 (in-process) unviolated.

---

## P3 — Enhancements

### WV-011 — Vestigial `qa_warnings` table
- **Area:** Storage
- **Type:** Storage cleanup
- **Evidence:** `grep qa_warnings` → `schema.sql`, `storage/volumes.py`, `services/volume.py` (delete cleanup), tests only — never written by the QA path.
- **Root cause:** Legacy carry-over from pre-reset CLI `validate`.
- **Fix direction:** Either wire QA to persist into it (supports WV-006/WV-003 "last validated") or remove it + its delete-cleanup. Decide alongside the Validation-persistence call.
- **Acceptance:** The table is either populated by a real code path or removed with its cleanup; no orphan references; migration note in `docs/MAINTENANCE.md`.

### WV-012 — Two preview concepts and two export paths
- **Area:** Preview / Export
- **Type:** Service + Doc
- **Evidence:** CLI `services/preview.py` (text pairs) vs web structure preview; legacy `services/export.py` (single-project) vs `services/export_book.py` (volume-aware) — documented as an accepted boundary (`docs/WEB_WORKFLOW.md:270`, `ARCHITECTURE.md:39`).
- **Root cause:** Parallel CLI/web evolution; deliberate MVP boundary.
- **Fix direction:** Document the boundary in one place; once WV-002 (Reading Preview) lands, deprecate the CLI text-pair preview or align it; consider back-porting volume-aware export to the CLI (post-Q).
- **Acceptance:** One doc section defines which path is canonical for each surface; no behavior change required for closure (doc-led).

### WV-013 — Editor lacks an inline context panel
- **Area:** Translation Editor
- **Type:** UI
- **Evidence:** `workspace.html` is 2-column; glossary/characters/candidates/history are separate pages (`_sidebar.html`, `candidates.html`); `sourceofarchitecture.md §13.1` wants 3 columns.
- **Root cause:** Editor predates candidates; never merged.
- **Fix direction:** Add a right-hand context panel (detected glossary terms, characters in segment, AI candidates with Generate, history, consistency warnings) as HTMX fragments.
- **Acceptance:** A translator consults glossary/characters/candidates/history without leaving the editor; panel updates on segment focus; no new dependency.

### WV-014 — Furigana/ruby and vertical-text fidelity unverified
- **Area:** Parser / Renderer (LN-specific)
- **Type:** Parser + Test (investigation)
- **Evidence:** Honorifics via glossary supported (`test_cli_honorifics.py`); no evidence of ruby/`<rt>` or `writing-mode` handling in readers/renderers; TXT/HTML synthesis path may flatten markup (`renderers/epub_synthesis.py`).
- **Root cause:** Not in MVP scope.
- **Fix direction:** Spike: confirm whether ruby/furigana and vertical text survive import→export; if lost, scope a preservation task.
- **Acceptance:** A documented finding (preserved or lost) with a fixture; if lost, a follow-up issue with scope.

---

## Backlog summary

| ID | Title | Priority | Type (lead) | Sprint |
|---|---|---|---|---|
| WV-001 | Candidate/draft generation in UI | **P0** | UI | P |
| WV-002 | Reading/output Preview | P1 | API+UI | P |
| WV-003 | Review/Validation split + review status | P1 | Storage+API+UI | P |
| WV-004 | Navigation unification | P1 | UI | P |
| WV-005 | Project Overview | P1 | API+UI | P |
| WV-006 | Single status taxonomy + kill dead branches | P1 | Storage+API+UI | P |
| WV-007 | Join structure validation into QA | P2 | Service+UI | P |
| WV-008 | Missing checks + `error` tier | P2 | API+Test | P |
| WV-009 | Final-export gate + export history | P2 | Service+Storage+UI | P/Q |
| WV-010 | Project id + cross-project read layer | P2 | Storage+Service | Q |
| WV-011 | Remove/wire `qa_warnings` | P3 | Storage | P/Q |
| WV-012 | Resolve preview/export duplications | P3 | Service+Doc | Q |
| WV-013 | Editor context panel | P3 | UI | P |
| WV-014 | Furigana/vertical-text fidelity spike | P3 | Parser+Test | Q |
