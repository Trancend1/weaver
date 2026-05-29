# 0018: Config-Writer Service

Date: 2026-05-29
Status: accepted

## Context

PP2: there is no way to set provider/model without hand-editing `project.toml` or passing `--provider/--model` every run. The global config resolver (`core/global_config.py`) reads `~/.weaver/config.toml` but **nothing writes it**. The `weaver new` wizard collects a provider then discards it (`services/wizard.py` vs `cli/main.py`), and `initialize_project` hardcodes `type = "deepseek"` with a stray ollama `base_url` (`services/project.py`).

The cockpit (ADR `0016`) needs to write provider/model from a dropdown, at either project or global scope. Config writes touch valuable user state, so they must be atomic and must not clobber unrelated keys. API keys must never be written (CLAUDE.md §4.2, ADR `0017`).

## Decision

Add a new service `src/weaver/services/config_writer.py` (one concept per file, CLAUDE.md §4.2). It is the single writer for provider/model config, used by both the cockpit and the wizard fix.

- **API:** `set_provider(target, *, provider_type=None, model=None, base_url=None)` where `target` selects scope: a `project.toml` path (project scope) or the global `~/.weaver/config.toml` (global default).
- **Atomic writes:** `tempfile` + `os.replace` (CLAUDE.md §4.2). Never partial writes.
- **Preserve unrelated keys:** read existing TOML, update only the touched keys in `[provider]` (project) or the relevant global keys, re-serialize. Comments may be lost (documented limitation) but no data keys are dropped.
- **Never writes secrets:** only `type`, `model`, `base_url`. API keys stay env-only.
- **Wizard/init fix:** `initialize_project` gains an optional `provider` argument; `weaver new` passes the wizard's chosen provider through `config_writer`. The stray hardcoded ollama `base_url` for the deepseek default is corrected.

Precedence at read time is unchanged: CLI flag > env var > project.toml > global config > built-in default (`core/global_config.py`).

## Consequences

Easier: provider/model switching becomes a one-click (cockpit) or one-call (wizard) operation; the global default is finally writable; the discarded-provider bug is fixed.

Harder: TOML round-tripping with `tomllib` (read) + manual serialize (write) does not preserve comments — acceptable for machine-managed config sections. A future need to preserve comments would require a round-trip TOML library (new dep, new ADR).
