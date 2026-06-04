# ADR 004 — FastAPI Cockpit Technical Direction

## Status

Accepted · **Migration complete (Sprint 13B, 2026-06-04):** the staged Flask→FastAPI migration finished — `weaver serve` flipped to FastAPI in Sprint 12B, a real-workflow soak confirmed stability ([SPRINT13A5_SOAK_RESULT.md](../SPRINT13A5_SOAK_RESULT.md)), and Sprint 13B removed the Flask cockpit entirely (`serve-flask`, `src/weaver/web/**`, Flask-only tests, and the `flask` dependency). FastAPI is now the sole web cockpit. The Flask-era discussion below is retained as historical rationale.

## Context

The current web cockpit runs on **Flask (sync)** + vendored HTMX + Jinja2, chosen in archived ADR `0016` because the service core was synchronous and FastAPI/asyncio were on the rejected stack list. That cockpit is **shipped and working** (project discovery, monitor + SSE, file browse/upload, provider/model config, translate + stop, export, glossary review), all behind the optional extra `weaver[web]`.

The product is now committed to growing into an **API-first cockpit** for the full translator workflow (import, provider config, translation jobs, progress, glossary, character DB, translation memory, batch, export). For that trajectory the maintainer has chosen **FastAPI** as the target backend: typed Pydantic request/response schemas at the boundary, `APIRouter` modules, dependency injection for web wiring, and an ASGI runtime (Uvicorn) — a better fit for a structured local API than hand-grown Flask routes.

This is a direction decision, **not** a rewrite order.

## Decision

**FastAPI is the target backend framework for the web cockpit.** The Flask cockpit is the **legacy working baseline** and is preserved until a FastAPI migration reaches feature/behavior parity.

Binding rules:

1. **Do not delete or break the Flask cockpit now.** It remains the shipped surface until parity is planned and reached.
2. **No FastAPI implementation in this reset.** Source code is untouched; this ADR only records direction. Migration is its own sprint(s) with its own gate.
3. **Migrate route-by-route, not big-bang.** Each migrated endpoint must preserve existing behavior; Flask and FastAPI may coexist transitionally if needed, with the transitional code clearly marked.
4. **Shared/core stays framework-agnostic** (ADR `002`). Domain logic never depends on `Request`/`Response`, FastAPI dependencies, or HTMX fragments. The migration must, if anything, *strengthen* the core/web split.
5. **Pydantic only at the web boundary** — request/response DTOs — not inside pure domain services unless a DTO is deliberately shared.
6. **No domain logic in endpoint handlers.** Handlers wire HTTP ↔ services; long-running translation runs behind a job/progress boundary (carry forward the single-job + SSE-progress pattern from archived ADR `0019`), never inline in a request.
7. **Carry forward the security model** (archived ADR `0017`): bind `127.0.0.1` only, no auth (single-user loopback), sandboxed file browser rejecting `..`, upload limits.
8. **Carry forward secret handling** (archived ADR `0020`): keys live only in env vars or `~/.weaver/secrets.toml` (mode `0o600`, env wins), never in project/global config, never logged, never rendered — UI shows env-var name + present/absent only.
9. **HTMX may remain** as a lightweight interaction layer if it keeps the cockpit simple. **Do not** turn the cockpit into a complex SPA without a future ADR. asyncio is unlocked only for the FastAPI web layer; React/Node build, Celery/RQ, Docker stay rejected.

This **supersedes archived ADR `0016`** (which selected Flask and rejected FastAPI).

## Consequences

Improves: typed, self-documenting API surface; clean path to richer cockpit features; ASGI fits the API-first direction; the clean core (ADR `002`) makes the swap low-risk.

Tradeoffs: a second framework lives in-tree during migration; the team owns parity testing so no shipped behavior regresses; `weaver[web]` gains FastAPI + Uvicorn deps (Flask removed only after parity); contributors must keep async confined to `web/` and never leak it into shared-core.

## Related Files

- `src/weaver/web/` (current Flask app — legacy baseline)
- `pyproject.toml` (`[project.optional-dependencies] web`)
- Supersedes archived ADR `0016`; carries forward archived `0017`, `0019`, `0020`.
- `docs/COCKPIT_WORKFLOW.md` (to be written in Task 3)
