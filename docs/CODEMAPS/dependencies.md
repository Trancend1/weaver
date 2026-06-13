<!-- Generated: 2026-06-13 | Files scanned: pyproject.toml, src/weaver/providers/*.py, desktop/src/*.rs, remote origin/main:docs/{PROVIDER_AND_MODEL_CONFIG,SECURITY_AND_PERFORMANCE,INSTALL_DESKTOP,PROMPT_DESIGN}.md | Token estimate: ~900 -->
# Dependencies

## Runtime (`pyproject.toml`)
- `typer>=0.12`, `rich>=13` -> CLI.
- `pydantic>=2` -> boundary DTO/config validation; shared/core stays framework-light.
- `ebooklib>=0.20` -> EPUB read/write.
- `jinja2>=3.1` -> server-rendered cockpit.
- `httpx>=0.27` -> HTTP client for providers/services.
- `openai>=1.40` -> DeepSeek + `custom` OpenAI-compatible providers.
- `google-generativeai>=0.7` -> Gemini provider.
- stdlib: `sqlite3`, `tomllib`, `asyncio` (FastAPI layer only), `zipfile`, `tempfile`, `pathlib`.

## Optional Extras
- `weaver[web]`: `fastapi>=0.115`, `uvicorn>=0.30`, `python-multipart>=0.0.9`.
- `weaver[tui]`: `textual>=0.60` read-only dashboard.
- `weaver[wizard]`: `questionary>=2.0` interactive `weaver new`.
- `weaver[dev]`: `pytest>=8`, `ruff>=0.6`, `pyright>=1.1`.
- `weaver[all]` -> `tui,wizard,web`.

## Provider Adapters (`src/weaver/providers/`)
Registry-driven: `known_provider_types()` from `providers/registry.py` is the single source of truth.

| Provider | Auth | Notes |
| --- | --- | --- |
| `deepseek` | `DEEPSEEK_API_KEY` | Default cloud. OpenAI-compatible `/v1/chat/completions`; honors JSON response format. |
| `gemini` | `GEMINI_API_KEY` | Free-tier cloud. Uses `google-generativeai`; honors JSON MIME + output cap. |
| `ollama` | none | Local inference via `/api/generate`; no cloud traffic. |
| `custom` | env-var per `api_key_env` | Any OpenAI-compatible endpoint; `base_url` from config. |
| `fake` | none | Dev/CI deterministic provider. Never use live LLMs in CI. |

All transport providers implement `translate()` and domain-agnostic `complete(prompt, system, max_output_tokens) -> Completion` (ADR `014`). Feature prompts/parsing stay in services (`providers/prompts.py`, `services/glossary_suggestion.py`, translation services).

## Provider Config / Secrets
- Project config: `.weaver/<name>/project.toml` `[provider] type/model/base_url/api_key_env/allow_insecure` plus `[translation]`, `[glossary]`, `[qa]`.
- API keys: environment variables or `~/.weaver/secrets.toml` with restrictive mode; env wins.
- Keys never appear in config responses, rendered HTML, logs, provider logs, or SSE events.
- Web secrets endpoints accept POST/DELETE only; no endpoint returns a secret value.
- Cloud HTTP must be HTTPS unless `allow_insecure=true` for debug/local testing.

## Config Precedence
CLI flag › env var (`WEAVER_DEFAULT_PROVIDER` / `WEAVER_DEFAULT_MODEL` / `WEAVER_OUTPUT_DIR`) › `project.toml [provider]` › `~/.weaver/config.toml [defaults]` › built-in default.

## CLI Secret Store Commands
```bash
weaver secrets set DEEPSEEK_API_KEY           # hidden prompt
weaver secrets set MY_KEY --value sk-...      # non-interactive
weaver secrets list                           # names only — values never shown
weaver secrets rm MY_KEY
```
`apply_secrets_to_env()` at startup loads the store and sets keys **not already in env**. Override store path with `WEAVER_SECRETS_PATH`.

## Adding a Provider Type
1. Add adapter in `providers/` implementing the interface (`base.py`; OpenAI-compatible → reuse `custom` engine as model).
2. Register in `providers/registry.py` → `known_provider_types()`.
3. Resolve key from env var or `api_key_env` via secret-store — never hardcode in config.
4. Unit tests using `FakeProvider` patterns; never call live LLMs in CI.

## Prompt / AI Contracts
- Prompt design is data-flow-specific, not provider-specific. Provider adapters are transport; domain validation belongs in services.
- Deterministic checks preferred; LLM output must be JSON-validated/repair-limited where used.
- AI artifacts are explicit, editable/dismissable, failure-visible, and cost-visible.
- No hidden vendor default for AI suggestions; configured provider is used.

## External Services
- DeepSeek, Gemini, Ollama, and custom OpenAI-compatible endpoints only when configured.
- No telemetry, no hosted backend, no phone-home, no Sentry/OpenTelemetry.
- EPUBCheck is optional external validation requiring Java + `epubcheck.jar`.

## Desktop Toolchain
- `desktop/` is Tauri 2 Rust host, isolated from Python dependency graph.
- Windows baseline: WebView2, Rust >= 1.77, MSVC Build Tools; optional NSIS for installer.
- Sprint O baseline resolves `weaver serve` from PATH; PyInstaller/embedded Python single-file bundling is deferred.
- Host writes logs under `%APPDATA%\Weaver\` and tails `sidecar.console.log` on crash.

## Locked-Out (ADR required)
No Flask, Django, SQLAlchemy, Celery, RQ, Docker requirement, React/Node build, SPA framework, OpenTelemetry, Sentry, external queue/worker daemon, or global mutable cross-project store. asyncio rejected outside FastAPI web layer.

## Test / Quality Tooling
- `pytest` with markers `requires_ollama`, `requires_cloud`, `slow`, `perf`.
- `ruff` + format, `pyright --project pyrightconfig.json`, pytest suite are the standard gate.
- Live provider tests under `test_*_live.py` require keys/running Ollama and are skipped in CI.
- Maintenance rule: if a change touches I/O/secrets/filesystem/network/provider paths, run security-focused checks or document why not.
