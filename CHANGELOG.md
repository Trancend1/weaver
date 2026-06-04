# Changelog

All notable changes to Weaver are recorded here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

MVP "Web Cockpit Foundation" release candidate. This entry consolidates the work
that landed after the `0.1.0` alpha (intermediate `0.2.0`–`0.6.0` internal version
strings were never released or changelogged). The headline change is a complete
local **web cockpit on FastAPI** plus the retirement of the original Flask
cockpit. The CLI remains fully functional.

### Added

- **FastAPI web cockpit** (`weaver serve`) — local, single-user, loopback-only
  (`127.0.0.1`, no auth) browser UI built with server-rendered Jinja2 + vendored
  HTMX (no Node, no build, no SPA; ADR `004`/`007`). Ships behind the optional
  `weaver[web]` extra.
- **Headless API** (`weaver serve-api`) — the same FastAPI app without a browser,
  exposing the typed JSON API.
- **Novel → Volume → Chapter project model** with multi-format import (EPUB / TXT
  / HTML); `weaver import` adds a source as a new volume.
- **Translation workspace** — two-column JP/EN read, per-segment edit/save
  (status → `manual`), and revision history.
- **Provider & AI translation** in the cockpit — configurable provider/model,
  per-request overrides, chapter/selection translate, and **safe retranslate**
  modes (`skip_existing`, `retranslate_non_manual`, `force_selected`; manual
  edits are protected).
- **Glossary & character database** — project-scoped CRUD plus glossary candidate
  review (approve/edit/reject, conflicts, coverage diff); both injected into the
  translation prompt.
- **Translation memory** — source→target store with lookup-before-AI reuse and
  AI fallback on miss; manual edits are the memory source of truth.
- **Batch translation** — chapter / volume / novel scope with live progress,
  per-unit status, cooperative cancel, and SSE streaming (single-process thread
  worker; no external queue).
- **Export** — volume-aware **EPUB / TXT / HTML** artifacts from the cockpit
  (`POST /projects/{name}/export/{novel|volumes/{id}|chapters/{id}}`).
- **Secret store** — API keys in `~/.weaver/secrets.toml` (mode `0o600`); shell
  env wins; keys are never written to config, logged, or rendered.

### Changed

- **Web framework is FastAPI** (ADR `004`). `weaver serve` defaults to the
  FastAPI cockpit UI; `weaver serve-api` runs it headless.
- Shared/core stays framework-agnostic; Pydantic and web types are confined to
  the `api/` boundary (ADR `002`).

### Removed

- **Legacy Flask cockpit** (BREAKING for the web surface): `weaver serve-flask`,
  `src/weaver/web/**`, Flask-only tests, and the `flask` dependency were removed
  in Sprint 13B after a parity audit, a default flip, and a real-workflow soak.
  FastAPI is now the only web cockpit.

### Fixed

- Import volume-id collision: chapter/segment ids are now scoped per volume, so
  importing content that collides with an existing volume no longer re-parents
  its chapters.
- DeepSeek provider healthcheck JSON-mode handling.

### Known Limitations / Deferred (not RC blockers)

- **DOCX export** is out of MVP — `target="docx"` returns HTTP 422 (handled, not
  a crash).
- **Cockpit UI is functional parity, not visual polish** (ADR `005`); empty
  states, layout, and visual hierarchy are deferred.
- Combined EPUB/ZIP bundle export deferred.
- Legacy CLI `weaver translate` / `weaver export` remain **single-volume**;
  multi-volume translate/export is the cockpit's job.

## [0.1.0] - 2026-05-19

First public alpha release. Implements the full MVP-0 command set defined in [PRD_v2.md](docs/PRD_v2.md) section 6 and built per [BLUEPRINT_EXECUTION_PLAN.md](docs/BLUEPRINT_EXECUTION_PLAN.md) phases 0-10.

### Added

#### Commands

- `weaver init <input.epub>` creates a project, segments EPUB into a `DocumentIR`, writes a SQLite WAL database, and extracts glossary candidates to TSV.
- `weaver inspect <project.toml> [--healthcheck]` prints a read-only status panel; `--healthcheck` probes the configured provider.
- `weaver glossary review <project.toml>` provides interactive approve / edit / reject / skip / undo / quit review with example sentences.
- `weaver glossary edit <project.toml>` opens glossary TSV in `$EDITOR` and resyncs to SQLite.
- `weaver glossary conflicts <project.toml>` prints approved-term target conflicts.
- `weaver translate <project.toml> [--retry-failed]` translates pending segments through the configured provider; `--retry-failed` retries only failed rows.
- `weaver edit <project.toml> <segment-id>` overrides one translation through `$EDITOR`, sets segment status `manual`, and survives `--retry-failed`.
- `weaver export <project.toml> --mode markdown [--translation-only]` writes per-chapter Markdown files plus a `review.md` index.
- `weaver export <project.toml> --mode epub` writes a translated EPUB preserving spine order, metadata, asset references, and CSS.
- `weaver validate <project.toml> [--json]` runs six deterministic QA checks; critical findings exit `1`.

#### Providers

- `deepseek` cloud provider via OpenAI-compatible SDK; API key from `DEEPSEEK_API_KEY`.
- `gemini` provider via `google-generativeai`; API key from `GEMINI_API_KEY`.
- `ollama` local HTTP provider with configurable base URL and model.
- `fake` zero-dependency deterministic provider for development and CI.

#### Outputs

- Translated EPUB (`.translated.epub`) reopenable in `ebooklib` and EPUB 2 readers.
- Per-chapter Markdown review file plus top-level `review.md` index.
- `weaver.db` SQLite WAL database with schema v2 and token-usage columns.
- Six deterministic QA checks in `weaver.qa.checks`.

#### Release Hardening

- `weaver.core.config.load_project_config(path)` centralizes `project.toml` parsing and turns TOML errors into `ConfigError`.
- 200-chapter / 10,000-block synthetic EPUB fixture in `tests/fixtures/synthetic_200_chapter.epub`.
- Repeatable benchmark runner in `bench/run_performance_budgets.py`; latest results recorded in [docs/benchmarks.md](docs/benchmarks.md).
- Repeatable AC-1 through AC-9 release gate in `bench/run_acceptance_gate.py`; latest results recorded in [docs/release_acceptance.md](docs/release_acceptance.md).
- MkDocs site config (`mkdocs.yml`) and GitHub Pages workflow (`.github/workflows/pages.yml`).
- Five ADRs in [docs/decisions/](docs/decisions/).

### Fixed

- `weaver export --help` lists both `markdown` and `epub` modes.
- CLI error mapping now returns exit codes `3`, `4`, `5`, `6`, and `7` for provider, EPUB, segment, glossary conflict, and config failures.
- `weaver glossary review` shows up to two example sentences per candidate.
- `weaver translate` pre-flights the configured provider via `healthcheck()` and exits `3` cleanly when the provider is unreachable.
- EPUB export rebuilds malformed source TOC entries when `ebooklib` reopens nav links without serializable UIDs.
- JSON validation output uses `ensure_ascii=True`; Rich validation table render is routed through codepage-safe output on Windows.

### Known Limitations

- The hands-on acceptance pass uses the bundled public-domain `aozora_sample.epub` fixture (2 chapters / 6 segments); scale budgets use the separate 200-chapter synthetic fixture.
- `project.toml` pydantic schema validation from PRD section 9 is not yet implemented; `load_project_config` enforces required tables but not every field-level constraint.

[Unreleased]: https://github.com/Trancend1/weaver/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Trancend1/weaver/releases/tag/v0.1.0
