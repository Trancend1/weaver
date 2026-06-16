# Security Review — Connection-First + Enforcement Surfaces (webUI + Desktop)

**Date:** 2026-06-16 · **Scope:** v0.7.2 connection/routing/enforcement routes, audited against the
desktop sidecar contract (`docs/SIDECAR_CONTRACT.md`) and the cockpit rules (CLAUDE.md §4.2).
**Branch:** `feat/connection-first-routing`. **Role:** Security / Safety Engineer (T7).

## Surfaces reviewed

- `api/routers/ui_providers.py` — connection register/test/delete, secrets set/delete, per-project
  switch, health-check.
- `api/routers/ui_routing.py` — Active AI panel, Switch AI, Load/cached models, fallback add/clear.
- `services/connections.py`, `core/connection_registry.py`, `core/connection_models.py`,
  `core/secret_store.py`, `providers/discovery.py`, `services/project_discovery.py`.
- Templates: `_connection_*`, `_connections`, `_active_ai`, `_routing_models`, `_secrets`,
  `_provider_row`, `providers_hub.html`.

## Findings & fixes

| # | Severity | Finding | Status |
|---|----------|---------|--------|
| 1 | **Medium** (Windows/desktop) | **Path traversal in `find_project`** — the `{name}` route param was joined as `books_dir/.weaver/<name>/project.toml`. FastAPI blocks `/`, but on Windows (the desktop target) `\` is a separator, so `..\..\x` could escape `.weaver`. | **Fixed** — `find_project` rejects `name` containing `/` or `\`, or equal to `.`/`..`. +test. |
| 2 | **Low–Medium** | **Reflected XSS** — the inline "No project named …" / switch-error fallbacks interpolated the untrusted `name` path param into raw HTML via f-string (Jinja templates autoescape; these shortcuts did not). | **Fixed** — `html.escape(name)` in `ui_routing._no_project` (4 call sites) and `ui_providers.provider_switch`. +test. |

## Verified safe (no change needed)

- **Session-token boundary (desktop):** the global middleware (`app.py`) enforces `X-Weaver-Session`
  on every path except `_PUBLIC_PATHS = {/healthz, /health, /version, /static}`. All connection/routing
  routes (`/ui/providers/*`, `/ui/projects/*/routing/*`) are **behind the token**. Desktop CORS is
  same-origin only (`allow_origins=[]`).
- **Gate B1 (no provider call on render):** `providers_page` + `routing_panel` + `routing_cached_models`
  read TOML / DB / the model cache only. The *only* provider calls are explicit POSTs
  (`/healthcheck`, `/connections/test`, `/connections/{name}/test`, `/routing/models`).
- **Secret confidentiality:** key *values* are accepted only by the connection/secret forms and stored
  in `~/.weaver/secrets.toml`. Responses render names/counts only (`ConnectionView` "never carries a
  key value"; `_secrets.html` shows env names). Existing tests assert `sk-SECRET` is never echoed.
- **Secret-name injection:** `core/secret_store.set_secret` validates `env_var` against
  `^[A-Za-z_][A-Za-z0-9_]*$` and escapes the value → no TOML injection / path abuse. Written atomically
  at `0o600`. Connection names are slug-validated (`_NAME_RE`) and the derived env name is sanitized to
  `[A-Z0-9_]` (`derive_env_name`).
- **No host hardcoding:** every HTMX hook in the connection/routing partials uses a **relative** path
  (`/ui/...`), so the desktop webview injects the session header and the random port; no
  `127.0.0.1:8765` anywhere.
- **Probe errors:** `providers/discovery._map_error` builds messages from the SDK exception (response
  body), not the request bearer — the key is not echoed in error text.
- **Local file perms:** `connections.toml`, `secrets.toml`, `connection_models.json` are written
  owner-only (`0o600`, best-effort on Windows).

## Residual / accepted

- `find_project` still appends a fixed `/project.toml`, so even a hypothetical name that passed the
  guard can only ever open a `project.toml`, never an arbitrary file. The new separator/`..` guard
  closes the practical traversal vector.
- Single-user, local-first model (CLAUDE.md): the session token + same-origin CORS already bound the
  attacker model; the two fixes are defense-in-depth for the desktop webview.

**Verification:** `ruff`/`pyright` clean; new tests `test_find_project_rejects_traversal_names`,
`test_routing_panel_escapes_unknown_project_name`; full suite green.
