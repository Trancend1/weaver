# ADR 015 — Single provider-config surface at `/ui/providers`

**Status:** Accepted (2026-06-13) · **Update (Sprint Q2D, 2026-06-14):** `/ui/config` is retained as a compatibility-only GET redirect to `/ui/providers#config-editor`; it has no edit surface.

## Context

Provider setup was split across two cockpit surfaces: the global `/ui/config`
page (a scoped provider/model + secret editor) and the `/ui/providers` hub (a
read-only cross-project routing/health view). This duplicated the config concept,
left a dangling `/ui/projects/{name}/config` link on the hub, and contradicted the
"no hidden default provider" principle by making provider setup feel like generic
config rather than a first-class feature.

## Decision

`/ui/providers` is the single source of truth for provider type, model, API-key env
name, base URL, config validation, provider health, and provider-secret handling.
The provider/model config POST and secret POST/delete routes live at
`/ui/providers/config` and `/ui/providers/secrets[...]`. The hub GET renders the
read-only cross-project table plus the config + secrets editor panels.

`/ui/config` is compatibility-only: GET redirects to `/ui/providers#config-editor`
and preserves `?project=...` as `/ui/providers?project=...#config-editor`. No edit
form, template, POST route, or internal navigation entry exists at `/ui/config`;
the ws-hub sidebar "Providers" entry is the provider-config entry point.
`config.html` remains absent.

The hub GET stays Gate-B1-safe: it only reads provider status summaries, TOML, and
secret names. It must not call providers, run QA, hash source files, migrate DBs, or
store secrets. Health remains an explicit per-project POST. Secret values are
accepted only through the provider hub secret form or JSON secret API and are never
rendered — only env-var names and presence are shown. Legacy aliases (`deepseek`,
`gemini`, `ollama`, `fake`) remain supported through the provider registry. The
`provider_config` service and the JSON `/config` API are unchanged.

## Consequences

- One place to configure providers; `/ui/config` is a bookmark compatibility redirect only.
- The hub GET now also calls `read_config` (TOML-only) — still no provider call on render.
- Any external bookmark to `/ui/config` lands on the canonical provider editor.
- The JSON `/config` API remains the machine/API surface for redacted config reads/writes.
- Legacy aliases stay valid; custom provider types still require an explicit supported protocol and required fields.
- `ui_admin.py` is now glossary/characters/TM only.

## Related Files

- `src/weaver/api/routers/ui_providers.py`
- `src/weaver/api/routers/config.py`
- `src/weaver/api/templates/providers_hub.html`
- `src/weaver/api/templates/partials/_config_form.html`
- `src/weaver/api/templates/partials/_secrets.html`
