# ADR 018 — Connection-first routing: collapse providers to one real protocol

**Status:** Accepted (2026-06-15) — implemented and shipped in **v0.7.2** (2026-06-16; tagged on `main`). The legacy gemini shim endpoint was corrected to `…/v1beta/openai` in the 2026-07-05 post-release audit fix (`fix/v072-audit-blockers`).

## Context

Weaver's provider layer pretends to have several "providers" but the code tells a
different story:

- `providers/deepseek.py` → `DeepSeekProvider` is **not** a DeepSeek client. Its
  own docstring says *"OpenAI-compatible chat-completions client (DeepSeek or
  custom endpoint)"* (`deepseek.py:45`). It is the generic `openai_chat` engine,
  misnamed after one vendor. The brand string "DeepSeek" leaks into errors for
  **any** OpenAI-compatible endpoint (`deepseek.py:202,207,227`), so an OpenRouter
  or Groq failure reads as a "DeepSeek response error".
- The registry exposes legacy `type` aliases (`deepseek`, `gemini`, `ollama`,
  `fake`) as a public concept, and the cockpit advertises them verbatim:
  *"Legacy aliases remain supported: deepseek, gemini, ollama, fake"*
  (`_config_form.html:27`). This is internal provider-coupling bleeding onto the
  public surface. A user does not want a *provider name*; they want to point at an
  endpoint and run a *model*.
- `providers/gemini.py` (Google `google-generativeai` SDK, protocol
  `gemini_generate`) and `providers/ollama.py` (native HTTP `/api/generate`) are
  separate wire formats — but both vendors also serve an OpenAI-compatible
  endpoint (Gemini at `…/v1beta/openai`, Ollama at `:11434/v1`). The native
  adapters are redundant maintenance surface that exist only to carry a brand
  name.

The real missing capability is not "more providers". It is a **workspace
connection registry + real routing**: register an endpoint once (URL + key env +
default model), check it, target **any** model id by free string, and route /
fall back across connections per task. The model set is open-ended
(`deepseek-v4-pro`, `deepseek-v4-flash`, `minimax-m3`, …) and must never be
constrained to a curated provider list.

This ADR governs the **Connection-First Routing** sprint (v0.7.2). It changes the
provider contract shape (removes/renames provider files, drops a dependency) and
adds a new config file + precedence tier, so it requires its own ADR per
CLAUDE.md §3.6 and the ADR rules in `docs/DECISIONS.md`.

## User-facing direction (the mental model)

Two owner insight docs (`.proposal/weaver-user-behavior-reality.md`,
`.proposal/weaver-LLM-connection-reality.md`) fix the surface this ADR targets.
The current cockpit is **provider-centric** — it asks the user to pick a provider
*type*, *protocol*, and *engine*. That is backwards. The user thinks in three
orthogonal concepts:

- **Connection** — *where + how* to reach an endpoint: a name, an endpoint URL,
  and an API key. Workspace-level, configured once, reused by every project.
- **Model** — *what* to run. **Discovered** from a connection, never memorised or
  typed.
- **Active AI** — the resolved `(connection, model)` for a project + task right
  now; switchable in one click from the workspace.

`protocol`, `adapter`, and `engine` are implementation details and must be
**hidden** from the user (progressive disclosure). Because D1 collapses the real
transport to a single protocol (`openai_chat`), the UI can drop the protocol/type
/engine fields entirely: a connection is just **Name + Endpoint + Key**, the
protocol is implied.

**Lean backing (owner decision 2026-06-15).** The UX shape above is adopted in
full, but its *backing stays lean*: the rich connection card, health badge,
one-click Switch AI, and fallback are delivered by the simplest mechanism that
produces the visible result (last-probe status, simple try-next fallback,
`project.toml` write + mtime cache). The heavy gateway machinery in
`weaver-LLM-connection-reality.md` (circuit breaker, weighted health-score,
presets, cost dashboard, secret-rotation window, `routing_decisions` ledger) is
**deferred** (D9) — it reopens only with evidence + its own ADR.

## Relationship to prior ADRs

- **Builds on** ADR 014 (`complete()` primitive) and ADR 015 (single config
  surface). The `LLMProvider` ABC (`translate` / `healthcheck` / `complete`) is
  **unchanged**; routing composes the existing methods and adds no provider
  method.
- **Narrowly supersedes one clause of ADR 015.** ADR 015 states *"Legacy aliases
  (`deepseek`, `gemini`, `ollama`, `fake`) remain supported through the provider
  registry."* This ADR removes the **brand aliases** (`deepseek`, `gemini`,
  `ollama`) from the public surface and the engine name, replacing them with a
  protocol-first model (`openai_chat` + `fake`). Existing projects keep working
  via an automatic back-compat mapping (D6), so no user config breaks. Every other
  ADR 015 guarantee (one config surface, Gate-B1 read-only hub, secret values
  never rendered) remains in force.
- **Respects** ADR 010 (single-process, in-thread JobRegistry — routing/fallback
  is inline, no Celery/Redis) and the Gate B1 render-path budget (probes are
  explicit POST only; no background discovery thread).

## Decisions

### D1 — One real protocol: `openai_chat`; `fake` for tests

`openai_chat` is the canonical transport. `fake` remains the test double. The
named-provider files are removed:

- **Rename** `providers/deepseek.py` → `providers/openai_chat.py`;
  `DeepSeekProvider` → `OpenAIChatProvider`; `DeepSeekConfig` →
  `OpenAIChatConfig`. Drop the DeepSeek-branded defaults (`api.deepseek.com`,
  `DEEPSEEK_API_KEY`, `name="deepseek"`); `base_url`, `api_key_env`, and `model`
  become required, brand-free fields. All leaked "DeepSeek" strings become
  *"OpenAI-compatible endpoint `{connection}`"*.
- **Remove** `providers/gemini.py` and `providers/ollama.py`. Gemini and Ollama
  become `openai_chat` **connections** (Gemini → `…/v1beta/openai`, Ollama →
  `http://localhost:11434/v1`), not provider files.
- **Drop** the `google-generativeai` runtime dependency (no longer imported).
- Registry keeps `protocol` as the real selector and `fake`; `type` degrades to a
  cosmetic connection label, never an engine selector. `_LEGACY_DEFAULTS` brand
  table and `register_provider("deepseek"|"gemini"|"ollama")` are removed from the
  public path (retained only inside the D6 migration shim).

### D2 — Connection registry as a workspace entity

New file `~/.weaver/connections.toml` (honors `WEAVER_DATA_DIR`, owner-only mode,
atomic writer reused from `config_writer.py:282`), parallel to `secrets.toml`.
New pure module `core/connection_registry.py`:
`Connection{name, protocol, base_url, api_key_env, default_model, headers,
timeout_seconds, requires_key}` with `register/get/list/delete`. Non-secret
config only — the key **value** stays in `secrets.toml`; `api_key_env` is the
bridge (a name, never a value).

### D3 — Model discovery is core; `model` stays a free-form string

Discovery is **central to the UX**, not a secondary nicety: after a connection's
Test/Refresh, the card shows the model count ("145 models") and the project
"Choose AI" / "Switch AI" pickers list discovered models. On-demand `GET
/v1/models` (explicit POST on Test/Refresh, **no background thread**, never on
render) fills a per-connection cache. Discovery only ever *suggests* — the model
field remains an open string at every layer (config, routing, UI input); any id is
valid (`deepseek-v4-pro`, `minimax-m3`, vendor-prefixed or not). An endpoint that
exposes no `/models` simply offers no suggestions; free-text still works.

### D4 — Routing resolver + simple fallback (no circuit breaker)

New pure module `services/routing.py`:
`resolve(task, project) -> (provider, connection_name, model)` with precedence
`[routing.<task>]` → `connection_ref` → legacy `[provider]` → `[defaults]`. A
`resolve_with_fallback()` yields ordered candidates; on `ProviderError` / timeout
/ 429 the caller advances to the next candidate and cold-marks the failed
connection for a short in-process window. Fallback runs **per segment** inside the
translate loop (`translation.py:262+` is restructured so the provider is resolved
per segment, not once per run). Translation-memory short-circuit
(`translation.py:469`) stays ahead of routing — a TM hit never consults a
connection.

Explicitly **out of scope** (deferred, no evidence yet): 3-state circuit breaker,
weighted health-score formula, p95 SLA tracking, full observability dashboard,
`routing_decisions` ledger table, secret-rotation windows, and native non-OpenAI
provider families. These are SaaS-gateway machinery inappropriate for a
single-user local tool and reopen only with their own ADR + evidence.

### D5 — De-brand the public surface

Remove the `_config_form.html:27` "legacy aliases" hint (and its assertion in
`test_ui_providers.py:344`). The cockpit speaks in **connections + model** — never
provider brand names, `protocol`, `type`, or `engine`. The hub stays Gate-B1
read-only; Check Connection is an explicit POST.

### D6 — Back-compat: automatic mapping, no broken projects

A migration shim maps legacy project config so **existing projects keep working
unchanged**:

- `[provider] type = deepseek` → `openai_chat` connection (`api.deepseek.com`,
  `DEEPSEEK_API_KEY`).
- `type = ollama` → `openai_chat` to `http://localhost:11434/v1`.
- `type = gemini` → `openai_chat` to the Gemini OpenAI-compatible endpoint
  (`GEMINI_API_KEY`).

The shim lives only in the migration path; it is not a public registry entry. A
project with a bare legacy `[provider]` block (no `[routing]`, no
`connection_ref`) resolves bit-for-bit to today's behavior.

### D7 — Connection-first cockpit: Name + Endpoint + Key (protocol hidden)

The provider-centric config form (`_config_form.html`: type / protocol / engine /
model / base_url / api_key_env) is **replaced** by a connection form with three
fields — **Connection Name**, **Endpoint**, **API Key** — plus a **Test
Connection** action that, on success, shows `✓ Connected · N models · NNN ms`
before **Save**. No protocol/type/engine field is shown; `openai_chat` is implied
(D1). The "Providers" surface is relabelled **Connections** (the user-facing term);
the route may stay `/ui/providers` (or alias `/ui/connections`) to keep ADR 015
bookmarks alive. Project AI is chosen as a **model** ("Choose AI" / "Switch AI"),
and the project header shows the **Active AI** (`model via connection`) with a
one-click switch that writes `[routing.<task>]` and takes effect on the next
segment.

### D8 — Connection vs model vs active-AI are distinct

A model id is **not** a connection. Models are discovered *under* a connection and
scoped to it in pickers (the same id on two connections is two distinct choices).
The project stores a *reference* — `(connection, model)` per task — never the
connection's contents.

### D9 — Lean backing (defer the gateway machinery)

The connection-first UX is delivered by the simplest backing that produces the
visible result. **Explicitly deferred** (reopen only with evidence + their own
ADR), and **must not** appear in v0.7.2: 3-state circuit breaker, weighted
health-score formula / p95 SLA, routing presets, cost/observability dashboard,
`routing_decisions` ledger table, and the secret-rotation dual-key window.
Concretely: health badge = **last Test-probe result** (not a rolling score);
fallback = **try-next on 5xx/timeout/429 + short in-process cold-mark** (not a
breaker); key change = **overwrite `secrets.toml`** (not a rotation window);
Switch AI = **`project.toml` write + mtime cache** (not a preset engine).

## Consequences

- No vendor brand appears in the engine, errors, or cockpit copy. "Provider" as a
  user concept is replaced by "connection + model".
- One transport to maintain (`openai_chat`) instead of three; `google-generativeai`
  leaves `pyproject.toml`.
- `model` stays open-ended forever; new models work the day they ship, no code
  change. Discovery only adds convenience.
- Routing/fallback is real and per-segment; a primary 429/5xx no longer aborts a
  long run.
- ADR 015's alias clause is partially superseded (recorded here, not silent).
- Migration risk: Gemini via its OpenAI-compatible endpoint and Ollama via `/v1`
  must be validated against live endpoints (gated by `requires_cloud` /
  `requires_ollama`) before the native files are deleted.

## Migration / rollback

Per-phase, reversible: (1) land the rename + de-brand behind the D6 shim with the
native files still present but unused; (2) validate Gemini/Ollama over their
OpenAI-compatible endpoints; (3) delete `gemini.py`/`ollama.py` and drop the
dependency. Roll back is per phase — restoring a deleted file + dependency pin.

## Related files

- `src/weaver/providers/deepseek.py` → `openai_chat.py` (rename + de-brand)
- `src/weaver/providers/gemini.py`, `src/weaver/providers/ollama.py` (remove)
- `src/weaver/providers/registry.py` (protocol-first; drop brand aliases)
- `src/weaver/core/connection_registry.py` (new)
- `src/weaver/services/routing.py` (new)
- `src/weaver/services/translation.py`, `glossary_suggestion.py`,
  `candidate_generation.py` (call resolver)
- `src/weaver/api/templates/partials/_config_form.html` (de-brand)
- `src/weaver/api/routers/ui_providers.py` (connection register/check/discover)
- `pyproject.toml` (drop `google-generativeai`)
- `tests/unit/api/test_ui_providers.py:344` (update assertion)
