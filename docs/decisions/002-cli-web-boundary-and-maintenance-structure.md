# ADR 002 — CLI / Web / Shared-Core Boundary and Maintenance Structure

## Status

Accepted

## Context

Weaver has two delivery surfaces — the CLI (`typer`) and the local web cockpit (currently Flask, migrating to FastAPI per ADR `004`). Both must drive the **same** translation/glossary/export logic. The current codebase already separates cleanly:

- `cli/` — typer commands, terminal I/O.
- `web/` — Flask app factory, route blueprints, SSE, Jinja templates.
- `services/`, `storage/`, `core/`, `providers/`, `readers/`, `renderers/`, `qa/` — domain logic with **no** web/CLI framework coupling.

This separation is the project's most valuable asset for the upcoming Flask→FastAPI migration: a clean core means the web layer can be swapped without touching translation logic. The reset formalizes it as a rule so it is not eroded during migration or feature work.

## Decision

Three boundaries are binding for all future work:

**CLI layer (`cli/`)** — command parsing, orchestration, terminal output/logging. **Must not** contain web app/router creation, request/response handling, or template logic.

**Web layer (`web/`)** — app factory/entrypoint, route modules, request/response schemas, web wiring, job-trigger endpoints, templates/static assets, lightweight interactivity (HTMX). **Must not** contain reusable domain logic, provider logic coupled only to the web framework, CLI assumptions, terminal output, or long-running translation inside a request handler without a job/progress boundary.

**Shared/core (`services/`, `storage/`, `core/`, `providers/`, `readers/`, `renderers/`, `qa/`)** — project/novel/volume/chapter model, provider config, translation pipeline, prompt/context builder, glossary, character database, translation memory, import/export, batch/job logic, validation. **Must stay framework-agnostic**: no web `Request`/`Response` objects, no dependency-injection wiring, no template rendering, no CLI formatting, no UI-only state.

Maintenance rules: one concept per file; name modules for what they do (no `utils.py`/`helpers.py`/`manager.py`); errors via the `WeaverError` hierarchy; state writes go through services (CLI/web never touch SQLite directly); one PR = one concern.

## Consequences

Improves: either surface can evolve (or be replaced) independently; the FastAPI migration touches only `web/`; tests target the core without spinning up a server.

Tradeoffs: contributors must resist the convenience of putting logic in a route handler or a CLI command. New shared behavior costs a service function plus a thin caller on each surface, rather than one inline block.

## Related Files

- `src/weaver/cli/`, `src/weaver/web/`
- `src/weaver/services/`, `storage/`, `core/`, `providers/`, `readers/`, `renderers/`, `qa/`
- `src/weaver/errors.py`
- Supersedes the boundary clause of archived ADR `0016`.
