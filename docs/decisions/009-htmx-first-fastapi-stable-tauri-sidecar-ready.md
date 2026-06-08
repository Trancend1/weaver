# ADR 009 — HTMX-first, FastAPI-stable, Tauri-sidecar-ready

## Status

Accepted (maintainer, 2026-06-08). **Supersedes** the "Phase Final — Distribution & Installer" entry in [CLAUDE.md §2.1](../../CLAUDE.md) that targeted an npm `@weaver/cli` wrapper. **Governs** Sprints G–O in [docs/weaver_next_plan.md](../weaver_next_plan.md).

## Context

Phase F shipped EPUB structure parsing / preview / fidelity on `feat/epub-metadata-parse`. CLAUDE.md previously named the next phase **"Phase Final — Distribution & Installer"**, scoped as `@weaver/cli → npm install -g → weaver`: an npm-published shell that bootstraps Python/uv and launches the local FastAPI cockpit.

Reviewing the path against the codebase produced four concerns:

1. **Two distribution surfaces.** The npm wrapper does not eliminate the need for a real desktop shell later (window management, app-data location, OS conventions); it adds one. The user's longer-term direction is desktop distribution, and the wrapper would become legacy on first ship.
2. **Backend assumptions.** The FastAPI cockpit has no `/healthz`, no `/version`, no explicit app-data abstraction, no structured logs, and no desktop-mode security baseline. Any shell — npm wrapper or Tauri — needs these contracts. Building the shell before the contracts forces rework.
3. **Long-running work is in-process only.** `src/weaver/api/jobs.py` holds translate/batch/export progress in memory; refresh loses progress, process restart loses everything. A shell that re-launches the backend on update would compound this.
4. **Hierarchy terminology.** Phase E and earlier UI work uses "Project" inconsistently with ADR `006`'s "Novel". Locking the rename before downstream sprints prevents a second pass.

The user explicitly chose, on 2026-06-08, to **replace** the npm wrapper plan with a Tauri-sidecar path: one distribution surface, with backend contracts hardened first.

## Decision

**Adopt the strategic line "HTMX-first, FastAPI-stable, Tauri-sidecar-ready" as the post-Phase-F roadmap.**

1. **HTMX is the UI.** No SPA migration. No NiceGUI. No rewrite to Vue/React/Svelte. ADR `005` and ADR `007` continue to apply.
2. **FastAPI is the only runtime boundary.** All shells (Tauri now; anything else later) talk to the same local FastAPI service via the same JSON / HTMX routes. The shell never re-implements business logic.
3. **Tauri is the packaging shell**, not a reason to rewrite. It launches FastAPI as a sidecar on `127.0.0.1`, waits on `/healthz`, opens a WebView, and shuts the sidecar down on close. The shell lives in a separate subtree (`desktop/`) and adds no Python runtime dependency.
4. **The npm `@weaver/cli` wrapper is retired** as the active distribution target. It is recorded in CLAUDE.md §2.1 as deferred legacy. Revisiting it requires a new ADR that supersedes this one in part.
5. **Sprint sequence is dependency-driven** ([weaver_next_plan.md §1](../weaver_next_plan.md)):
   ```text
   G  Runtime contract (health, version, app-data, logs, desktop mode, sidecar contract)
   H  Project / Volume lifecycle + Novel → Project consolidation (ADR 011)
   I  Persistent job core, SQLite-backed, single-process (ADR 010)
   J  EPUB preservation snapshot (persist Phase F)
   K  Export fidelity wiring
   L  Candidate review + Character Page text draft
   M  Image preview / OCR security gate (ADR 012, then optional impl)
   N  Tauri shell alpha
   O  Production desktop packaging
   ```
6. **Companion ADRs** ship inside the sprints that need them:
   - ADR `010` — Persistent Job Core (SQLite, in-process, no external worker). Locked before Sprint I.
   - ADR `011` — Project Terminology Consolidation (retires "Novel" from ADR `006`). Locked before Sprint H.
   - ADR `012` — Image Preview / OCR Security Gate. Locked inside Sprint M Gate A; no image bytes or OCR ship before it.

## Consequences

**Improves.**

- One distribution surface to maintain instead of two.
- Backend contracts that a shell can rely on (health, version, app-data, security baseline, sidecar lifecycle) ship in Sprint G before any shell work begins.
- The Tauri shell can be evaluated against a real, stable backend; if Tauri proves unsuitable later, the same contracts make it cheap to swap shells.
- ADR `010` formally documents the persistent-job boundary so SQLite persistence is not mistaken as a license to introduce Celery / Redis / RQ / external workers.

**Tradeoffs.**

- Desktop distribution lands later than an npm wrapper would have. The judgement call is that a stable backend + a real shell beats a shipped wrapper that needs to be replaced.
- Tauri adds a Rust toolchain dependency for desktop releases (not for core development; the shell lives in `desktop/`). The locked Python stack (CLAUDE.md §3) is unchanged.
- Three new ADRs (`010`, `011`, `012`) raise the documentation surface. The alternative — implicit decisions — would compound the same drift this ADR is correcting.

## Related Files

- [docs/weaver_next_plan.md](../weaver_next_plan.md) — full sprint specification this ADR governs.
- [CLAUDE.md](../../CLAUDE.md) §2.1 — roadmap row updated to point to Sprint G.
- ADR [`004`](004-fastapi-cockpit-technical-direction.md) (FastAPI direction), ADR [`005`](005-cockpit-ui-ux-direction.md) (UI/UX direction), ADR [`007`](007-fastapi-ui-stack.md) (FastAPI UI stack), ADR [`006`](006-novel-volume-chapter-data-model.md) (superseded in part by ADR `011`).
- `src/weaver/api/jobs.py:8-10` — the architectural boundary ADR `010` formalizes.
