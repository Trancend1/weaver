# Weaver AI Connection & Routing UX

## Core Principle

> Register once in a global Connection Registry, reuse across projects, and switch AI directly from the project context without returning to configuration pages.

Connections are **global, non-secret resources** that hold *where* to talk to. Keys live separately in the secret store. Models are **discovered**, not typed. A project holds a *reference* to a connection, not the connection's contents.

---

## 1. Architecture Overview

### 1.1 Four-tier flow

```
   ┌─────────────────────────────┐
1  │  Connection Registry        │  workspace-level (~/.weaver/connections.toml)
   │  (one place to register)    │  protocol, base_url, api_key_env, default_model
   └────────────┬────────────────┘
                ▼
   ┌─────────────────────────────┐
2  │  Model Discovery            │  on-demand probe (POST, never on render)
   │  (per-connection cache)     │  vendor /models → cache → stale fallback
   └────────────┬────────────────┘
                ▼
   ┌─────────────────────────────┐
3  │  Project Assignment         │  per-project (project.toml)
   │  (per-task routing)         │  task → (connection, model) + fallback chain
   └────────────┬────────────────┘
                ▼
   ┌─────────────────────────────┐
4  │  Runtime Switching          │  in-cockpit dropdown, immediate effect
   │  (per-task)                 │  on next segment, mid-run safe
   └─────────────────────────────┘
```

**Prefer** the connection-first flow above.

**Avoid** the provider-centric flow that puts implementation details at the top:

```
Providers                  ← implementation detail, not what users think in
   ↓
Protocols                  ← implementation detail
   ↓
Models
```

Users do not think in providers and protocols. They think in *where do I point Weaver* and *what model do I want for this task*.

### 1.2 Three orthogonal concepts

| Concept | Lifetime | Example | Where stored |
|---|---|---|---|
| **Connection** | workspace | `openrouter` | `~/.weaver/connections.toml` |
| **Model** | derived from a connection | `deepseek/deepseek-chat` | cache + on-demand probe |
| **Active AI** | project + task | `translate → (openrouter, deepseek/deepseek-chat)` | `project.toml [routing]` block |

A connection is *where* + *how*. A model is *what*. An active AI is a *resolved (connection, model) pair for a given task*.

---

## 2. Level 1 — Global Connection Registry

### 2.1 Menu location

**Sidebar → Connections** (top-level). The **Models** sub-view lives underneath, not as a sibling.

```
Sidebar
├── Projects
├── Connections
│   ├── All Connections
│   ├── Models
│   └── Audit Log
└── Settings
```

### 2.2 Purpose

A user registers AI endpoints *once* and reuses them across every project. The registry is global, single-user, and lives in `~/.weaver/connections.toml` (atomic writes, mode `0o600`).

Connections are **not tied to any project**. They are workspace-level resources, identical across the workspace, addressable by name.

### 2.3 Connection card

Each registered connection shows:

```
┌────────────────────────────────────────────────┐
│ OpenRouter                          [ ⋮ ]      │
│ ● Healthy       Latency 320 ms    145 models   │
│ openai_chat · https://openrouter.ai/api/v1     │
│                                                │
│  [ Test ]  [ Refresh Models ]  [ Edit ]  [ ⋯ ] │
└────────────────────────────────────────────────┘
```

Fields:
- **Status** — healthy / degraded / unhealthy, computed from a rolling health score (last 1h)
- **Latency** — p50 from the last probe
- **Models** — count from the latest discovery snapshot
- **Protocol** — wire protocol (`openai_chat`, `gemini_generate`, …)
- **Base URL** — endpoint

Actions:
- **Test Connection** — explicit POST; runs a tiny probe (`max_tokens=1`) and updates status
- **Refresh Models** — explicit POST; re-probes `/v1/models` and updates the cache
- **Edit Configuration** — opens the edit modal (protocol, base_url, default_model, headers, timeout, tags)
- **Rotate API Key** — opens the secret rotation flow (the key itself lives in `secrets.toml`; the connection only holds the env var *name*)
- **Add Connection** — same form as Edit, with a new handle

### 2.4 Connection properties

```yaml
# ~/.weaver/connections.toml
[connections.openrouter]
protocol: openai_chat              # wire protocol; drives adapter selection
base_url: https://openrouter.ai/api/v1
api_key_env: OPENROUTER_API_KEY   # NAME only, value lives in secrets.toml
default_model: deepseek/deepseek-chat
timeout_seconds: 60
headers: {}                        # optional vendor-specific HTTP headers
tags: [cloud, paid]                # free-form labels for filtering
requires_key: true
```

Notes:
- `protocol` and `base_url` together identify the adapter; the `LLMProvider` ABC is unchanged.
- `api_key_env` is a *name*, never a value. The secret value resolves from `~/.weaver/secrets.toml` at call time, into `os.environ`.
- `default_model` is the fallback used when a routing profile omits an explicit model.
- `health` and `models` are **derived**, not stored. They live in the discovery cache (`connection_models` table) and the health log.
- The registry is the *only* place to register a connection. Per-project files reference by name.

### 2.5 Registered connections

The Connections page lists all registered connections in a stack of cards. Status colors follow the design system (forest green = healthy, amber = degraded, red = unhealthy; **never AI purple**).

| Example handle | Protocol | Base URL | Use case |
|---|---|---|---|
| `openrouter` | `openai_chat` | `https://openrouter.ai/api/v1` | Cloud, many models |
| `gemini` | `gemini_generate` | `https://generativelanguage.googleapis.com` | Cloud, Google models |
| `local_ollama` | `openai_chat` | `http://localhost:11434/v1` | Local, offline, free |
| `deepseek` | `openai_chat` | `https://api.deepseek.com/v1` | Cloud, direct DeepSeek |

> Connection handles are free-form slugs (`openrouter`, `claude_work`, `local_ollama`). They become the *only* thing the user types elsewhere.

A model (e.g. a specific LLM name like `mimo`) is **not** a connection. Models are discovered from a connection's `/v1/models` endpoint and are scoped under that connection in the picker.

---

## 3. Model Discovery

### 3.1 Why

Users should not have to know a model id by heart. Once a connection is registered, Weaver probes its `/v1/models` (or the vendor's equivalent) and presents a searchable picker.

### 3.2 When

- **Never on render.** Per ADR 015 / Gate B1: the Connections page GET reads only TOML/DB.
- **Manual refresh** via the **Refresh Models** button on the connection card.
- **Background TTL** of 6 hours, configurable, opt-in. The default is *no* background thread; manual refresh only.

### 3.3 Result

```
┌─────────────────────────────────────────────────┐
│ Models for openrouter            Search: [____] │
├─────────────────────────────────────────────────┤
│ deepseek/deepseek-chat        [chat]   64K ctx  │
│ deepseek/deepseek-reasoner    [chat]   64K ctx  │
│ anthropic/claude-sonnet-4.6   [chat]  200K ctx  │
│ openai/gpt-5                  [chat]  128K ctx  │
│ google/gemini-2.5-pro         [chat]  1M  ctx  │
└─────────────────────────────────────────────────┘
        Last refresh: 14 min ago     [ Refresh now ]
```

Capability badges (`chat`, `vision`, `tools`) come from the discovery adapter. Vendors that don't expose capabilities fall back to a curated list with an `(unverified)` badge.

If the upstream probe fails, the picker shows the last good snapshot with a `(stale)` badge. The user is never stranded by a transient outage.

### 3.4 Caching

- Storage: `connection_models` table in the project DB.
- TTL: 6 hours default; configurable per connection via `[discovery] ttl_seconds = 21600`.
- Conflict policy: if two connections return the same model id, the picker shows it twice, one per connection. No global dedupe — connections are independent and may differ in price, latency, or SLA.

---

## 4. Level 2 — Project AI Assignment

### 4.1 Project header

```
┌──────────────────────────────────────────────────────────┐
│ The Insipid Prince                                       │
│                                                          │
│ Active AI for translate:                                 │
│   DeepSeek V3                                            │
│   via openrouter · 320 ms · ● Healthy                    │
│                                                          │
│ [ Switch AI ▾ ]                                          │
└──────────────────────────────────────────────────────────┘
```

The header shows *one* task at a time, with a task selector for users who configured per-task routing. The default view is **translate** because that's the primary workflow.

### 4.2 Routing profile (per-task)

A project's `project.toml` declares one `(connection, model)` pair **per task**, plus a fallback chain:

```toml
# .weaver/the_insipid_prince/project.toml

# Legacy block (1:1, optional) — still supported, see §11
[provider]
type = "custom"
protocol = "openai_chat"
base_url = "https://openrouter.ai/api/v1"
api_key_env = "OPENROUTER_API_KEY"
model = "deepseek/deepseek-chat"

# New: per-task routing
[routing.translate]
connection = "openrouter"
model = "deepseek/deepseek-chat"

[routing.glossary_suggest]
connection = "claude"
model = "claude-sonnet-4.6"

[routing.candidate]
connection = "local_ollama"
model = "qwen3:14b"

# Per-task fallback chain
[routing.fallback.translate]
primary = { connection = "openrouter", model = "deepseek/deepseek-chat" }
fallback = [
  { connection = "claude",        model = "claude-sonnet-4.6", trigger = ["5xx", "timeout", "rate_limit"] },
  { connection = "local_ollama",  model = "qwen3:14b",         trigger = ["5xx", "timeout", "rate_limit"] },
]
```

**Resolution precedence** for *any* task:

1. `[routing.<task>]` in this project
2. `[provider]` legacy block (acts as the default for all tasks)
3. Workspace `[defaults]` (`default_connection`, `default_model`)
4. `ConfigError("no connection for task X")` with a *Likely cause / Next command* hint

### 4.3 Active AI in the project header

For a given task, the *active AI* is the resolved `(connection, model)`. The project header shows the active AI for the currently selected task.

| Concept | Scope | Lifetime | Where |
|---|---|---|---|
| Registered AI | workspace | persistent | `connections.toml` |
| Active AI | project + task | persistent + runtime cache | `project.toml` + in-memory `(project_mtime, task)` cache |
| Fallback chain | project + task | persistent | `project.toml [routing.fallback.<task>]` |

### 4.4 Mental model: Git remotes and branches

```
git remote add openrouter <url>      ←  register a connection (once)
git fetch openrouter                 ←  discover models
git checkout -b translate/deepseek   ←  bind a task to (connection, model)
git checkout translate/claude        ←  runtime switch
```

- **Registered AI** = the *inventory* of remotes. You have them; you may not be using them.
- **Active AI** = the *current branch*. What is checked out right now, for this task.
- **Fallback** = a *refspec merge strategy* — try the primary, fall back if the upstream rejects.

This is closer to how users think than the alternative mental model of "providers and protocols".

---

## 5. AI Presets

### 5.1 Why presets

Power users reuse the same routing shape across many projects. A preset is a *named bundle* of `(task → connection, model)` mappings plus a fallback chain. Presets live at the workspace level and are *referenced* by projects.

### 5.2 Example presets (workspace-level)

```yaml
# ~/.weaver/routing_presets.toml

[presets.fast]
translate        = { connection = "openrouter", model = "deepseek/deepseek-chat" }
glossary_suggest = { connection = "openrouter", model = "deepseek/deepseek-chat" }
candidate        = { connection = "openrouter", model = "deepseek/deepseek-chat" }

[presets.balanced]
translate        = { connection = "openrouter", model = "gpt-5-mini" }
glossary_suggest = { connection = "openrouter", model = "gpt-5-mini" }
candidate        = { connection = "openrouter", model = "deepseek/deepseek-chat" }

[presets.quality]
translate        = { connection = "openrouter", model = "anthropic/claude-sonnet-4.6" }
glossary_suggest = { connection = "openrouter", model = "anthropic/claude-sonnet-4.6" }
candidate        = { connection = "openrouter", model = "gpt-5-mini" }

[presets.offline]
translate        = { connection = "local_ollama", model = "qwen3:14b" }
glossary_suggest = { connection = "local_ollama", model = "qwen3:14b" }
candidate        = { connection = "local_ollama", model = "qwen3:14b" }
```

Notes:
- Presets reference **registered connections** by handle. They do not embed URLs or keys.
- A preset never invents a connection. A preset that references an unregistered connection raises a clear `ConfigError` at load time.
- Native Anthropic / Google protocols are Sprint 8 + ADR-gated; presets may reference a `claude` connection only after that lands, and only via an OpenAI-compat proxy until then.

### 5.3 Project assignment via preset

```toml
# .weaver/<project>/project.toml
[routing]
preset = "quality"                                                # applies all of the preset's task mappings
overrides = { translate = { connection = "openrouter", model = "gpt-5-mini" } }   # override a single task
```

A project can opt in to a preset and override a single task. This is the high-trust path for "I want quality for everything except translation, which I want cheap and fast".

### 5.4 Preset UX

The routing editor shows three columns side by side:

```
   Preset                       Task                          Override
┌────────────┐    ┌──────────────────────────────────┐    ┌──────────────────┐
│ Fast       │    │ translate        [openrouter ▾]  │    │ [ Apply preset ] │
│ Balanced ● │    │ glossary_suggest [openrouter ▾]  │    │ [ Reset to       │
│ Quality    │    │ candidate        [openrouter ▾]  │    │   preset       ] │
│ Offline    │    │                                  │    │                  │
│ + New      │    │ + fallback chain editor          │    │                  │
└────────────┘    └──────────────────────────────────┘    └──────────────────┘
```

The active preset shows a dot (`●`). Editing a single task creates an *override*; the preset itself is unchanged.

---

## 6. Switch AI Flow

### 6.1 The Switch AI modal

Clicking **Switch AI** in the project header opens a modal with a *grouped* picker:

```
┌──────────────────────────────────────────────────────┐
│ Switch AI for: translate                       [ ✕ ] │
│                                                      │
│ Currently: DeepSeek V3 via openrouter                │
│                                                      │
│ Search models: [___________________________]         │
│                                                      │
│ ▾ openrouter                            [● current]  │
│   • DeepSeek V3                                      │
│   • Claude Sonnet 4.6                                │
│   • GPT-5                                            │
│ ▾ claude                                            │
│   • Claude Sonnet 4.6                                │
│   • Claude Opus 4                                    │
│ ▾ local_ollama                                      │
│   • Qwen3 14B                                        │
│   • Llama 3.3 70B                                    │
│                                                      │
│                              [ Cancel ]  [ Switch ]  │
└──────────────────────────────────────────────────────┘
```

Key behaviors:
- Models are **grouped by connection**. Selecting `Claude Sonnet 4.6` under `openrouter` and selecting it under `claude` are *different choices* — the same model id can exist on different connections with different prices, SLAs, and key scopes.
- The currently active AI is marked `● current` and shown at the top.
- Search is fuzzy and matches both model id and display name.
- Hitting Enter selects the focused row; arrow keys move.
- Switching is *per task*. A small task selector at the top lets the user switch AI for `glossary_suggest` or `candidate` from the same modal.

### 6.2 What happens on Switch

1. The new `(connection, model)` is written to `project.toml [routing.<task>]` (atomic writer, preserves comments).
2. The in-memory resolver cache is invalidated by mtime.
3. The project header updates immediately.
4. **Mid-run behavior:** in-flight segments finish with their current model; the next segment picks up the new model. Streaming mid-call failover is not supported — the whole segment restarts from scratch if the stream dies after the first token.

### 6.3 Confirmation

Switching AI for `translate` does not require a confirmation — the operation is reversible (re-open the modal, pick the previous model). Switching that *removes a fallback* does require a confirmation: a fragment modal (not a native `confirm()`), per ADR 005.

---

## 7. Runtime Switching in the Cockpit

### 7.1 Translation cockpit

While a translation is running, a small dropdown is pinned to the top of the segment table:

```
AI for translate:  DeepSeek V3 (openrouter) ▾
```

Clicking the caret opens the *same* Switch AI modal (Section 6). The active row is highlighted; the next segment uses the new model.

### 7.2 Multi-task switcher

If the project uses per-task routing, the cockpit shows:

```
translate         → DeepSeek V3 (openrouter)        [ Switch ]
glossary_suggest  → Claude Sonnet 4.6 (openrouter)  [ Switch ]
candidate         → Qwen3 14B (local_ollama)        [ Switch ]
```

A user can swap any of the three without leaving the cockpit. Each **Switch** opens the same modal, defaulting to that task.

### 7.3 Per-task quick switch

The `[routing]` block in `project.toml` is the source of truth. The cockpit reads it via the resolver, which:
- checks `[routing.<task>]` first,
- falls back to `[provider]` (legacy),
- falls back to workspace `[defaults]`.

The resolver is *called per segment*, not per run. Mid-run switches take effect on the next segment. Cooperative cancel (`should_cancel`) is honored — if the user cancels mid-segment, the switch is not retroactive.

---

## 8. Fallback Chain

### 8.1 Why

A connection outage should not halt a 10,000-segment translation. The fallback chain is the *rescue* the user gets for free when they register more than one connection.

### 8.2 Chain shape

```toml
[routing.fallback.translate]
primary = { connection = "openrouter", model = "deepseek/deepseek-chat" }
fallback = [
  { connection = "claude",       model = "claude-sonnet-4.6", trigger = ["5xx", "timeout", "rate_limit"] },
  { connection = "local_ollama", model = "qwen3:14b",         trigger = ["5xx", "timeout", "rate_limit", "content_filter"] },
]
```

`trigger` is an enum: `5xx`, `4xx`, `timeout`, `rate_limit`, `content_filter`. A 4xx (other than `rate_limit`) is *not* a fallback trigger — it's a request error and should bubble up.

### 8.3 Circuit breaker

Each connection has a per-process circuit breaker:

```
CLOSED  (3 consecutive failures in 60s)  →  OPEN
OPEN    (block all calls; auto-half-open after 30s)  →  HALF_OPEN
HALF_OPEN  (1 trial; success → CLOSED, fail → OPEN for 60s)
```

The breaker state is in-memory per process. SQLite mirrors the last 100 events for the hub to render.

### 8.4 Cost ceiling per chain

A routing profile can cap spend per segment:

```toml
[routing.fallback.translate]
primary = { ... }
max_cost_per_segment_usd = 0.05     # hard cap; the resolver aborts before exceeding it
```

If the next candidate would exceed the cap, the chain aborts and the segment is marked `failed: budget_exceeded`. The user sees a visible warning at chain build time if the fallback is more expensive than the primary.

### 8.5 Audit

Every routing decision is logged:

```
routing_decisions:
  job_id, segment_id, task, candidates_json, selected_*, trigger,
  input_tokens, output_tokens, cost_usd, latency_ms, outcome, created_at
```

The Cockpit's **Why this AI?** link opens the latest 100 decisions for that project, with the full candidate list, scores, and outcomes. This is the *only* way the user can answer "why did this segment use Claude instead of DeepSeek?".

---

## 9. Health & Observability

### 9.1 Connection status

The connection card shows a rolling status:

| Score | Status | Color | Routing behavior |
|---|---|---|---|
| ≥ 0.8 | Healthy | forest green | primary candidate |
| 0.5 – 0.8 | Degraded | amber | eligible, deprioritized |
| < 0.5 | Unhealthy | red | auto-skip in routing |

The score is a weighted blend:

```
score = 0.40 * active_probe_success_rate
      + 0.40 * passive_success_rate (last 1h, min 10 samples)
      + 0.20 * (1 - clamp(p95_latency_ms / sla_latency_ms, 0, 1))
```

Hysteresis: require **2 consecutive unhealthy reads** before flipping. This avoids flapping when a vendor has a 30-second blip.

### 9.2 Health history

The connection card expands to show a 24h sparkline of probe results and p95 latency. All read paths are DB-only; the dashboard never makes a provider call on render.

### 9.3 Cost dashboard

A separate `Usage` page renders:

- Time-series: per-project, per-day, per-task token usage (last 30 days)
- Per-connection success rate (rolling 1h, 24h, 7d)
- Cost estimate in USD (price table is editable in `connections.toml` under `[prices.<connection>.<model>]`; estimates are labelled "estimated")
- Routing audit: the latest 100 decisions with the full candidate list

The page is opt-in via `?show_costs=1` (privacy by default). Per ADR 014, this is the *only* place we display cost.

---

## 10. Security Model

### 10.1 Two-file separation

| File | Holds | Mode | Owner |
|---|---|---|---|
| `~/.weaver/connections.toml` | non-secret: protocol, base_url, default_model, headers, timeout, tags | `0o600` | user |
| `~/.weaver/secrets.toml` | secret: env-var name → value | `0o600` | user |

The connection's `api_key_env` is a **name**, not a value. The secret store resolves it to a value at call time, into `os.environ`. The connection registry never contains a key.

### 10.2 Rotation

A **Rotate API Key** action on the connection card opens a flow that:

1. Reads the current value from `secrets.toml`.
2. Accepts a new value.
3. Marks the old value `(rotating)` for 5 minutes, then deletes it.
4. Writes the new value atomically.
5. Emits an audit log entry: who, when, which env name.

During the 5-minute window, both values resolve. The next provider call uses the new value; a long-running call that started before the rotation may use the old one. This is acceptable for a local-first tool and is documented.

### 10.3 Redaction

A single chokepoint middleware scrubs any env-var value from logs, SSE events, and rendered HTML. This is the same rule that already applies in `services/provider_config.py` (no key value in any return path) and is enforced as a CI lint rule.

### 10.4 What never leaves the machine

- API key values
- Source text from a project (unless the user explicitly exports)
- The audit log is local-only; no remote sync, no SaaS

---

## 11. Backward Compatibility

### 11.1 Legacy `[provider]` block

Projects that pre-date the registry keep working *unchanged*. The resolver synthesizes a connection from `[provider]` when no `[routing]` block exists:

```toml
[provider]
type = "custom"
protocol = "openai_chat"
base_url = "https://openrouter.ai/api/v1"
api_key_env = "OPENROUTER_API_KEY"
model = "deepseek/deepseek-chat"
```

Becomes (logically, not on disk):

```
synthesized_connection = {
  name: "__legacy_<project_id>",
  protocol: "openai_chat",
  base_url: "https://openrouter.ai/api/v1",
  api_key_env: "OPENROUTER_API_KEY",
  default_model: "deepseek/deepseek-chat"
}
```

The `[provider]` block continues to work for all tasks. Switching to `[routing]` is opt-in.

### 11.2 Phased rollout (matches existing precedent)

1. **Phase 1 — Read-side support.** The resolver understands both `[provider]` and `[routing]`. No writes to either. Default behavior (no `[routing]`) is bit-exact with the previous version.
2. **Phase 2 — Lazy migrate.** The first time a user opens the routing editor, a `[routing]` block is synthesized from `[provider]`. The `[provider]` block is preserved for one release.
3. **Phase 3 — Drop.** After 2 minor releases, drop the `[provider]` block in the resolver. A codemod script helps users with custom scripts.

Phases are not combined. Rollback is per-phase.

### 11.3 What if both `[provider]` and `[routing]` are present?

`[routing.<task>]` wins for any task it declares. For tasks not in `[routing]`, the resolver falls back to `[provider]`. A project with *both* is supported; a deprecation warning is logged for the legacy block.

---

## 12. Navigation Structure

### 12.1 Sidebar

```
Sidebar
├── Projects
├── Connections
│   ├── All Connections
│   ├── Models            (browse all discovered models across connections)
│   └── Audit Log         (secret rotations, connection lifecycle)
├── Usage                 (observability, opt-in costs)
└── Settings
```

`Models` is a sub-view of `Connections`, not a sibling. The audit log lives under `Connections` because it is connection-related; it is not a global system log.

### 12.2 Project header

```
┌──────────────────────────────────────────────────────────┐
│ The Insipid Prince                                       │
│                                                          │
│ Active AI for translate:                                 │
│   DeepSeek V3 (openrouter)                               │
│   320 ms · ● Healthy                                     │
│                                                          │
│ [ Switch AI ▾ ]                                          │
└──────────────────────────────────────────────────────────┘
```

For projects with per-task routing, the header shows the active task in a small selector:

```
Task:  [ translate ▾ ]   ( glossary_suggest · candidate )
```

Switching the task selector changes which active AI is displayed. Clicking **Switch AI** opens the modal defaulting to the selected task.

### 12.3 Cockpit dropdown

```
AI for translate:  DeepSeek V3 (openrouter) ▾
```

Same picker as the header Switch AI modal. Mid-run safe.

---

## 13. UX Philosophy

### 13.1 What users are actually trying to do

A user opens Weaver to translate a novel. They are not trying to *manage a provider*. They are trying to:

1. Pick the *best* AI for *this* novel — given cost, language, style, and personal taste.
2. Keep the project running when their favorite AI is down.
3. Switch mid-translation when they realize a different AI is doing better on a chapter.
4. See how much they spent and on what.

The system should support those four jobs and *get out of the way* for everything else.

### 13.2 What this means for design

- **Connection registration is a one-time task.** It should take less than 30 seconds. URL + protocol + key → done.
- **Model discovery is automatic.** The user should never type a model id.
- **Project-level AI is a *reference*, not a *configuration*.** The project says "I want Claude for translation", not "https://..., api_key=..., model=..., timeout=...".
- **Runtime switching is a single click.** No save dialog, no page reload, no "are you sure".
- **Fallback is invisible until needed.** The user does not configure it up front; they add connections over time, and the system uses them as fallbacks.
- **Cost is opt-in.** The default UI shows task status, not dollar signs.
- **Errors render inline, never in modals.** Per ADR 005, the routing audit is the canonical "why" page when something goes wrong.

### 13.3 What the system does *not* do

- It does not aggregate connections (no "Weaver Cloud"). Users bring their own endpoints.
- It does not track vendor prices. The price table is the user's; estimates are estimates.
- It does not call any provider on render. Per Gate B1, every provider call is an explicit POST.
- It does not put a key in `connections.toml` or a URL in `secrets.toml`. Two-file separation is the security model.
- It does not add a new provider family without an ADR. Anthropic-native and Google-native are Sprint 8, gated.
- It does not list a model name as a connection. A model is discovered from a connection; it is not itself a registered resource.

---

## 14. Quick Reference

### 14.1 Glossary

| Term | Definition |
|---|---|
| **Connection** | A registered endpoint: protocol + base_url + default_model + env-var name for the key |
| **Registered AI** | All registered connections in the workspace |
| **Active AI** | The resolved (connection, model) for a project + task at the current moment |
| **Model** | A model id discovered from a connection (e.g. `deepseek/deepseek-chat`) |
| **Preset** | A named bundle of `(task → connection, model)` mappings |
| **Routing profile** | A project's `[routing]` block: per-task (connection, model) + fallback chain |
| **Fallback chain** | A list of candidate (connection, model) pairs tried in order when the primary fails |
| **Task** | One of `translate`, `glossary_suggest`, `candidate`, `qa_critique` |
| **Circuit breaker** | Per-connection 3-state machine (CLOSED / OPEN / HALF_OPEN) that skips a connection after repeated failures |
| **Cost ceiling** | Optional `max_cost_per_segment_usd` cap on a routing profile |

### 14.2 File map

| Concern | File |
|---|---|
| Connection registry | `~/.weaver/connections.toml` |
| Routing presets | `~/.weaver/routing_presets.toml` |
| Per-project routing | `.weaver/<project>/project.toml [routing]` block |
| Legacy per-project config | `.weaver/<project>/project.toml [provider]` block |
| Secret store | `~/.weaver/secrets.toml` (mode `0o600`) |
| Secret audit log | `~/.weaver/secrets_audit.log` (JSONL, mode `0o600`) |
| Discovery cache | `connection_models` table in project DB |
| Routing decisions | `routing_decisions` table in project DB |
| Price table | `~/.weaver/connections.toml [prices.<connection>.<model>]` section |

### 14.3 ADR-required changes

| Change | ADR? |
|---|---|
| New protocol adapter (Sprint 8) | **YES** — per `CLAUDE.md §3.4` |
| Cost auditing for `complete()` (Sprint 5) | **YES** — reopens ADR 014 |
| Workspace-level translation memory (F-03) | **YES** — schema change spans projects |
| Multi-user / team sharing | **YES** — violates `CLAUDE.md §3.4` single-user rule |
| Adding a SaaS feature (e.g. cloud sync) | **YES** — violates local-first principle |

Anything that re-opens a locked decision in `CLAUDE.md §3.4/§3.5` requires a new ADR. The connection-routing proposal stays inside the existing boundary.
