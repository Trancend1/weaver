# ADR 007 — FastAPI Cockpit UI Stack

## Status

Accepted (maintainer, 2026-06-03) · **Coexistence ended (Sprint 13B, 2026-06-04):** the Flask cockpit was removed; the FastAPI Jinja2+HTMX UI described here is now the only web UI. References below to Flask coexistence/fallback are historical.

## Context

Sprint 10 closed all **functional/domain** parity between the Flask and FastAPI cockpits (ADR `004`); the parity re-audit (in git history) found the **only** remaining difference is the rendered browser UI — Flask serves HTML templates, FastAPI is JSON-only. UI work was deliberately deferred under ADR `005`. Sprint 11 now builds a FastAPI-backed browser UI to reach **functional UI parity** so Flask can eventually be retired (Sprint 12 audit → Sprint 13 decommission, only if approved).

The locked stack ([CLAUDE.md §3](../../CLAUDE.md)) **rejects React/Node build / SPA without an ADR**. ADR `005` already set the direction ("HTMX is allowed… the cockpit is **not** a complex SPA unless a future ADR explicitly chooses that path"). This ADR pins the concrete UI stack for the FastAPI cockpit.

## Decision

**The FastAPI cockpit UI is server-rendered Jinja2 templates with HTMX as the interaction layer.**

- **Rendering:** FastAPI/Starlette `Jinja2Templates`. `jinja2>=3.1` is already a **core** dependency — **no new runtime dependency is added**.
- **Interaction:** HTMX for partial swaps, form posts, and SSE-driven job progress. HTMX (and any tiny helpers) is **vendored as a static asset** under the FastAPI app's static dir — **no npm, no Node, no bundler, no build step**.
- **Banned here:** React, Vue, Svelte, any SPA framework, any client-side build toolchain. (Unchanged from §3.)
- **Layering (CLAUDE.md §4.2):** the UI is a thin **presentation** layer. Templates + HTMX consume the existing Sprint 2–10 services/endpoints. **No business logic in the UI layer.** Where HTMX needs HTML fragments, FastAPI renders template partials from the **same services** the JSON routers already call — logic is never duplicated or reimplemented.
- **Scope guardrail (Sprint 11):** **functional parity, not visual polish.** ADR `005` remains the rubric for later polish (semantic color, responsive tiers, full state coverage).
- **Coexistence:** Flask is untouched and remains the fallback browser cockpit. `weaver serve` stays Flask; `weaver serve-api` (FastAPI) gains the new UI alongside its JSON API. **No default-serve flip and no Flask removal in Sprint 11** — those are gated on the Sprint 12 UI parity audit and explicit approval (ADR `004` posture).

**Reconsideration clause.** React/Next/SPA may be revisited **only after** FastAPI UI functional parity is complete, and **only via a new ADR** that explicitly overrides the §3 rejected-stack entry. Until then, this decision holds.

## Consequences

Improves: stays inside the locked stack; reuses Flask's proven no-build SSR+HTMX approach; one templating engine (`jinja2`) across both web layers; server-rendered HTML is simple, accessible, and testable with `TestClient`.

Tradeoffs: HTMX patterns for the richer interactions (batch monitor, debounced autosave, multi-job SSE) need discipline to stay simple. Some endpoints may need an **HTML-fragment** variant beside their JSON form; these stay thin adapters over the same services (no logic fork). Two web stacks (Flask + FastAPI) coexist until Sprint 13.

## Related Files

- `src/weaver/api/` — `templates/` + `static/` to be added in Sprint 11A; UI router(s) under `api/routers/`.
- ADR [`004`](004-fastapi-cockpit-technical-direction.md) (FastAPI direction), ADR [`005`](005-cockpit-ui-ux-direction.md) (UI/UX direction).
- [COCKPIT_WORKFLOW.md](../COCKPIT_WORKFLOW.md). (The Flask↔FastAPI parity audit that motivated this ADR is in git history.)
- [CLAUDE.md §3](../../CLAUDE.md) (locked stack).
