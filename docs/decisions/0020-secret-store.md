# 0020: Local Secret Store for Provider API Keys

Date: 2026-05-29
Status: accepted

## Context

Until now API keys were **env-var only** (CLAUDE.md §4.2, ADR `0017`): the user
exported `DEEPSEEK_API_KEY` / `GEMINI_API_KEY` in their shell, and Weaver read
`os.environ`. That rule deliberately kept keys out of `project.toml`,
`~/.weaver/config.toml`, and logs — the repo even ships a `.githooks` secret
scanner.

Two needs break the env-only-via-shell assumption:

1. **Configurable / custom providers** (this change). Users want to point Weaver
   at arbitrary OpenAI-compatible endpoints, each with its own key under a
   user-chosen env-var name — not just the two hardcoded names.
2. **The web cockpit** has no shell. A user driving Weaver entirely from the
   browser (Phase 12) cannot `export` a variable; they need a way to supply a key
   that persists across runs without hand-editing dotfiles.

Writing keys into `project.toml` / global config is still unacceptable: those
files are meant to be shareable/committable and are scanned by the pre-commit
hook. We need a *separate* secret location that is never the project config.

## Decision

Introduce a dedicated **local secret store**, `~/.weaver/secrets.toml`, owned by
a new `core/secret_store.py` service. It is the *only* place Weaver writes keys.

- **Location & scope.** `~/.weaver/secrets.toml` (overridable for tests). Holds a
  single `[keys]` table mapping an **env-var name → secret value**
  (e.g. `DEEPSEEK_API_KEY = "sk-..."`). Never `project.toml`, never
  `~/.weaver/config.toml`.
- **File permissions.** Written atomically (`tempfile` + `os.replace`) with mode
  `0o600` (owner read/write only) on POSIX; best-effort on Windows. The file is
  outside the repo tree, so it is never committed; `.gitignore` also lists it
  defensively.
- **Resolution & precedence.** At CLI and web startup, `apply_secrets_to_env()`
  loads the store and sets any key **not already present** in `os.environ`. A real
  shell env var therefore always wins over the file. Providers continue to read
  `os.environ` unchanged — they do not know the store exists.
- **Never logged, never rendered.** Values never appear in logs, SSE events, error
  messages, or HTML. The UI/CLI may show only env-var **names** and a
  present/absent flag (extends ADR `0017`'s "show presence, never value").
- **Provider config split.** `config_writer` (ADR `0018`) still writes only
  `type` / `model` / `base_url` / `api_key_env` to `project.toml`. The *name* of
  the env var (`api_key_env`) lives in `project.toml`; the *value* lives only in
  the secret store. Setting a key is a separate operation from setting provider
  config.

This supersedes the absolute "env-var only" wording of CLAUDE.md §4.2 and ADR
`0017`'s secret clause: keys may now also live in the dedicated secret store —
but never in project/global config, and never in logs or rendered output.

## Consequences

Easier: browser-only and custom-provider users can persist keys without shell
exports; each provider can name its own key env var; the env-only invariant for
`project.toml` / global config / logs is preserved exactly.

Harder: a second secret surface to protect — mitigated by `0o600`, atomic writes,
home-directory location, `.gitignore`, and the never-log/never-render rule. The
secret-scan hook keeps guarding the *repo*; the store lives outside it. Windows
cannot fully enforce `0o600`; documented as a known limitation (the file is still
user-profile scoped).
