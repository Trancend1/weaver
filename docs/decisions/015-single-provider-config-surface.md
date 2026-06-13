# ADR 015 — Single provider-config surface at `/ui/providers`

**Status:** Accepted (2026-06-13)

## Context

Provider setup was split across two cockpit surfaces: the global `/ui/config`
page (a scoped provider/model + secret editor) and the `/ui/providers` hub (a
read-only cross-project routing/health view). This duplicated the config concept,
left a dangling `/ui/projects/{name}/config` link on the hub, and contradicted the
"no hidden default provider" principle by making provider setup feel like generic
config rather than a first-class feature.

## Decision

`/ui/providers` is the single source of truth for provider type, model, API-key env
name, base URL, config validation, and provider health. The provider/model config
POST and secret POST/delete routes move to `/ui/providers/config` and
`/ui/providers/secrets[...]`. The hub GET renders the read-only cross-project table
plus the config + secrets editor panels. `/ui/config` and `config.html` are removed;
the topnav "Config" link is removed (the ws-hub sidebar "Providers" entry is the
entry point). The hub GET stays Gate-B1-safe: it only reads TOML + secret names (no
DB connect, no provider build, no source hashing). Health remains an explicit
per-project POST. Secret values are never rendered — only env-var names. The
`provider_config` service and the JSON `/config` API are unchanged.

## Consequences

- One place to configure providers; no duplicate config surface or legacy redirect.
- The hub GET now also calls `read_config` (TOML-only) — still no provider call on render.
- Any external bookmark to `/ui/config` 404s (acceptable: local single-user cockpit).
- `ui_admin.py` is now glossary/characters/TM only.
