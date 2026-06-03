# Sprint 11A — FastAPI UI Shell (Implementation Plan)

> **Status: IMPLEMENTED (Gate 11A passed, 2026-06-03).** Approach unchanged from
> the approved plan. Stack per ADR `007` (Jinja2 + HTMX, no build, no SPA). Goal
> met: **functional parity, not visual polish.** Flask untouched; no default-`serve`
> flip. URL layout: `/ui` prefix + `GET /`→`/ui` (option 1, approved). HTMX 1.9.12
> vendored. See COCKPIT_WORKFLOW "FastAPI browser UI" + CLAUDE.md §2 for the result.

## 1. Goal & scope

Stand up the FastAPI-served browser **shell** so later sprints (11B/11C) hang
workflow screens off it. In scope for 11A only:

- Dashboard / home (project list + resolved global provider default).
- Project view (Novel → Volume → Chapter tree + navigation).
- Base layout, navigation chrome, and the shared **state primitives**: loading,
  empty, error, 404.

**Out of scope (11B/11C):** create/import, workspace read/save, translate/export
triggers, glossary/character/TM/config screens. 11A only proves the shell + read
screens + state handling.

## 2. Architecture (per ADR 007)

- **Templating:** Starlette `Jinja2Templates` pointed at `src/weaver/api/templates/`.
  `jinja2` is already a core dep — no new dependency.
- **Static assets:** `src/weaver/api/static/` holding a **vendored** `htmx.min.js`
  (committed file, no Node) + one small `app.css`. Mounted via `StaticFiles`.
- **UI router:** new `src/weaver/api/routers/ui.py` returning `HTMLResponse`.
  **Adapter-only** — it calls the *same services* the JSON routers use
  (`services/project_discovery`, `services/project_tree`,
  `core/global_config`). No new business logic, no storage access.
- **URL layout (proposed):** all HTML under a **`/ui`** prefix to keep the JSON
  API and the HTML surface cleanly separable (matters for the Sprint 12
  default-`serve` decision). `GET /` → 302 redirect to `/ui`.
  - `GET /ui` → dashboard (project list).
  - `GET /ui/projects/{name}` → project view (tree).
  - `GET /ui/partials/...` → HTMX fragment endpoints as needed (e.g. a tree
    refresh). 11A keeps fragments minimal.
  - _Alternative considered:_ serve dashboard at `GET /` directly. Rejected for
    11A because a clean `/ui` namespace makes "does the API still work headless?"
    and the eventual serve-flip both unambiguous. **Confirm if you prefer `/`.**

## 3. Files (planned)

```
src/weaver/api/
  templates/
    base.html            # shell: <head>, htmx script, nav, flash/error region, {% block %}
    dashboard.html       # project list table + global provider/model default + empty state
    project.html         # Novel→Volume→Chapter tree + back-nav + empty/error states
    partials/
      _project_row.html  # (if needed) one project row
      _error.html        # reusable inline error block
  static/
    htmx.min.js          # vendored, pinned version (no Node)
    app.css              # minimal layout only (no polish)
  routers/
    ui.py                # HTMLResponse routes above (adapter over services)
  templating.py          # Jinja2Templates + StaticFiles wiring helper (one place)
```

`api/app.py`: mount `StaticFiles`, include `ui_router`, add `GET /` redirect.
Wiring lives in `templating.py` so `app.py` stays a thin factory.

## 4. State primitives (must exist in 11A)

Minimum from ADR `005`'s list, scoped to read screens:
- **loading** — HTMX request indicator (`htmx-indicator` class).
- **empty** — "no projects yet" / "no volumes yet" blocks.
- **error** — inline `_error.html` for failed fetches; readable message.
- **404** — unknown project → friendly page, not a raw JSON 404.

Running/saving/batch/export states are deferred to 11B/11C where those actions live.

## 5. Reuse map (no logic in UI)

| Screen | Service reused (already built) |
|---|---|
| Dashboard list | `services/project_discovery.discover_projects` |
| Global default | `core/global_config.load_global_config` / `resolve_config_value` |
| Project tree | `services/project_tree.project_tree` |

The UI router converts service dataclasses → template context dicts. It must not
import storage, open SQLite, or branch on domain rules beyond display.

## 6. Tests (mirror source tree)

`tests/unit/api/test_ui_shell.py` (TestClient):
- `GET /` → 302 → `/ui`.
- `GET /ui` → 200, `text/html`, lists a known project (uses an initialized tmp project), shows empty state when none.
- `GET /ui/projects/{name}` → 200, renders volumes/chapters from the tree.
- `GET /ui/projects/ghost` → 404 HTML (not JSON).
- Static: `GET /static/htmx.min.js` → 200.
- **Headless-API intact:** `GET /projects` (JSON) still 200 — UI mount doesn't shadow the API.

## 7. Guardrails / non-goals

- Flask `web/` untouched; `weaver serve` stays Flask; **no default flip**.
- No visual polish (ADR `005` polish rubric is for later) — layout only.
- No new runtime dependency; HTMX vendored as a static file.
- No business logic, no storage access, no Pydantic models needed for HTML routes.
- `serve-api` will now also serve `/ui`; document this in COCKPIT_WORKFLOW on completion.

## 8. Validation (Gate 11A)

`pytest` · `pyright` · `ruff check` · `ruff format --check` · CLI smoke · Flask
smoke (still 13 routes, `/`→200) · FastAPI smoke (JSON routes intact + new
`/ui`, `/`, `/static/*` reachable).

## 9. Open questions for approval

1. **URL layout:** `/ui` prefix (recommended) vs dashboard at `/`?
2. **HTMX version** to vendor (propose latest stable 1.x `htmx.min.js`).
3. Anything in 11A's read-screen scope you want pulled forward or pushed to 11B?
