# Consolidate Provider Config into `/ui/providers` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the `/ui/config` route/page entirely and make `/ui/providers` the single source of truth for provider type, model, API-key env name, base URL, config validation, and provider health.

**Architecture:** `/ui/providers` keeps its read-only cross-project table (writes still flow through the `provider_config` service, never direct DB) and gains two editor panels on the same page: a **Provider / model config** panel (global-or-per-project, with a project selector) and a **Secrets** panel. The provider-config GET/POST/secret routes move from `ui_admin.py` to `ui_providers.py` under the `/ui/providers/...` prefix. The cross-project table's GET stays Gate-B1-safe: it only reads TOML via `read_config` (no DB connect, no provider build, no source hashing). Health stays an explicit per-project POST. The global topnav "Config" link is removed; the ws-hub sidebar "Providers" entry is the only config entry point.

**Tech Stack:** FastAPI · server-rendered Jinja2 + HTMX · pytest · pyright (basic) · ruff. No new dependencies.

**Architecture decision:** This is a routing/UX SoT decision (single config surface). Per CLAUDE.md §4.2 it gets a one-page ADR (`015`). No schema change, no service-signature change — `provider_config.read_config/write_config/store_secret/remove_secret` are reused as-is.

**Non-goals:**
- No change to the JSON API router `config.py` (`/config`, `/config/secrets/...`) — that is the programmatic API and stays.
- No change to `provider_config` service signatures, `workspace_providers`, or any storage/schema.
- No provider call, DB connect, or source hashing added to the hub GET (Gate B1 holds).
- No new "Settings" sidebar feature (the disabled Settings stub stays disabled).

---

## File Structure

| File | Responsibility | Action |
| --- | --- | --- |
| `src/weaver/api/routers/ui_providers.py` | Providers hub GET (table + config editor context) + health POST + provider-config POST + secret POST/delete | Modify |
| `src/weaver/api/routers/ui_admin.py` | Glossary/characters/TM admin only — provider/secret config removed | Modify |
| `src/weaver/api/templates/providers_hub.html` | Hub table + project selector + config + secrets panels; fix dangling link/hints | Modify |
| `src/weaver/api/templates/partials/_config_form.html` | Config form — repoint `hx-post` to `/ui/providers/config` | Modify |
| `src/weaver/api/templates/partials/_secrets.html` | Secrets form — repoint `hx-post` to `/ui/providers/secrets[...]` | Modify |
| `src/weaver/api/templates/config.html` | Old standalone config page | Delete |
| `src/weaver/api/templates/base.html` | Global topnav — remove "Config" link | Modify |
| `tests/unit/api/test_ui_providers.py` | Add config-editor + config-save + secret tests at new URLs | Modify |
| `tests/unit/api/test_ui_admin.py` | Remove provider/secret config tests; fix dashboard-link assertion; keep `/ui/new` assertions | Modify |
| `tests/unit/api/test_ui_layout.py` | Drop `/ui/config` from the global-mode parametrize | Modify |
| `tests/unit/api/test_ui_workspace_hub.py` | Remove `test_config_route_still_global_layout` | Modify |
| `docs/decisions/015-single-provider-config-surface.md` | ADR for the SoT decision | Create |
| `docs/CODEMAPS/backend.md`, `docs/CODEMAPS/frontend.md`, `docs/MAINTENANCE.md` | Replace `/ui/config` references | Modify |

---

## Task 1: New provider-config + secret routes under `/ui/providers` (tests first)

**Files:**
- Test: `tests/unit/api/test_ui_providers.py`

These tests target the moved POST endpoints. They will fail until Task 2 adds the routes. The POST response renders the existing partials (`_config_form.html` / `_secrets.html`), whose field markup is already correct, so these tests do not depend on Task 3's template move.

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/api/test_ui_providers.py` (append at end of file). Note the file's `providers_client` fixture creates projects `alpha` + `beta` (provider `deepseek`).

```python
# ---------------------------------------------------------------------------
# 9. Provider config editor (moved from /ui/config)
# ---------------------------------------------------------------------------


def test_providers_config_save_persists(providers_client: TestClient) -> None:
    r = providers_client.post(
        "/ui/providers/config",
        data={"scope": "project", "project": "alpha", "provider_type": "fake", "model": "fake-9"},
    )
    assert r.status_code == 200 and "Saved" in r.text
    view = providers_client.get("/config?project=alpha").json()
    assert view["model"] == "fake-9"


def test_providers_config_freeform_provider_type(providers_client: TestClient) -> None:
    r = providers_client.post(
        "/ui/providers/config",
        data={"scope": "project", "project": "alpha", "provider_type": "not-real"},
    )
    assert r.status_code == 200
    assert "Saved" in r.text


def test_providers_secret_set_and_delete_without_exposing_value(
    providers_client: TestClient,
) -> None:
    r = providers_client.post(
        "/ui/providers/secrets", data={"env_name": "MY_KEY", "value": "sk-LEAKCHECK"}
    )
    assert r.status_code == 200
    assert "MY_KEY" in r.text
    assert "sk-LEAKCHECK" not in r.text  # value never rendered
    assert "sk-LEAKCHECK" not in providers_client.get("/ui/providers").text

    delete = providers_client.post("/ui/providers/secrets/MY_KEY/delete")
    assert delete.status_code == 200
    assert "MY_KEY" not in delete.text


def test_providers_secret_invalid_name_error(providers_client: TestClient) -> None:
    r = providers_client.post(
        "/ui/providers/secrets", data={"env_name": "bad name!", "value": "x"}
    )
    assert r.status_code == 200
    assert "error" in r.text.lower()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `rtk pytest tests/unit/api/test_ui_providers.py -k "providers_config or providers_secret" -q`
Expected: FAIL — `404 Not Found` (routes don't exist yet), so the `status_code == 200` asserts fail.

- [ ] **Step 3: Commit the failing tests**

```bash
git add tests/unit/api/test_ui_providers.py
git commit -m "test(providers): add config/secret tests at /ui/providers endpoints"
```

---

## Task 2: Add provider-config + secret routes to `ui_providers.py`

**Files:**
- Modify: `src/weaver/api/routers/ui_providers.py`

Move the editor context helper + the three write routes here, and add a `project` query param to the hub GET so a project's `[provider]` block can be preloaded into the editor.

- [ ] **Step 1: Update imports**

Replace the import block in `src/weaver/api/routers/ui_providers.py` (currently lines 14–24) with:

```python
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse

from weaver.api.templating import templates
from weaver.api.ui_context import ws_hub_layout
from weaver.errors import SecretNotFoundError, WeaverError
from weaver.services import provider_config as config_service
from weaver.services.project import inspect_project
from weaver.services.project_discovery import discover_projects, find_project
from weaver.services.workspace_providers import build_workspace_providers
```

- [ ] **Step 2: Add helpers + editor context after `_base_dir`**

Insert directly after the `_base_dir` function:

```python
def _opt(value: str | None) -> str | None:
    return value.strip() if value and value.strip() else None


def _config_ctx(request: Request, project: str | None) -> dict[str, object]:
    """Redacted provider/model + secret-name context for the hub editor panels.

    Reads TOML + the secret-name list only (no DB connect, no provider build,
    no source hashing) so the hub GET stays Gate-B1-safe.
    """
    base = _base_dir(request)
    view = config_service.read_config(base, project=_opt(project))
    return {
        "view": view,
        "project": _opt(project),
        "projects": [dp.name for dp in discover_projects(base)],
    }
```

- [ ] **Step 3: Replace `providers_page` to add the `project` param + editor context**

Replace the existing `providers_page` function with:

```python
@router.get("/ui/providers", response_class=HTMLResponse)
def providers_page(request: Request, project: str | None = None) -> HTMLResponse:
    """Global Providers hub — cross-project routing table + the provider/model +
    secret config editor (the single config surface). The table is read-only; edits
    flow through the ``provider_config`` service via the POST routes below."""
    base = _base_dir(request)
    providers = build_workspace_providers(base)
    try:
        config_ctx = _config_ctx(request, project)
    except WeaverError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return templates.TemplateResponse(
        request,
        "providers_hub.html",
        {
            **ws_hub_layout("providers"),
            "providers": providers,
            "books_dir": str(base),
            **config_ctx,
        },
    )
```

- [ ] **Step 4: Append the write routes (after `provider_healthcheck`)**

```python
@router.post("/ui/providers/config", response_class=HTMLResponse)
def config_save(
    request: Request,
    scope: str = Form("project"),
    project: str | None = Form(None),
    provider_type: str | None = Form(None),
    protocol: str | None = Form(None),
    model: str | None = Form(None),
    base_url: str | None = Form(None),
    api_key_env: str | None = Form(None),
) -> HTMLResponse:
    """Persist provider/model config (no key value accepted), then re-render the form."""
    base = _base_dir(request)
    error: str | None = None
    try:
        config_service.write_config(
            base,
            scope=scope,
            project=_opt(project),
            provider_type=_opt(provider_type),
            protocol=_opt(protocol),
            model=_opt(model),
            base_url=_opt(base_url),
            api_key_env=_opt(api_key_env),
        )
    except WeaverError as exc:
        error = str(exc)
    ctx = _config_ctx(request, project)
    ctx["error"] = error
    ctx["saved"] = error is None
    return templates.TemplateResponse(request, "partials/_config_form.html", ctx)


@router.post("/ui/providers/secrets", response_class=HTMLResponse)
def config_secret_set(
    request: Request,
    project: str | None = Form(None),
    env_name: str = Form(...),
    value: str = Form(...),
) -> HTMLResponse:
    """Store an API-key secret under an env-var name (value never echoed back)."""
    error: str | None = None
    try:
        config_service.store_secret(env_name, value)
    except WeaverError as exc:
        error = str(exc)
    ctx = _config_ctx(request, project)
    ctx["secret_error"] = error
    ctx["secret_saved"] = error is None
    return templates.TemplateResponse(request, "partials/_secrets.html", ctx)


@router.post("/ui/providers/secrets/{env_name}/delete", response_class=HTMLResponse)
def config_secret_delete(
    env_name: str, request: Request, project: str | None = Form(None)
) -> HTMLResponse:
    """Remove a stored secret, then re-render the secret list."""
    error: str | None = None
    try:
        config_service.remove_secret(env_name)
    except SecretNotFoundError as exc:
        error = str(exc)
    ctx = _config_ctx(request, project)
    ctx["secret_error"] = error
    return templates.TemplateResponse(request, "partials/_secrets.html", ctx)
```

- [ ] **Step 5: Run Task 1 tests to verify they pass**

Run: `rtk pytest tests/unit/api/test_ui_providers.py -k "providers_config or providers_secret" -q`
Expected: PASS (4 tests).

- [ ] **Step 6: Verify the thin-route + no-provider-call gates still hold**

Run: `rtk pytest tests/unit/api/test_ui_providers.py::test_providers_get_route_is_thin tests/unit/api/test_ui_providers.py::test_no_provider_call_on_hub_get -q`
Expected: PASS. (`_config_ctx` is a separate function, so `providers_page` source contains neither `connect_database` nor `connect_readonly_database`; `read_config` never builds a provider.)

- [ ] **Step 7: Commit**

```bash
git add src/weaver/api/routers/ui_providers.py
git commit -m "feat(providers): move provider/model + secret config routes to /ui/providers"
```

---

## Task 3: Wire the editor into `providers_hub.html` + repoint partials + delete `config.html`

**Files:**
- Modify: `src/weaver/api/templates/partials/_config_form.html`
- Modify: `src/weaver/api/templates/partials/_secrets.html`
- Modify: `src/weaver/api/templates/providers_hub.html`
- Delete: `src/weaver/api/templates/config.html`
- Test: `tests/unit/api/test_ui_providers.py`

- [ ] **Step 1: Write the failing editor-render test**

Append to `tests/unit/api/test_ui_providers.py`:

```python
def test_providers_hub_renders_config_editor(providers_client: TestClient) -> None:
    html = providers_client.get("/ui/providers").text
    # free-form provider config fields are present (no provider <select>)
    assert 'name="provider_type"' in html
    assert 'name="protocol"' in html
    assert '<select name="provider_type"' not in html
    # the editor posts to the consolidated endpoint, not the removed /ui/config
    assert 'hx-post="/ui/providers/config"' in html
    assert 'hx-post="/ui/providers/secrets"' in html
    assert "/ui/config" not in html


def test_providers_hub_project_param_loads_project_config(providers_client: TestClient) -> None:
    providers_client.post(
        "/ui/providers/config",
        data={"scope": "project", "project": "alpha", "provider_type": "fake", "model": "fake-42"},
    )
    html = providers_client.get("/ui/providers", params={"project": "alpha"}).text
    assert "fake-42" in html
```

- [ ] **Step 2: Run to verify failure**

Run: `rtk pytest tests/unit/api/test_ui_providers.py -k "config_editor or project_param_loads" -q`
Expected: FAIL — editor markup not yet in `providers_hub.html`; `_config_form.html` still posts to `/ui/config`.

- [ ] **Step 3: Repoint `_config_form.html`**

In `src/weaver/api/templates/partials/_config_form.html`, change line 17 from:

```html
  <form class="stack" hx-post="/ui/config" hx-target="#config-form" hx-swap="outerHTML">
```

to:

```html
  <form class="stack" hx-post="/ui/providers/config" hx-target="#config-form" hx-swap="outerHTML">
```

- [ ] **Step 4: Repoint `_secrets.html`**

In `src/weaver/api/templates/partials/_secrets.html`:
- Line 11: `hx-post="/ui/config/secrets/{{ env }}/delete"` → `hx-post="/ui/providers/secrets/{{ env }}/delete"`
- Line 22: `hx-post="/ui/config/secrets"` → `hx-post="/ui/providers/secrets"`

- [ ] **Step 5: Add the editor panels to `providers_hub.html` + fix stale references**

In `src/weaver/api/templates/providers_hub.html`:

(a) Replace the `page_actions` block (lines 10–12) — drop the "config edits stay on each project's Config page" hint:

```html
  {% set page_actions %}
    <span class="hint">Read-only routing view · edit provider/model + secrets below.</span>
  {% endset %}
```

(b) Fix the dangling per-project config link (line 57). Replace:

```html
              <a href="/ui/projects/{{ p.project_name }}/config" class="badge bad"
                 title="{{ p.api_key_env }} is not set — open Config to add it">{{ p.api_key_env or "key" }} missing</a>
```

with:

```html
              <a href="/ui/providers?project={{ p.project_name }}#config-editor" class="badge bad"
                 title="{{ p.api_key_env }} is not set — set it in the config editor below">{{ p.api_key_env or "key" }} missing</a>
```

(c) Fix the empty-state hint (line 101). Replace `Configure providers from each project's Config page.` with `Configure providers in the editor below.`

(d) Insert the editor panels just before the closing `</section>` (currently line 106, after the `{% endif %}` that closes the projects/empty block):

```html
  <section id="config-editor" class="panel c-panel">
    <h2 class="panel__title">Provider / model</h2>
    <p class="meta">Global defaults and optional per-project provider overrides. No hidden default provider — set provider, model, API-key env name, and base URL here.</p>
    <form class="inline-form form-row" method="get" action="/ui/providers">
      <label>Project
        <select name="project">
          <option value="">(global only)</option>
          {% for p in projects %}
          <option value="{{ p }}"{% if p == project %} selected{% endif %}>{{ p }}</option>
          {% endfor %}
        </select>
      </label>
      <button type="submit">Load</button>
    </form>
    {% include "partials/_config_form.html" %}
  </section>

  <section class="panel c-panel">
    <h2 class="panel__title">Secrets</h2>
    <p class="meta">API-key values are stored in <code>~/.weaver/secrets.toml</code> and never returned by the API or rendered here.</p>
    {% include "partials/_secrets.html" %}
  </section>
```

Note: the `<section class="providers-hub">` wrapper already opens at the top; the two new `<section>` panels nest inside it before its closing tag, matching the existing `panel c-panel` pattern from the old `config.html`.

- [ ] **Step 6: Delete the standalone config page**

```bash
git rm src/weaver/api/templates/config.html
```

- [ ] **Step 7: Run the editor-render tests**

Run: `rtk pytest tests/unit/api/test_ui_providers.py -k "config_editor or project_param_loads" -q`
Expected: PASS (2 tests).

- [ ] **Step 8: Commit**

```bash
git add src/weaver/api/templates/
git commit -m "feat(providers): render provider/model + secret editor on /ui/providers; remove config.html"
```

---

## Task 4: Remove `/ui/config` routes + dead code from `ui_admin.py`

**Files:**
- Modify: `src/weaver/api/routers/ui_admin.py`

- [ ] **Step 1: Delete the provider/secret config section**

Delete the entire `# --- provider / secret config ---` block in `src/weaver/api/routers/ui_admin.py` (currently lines 518–607): `_config_ctx`, `config_page`, `config_save`, `config_secret_set`, `config_secret_delete`.

- [ ] **Step 2: Remove now-unused imports**

In the import block:
- Change `from weaver.api.ui_context import global_layout, project_layout` to `from weaver.api.ui_context import project_layout` (`global_layout` was used only in `_config_ctx`).
- Remove `SecretNotFoundError` from the `weaver.errors` import (used only in `config_secret_delete`).
- Remove `from weaver.services import provider_config as config_service` (used only by the deleted routes).
- Remove `discover_projects` from `from weaver.services.project_discovery import discover_projects, find_project` → leave `from weaver.services.project_discovery import find_project` (`discover_projects` was used only in `_config_ctx`).

Verify each removed symbol has no other use first:

Run: `rtk grep -n "global_layout\|SecretNotFoundError\|config_service\|discover_projects" src/weaver/api/routers/ui_admin.py`
Expected: after the deletions, zero matches.

- [ ] **Step 3: Update the module docstring**

In the top docstring (lines 1–9), drop the trailing reference to config/secrets. Change the first line from:

```python
"""Consistency/admin browser UI (Stage 11C): glossary, characters, TM, config.
```

to:

```python
"""Consistency/admin browser UI (Stage 11C): glossary, characters, TM.
```

and remove the `provider_config` / API-key clause from the paragraph below it (the secret-form sentence on lines 6–8), leaving the glossary/characters/TM description intact.

- [ ] **Step 4: Verify `/ui/config` is gone and the module imports clean**

Run: `rtk grep -n "/ui/config" src/weaver/api/routers/ui_admin.py`
Expected: zero matches.

Run: `rtk pytest tests/unit/api/test_ui_admin.py -q`
Expected: FAIL only on the config/secret/dashboard-link tests still referencing `/ui/config` (fixed in Task 6) — no import errors, no collection errors.

- [ ] **Step 5: Commit**

```bash
git add src/weaver/api/routers/ui_admin.py
git commit -m "refactor(ui-admin): remove /ui/config routes (moved to /ui/providers)"
```

---

## Task 5: Remove the "Config" link from the global topnav

**Files:**
- Modify: `src/weaver/api/templates/base.html`

- [ ] **Step 1: Delete the Config nav link**

Remove line 23 from `src/weaver/api/templates/base.html`:

```html
      <a href="/ui/config"{% if active_nav|default('') == "config" or _path.startswith("/ui/config") %} class="active" aria-current="page"{% endif %}>Config</a>
```

The topnav now has only Dashboard + New project; the ws-hub sidebar "Providers" entry is the config entry point.

- [ ] **Step 2: Verify no `/ui/config` remains in any template**

Run: `rtk grep -rn "/ui/config" src/weaver/api/templates`
Expected: zero matches.

- [ ] **Step 3: Commit**

```bash
git add src/weaver/api/templates/base.html
git commit -m "refactor(ui): drop Config from topnav; Providers hub is the config surface"
```

---

## Task 6: Update stale tests referencing `/ui/config`

**Files:**
- Modify: `tests/unit/api/test_ui_admin.py`
- Modify: `tests/unit/api/test_ui_layout.py`
- Modify: `tests/unit/api/test_ui_workspace_hub.py`

- [ ] **Step 1: `test_ui_admin.py` — remove moved config/secret tests**

Delete these functions (they now live in `test_ui_providers.py`):
- `test_config_page_and_save` (lines 224–236)
- `test_config_freeform_provider_type` (lines 239–246)
- `test_secret_set_and_delete_without_exposing_value` (lines 249–261)
- `test_secret_invalid_name_error` (lines 264–267)

Also delete the now-empty `# --- provider / secret config ---` comment banner (line 221).

- [ ] **Step 2: `test_ui_admin.py` — fix the dashboard-link assertion**

In `test_project_page_links_admin_sections` change line 279 from:

```python
    assert "/ui/config" in admin_client.get("/ui").text
```

to:

```python
    assert "/ui/providers" in admin_client.get("/ui").text
```

- [ ] **Step 3: `test_ui_admin.py` — narrow `test_config_and_new_use_freeform_provider_config` to `/ui/new`**

The config half moved to `test_providers_hub_renders_config_editor` (Task 3). Replace `test_config_and_new_use_freeform_provider_config` (lines 311–319) with the `/ui/new`-only assertion:

```python
def test_new_project_uses_freeform_provider_config(admin_client: TestClient) -> None:
    new = admin_client.get("/ui/new").text
    assert '<select name="provider"' not in new
    assert "Provider settings start empty" in new
```

- [ ] **Step 4: `test_ui_layout.py` — drop `/ui/config` from the global-mode parametrize**

Change the parametrize on line 33–36 from:

```python
@pytest.mark.parametrize(
    ("path", "nav_label"),
    [("/ui/new", "New project"), ("/ui/config", "Config")],
)
```

to:

```python
@pytest.mark.parametrize(
    ("path", "nav_label"),
    [("/ui/new", "New project")],
)
```

- [ ] **Step 5: `test_ui_workspace_hub.py` — remove the config-route layout test**

Delete `test_config_route_still_global_layout` (lines 295–298). `/ui/config` no longer exists; `/ui/providers` ws-hub layout is already covered by `test_providers_uses_ws_hub_layout`.

- [ ] **Step 6: Run the touched test modules**

Run: `rtk pytest tests/unit/api/test_ui_admin.py tests/unit/api/test_ui_layout.py tests/unit/api/test_ui_workspace_hub.py tests/unit/api/test_ui_providers.py -q`
Expected: PASS (no remaining `/ui/config` references; all config/secret behavior asserted at `/ui/providers`).

- [ ] **Step 7: Verify no test references `/ui/config` anywhere**

Run: `rtk grep -rn "/ui/config" tests`
Expected: zero matches.

- [ ] **Step 8: Commit**

```bash
git add tests/unit/api/test_ui_admin.py tests/unit/api/test_ui_layout.py tests/unit/api/test_ui_workspace_hub.py
git commit -m "test: repoint config/secret coverage from /ui/config to /ui/providers"
```

---

## Task 7: ADR `015` + doc sync (T0)

**Files:**
- Create: `docs/decisions/015-single-provider-config-surface.md`
- Modify: `docs/CODEMAPS/backend.md`, `docs/CODEMAPS/frontend.md`, `docs/MAINTENANCE.md`

- [ ] **Step 1: Write ADR `015`**

Create `docs/decisions/015-single-provider-config-surface.md`:

```markdown
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
the topnav "Config" link is removed. The hub GET stays Gate-B1-safe: it only reads
TOML + secret names (no DB connect, no provider build, no source hashing). Health
remains an explicit per-project POST. Secret values are never rendered — only env-var
names. The `provider_config` service and the JSON `/config` API are unchanged.

## Consequences

- One place to configure providers; no duplicate config surface or legacy redirect.
- The hub GET now also calls `read_config` (TOML-only) — still no provider call on render.
- Any external bookmark to `/ui/config` 404s (acceptable: local single-user cockpit).
- `ui_admin.py` is now glossary/characters/TM only.
```

- [ ] **Step 2: Sync the codemaps + maintenance doc**

Run: `rtk grep -rn "/ui/config" docs`
For each hit in `docs/CODEMAPS/backend.md`, `docs/CODEMAPS/frontend.md`, and `docs/MAINTENANCE.md`, replace the `/ui/config` route/page reference with `/ui/providers` (provider/model + secret config now lives on the Providers hub). Update any sentence describing `ui_admin.py` as owning provider/secret config to say `ui_providers.py`.

- [ ] **Step 3: Verify docs no longer reference the removed route**

Run: `rtk grep -rn "/ui/config" docs`
Expected: matches only inside ADR `015` (which intentionally names the removed route) and any historical sprint/audit doc under `.docs/audit/` (leave those — they are historical record).

- [ ] **Step 4: Commit**

```bash
git add docs/decisions/015-single-provider-config-surface.md docs/CODEMAPS/backend.md docs/CODEMAPS/frontend.md docs/MAINTENANCE.md
git commit -m "docs: ADR 015 single provider-config surface; sync codemaps + maintenance"
```

---

## Task 8: Full verification gate (T6/T7/T8 + Gate D)

**Files:** none (verification only).

- [ ] **Step 1: Full test suite**

Run: `rtk pytest -q`
Expected: PASS — full suite green (prior baseline 1401/4; this change moves coverage, it does not remove behavior).

- [ ] **Step 2: Typecheck**

Run: `rtk proxy powershell -NoProfile -Command "pyright"`
Expected: 0 errors.

- [ ] **Step 3: Lint + format**

Run: `rtk proxy powershell -NoProfile -Command "ruff check . ; ruff format --check ."`
Expected: clean.

- [ ] **Step 4: Manual smoke (the single config surface)**

Start the cockpit, then verify:
- `GET /ui/providers` renders the table + config editor + secrets panel.
- `GET /ui/config` returns 404.
- Selecting a project in the editor dropdown + Load preloads its `[provider]` block.
- Saving config persists (re-open shows the value); a stored secret shows only its env-var name, never the value.
- The "Check" health button still runs an explicit POST and is the only path that calls a provider.
- Topnav has no "Config" link; the ws-hub "Providers" sidebar entry is active on the hub.

- [ ] **Step 5: Security re-check (secret leak)**

Run: `rtk pytest tests/unit/api/test_ui_providers.py -k secret -q`
Expected: PASS — secret values never rendered; env-var names only.

- [ ] **Step 6: Final commit (if any doc/status tweaks remain) + handoff note**

Write the §8 handoff note in the PR description: scope, files touched, what changed, what was intentionally not changed (service signatures, JSON `/config` API, schema), validation evidence (paste the suite/pyright/ruff output), known risks (external `/ui/config` bookmarks 404), recommended next step (open PR for Critic + Release gate).

---

## Self-Review Notes (author checklist — already applied)

- **Spec coverage:** remove `/ui/config` (T4) · remove sidebar/link/internal refs (T3 dangling link, T5 topnav, T6 tests, T7 docs) · move config form/action to `/ui/providers` (T2/T3) · empty/legacy/custom base_url/api_key_env handled (reuses `read_config`/`write_config` + `normalize_provider_config`, unchanged) · health stays explicit POST (untouched) · no secret value rendered (T1/T8 assert) · update tests expecting `/ui/config` (T6). All covered.
- **Type/name consistency:** route fn names `config_save` / `config_secret_set` / `config_secret_delete` and context keys `view` / `project` / `projects` / `saved` / `error` / `secret_saved` / `secret_error` match the partials' existing variable names verbatim, so the moved partials render unchanged.
- **Gate B1:** the only new GET-path call is `read_config` (TOML + secret-name read); no DB connect, no `build_provider`, no source hashing — `test_providers_get_route_is_thin` + `test_no_provider_call_on_hub_get` enforce it.
