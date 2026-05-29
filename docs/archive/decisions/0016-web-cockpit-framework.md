# 0016: Web Cockpit Framework — Flask + HTMX

Date: 2026-05-29
Status: accepted

## Context

Daily CLI use carries four confirmed friction points (PP1 long paths, PP2 provider/model switching, PP3 weak monitoring, PP4 multi-step flow). The maintainer chose a **local web cockpit** as the primary daily surface (CLI stays additive). See [feature_plan/web-feature-plan.md](../feature_plan/web-feature-plan.md).

A web surface needs a server. The locked stack ([CLAUDE.md §3](../../CLAUDE.md)) rejects Django, Flask, FastAPI, and asyncio. Stack changes require an ADR. The existing service core (`translate_project`, `initialize_project`, glossary, export) is **synchronous**. FastAPI implies asyncio (rejected) and pairs with a node/React build (anti-slop, heavy). A pure stdlib `http.server` means hand-rolling routing, JSON, static serving, and SSE — large boilerplate and bug surface.

## Decision

Reopen the stack to allow **Flask (sync only)** for a local web cockpit, behind optional extra `weaver[web]`.

- **Framework:** Flask, synchronous request handling. No `async def` routes, no ASGI.
- **Templating:** Jinja2 — already in the locked stack.
- **Interactivity:** **HTMX**, vendored as `static/htmx.min.js` (no CDN — preserves offline ethos; no node/React build step).
- **Long jobs:** one background **thread** per translate run (see ADR `0019`). No asyncio, no queue/worker framework (Celery/RQ stay rejected).
- **Server:** Flask built-in dev server with `threaded=True` (decision D1). No `waitress`.
- **Scope of web layer:** routing, job lifecycle, HTML rendering only. **Zero** translation/glossary/export logic — all domain logic stays in `services/`, shared with the CLI.

**Still rejected (unchanged):** Django, FastAPI, asyncio, React/Node build, websockets, SQLAlchemy, Celery, RQ, Docker.

**Gate:** no Flask or cockpit code enters the codebase until this ADR is merged.

## Consequences

Easier: one dep (`flask`); reuses locked Jinja2; sync model matches the existing sync services with no rewrite; HTMX gives liveness without a frontend build; CLI and web share one service core.

Harder: Flask leaves the rejected list and must be maintained as a real dependency (behind `weaver[web]`). Future contributors adding async, a JS build, or a second web framework must supersede this ADR first. The dev-server "not for production" warning is accepted as harmless for a localhost single-user tool.
