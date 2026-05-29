# Provider and Model Configuration

Provider types are **registry-driven** (`providers/registry.py`) — no hardcoded enum. `project.toml [provider]` stores only `type` / `model` / `base_url` / `api_key_env`. **No API keys in any config file, ever.**

## Built-in provider types

| Provider | When | Auth env var |
|---|---|---|
| `deepseek` | Default cloud (~$2–4 per novel) | `DEEPSEEK_API_KEY` |
| `gemini` | Free-tier cloud (15 req/min, 1M tok/day) | `GEMINI_API_KEY` |
| `ollama` | Local inference (needs GPU) | none |
| `custom` | Any OpenAI-compatible endpoint | env var you name via `api_key_env` |
| `fake` | Dev / CI | none |

> MVP target (ADR 003) adds first-class OpenAI / Groq / OpenRouter support. Today they are reachable through the `custom` OpenAI-compatible type; native types are an MVP item.

## project.toml

```toml
[provider]
type    = "deepseek"
model   = "deepseek-chat"

# custom OpenAI-compatible endpoint:
# type        = "custom"
# base_url    = "https://api.example.com/v1"
# model       = "your-model"
# api_key_env = "MY_API_KEY"
```

## Global defaults & precedence

`~/.weaver/config.toml`:
```toml
[defaults]
default_provider = "deepseek"
default_model    = "deepseek-chat"
output_dir       = "~/translations"
editor           = "code -w"
```

**Precedence (highest → lowest):** CLI flag › env var (`WEAVER_DEFAULT_PROVIDER` / `WEAVER_DEFAULT_MODEL` / `WEAVER_OUTPUT_DIR`) › `project.toml` › `~/.weaver/config.toml` › built-in default.

## API keys & the secret store

Keys come from **environment variables** or the dedicated **local secret store** `~/.weaver/secrets.toml` (mode `0o600`, outside any repo). A shell env var always wins over the stored value. Keys are **never** written to `project.toml` / `~/.weaver/config.toml`, never logged, never rendered.

```bash
weaver secrets set DEEPSEEK_API_KEY           # hidden prompt
weaver secrets set MY_API_KEY --value sk-...   # non-interactive
weaver secrets list                            # names only — values never shown
weaver secrets rm MY_API_KEY
```

At startup `apply_secrets_to_env()` loads the store and sets any key **not already present** in the environment; providers read `os.environ` unchanged. Override the store path with `WEAVER_SECRETS_PATH` (tests/alt setups). In the cockpit, the provider form's key field writes only to the secret store.

## Adding a provider type

1. Add an adapter in `providers/` implementing the provider interface (see `base.py` / `providers/deepseek.py` as a model; OpenAI-compatible ones can reuse the `custom` engine).
2. Register it in `providers/registry.py` so `known_provider_types()` includes it.
3. Resolve its key from an env var (built-in name or `api_key_env`) via the secret-store mechanism — never from config.
4. Add unit tests with `FakeProvider` patterns; never call a live LLM in CI.

## Safe provider handling

- Never echo or render a key; show env-var **name + present/absent** only.
- Provider/model changes go through `config_writer` (atomic, comment-preserving) — it writes `type`/`model`/`base_url`/`api_key_env` only.
- `weaver doctor` / `inspect --healthcheck` report whether a key is present and whether the endpoint is reachable, without exposing the value.
