# Weaver — UI Design Notes

Concise, current reference for maintaining the web cockpit UI. Reflects what is
actually shipped (not aspirational). The full design exploration that seeded this
(Cal.com token study + hybrid-layout guide) lived in `docs/DESIGN.md` /
`docs/DESIGN_GUIDE.md` and is preserved in **git history** — these notes replace them.

## Hard constraints (do not break)

- **Server-rendered Jinja2 + HTMX.** No SPA, no client framework, no build step.
- **No web fonts.** System UI stack only (`--font-ui`). Type hierarchy comes from
  weight / size / tracking / `tabular-nums`, never from loaded fonts.
- **Functional over decorative.** No glassmorphism, parallax, grain, spring physics,
  marketing imagery. Motion is limited to ≤140ms hover/press transitions and the HTMX
  indicator; `prefers-reduced-motion` is honored globally.
- **No backend logic in templates.** Routes call `services/*`; templates only present.
- **Never rename/remove these HTMX hooks:** `#tree`, `#ws-grid`, `#job-panel`,
  `#export-panel`, `#browser`, `#selected_source`, `#source_path`, `#qa-badge-status`,
  `#qa-issues`, `id="seg-{id}"`, and the `qa-badge-vol-*` / `qa-badge-ch-*` slots.

## Tokens — single source: `api/static/app.css` `:root`

- **Color:** `--color-page` (app bg, tinted gray) · `--color-canvas` (white cards) ·
  `--color-surface` (faint fills, th, JP column) · `--color-panel` / `-strong` ·
  `--color-line` / `-soft` (borders) · `--color-ink` / `-body` / `-muted` / `-muted-soft`
  (text) · `--color-primary` (black CTA) · `--color-ok` / `-warn` / `-bad` / `-info`.
- **Type scale:** `--text-xs … --text-display`. h1 760/-0.018em, h2 720, h3 = uppercase
  label. Numeric data uses `font-variant-numeric: tabular-nums`.
- **Spacing:** `--space-xxs … --space-xxl` (4px base). **Radius:** `--radius-xs … -pill`.
- **Shadow:** `--shadow-card` (cards), `--shadow-panel` (subtle). Neutral, low-alpha.
- **Layout:** `--topbar-height` 56 · `--sidebar-width` 264 · `--sidebar-collapsed` 56 ·
  `--content-max` 1160 · `--content-wide` 1480 · `--control-height` 40.
- **z-index scale:** `--z-sticky` 5 · `--z-sidebar` 20 · `--z-topbar` 30 (no magic numbers).

## Layout — 3 modes, URL-dispatched in `api/ui_context.py`

| Mode | Pages | Shell |
| --- | --- | --- |
| **global** | `/ui`, `/ui/new`, `/ui/config` | topbar only, content centered (max 1160) |
| **project** | project, glossary, characters, memory, quality | topbar + 264px sidebar (tree + nav) |
| **workspace** | chapter editor | topbar + 56px icon rail |

- **Topbar** (`base.html`): brand (feather mark + wordmark) **left**, primary nav left
  next to it, active link = surface bg + weight 700 + `aria-current`. Same in all modes.
- **Content** is centered with a bounded width inside the post-sidebar column.
- **Mobile (CSS only, no JS hamburger — deferred):** ≤900px project sidebar collapses to
  a horizontal scroll strip (tree hidden); ≤720px workspace sidebar hidden, grids → 1 col.
- Breadcrumb is the standard "back" affordance, emitted by `_page_header.html` on every
  page (including 404 / error).

## Components (partials under `api/templates/partials/`)

- **Panels** `.panel` — white card, hairline, `--radius-lg`, `--shadow-card`.
- **Project cards** (`dashboard.html`) — name + status badge, provider/model, progress
  bar + %, stat row; whole card is a link with hover-lift.
- **Volume cards** (`_tree.html`) — header with title, QA slot, format, overall progress.
- **Stat tiles** (`_qa_summary.html`, `.stat`) — big number + label, colored when non-zero.
- **Sub-nav** `.subnav` — contained segmented control (not floating links).
- **Badges** `.badge` + `.ok` / `.bad` / `.warn`. **Buttons** `.btn`, `.btn--primary`
  (black), `.btn--danger` (red ghost), `.btn--sm`. **Tables** `.grid` in `.table-scroll`.
- **Icons** — inline SVG line set via `{% from "partials/_icons.html" import icon %}`
  (no icon font, no sprite build). Sidebar nav + brand mark + favicon use it.
- **Page header** `_page_header.html` — breadcrumb + h1 + meta + optional actions slot.

## States & a11y

- Hover, `:active` (1px press), `:focus-visible` (2px `--color-focus` ring), and
  `:disabled` are defined for buttons and inputs.
- Empty (`_empty_state.html`), error (`.error` + `role="alert"`), loading (HTMX
  indicator + native `<progress>`). No toasts, no `alert()`.
- Semantic HTML; `role="status"` on save; `aria-current` on active nav; copy is
  sentence-case, active-voice, no exclamation/"oops".

## Tests that pin UI copy/structure

`tests/unit/api/test_ui_shell.py`, `test_ui_layout.py`, `test_ui_qa.py`,
`test_ui_export_preflight.py`, `test_ui_delete.py`. Update these when intentionally
changing user-facing strings or layout-mode markers.
