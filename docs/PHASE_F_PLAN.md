# Phase F — Feature Polishing

> Pre-user-testing hardening pass over the cockpit. Phase E delivered the design
> system and visual overhaul; Phase F makes every surface feel finished, consistent,
> and trustworthy, then locks a clean regression before real-user testing.

## 1. Purpose & scope

**In scope** (presentation + interaction quality, mostly CSS / Jinja2 / HTMX):

- **State coverage** — every surface has a deliberate empty / loading / error /
  hover / active / disabled state. No bare blank panels, no dead controls.
- **Workspace usability** — the core translation surface (segment grid, save/history,
  job panel, retranslate modes) re-walked for friction, keyboard flow, and clarity.
- **Responsive** — verified at 390px through wide; no horizontal overflow; tables
  scroll inside wrappers; the JS-free sidebar degradation holds.
- **Accessibility** — keyboard path, focus order, visible `:focus-visible`, contrast,
  form labels, `role="alert"` / `role="status"`, `aria-current`.
- **Copy consistency** — one term per concept, sentence case, active voice, no filler;
  helpful microcopy on every action and status.
- **Visual consistency** — spacing rhythm, radius/shadow scale, badge/button variants,
  iconography stroke, typography scale all uniform (audit against `DESIGN_NOTES.md`).
- **QA + export flow stabilization** — end-to-end on a real EPUB: preflight → export,
  quality report navigation, tree badges, bundle ZIP — no broken links or stuck jobs.
- **Docs cleanup** — `DESIGN_NOTES.md` and `COCKPIT_WORKFLOW.md` match the shipped UI.

**Out of scope** (deferred to later phases):

- New product features, provider/translation/QA/TM/export *behavior* changes,
  schema/API changes (a deliberate, ADR-backed exception may be raised if a polish
  item genuinely needs one — default is no).
- Distribution / installer work (Phase G).
- New dependencies, web fonts, SPA, build step, decorative motion.

## 2. Constraints (inherited)

- Server-rendered Jinja2 + HTMX, no build, no web fonts, functional-over-decorative,
  `prefers-reduced-motion` honored — see [DESIGN_NOTES.md](DESIGN_NOTES.md).
- Do not rename/remove the pinned HTMX hooks (`#tree`, `#ws-grid`, `#job-panel`,
  `#export-panel`, `#qa-badge-status`, `#qa-issues`, `seg-*`, qa-badge slots).
- Templates stay presentation-only; logic lives in `services/*`.

## 3. Stages

| Stage | Focus | Output |
| --- | --- | --- |
| **F1** | State audit — sweep every page/partial for missing empty/loading/error/disabled states; build a findings list with severity. | Findings doc (in PR description or this file's log) |
| **F2** | Workspace usability — segment grid, save/history, job panel, retranslate; keyboard + dirty-state + auto-grow re-verified. | Targeted template/CSS fixes + tests |
| **F3** | Responsive + accessibility pass — 390px→wide, focus order, contrast, labels. | Fixes + (where deferred) logged gaps |
| **F4** | Copy + visual consistency — terminology, sentence case, spacing/radius/shadow/badge/button uniformity. | Copy + CSS normalization |
| **F5** | Flow stabilization + docs + regression — real-EPUB QA/export E2E; docs synced; full gate green. | Phase F exit evidence |

Each stage stops at the §2.2 gate in `CLAUDE.md` for inspection before the next.

## 4. Exit criteria

Phase F exits only when (mirrors `CLAUDE.md` §2.4):

- [ ] Every cockpit surface re-walked: empty / loading / error / hover / active /
      disabled states verified, including @390px.
- [ ] QA + export flows stabilized end-to-end on a real EPUB; no dead controls or
      broken links; jobs start / poll / cancel cleanly.
- [ ] Copy consistency pass (terminology, sentence case, active voice) across all pages.
- [ ] Accessibility pass (keyboard path, focus order, contrast, labels) with findings
      fixed or explicitly logged as deferred.
- [ ] Docs match code (`DESIGN_NOTES.md`, `COCKPIT_WORKFLOW.md`); CHANGELOG updated.
- [ ] Full regression green: `pytest`, `pyright`, `ruff check`, `ruff format --check`,
      `weaver --help`.

## 5. Validation gate

```bash
uv run pytest -q
uv run pyright
uv run ruff check .
uv run ruff format --check .
uv run weaver --help
```

Plus a manual cockpit walkthrough (dashboard → project → workspace → quality →
export) at desktop and 390px.
