# Changelog

All notable changes to Weaver are recorded here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- `weaver export --help` now lists both `markdown` and `epub` modes (previously said only `markdown` was implemented).
- `weaver` CLI maps `ProviderUnavailable` to exit code `3`, `EpubReadError`/`EpubWriteError` to `4`, and `ConfigError` to `7`, matching [PRD_v2.md](docs/PRD_v2.md) §10 AC-9. Previously every non-segment, non-glossary error collapsed to exit `1`.
- `weaver glossary review` now shows up to two example sentences per candidate, matching AC-3.
- Malformed or BOM-prefixed `project.toml` files now produce a `ConfigError` with field-and-expected-type guidance instead of an unhandled `TOMLDecodeError`.
- `weaver translate` pre-flights the configured provider via `healthcheck()` and exits `3` cleanly when the provider is unreachable instead of failing each segment one-by-one.

### Added

- `weaver.core.config.load_project_config(path)` — single entry point for parsing `project.toml`; all eight previous `tomllib.loads` callsites now route through it.

## [0.1.0] — Unreleased

First public release. Implements the full MVP-0 command set defined in [PRD_v2.md](docs/PRD_v2.md) §6 and built per [BLUEPRINT_EXECUTION_PLAN.md](docs/BLUEPRINT_EXECUTION_PLAN.md) phases 0–9.

### Added

#### Commands

- `weaver init <input.epub>` — create project, segment EPUB into a `DocumentIR`, write SQLite WAL database, extract glossary candidates to TSV.
- `weaver inspect <project.toml> [--healthcheck]` — read-only status panel; `--healthcheck` probes the configured provider.
- `weaver glossary review <project.toml>` — interactive approve / edit / reject / skip / undo / quit over candidates, with example sentences.
- `weaver glossary edit <project.toml>` — open glossary TSV in `$EDITOR` and resync to SQLite.
- `weaver glossary conflicts <project.toml>` — print approved-term target conflicts.
- `weaver translate <project.toml> [--retry-failed]` — translate pending segments through the configured provider; resumable across crashes; `--retry-failed` retries only `failed` rows.
- `weaver edit <project.toml> <segment-id>` — override one translation through `$EDITOR`; sets segment status `manual`; survives `--retry-failed`.
- `weaver export <project.toml> --mode markdown [--translation-only]` — per-chapter Markdown files plus `review.md` index; failed/stale/missing segments rendered as visible markers.
- `weaver export <project.toml> --mode epub` — translated EPUB preserving spine order, metadata, asset references, and CSS.
- `weaver validate <project.toml> [--json]` — six deterministic QA checks (empty, untranslated Japanese, length ratio, glossary mismatch, failed, stale); critical findings exit `1`.

#### Providers

- `deepseek` — default cloud provider via OpenAI-compatible SDK; API key from `DEEPSEEK_API_KEY`.
- `gemini` — Gemini Flash via `google-generativeai`; free-tier 15 req/min, 1M tokens/day; API key from `GEMINI_API_KEY`.
- `ollama` — local HTTP provider; configurable base URL and model.
- `fake` — zero-dependency deterministic provider for development and CI.

#### Outputs

- Translated EPUB (`.translated.epub`) reopenable in `ebooklib` and EPUB 2 readers (added `EpubNcx` navigation item).
- Per-chapter Markdown review file plus top-level `review.md` index, with source/translation side-by-side or translation-only modes.
- `weaver.db` SQLite WAL database holds full run state; one segment translation = one transaction.
- Translation attempts persist with `input_tokens` / `output_tokens` columns (schema v2).

#### QA

- Six deterministic checks in `weaver.qa.checks` consumed by `weaver validate`.
- Severity scheme: empty / untranslated Japanese / failed = `critical`; length ratio / glossary mismatch / stale = `warning`.
- `--json` output uses `ensure_ascii=True` so legacy Windows codepage stdout cannot crash on Japanese characters.
- Rich table render is routed through `console.capture()` + a codepage-safe echo so Windows CP1252 degrades gracefully instead of raising `UnicodeEncodeError`.

#### Engineering

- Python 3.11+, `uv`-managed, `pyproject.toml` canonical.
- Typer CLI, Rich progress and tables, pydantic v2 (planned), `tomllib` configuration.
- SQLite WAL with versioned migrations (currently v2).
- Jinja2 prompt templates (`balanced_system.txt`, `balanced_user.jinja2`, `repair.txt`).
- JSON output parser with single repair-retry on malformed responses.
- Error hierarchy in `weaver.errors` (`WeaverError` → `ConfigError` / `EpubReadError` / `EpubWriteError` / `ProviderError` family / `GlossaryConflictError` / `ParserError` / `SegmentNotFoundError` / `DatabaseError`).
- CI: `ruff check`, `ruff format --check`, `pyright`, `pytest -m "not requires_ollama and not requires_cloud"`. 142 tests passing locally.

### Known Limitations

- Single fixture (`tests/fixtures/aozora_sample.epub`, 6 segments). 200-chapter scale benchmark deferred to Sprint 10c.
- No ADRs yet (`docs/decisions/` to be added in Sprint 10b).
- No MkDocs site (Sprint 10d).
- Performance budgets from [SECURITY_AND_PERFORMANCE.md](docs/SECURITY_AND_PERFORMANCE.md) not yet measured against the scale fixture.
- `project.toml` `pydantic` schema (PRD §9) not yet implemented; `load_project_config` enforces required tables but not field-level constraints.

[Unreleased]: https://github.com/Trancend1/weaver-translate/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Trancend1/weaver-translate/releases/tag/v0.1.0
