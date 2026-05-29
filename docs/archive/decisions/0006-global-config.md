# 0006: Global Config and Environment Variable Layering

Date: 2026-05-23
Status: accepted

## Context

Users who maintain multiple Weaver projects repeat the same `[provider]` and `[output]` preferences in every `project.toml`. Power users want to set a default provider or model once, not per-project. Shell environments already carry `$EDITOR`; Weaver should respect it. A clear, unsurprising precedence chain prevents configuration surprises.

## Decision

Introduce a user-level config file at `~/.weaver/config.toml` (XDG not adopted — single-platform simplicity). The file is optional; a missing file is equivalent to an empty one.

Supported keys:

| Key                | Type   | Meaning                          |
|--------------------|--------|----------------------------------|
| `default_provider` | string | Provider type fallback           |
| `default_model`    | string | Model fallback                   |
| `output_dir`       | string | Default output directory         |
| `editor`           | string | Editor command for `weaver edit` |

Environment variables:

| Variable                 | Overrides                |
|--------------------------|--------------------------|
| `WEAVER_DEFAULT_PROVIDER`| `default_provider`       |
| `WEAVER_DEFAULT_MODEL`   | `default_model`          |
| `WEAVER_OUTPUT_DIR`      | `output_dir`             |

Precedence chain (highest wins):

1. CLI flag (`--provider`, `--model`)
2. Environment variable (`WEAVER_DEFAULT_PROVIDER`, etc.)
3. Project `project.toml` `[provider]` section
4. Global `~/.weaver/config.toml`
5. Built-in default (`deepseek` / `deepseek-chat`)

Resolution is implemented in `src/weaver/core/global_config.py` via a single `resolve_config_value()` function. Services call this function; the CLI does not implement precedence logic itself.

API keys remain environment-variable-only (`DEEPSEEK_API_KEY`, `GEMINI_API_KEY`). They are never stored in any config file.

## Consequences

**Easier:** Users configure once for all projects. CI can set env vars for provider overrides without touching project files. `$EDITOR` resolution is consistent.

**Harder:** One more file to document. Debugging "which config won?" requires inspecting four layers. Mitigated by `weaver doctor` reporting the resolved values in a future enhancement.
