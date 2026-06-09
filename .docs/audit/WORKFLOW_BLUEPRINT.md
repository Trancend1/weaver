# Workflow Blueprint

> **Purpose.** The audited target workflow for every Weaver process, derived from [`docs/sourceofarchitecture.md`](../../docs/sourceofarchitecture.md) and reconciled against the actual implementation in [THE_COUNCIL_WEAVER_AUDIT](THE_COUNCIL_WEAVER_AUDIT.md).
> **Reading guide.** Each process states **Today** (what the repo does, with evidence), **Target** (the audited ideal), and **Delta** (what must change, with the responsible sprint from [ROADMAP_REPLAN](ROADMAP_REPLAN.md)).
> **Legend.** ✅ built · ◑ partial · ⬜ missing.

---

## 0. The spine

```text
Import → Inspect → (Parse/Reparse) → Translate → Review → Validate → Preview → Export → Recover/Iterate
```

The user must always know three things on every page (`sourceofarchitecture.md §23`): **what they are working on**, **where progress stands**, **what to do next**. The blueprint below holds that contract at each step.

```text
Dashboard
  → Select Project → Project Overview
    → Select Volume → Content Explorer (inspect structure)
      → Translation Editor (chapter/segment)
        → Review (human) ⇄ Validation (automatic)
          → Reading Preview (translated output + before/after)
            → Export (draft → final, versioned)
              → Recover / iterate
```

---

## 1. Import

- **Today (◑).** Cockpit New-project (upload **or** browse a sandboxed source) and Import-volume; CLI `weaver init` / `weaver import`. Source is read by `read_epub`→`DocumentIR`, scoped to a volume, persisted. Sandboxed (`source_browser`, `source_intake`), upload-capped, EPUB/TXT/HTML.
  - *Evidence:* `api/routers/ui.py:600,643`; `docs/WEB_WORKFLOW.md:32,154`.
  - *Gap:* **sourceless project creation is unsupported** — a project cannot exist before its first volume.
- **Target.** Create an empty Project, then attach one or more Volumes. Import shows: detected format, volume title, and a one-click path to Inspect. A Project is the series; each EPUB/TXT/HTML is a Volume inside it (`sourceofarchitecture.md §4.2–4.3`).
- **Delta.**
  - ⬜ `POST /projects` explicit create-without-import (already specced in `weaver_next_plan.md` Sprint H; verify shipped, else carry into **Sprint P**).
  - ◑ Import confirmation should route into **Content Explorer**, not back to a flat tree.

---

## 2. Inspect (structure)

- **Today (✅).** Structure preview: metadata, TOC (NAV/NCX), spine reading order, image inventory with roles + gated byte preview, structural validation issues with a safe/warnings/errors readiness badge. Persisted as a versioned snapshot.
  - *Evidence:* `templates/epub_preview.html`; `routers/ui.py:483`; snapshot `storage/schema.sql:187`.
- **Target = Content Explorer** (`sourceofarchitecture.md §12`): Volume tree (spine order, *not* raw file order) · Chapter list (counts + statuses) · Segment list (jump to problems) · Asset browser (cover/illustrations/character pages/dividers/CSS/fonts) · Metadata inspector · Structure warnings.
- **Delta.**
  - ◑ Reframe the structure preview as the **Content Explorer** entry surface; keep the snapshot as its data source.
  - ⬜ Add Chapter-list + Segment-list views with per-node status badges (depends on the unified status taxonomy).
  - **Sprint:** P (reframe + status), Q (full asset/segment explorer).

---

## 3. Parse / Reparse

- **Today (✅).** Reparse runs as a Sprint-I job; snapshot invalidates on `source_hash` or `parser_version` change; UI shows a "reparse" CTA when stale.
  - *Evidence:* `routers/ui.py:424`; `services/epub_reparse.py`; `services/epub_snapshot.py`.
- **Target.** Unchanged — reparse-as-job is correct. Surface staleness inside Content Explorer and the export preflight (already partially done — `ui_qa.py:223`).
- **Delta.** ✅ No structural change. Wire the stale CTA into Content Explorer once it exists (Sprint P/Q).

---

## 4. Translate

- **Today (◑).** Two-column JP/EN chapter editor; per-segment save (→ `manual`); Translate / Retranslate (`skip_existing` / `retranslate_non_manual` / `force_selected`); live job panel (SSE+poll); TM lookup + glossary/character injection; on-demand history; filters; shortcuts.
  - *Evidence:* `templates/workspace.html`; `partials/_segment.html`; `routers/ui.py:825-879`; `docs/WEB_WORKFLOW.md:221-243,308-319`.
  - *Gaps:* no inline **context panel**; **no candidate generation** from the editor; dead status branches (`reused/tm/memory`).
- **Target = Translation Editor** (`sourceofarchitecture.md §13`): 3 columns — Content tree | Editor (source / translation / notes / status / actions) | **Context panel** (glossary terms, characters, **AI candidates**, history, consistency warnings). Actions include `Translate Segment`, `Retranslate`, `Translate Chapter`, `Compare Candidates`, `Approve AI`, `Approve as Manual Edit`.
- **Delta.**
  - ⬜ Add an inline context panel beside the editor.
  - ⬜ Add **Generate candidate** to the segment row (P-01 fix — service exists: `services/candidate_generation.generate_candidate`).
  - ⬜ Remove dead status branches; show the canonical translation status.
  - **Sprint:** P.

---

## 5. Review (human)

- **Today (◑).** Candidate-review and character-draft pages (approve/reject/apply). Glossary candidate review is the most complete loop. **Generation is JSON-only — not in the UI.** No per-segment human-review state.
  - *Evidence:* `routers/ui.py:935-1133`; `routers/candidates.py:146,269`; `candidates.html:14`; `grep candidates/generate` in templates → none.
- **Target.** **Review = the human editorial checkpoint** with a persistent per-segment state (`Not Reviewed / Needs Review / Needs Revision / Approved / Rejected`, `sourceofarchitecture.md §20.2`). A **Review Queue** lists segments needing attention (needs-review, suspicious, glossary/character conflicts, untranslated) with filters by chapter/severity/type/status. A **Resolution Workflow** offers `Open in Editor / Accept Current / Edit / Retranslate / Ignore Once / Mark Resolved / Add to Glossary / Add Character Mapping` (`§14.5`). Generating a candidate **never** mutates the current translation; only Approve promotes it (invariant already enforced by `apply_candidate`).
- **Delta.**
  - ⬜ Surface candidate/draft **generation** (P-01).
  - ⬜ Add a persisted **review status** axis on segments (P-03).
  - ⬜ Build a Review Queue + resolution actions.
  - **Sprint:** P (generation + review status + queue MVP), Q (full resolution actions).

---

## 6. Validate (automatic)

- **Today (◑).** Deterministic QA over chapter/volume/novel; severity `info/warning/critical`; badge `clean/warnings/errors`; categories `completeness/staleness/consistency/quality/export_readiness`; advisory preflight. **Structure validation is a separate engine, not in the QA report.** Computed on demand; never persisted.
  - *Evidence:* `services/translation_qa.py`; `qa/checks.py`; `ui_qa.py`; `readers/epub_validation.py` (separate).
- **Target = Validation** (`sourceofarchitecture.md §14.2–14.4`): one report covering translation **and** structure checks. Add max-length ratio, honorific mismatch, punctuation mismatch, broken line breaks; severities `info/warning/error/critical`. Validation status is per-segment-derivable (`Not Checked/Passed/Warning/Failed/Critical`).
- **Delta.**
  - ⬜ Join structural findings (from the persisted snapshot) into the QA report as a category (P-06).
  - ⬜ Add the four missing checks + the `error` tier.
  - ◑ Decide persistence: keep on-demand (cheap) but expose a per-scope "last validated" timestamp; remove the unused `qa_warnings` table or repurpose it (P-10).
  - **Sprint:** P (join + checks + tier), Q (persistence decision).

---

## 7. Preview (output)

- **Today (⬜).** No translated reading preview. "EPUB Preview" shows **source** structure. CLI `weaver preview` prints source/translation text pairs (not a reading view).
  - *Evidence:* `epub_preview.html:156`; `services/preview.py`.
- **Target = EPUB Preview** (`sourceofarchitecture.md §15`): Reading Preview (cover → illustrations → chapter flow → inserts → afterword) of the **translated** output · Before/After (source ↔ translation; original ↔ export layout; image preserved/translated) · Image Preview in context · Structure Preview (final order).
- **Delta.**
  - ⬜ Build a read-only Reading Preview by reusing the export renderer (`renderers/rendered_document.RenderChapter` / `block_to_html`) **without writing files** (P-02).
  - ⬜ Add a Before/After segment view (source + current translation side by side — `services/preview.py` already computes the pairs; needs a web surface).
  - **Sprint:** P.

---

## 8. Export

- **Today (✅/◑).** Volume-aware EPUB/TXT/HTML/DOCX (one artifact per volume) + optional ZIP bundle; advisory preflight; atomic write; post-export fidelity report; snapshot-faithful EPUB. Legacy single-project CLI exporter remains.
  - *Evidence:* `services/export_book.py`; `renderers/*`; `services/epub_export_fidelity.py`; `ui_qa.py:180`; `routers/ui.py:896`.
  - *Gaps:* always advisory (no Final gate); no persisted export status/history.
- **Target = Export** (`sourceofarchitecture.md §16`): Export Readiness · Format Selection · Export Settings (preserve structure/images, include metadata/glossary appendix/review notes, scope) · **Validation Gate** (draft always allowed; **opt-in** require-clean for Final) · **Export History** (date/format/status/validation result/path/size/version label) · Output files.
- **Delta.**
  - ◑ Keep advisory default; add an **opt-in** "block Final on unresolved critical" + a Draft/Final distinction (P-07).
  - ⬜ Persist an **export-history ledger** + a persisted export status axis.
  - **Sprint:** P (gate toggle + Draft/Final), Q (history ledger + settings panel).

---

## 9. Recover / Iterate

- **Today (✅).** Cold-start recovery marks orphaned `running` jobs `failed` with a stable reason; jobs survive refresh (SSE resume from last persisted event). Manual edits are append-only history; retranslate never destroys prior attempts.
  - *Evidence:* `api/app.py:91`; `services/job_store.py`; `docs/WEB_WORKFLOW.md:241`.
- **Target.** Unchanged — this is a strength. Add a single **Job Detail / Active Jobs** affordance reachable from the global nav (the Job Detail page exists at `routers/ui.py:273`; it needs a global entry point once the Workspace nav lands).
- **Delta.** ◑ Add a global "Active jobs" entry point (Sprint P/Q). Iteration loop (fix issue → regenerate export) is functional once Preview (P-02) + Review (P-03) close the loop.

---

## 10. End-to-end target walkthrough

```text
1.  Dashboard            → see current project, progress, next action, queue, provider health, activity
2.  Open Project         → Project Overview (summary · progress · health · current activity · quick actions)
3.  Select Volume        → Content Explorer (spine reading order · chapters · segments · assets · metadata · warnings)
4.  Translate            → 3-column editor: source | translation | context (glossary/characters/candidates/history)
                            - Generate candidate (never mutates current) → Compare → Approve/Approve-as-manual
5.  Review (human)       → Review Queue (needs-review/suspicious/conflicts) → resolution actions → per-segment review status
6.  Validate (auto)      → one report: translation + structure checks, severity info/warning/error/critical
7.  Preview (output)     → Reading Preview of translated flow + Before/After + in-context illustrations
8.  Export               → Readiness → Format/Settings → Validation Gate (Draft always / Final opt-in clean) → versioned artifact + history
9.  Iterate              → fix flagged issues → regenerate export → next volume; jobs are refresh-safe and recoverable
```

Steps 1–3 (Dashboard command-center, Project Overview, full Content Explorer) and the Workspace hubs are **Sprint Q**; steps 4–8's coherence fixes are **Sprint P**; the recovery spine (step 9) is already built.
