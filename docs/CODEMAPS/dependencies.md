<!-- Generated: 2026-06-14 | Updated: 2026-07-05 (ADR 018 connection-first routing) | Files scanned: pyproject.toml, src/weaver/providers/*.py, desktop/src/*.rs | Token estimate: ~900 -->
# Dependencies

## Runtime (`pyproject.toml`)
- `typer>=0.12`, `rich>=13` -> CLI.
- `pydantic>=2` -> boundary DTO/config validation; shared/core stays framework-light.
- `ebooklib>=0.20` -> EPUB read/write.
- `jinja2>=3.1` -> server-rendered cockpit.
- `httpx>=0.27` -> HTTP client for providers/services.
- `openai>=1.40` -> the single `openai_chat` transport: any OpenAI-compatible endpoint (DeepSeek, OpenRouter, Groq, Gemini/Ollama compat endpoints, local servers). `google-generativeai` was removed in v0.7.2 (ADR 018).
- stdlib: `sqlite3`, `tomllib`, `asyncio` (FastAPI layer only), `zipfile`, `tempfile`, `pathlib`.

## Optional Extras
- `weaver[web]`: `fastapi>=0.115`, `uvicorn>=0.30`, `python-multipart>=0.0.9`.
- `weaver[tui]`: `textual>=0.60` read-only dashboard.
- `weaver[wizard]`: `questionary>=2.0` interactive `weaver new`.
- `weaver[dev]`: `pytest>=8`, `ruff>=0.6`, `pyright>=1.1`.
- `weaver[all]` -> `tui,wizard,web`.

## Provider Engines (`src/weaver/providers/`)
One real transport since v0.7.2 (ADR 018): `openai_chat` (OpenAI-compatible `/chat/completions`, `providers/openai_chat.py`) plus `fake` for dev/CI. Legacy `[provider] type` brand labels (`deepseek`, `gemini`, `ollama`) survive only as a migration shim (`_LEGACY_DEFAULTS` in `providers/registry.py`) that normalizes onto `openai_chat` endpoints (gemini → `…/v1beta/openai`, ollama → `:11434/v1` keyless).

| Engine | Auth | Notes |
| --- | --- | --- |
| `openai_chat` | env var named by `api_key_env`; value resolved **shell env → `~/.weaver/secrets.toml`** at build time; keyless supported (empty `api_key_env`) | Any OpenAI-compatible endpoint; `base_url`/`model` per connection or `[provider]` block. |
| `fake` | none | Dev/CI deterministic provider. Never use live LLMs in CI. |

Connections (ADR 018): registry `~/.weaver/connections.toml` (`core/connection_registry.py`, `WEAVER_CONNECTIONS_PATH`), model-discovery cache `~/.weaver/connection_models.json` (`core/connection_models.py`). The cockpit's hybrid key flow stores a typed key under `WEAVER_CONN_<NAME>` in the secret store.

Transport providers implement `translate()` and domain-agnostic `complete(prompt, system, max_output_tokens) -> Completion` (ADR `014`). Feature prompts/parsing stay in services (`providers/prompts.py`, `services/glossary_suggestion.py`, translation services).

## Provider Config / Secrets
- `/ui/providers` is the canonical **Connections** UI (Add/Test/Delete + per-project Active AI / Switch AI). `/ui/config` is a GET-only compatibility redirect to `/ui/providers#connections`; the legacy per-project editor form was removed in v0.7.2.
- `/config` remains the JSON provider/model + secrets API; it is separate from the hub UI and returns redacted config only.
- Project config: `.weaver/<name>/project.toml` — `[routing.<task>]` (`connection`/`model` + `fallback` array, machine-managed via `config_writer.set_routing`) and/or legacy `[provider] type/model/base_url/api_key_env/allow_insecure`, plus `[translation]`, `[translation_profile]`, `[glossary]`, `[qa]`.
- API keys: environment variables or `~/.weaver/secrets.toml` with restrictive mode; env wins.
- Keys never appear in config responses, rendered HTML, logs, provider logs, or SSE events.
- Web secrets endpoints accept POST/DELETE only; the provider hub and JSON secret API store values but only render/return secret names and presence.
- Cloud HTTP must be HTTPS unless `allow_insecure=true` for debug/local testing.

## Config Precedence
- Translate engine (ADR 018, `services/routing.py`): `[routing.<task>]` connection › legacy `[provider]` (when it carries a model) › workspace `[defaults].default_connection`.
- Other config: CLI flag › env var (`WEAVER_DEFAULT_PROVIDER` / `WEAVER_DEFAULT_MODEL` / `WEAVER_OUTPUT_DIR`) › `project.toml` › `~/.weaver/config.toml [defaults]` › built-in default.

## CLI Secret Store Commands
```bash
weaver secrets set DEEPSEEK_API_KEY           # hidden prompt
weaver secrets set MY_KEY --value sk-...      # non-interactive
weaver secrets list                           # names only — values never shown
weaver secrets rm MY_KEY
```
`apply_secrets_to_env()` at startup loads the store and sets keys **not already in env**; the provider factory additionally falls back to the store at build time, so a key saved from a running cockpit works without a restart (shell env always wins). Override store path with `WEAVER_SECRETS_PATH`.

## Adding an Endpoint / Provider
- A new endpoint is **configuration, not code**: add a connection (cockpit Connections or `weaver connections add`) with name + base_url + key; pick a model via Switch AI or `weaver routing set`.
- A new transport *protocol* (anything not OpenAI-compatible) requires a new ADR (ADR 018 D1 collapsed the registry to `openai_chat` + `fake`).

## Prompt / AI Contracts
- Prompt design is data-flow-specific, not provider-specific. Provider adapters are transport; domain validation belongs in services.
- Deterministic checks preferred; LLM output must be JSON-validated/repair-limited where used.
- AI artifacts are explicit, editable/dismissable, failure-visible, and cost-visible.
- No hidden vendor default for AI suggestions; configured provider is used.

## External Services
- Only user-configured OpenAI-compatible endpoints (DeepSeek, OpenRouter, Gemini/Ollama compat endpoints, local servers, …) are ever contacted.
- No telemetry, no hosted backend, no phone-home, no Sentry/OpenTelemetry.
- EPUBCheck is optional external validation requiring Java + `epubcheck.jar`.

## Desktop Toolchain
- `desktop/` is Tauri 2 Rust host, isolated from Python dependency graph.
- Windows baseline: WebView2, Rust >= 1.77, MSVC Build Tools; optional NSIS for installer.
- Sprint P bundles the sidecar: a PyInstaller onedir `weaver.exe` is staged via Tauri `bundle.externalBin`; the Rust host resolves it (override → bundled → PATH fallback), so packaged launches need no external `weaver` on PATH. onefile/size optimization remains deferred (ADR 016).
- Host writes logs under `%APPDATA%\Weaver\` and tails `sidecar.console.log` on crash.

## Locked-Out (ADR required)
No Flask, Django, SQLAlchemy, Celery, RQ, Docker requirement, React/Node build, SPA framework, OpenTelemetry, Sentry, external queue/worker daemon, or global mutable cross-project store. asyncio rejected outside FastAPI web layer.

## Test / Quality Tooling
- `pytest` with markers `requires_ollama`, `requires_cloud`, `slow`, `perf`.
- `ruff` + format, `pyright --project pyrightconfig.json`, pytest suite are the standard gate.
- Live provider tests under `test_*_live.py` require keys/running Ollama and are skipped in CI.
- Maintenance rule: if a change touches I/O/secrets/filesystem/network/provider paths, run security-focused checks or document why not.
