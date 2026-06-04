# Phase A — UI/UX Polish · Stage A1 UX Audit

> **Status:** Stage A1 (audit only — no implementation). Gate A1 deliverable.
> **Scope:** FastAPI cockpit UI (`src/weaver/api/templates/**`, `src/weaver/api/static/app.css`,
> `routers/ui.py`, `routers/ui_admin.py`). Server-rendered Jinja2 + HTMX (ADR `007`).
> **Baseline:** `v0.7.0-rc.1` (FastAPI default, Flask removed). Functional parity reached; this
> phase is **polish/stabilization, not new core architecture**.
> **Non-goals (Phase A rules):** no new major backend features · no provider expansion · no DOCX ·
> no React/Vue/Node · keep Jinja2 + HTMX · keep FastAPI default · preserve CLI behavior · fix only
> UX bugs or small missing affordances.

---

## 1. Method

Static audit of every UI template, the single stylesheet, and the two presentation-only routers.
Findings are grounded in source (file:line). A live rendered/interaction pass (screenshots at
desktop + 390px, keyboard walk) is **the first task of Stage A2**, not a prerequisite for this
audit — every finding below is verifiable from the code as written.

Finding IDs: `C#` = cross-cutting (shared shell, fixes once → helps every page); page prefixes
`D` dashboard · `N` new · `P` project · `W` workspace · `G` glossary · `Ch` characters · `M` memory ·
`Cfg` config · `E` error/404.

---

## 2. Cross-cutting findings (shared shell)

These live in `base.html` / `app.css` and therefore affect **every page at once** — highest leverage.

| ID | Finding | Evidence | Sev | Effort |
|----|---------|----------|-----|--------|
| **C1** | Only `h1` is styled (1.3rem). `h2`/`h3` use UA defaults (~1.5em / 1.17em), so **section headings render *larger* than the page title** on project/glossary/config pages. Broken visual hierarchy. | `app.css:40` styles `h1` only; no `h2`/`h3` rule. Seen on `project.html` (h2 "Export novel"/"Import a volume"), `glossary.html` (4× h2), `config.html`. | High | S |
| **C2** | **No responsive handling at all** — zero `@media` queries. Dashboard's 9-column table and the topbar overflow at 390px. Mobile usability is a stated phase-gate item. | `app.css` (whole file, no `@media`); `dashboard.html:13–39` 9 cols; `.content{max-width:1100px}` only. | High | M |
| **C3** | **No `:focus`/`:focus-visible` styles.** Keyboard focus is invisible on links, buttons, inputs, and the link-styled action buttons. Fails a11y "focus visible" basic. | `app.css` has `button:hover` (`:75`) but no focus rule anywhere. | High | S |
| **C4** | No `prefers-reduced-motion` guard. The `.htmx-indicator` opacity transition (and any future motion) ignores the user's reduced-motion preference. | `app.css:125` transition; no media guard. | Low | S |
| **C5** | Topbar nav has no active/current-page state — user can't tell where they are. | `base.html:13–17`. | Low | S |
| **C6** | Internal/dev jargon leaks into chrome: header hint **"FastAPI cockpit (functional-parity UI)"** and footer **"serve-api · local only (127.0.0.1)"**. Meaningless to an end user; "functional-parity" is sprint vocabulary. | `base.html:18`, `base.html:26`. | Med | S |
| **C7** | **Placeholder-as-label** in all inline add/edit rows (glossary, characters, secrets). Placeholders disappear on input and aren't reliable accessible names. | `_glossary_terms.html:13–15,36–39`, `_characters.html:13–16,38–42`, `_secrets.html:22–23`. | Med | M |
| **C8** | No loading indicator on most mutating swaps. Import/segment-save/job-poll have one (`htmx-indicator`), but **glossary add/edit/delete, character add/edit/delete, candidate approve/reject, config save, secret set/delete have none** — slow ops give zero feedback. | `_glossary_terms.html`, `_characters.html`, `_glossary_candidates.html`, `_config_form.html`, `_secrets.html` (no indicator spans). | Med | M |
| **C9** | **Destructive actions have no confirmation.** Delete glossary term / character / TM entry / secret fire immediately on click; no `hx-confirm`, no undo. Real data-loss risk. | `_glossary_terms.html:22–24`, `_characters.html:24–26`, `_memory.html:15–17`, `_secrets.html:9–12`. | Med-High | S |
| **C10** | Error fragments are color-only (`<p class="error">`) with no `role="alert"`/icon — not announced to screen readers, weak for color-blind users. | `_glossary_terms.html:2`, `_job_error.html:2`, etc. | Low | S |

---

## 3. Page-by-page issues

### 3.1 Dashboard (`dashboard.html`)
- **D1 (High/S, copy bug):** Empty-state says *"Create one with the CLI (`weaver init <source>`) — the create/import UI lands in Sprint 11B."* That UI **shipped** (`/ui/new`). Copy is wrong and steers users away from the in-app flow. → `dashboard.html:43`.
- **D2 (Med/M):** 9-column table is dense; no row hover/zebra, no scan aids. "Translated"/"Pending" are raw counts with no ratio/progress cue. → `dashboard.html:13–39`.
- **D3 (Low/M, affordance):** No per-row quick actions (open / translate / export) — every action requires drilling into the project first.
- **D4 (Low-Med/S):** Error projects expose detail only via `title="{{ p.error }}"` tooltip — invisible on touch/keyboard. → `dashboard.html:33`.

### 3.2 New novel (`new.html`)
- **N1 (Low-Med/M):** Provider/Template are free-text inputs (placeholder "(default)") — no list of valid providers, easy to typo into a 422. A datalist/select would match the known registry. → `new.html:18–19`.
- **N2 (Low/S):** Plain (non-HTMX) POST with no submit/loading state; large EPUB parse looks frozen. → `new.html:11,20`.
- **N3 (Low/S):** Choosing both an upload *and* a browsed source is ambiguous; no way to clear a chosen browsed source once "use" is clicked. → `new.html:12–17`, `_browse.html:19–22`.

### 3.3 Project view (`project.html`)
- **P1 (Med/S):** Section order is Tree → **Export** → **Import**. For a fresh project with no volumes, the primary next action (Import) sits *below* an Export panel that can do nothing. Order/empty-state hierarchy is backwards for the empty case. → `project.html:13–56`.
- **P2 (Low/S):** Export offers no hint when nothing is translated yet (silently produces all-fallback output). → `project.html:16–31`.
- **P4 (Med/M):** Tree chapters show `N seg` only — no translated/pending per chapter, so progress isn't visible at the tree level. → `_tree.html:14–15`.

### 3.4 Workspace (`workspace.html` + `_segment.html` + `_job.html`)
- **W1 (Med/M):** On job completion the segment grid is **not** auto-refreshed; the done panel just offers a "Reload chapter" link. User must manually reload to see new translations. → `_job.html:23`.
- **W2 (Low-Med/S, copy):** "Translate untranslated" (button) and the Retranslate select both expose `skip_existing`; the relationship is unclear and the option is redundant across the two controls. → `workspace.html:13–29`.
- **W3 (Med/M):** No "unsaved changes" indicator and no bulk save — editing several segment textareas then navigating away silently loses unsaved edits. → `_segment.html:9`.
- **W4 (Low-Med/S):** Segment status badge only colors `manual`/`translated` as "ok"; `failed`/`stale`/`pending` render as neutral. **`failed` should read as bad.** → `_segment.html:12`.
- **W5 (Low/S):** Translation `<textarea rows=3>` is fixed-height; long segments require inner scroll, no auto-grow. → `_segment.html:9`.
- **W6 (Low/S):** Opened history has no collapse/close and renders into the EN column only. → `_segment.html:21`, `_history.html`.
- **W7 (Low/S, affordance):** No keyboard save (e.g. Ctrl+Enter) in the textarea.

### 3.5 Glossary (`glossary.html` + partials)
- **G1 (Low-Med/S, affordance):** Candidate review supports a server-side `find` filter (`list_pending(..., find=)`) but there is **no search box** in the UI — the filter is unreachable. → `ui_admin.py:72–86`, `_glossary_candidates.html` (no search input).
- **G2 (Low/S):** Four stacked h2 sections (Approved / Candidates / Conflicts / Coverage) on a long page with no in-page subnav or anchors. → `glossary.html`.
- **G3 (Low/S, copy):** Coverage diff labels "Chapter A/B" take ordinal numbers (default 1/2) with no explanation of what the ordinal maps to. → `glossary.html:32–38`, `_glossary_diff.html`.
- **G4 (Low/—):** Inline "Edit + approve" omits the notes field even though the service accepts notes. → `_glossary_candidates.html:16–22`.

### 3.6 Characters (`characters.html` + `_characters.html`)
- **Ch1 (Low/M):** Add row is 5 inline inputs that wrap awkwardly on narrow widths; placeholder-as-label (see C7). → `_characters.html:36–43`.

### 3.7 Translation memory (`memory.html` + `_memory.html`)
- **M1 (Med/M):** No pagination or search on the TM table — a full-length novel can render thousands of rows in one page. (Contrast: glossary candidates *are* paged.) → `_memory.html:4–22`.
- **M2 (Low/S):** Long source/target cells aren't truncated/wrapped for scanning. → `_memory.html:10–11`.

### 3.8 Config (`config.html` + `_config_form.html` + `_secrets.html`)
- **Cfg1 (Low-Med/M):** "Provider type" is free-text (placeholder lists the options) rather than a select over the known registry — typo-prone and inconsistent with the rest of the app. → `_config_form.html:24`.
- **Cfg2 (Low/S, copy):** Scope (project vs global) interaction is subtle; the default selection flips based on whether a project is loaded, with no explanation. → `_config_form.html:18–23`.
- **Cfg3 (Low/S):** Secret-set has no explicit success note after storing (only a silent re-render); pair with C8. → `_secrets.html:20–25`.

### 3.9 Error / 404 (`error.html`, `not_found.html`)
- **E1 (Low/—):** Functional and consistent; only inherits the cross-cutting heading/focus issues. No standalone fix needed.

---

## 4. Priority matrix

Buckets: **P0** = first slice (do now) · **P1** = next · **P2** = later in Phase A · **P3** = optional/stretch.
Effort: S ≤ ~30 min · M ≤ ~half day · L = larger.

| Priority | Findings | Why here |
|----------|----------|----------|
| **P0 — shell + correctness (first slice)** | C1, C3, C2, C4, C6, D1, W4, C9 | Shared shell + obvious correctness. Fix once → every page benefits. Pure presentation/copy + tiny `hx-confirm`. Zero backend/behavior/test risk. Directly satisfies the phase-gate's mobile-390 / focus-visible / "feel" items. |
| **P1 — feedback & safety** | C7, C8, C5, C10, P1, W1 | A11y labels, loading feedback on mutations, active-nav, alert roles, empty-case ordering, post-job refresh. Mostly template-level. |
| **P2 — per-page usability** | D2, D4, N1, N2, N3, P2, P4, W2, W3, W5, W6, G1, G2, G3, M1, M2, Cfg1, Cfg2, Cfg3, Ch1 | Page-specific scanning, missing affordances (candidate search, TM paging), copy clarity. |
| **P3 — stretch** | D3, W7, G4 | Nice-to-have affordances; defer unless cheap alongside a P2 in the same file. |

Severity roll-up: **High:** C1, C2, C3, D1. **Med-High:** C9. **Med:** C6, C7, C8, D2, P1, P4, W1, W3, M1. Rest Low/Low-Med.

---

## 5. Recommended first polish slice (Stage A2-1)

**"Global shell + CSS foundation + copy correctness"** — one presentation-only PR touching only
`base.html`, `app.css`, `dashboard.html`, the four destructive-delete partials, and `_segment.html`.

Contents (the P0 set):
1. **C1** — heading scale: explicit `h1/h2/h3` sizes so hierarchy reads correctly.
2. **C3** — visible `:focus-visible` ring on links, buttons, inputs, `.link-btn`.
3. **C2** — minimal responsive: topbar wraps; wide tables (dashboard/admin) get an `overflow-x` scroll wrapper or stack at ≤480px.
4. **C4** — `prefers-reduced-motion` guard around the HTMX indicator transition.
5. **C6** — replace dev-jargon chrome strings with plain user copy.
6. **D1** — fix the stale dashboard empty-state copy to point at `/ui/new`.
7. **W4** — status-badge colour map so `failed`/`stale` read distinctly (shared `.badge` variants).
8. **C9** — add `hx-confirm` to the four destructive delete buttons (term / character / TM / secret).

**Why this first:**
- **Leverage:** items 1–5 live in the shared shell, so the entire cockpit improves in one pass before any per-page work.
- **Risk:** templates + CSS + copy + one HTMX attribute only — **no router, service, schema, CLI, or API change**; existing tests and the soak driver stay green. Reversible.
- **Gate alignment:** knocks out the WORKFLOW phase-gate's mobile-390 / focus-visible / reduced-motion / "feel matches brief" items up front.
- **Unblocks:** establishes a sane visual baseline so P1/P2 per-page slices are judged against a correct hierarchy, not a broken one.

**Explicitly deferred from the first slice:** C7 (label semantics) and C8 (loading states) are P1 because they touch many partials and deserve their own focused pass; everything in §3 marked P2/P3 follows after.

---

## 6. Suggested Stage A2 sequence (for approval — not yet started)

1. **A2-1** P0 shell slice (above).
2. **A2-2** Feedback & safety (C7, C8, C5, C10) — labels, loading, active-nav, alert roles.
3. **A2-3** Workspace UX (W1, W2, W3, W5, W6) — the daily-driver surface.
4. **A2-4** Dashboard + project clarity (D2, D4, P1, P2, P4).
5. **A2-5** Admin usability (G1–G3, M1–M2, Cfg1–Cfg3, Ch1, N1–N3).
6. **A2-6** Live verification pass — desktop + 390px screenshots, keyboard walk, contrast check; demo-to-self.

---

## 7. Notes / out of scope

- A **live rendered pass** (screenshots, keyboard navigation, contrast measurement) belongs to A2-6;
  it confirms but does not change the findings above.
- Contrast spot-check from tokens: `--muted #5c6470` on `--bg #fff` ≈ 5:1 (passes AA for body text);
  worth re-measuring `--muted` on `--panel #f6f8fa` and small `.meta`/`.hint` text in the live pass.
- No backend, provider, DOCX, or framework work is implied by any finding here (Phase A rules).
