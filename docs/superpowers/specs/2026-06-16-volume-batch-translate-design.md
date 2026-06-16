# Volume batch translation from the project page

**Date:** 2026-06-16 · **Branch:** `feat/connection-first-routing` · **Scope:** cockpit project page

## Problem

Owner-reported, project page (`/ui/projects/{name}`): translating a whole volume requires
entering the workspace chapter-by-chapter. There is no one-click "translate this volume"
that fills in only the missing/untranslated segments and shows progress in place.

The batch backend already exists (`services/batch_translate.prepare_batch_translation` +
`run_batch_translation`, JSON API `POST /{name}/batch/volumes/{id}` with job + SSE). Only a
cockpit surface on the project page is missing.

## Decisions (owner, 2026-06-16)

- Add a **Translate volume** button beside **Delete volume** in each volume row.
- Mode is **`skip_existing`** — only pending/failed/stale segments; never overwrite manual
  or already-translated work.
- Progress shows **inline in the volume row** (self-polling fragment, mirroring the existing
  export job panel), not on a separate page.
- Out of scope (separate follow-ups): 0/0 illustration-chapter handling (#2a, mark-only) and
  image/illustration OCR translation (#2b, deferred by ADR 012 — needs a new ADR).

## Design

Reuse, no new translation logic. The UI routes call the same service path the JSON batch API
uses (`batch.py:_start_batch`), exactly as `ui.py:ui_export` reuses `export.py:_start_export`.

### Routes (`api/routers/ui.py`)
- `POST /ui/projects/{name}/volumes/{volume_id}/translate` — start a `volume`-scope,
  `skip_existing` batch job via `_start_batch`; render `_batch_job.html` into the row slot.
  `_start_batch` raises `HTTPException` (404 unknown project/volume, 422 bad config,
  502 unhealthy provider) → render `_job_error.html` in the slot (failure visible, anti-slop).
- `GET /ui/projects/{name}/batch/jobs/{job_id}` — poll one batch job; render `_batch_job.html`
  (self-refresh until terminal).
- `POST /ui/projects/{name}/batch/jobs/{job_id}/cancel` — cooperative cancel; render the panel.
- `GET /ui/projects/{name}/tree` — render `_tree.html` (for the on-done "Refresh progress").

### Partial `_batch_job.html` (mirrors `_export_job.html`)
Slot id = `batch-vol-{{ job.scope_id }}` (the volume id), so each volume row owns its panel.
- **running:** progress bar `chapters_done/chapters_total`; meta
  `segments_done/segments_total · translated · reused · failed` + current chapter; **Cancel**;
  self-poll `hx-get .../batch/jobs/{id}` `hx-trigger="load delay:1s"` `hx-swap=outerHTML`.
- **failed:** `job.error`.
- **done/cancelled:** result line `translated · reused · skipped · failed` (+ cancelled) and a
  **Refresh progress** button (`hx-get .../tree` → `#tree`) so the volume bar updates without
  leaving the page.

### Template `_tree.html`
In `vol-head__title`: a **Translate volume** button
(`hx-post .../volumes/{id}/translate`, `hx-target="#batch-vol-{id}"`, `hx-swap=outerHTML`)
plus an empty slot `<div id="batch-vol-{id}" class="batch-slot"></div>`.

## Validation
- pytest: start returns the running panel; unknown volume → error fragment; poll renders;
  cancel renders; tree route renders. Use `FakeProvider`/`fake` provider; never a live model.
- Live (playwright): click Translate volume on a partially-translated volume → panel polls →
  done shows counts; Refresh progress updates the bar. No provider call on project-page render
  (Gate B1).
- `ruff`, `ruff format`, `pyright`, glossary/ui suites green.

## Non-goals
- No new batch logic, no SSE (polling fragment is enough and matches the export pattern).
- No change to `skip_existing` semantics. No 0/0 handling. No OCR.
