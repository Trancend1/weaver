# Changelog

All notable changes to Weaver are recorded here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **DOCX export target** (Phase D) — the volume-aware cockpit exporter now supports
  `target="docx"` alongside EPUB/TXT/HTML. One `.docx` per volume under
  `output/docx/`, started/polled/cancelled through the same export job flow
  (`POST /projects/{name}/export/{novel|volumes/{id}|chapters/{id}}`, SSE/status
  unchanged) and selectable from the cockpit export dropdown.
  - New pure renderer `renderers/docx.py` (`render_docx`) — a **custom minimal
    OOXML (WordprocessingML) writer**. **No `python-docx`, no new dependency**
    (`weaver[web]` is sufficient); DOCX is always **synthesized** from the
    persisted chapter/segment content like TXT/HTML — there is **no write-back
    path**, so the source file is never re-read.
  - Same publishable rule as the other targets: latest `translated`/`manual`
    translation when the attempt's `source_hash` matches, else source fallback;
    manual edits preserved; translation history never exported; read-only (writes
    no translations, calls no provider).
  - Formatting baseline: document title, `Heading1` chapter headings, normal
    paragraphs, built-in `Quote` style for blockquotes, and a page break before
    chapters 2..N. No images, footnotes, advanced styling, or merged-omnibus DOCX.
- **Configurable QA thresholds** (Phase D) — the deterministic scope-level QA
  checks now read optional overrides from the existing `[qa]` table in
  `project.toml`: `fallback_heavy_ratio` (0.0–1.0), `min_segments` (≥1), and
  `repeated_min_chars` (≥1). Absent keys keep the Phase B defaults (`0.5` / `5` /
  `8`), so existing projects are unchanged. Values are validated (wrong type or
  out-of-range → `ConfigError`); foreign `[qa]` keys (the per-segment flags) are
  ignored. The same thresholds apply across the CLI/API/UI QA paths
  (`services/translation_qa.py`). New module `qa/thresholds.py`.
- **Combined ZIP bundle export** (Phase D) — an optional `bundle` flag packages a
  novel export's per-volume artifacts into one `output/<target>/bundle-<target>.zip`
  (any target, incl. DOCX). Off by default; the per-volume files are still written.
  Exposed as `ExportRequest.bundle` (API) and a "Bundle all volumes into one ZIP"
  checkbox in the cockpit export form; `ExportResult`/the job result now carry
  `bundle_path`. The bundle is skipped on cancel or when nothing was exported. New
  module `services/export_bundle.py`. (A *merged-omnibus* single EPUB is not built —
  a ZIP of per-volume files is the chosen, safe form.)

### Changed

- EPUB/TXT/HTML export behavior is unchanged. The export `target` validation set
  now includes `docx`; an unsupported `target` (e.g. `pdf`) still returns `422`.

## [0.7.0] - 2026-06-05

This release promotes the `v0.7.0-rc.1` release candidate to stable. It consolidates the
work that landed after the `0.1.0` alpha (intermediate `0.2.0`–`0.6.0` internal version
strings were never released or changelogged). The headline changes are a complete local
**web cockpit on FastAPI**, **UI/UX polish**, and a read-only **Translation QA** system
before export. The CLI remains fully functional.

### Added

#### Web Cockpit (MVP Sprints 1–13)

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

#### UI/UX Polish (Phase A)

- **Consistent shell** — shared header/nav, breadcrumb trail, `.flash-message`
  feedback bar, and descriptive `<title>` on every page.
- **Accessibility** — keyboard-navigable primary paths, visible focus ring,
  skip-nav link, `prefers-reduced-motion` respected, WCAG AA contrast on all
  status badges and action buttons.
- **Responsive at 390px** — all primary paths (project list, workspace, glossary,
  character DB, settings) usable at mobile viewport width.
- **Workspace UX** — improved two-column segment layout, inline save feedback,
  retranslate-mode labels clarified, segment status badges consistent.
- **Dashboard & project clarity** — project cards show volume/chapter/segment
  counts, status summary badges, and meaningful empty states.
- **Admin usability** — settings and secrets forms with validation feedback;
  glossary and character list pages gain search and pagination; provider selects
  use human-readable labels.

#### Translation QA (Phase B)

- **QA engine** (`services/translation_qa.py`) — read-only, deterministic,
  no provider/LLM calls, no mutation. Eleven rules across three scopes
  (novel / volume / chapter):
  - *Critical:* `failed_segment`, `empty_translation`, `untranslated_japanese`
  - *Warning:* `stale_segment`, `suspiciously_short`, `glossary_mismatch`,
    `untranslated_segment`, `character_name_missing`,
    `repeated_identical_translation`, `fallback_heavy_chapter`
  - *Info:* `mixed_status_chapter`
- **JSON QA API** — `GET /projects/{name}/qa`, `…/volumes/{id}/qa`,
  `…/chapters/{id}/qa`; returns `QAReport` with counts, issues, and
  per-chapter/per-volume roll-ups. Severity values: `info`, `warning`,
  `critical` (no `error` at the wire layer; ADR `008`).
- **QA report pages** (`/ui/projects/{name}/qa`, `…/volumes/{id}/qa`,
  `…/chapters/{id}/qa`) — badge (`clean` / `warnings` / `errors`), severity and
  category filters, per-segment links to the workspace, per-chapter links to
  chapter QA. No auto-fix; report only.
- **Advisory pre-export QA warning** (`GET …/export/preflight`) — shows QA
  summary before export; "Export anyway" always available; existing export
  route and source-fallback behaviour unchanged.
- ADR `008` documents the QA architecture and severity contract.

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

### Known Limitations / Deferred

- **DOCX export** is out of scope for this release — `target="docx"` returns
  HTTP 422 (handled, not a crash). Planned for Phase D.
- Combined EPUB/ZIP bundle export deferred to Phase D.
- Legacy CLI `weaver translate` / `weaver export` remain **single-volume**;
  multi-volume translate/export is the cockpit's job.
- QA threshold configuration (e.g. `fallback_heavy_chapter` ratio) is hardcoded
  as module constants; a config surface is planned for Phase D.
- Per-chapter QA badges on the project tree are deferred (QA only runs on
  explicit QA pages, not on every tree render).

## [0.1.0] - 2026-05-19

First public alpha release. Implements the full MVP-0 command set.

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
- Repeatable benchmark runner in `bench/run_performance_budgets.py`; benchmark results in git history.
- Repeatable AC-1 through AC-9 release gate in `bench/run_acceptance_gate.py`; acceptance results in git history.
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

[Unreleased]: https://github.com/Trancend1/weaver/compare/v0.7.0...HEAD
[0.7.0]: https://github.com/Trancend1/weaver/compare/v0.1.0...v0.7.0
[0.1.0]: https://github.com/Trancend1/weaver/releases/tag/v0.1.0
