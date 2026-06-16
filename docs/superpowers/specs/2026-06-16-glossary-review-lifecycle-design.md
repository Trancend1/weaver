# Glossary review lifecycle — bulk approve + return-to-review

**Date:** 2026-06-16 · **Branch:** `feat/connection-first-routing` · **Scope:** cockpit glossary workflow

## Problem

Owner-reported, glossary page (`/ui/projects/{name}/glossary`):

1. **Bulk "Approve selected" loses the translation.** After "Suggest targets" fills each
   row's editable EN target, "Approve selected" submits the *approve* form, which uses the
   candidate's stored `target` (the extraction placeholder `target = source`, i.e. the JP
   term) and ignores the suggested EN in the input. The suggestion is never saved.
2. **No way to un-approve.** Approved terms only have *Save* and *Delete* (hard delete).
   There is no path to send a term back to Candidate review for another pass.

## Decisions (owner, 2026-06-16)

- **A.** "Approve selected" saves the current EN value in each row's target box (acts like
  per-row *Save & approve* = the `edit` action), and **skips** rows whose target box is
  empty or still equals the JP source (placeholder). No JP→JP garbage terms.
- **B.** Approved-terms *Delete* becomes **Return to review**: drop the approved term and put
  its source back in the pending candidate queue. A manually-added term (no originating
  candidate) gets a fresh pending candidate created from it.
- **C.** Candidate-review *Reject* is unchanged (marks `rejected` + removes the approved
  term). It remains the only hard "delete query" path.

## Design

### Storage — `storage/glossary.py`
`return_glossary_term_to_review(conn, *, project_id, source)`:
- Term must exist (`UNIQUE(project_id, source)`), else `LookupError`.
- Candidate with that source in status `approved`/`edited` → set `status = 'pending'`
  (keep its EN target so it is reviewable with the wording already filled).
- No such candidate (manual term) → `insert_glossary_candidate(..., status='pending',
  frequency=0)` from the term's source/target/category/notes.
- `DELETE FROM glossary_terms WHERE project_id = ? AND source = ?`.

### Service — `services/glossary_terms.py`
`return_term_to_review(project_toml, *, source, cwd)` — transaction wrapper, maps the
missing-term `LookupError` to `GlossaryTermNotFoundError`.

### Router — `api/routers/ui_admin.py`
`POST /ui/projects/{name}/glossary/term/delete` calls `return_term_to_review`, then returns
the Approved-terms fragment **plus** the Candidate-review fragment rendered out-of-band
(`hx-swap-oob="true"`) so both panels update live.

### Templates
- `_glossary_terms.html` — *Delete* button → **Return to review**; confirm copy updated.
- `_glossary_candidates.html` — `{% if oob %}hx-swap-oob="true"{% endif %}` on the root;
  per-row *Approve target* disabled when `not c.target or c.target == c.source`.
- `glossary.html` — `bulk("approve")` submits the `edit` action for selected rows that have
  a real EN target (skip placeholders). Listener delegation moved from the
  `#glossary-candidates` node to `document` so bulk/selection survive every swap
  (search, paging, and the new OOB return-to-review) — fixes a pre-existing latent bug.

## Non-goals
- No change to extraction's `target = source` seed (separate concern; the predicate + approve
  guard neutralize its downstream effects here).
- No hard-delete button in Approved terms (Return → then Reject is the delete path).
- Reject semantics unchanged.

## Validation
- pytest: storage (candidate-derived + manual-term + missing), service, router (OOB fragment).
- Live (playwright): suggest→approve-selected persists EN; Return to review moves a term back
  into Candidate review with both panels refreshed; bulk still works after a swap.
- `ruff`, `ruff format`, `pyright`, full glossary suite green.
