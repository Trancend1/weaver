# ADR 005 — Cockpit UI/UX Direction

## Status

Accepted

## Context

Once the MVP baseline (ADR `003`) is in place, the cockpit needs a coherent visual/interaction direction so polish work supports the workflow instead of distracting from it. The reset plan defers UI polish until after MVP baseline; this ADR records the *direction* so later polish work has guardrails. It is direction-only — no UI implementation here.

The cockpit's daily job is a long, repetitive translation workflow: create project → import → organize Novel/Volume/Chapter → workspace → pick provider/model → manage glossary/characters → translate → edit → monitor batch → export. Speed, readability, and predictable state matter more than decoration.

## Decision

**Visual direction.** Calm, readable, workflow-speed-first. Avoid both bland/flat and noisy/over-colored UI. Color is a **semantic signal** (status/state), not decoration. Use contrast for hierarchy.

**Interaction model.** Keep it lightweight. HTMX is allowed as the interaction layer where it keeps things simple; the cockpit is **not** a complex SPA unless a future ADR explicitly chooses that path (aligns with ADR `004`).

**Primary workspace.** JP/EN two-column translation view is the centerpiece. Side panels (glossary, character DB, context, job monitor) are contextual, not always-on clutter.

**Responsive tiers.**
- Mobile: stacked layout, one primary task per screen, columns become tabs/stacked blocks, side panels become drawers.
- Tablet: compressed two-column or switchable panels; collapsible side panels; touch targets.
- Small desktop: stable two-column workspace; left project/chapter nav; optional right panel.
- Wide desktop: centered workspace; glossary/character/context + batch monitor as side panels.

**UI state coverage (must all be designed).** loading, empty, error, retry, success, disabled, saving, auto-saved, translation running, batch progress, export ready, provider missing, API key missing, import failed, partial batch failure.

## Consequences

Improves: polish work has a rubric; states that usually get forgotten (partial batch failure, key-missing) are first-class; responsive behavior is decided before pixels are pushed.

Tradeoffs: the semantic-color / state-complete bar is higher than "make it look nice" — every screen owes its full state set. Holding the line against SPA creep needs discipline as features grow.

## Related Files

- `src/weaver/web/templates/`, `src/weaver/web/static/`
- `docs/COCKPIT_WORKFLOW.md` (to be written in Task 3)
- Task 6 of the reset plan (UI/UX polish planning)
