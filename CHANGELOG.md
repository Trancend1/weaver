# Changelog

All notable changes to Weaver are recorded here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

> Note: the entries below predate v0.7.1. The `0.7.1` (desktop installer) and
> `0.7.2` (connection-first routing + enforcement loop) releases were tagged
> without a changelog cut, so this section was never closed — see ADR 016–019
> and git history for those releases. Left as-is rather than reconstructed from
> memory; the next release should retire it.

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
- **Opt-in QA tree badges** (Phase D) — the project tree can now show per-volume and
  per-chapter QA badges without ever running QA on page render. A "Load QA badges"
  button GETs `/ui/projects/{name}/qa/tree-badges`, which runs the novel QA **once**
  and returns out-of-band (`hx-swap-oob`) badge spans HTMX injects into the tree
  slots. The tree render stays cheap (Gate B1 preserved); badges are explicit.
- **Provider config hardening** (Phase D) — numeric `[provider]` settings are now
  validated when the provider is built (new `providers/config_values.py`): a bad
  `temperature` / `timeout_seconds` / `top_p` / `fail_rate` / `seed` (wrong type or
  out of range) raises a clear `ConfigError` instead of a raw `ValueError`. Runtime
  errors gained an **invalid-model** case for DeepSeek/custom and Gemini (misspelled
  or unavailable `[provider] model` → actionable message). No provider behavior
  change beyond validation/error mapping; **API key values never leak** into errors,
  logs, or status messages (a regression test guards this).
- **Delete a project** (Phase E) — the project page has a "Delete project" action and
  the CLI gains `weaver delete <project.toml> [--yes]`. Both call the new
  `services/project.delete_project`, which removes the project's `.weaver/<name>`
  directory (translations, history, glossary, exports) behind a path-safety guard;
  the **original imported source file is never touched**. The web route returns an
  `HX-Redirect` to the dashboard; the CLI confirms unless `--yes`.

### Changed

- EPUB/TXT/HTML export behavior is unchanged. The export `target` validation set
  now includes `docx`; an unsupported `target` (e.g. `pdf`) still returns `422`.
- **Cockpit design system & UI overhaul** (Phase E) — presentation-only refactor of
  the server-rendered UI: a full CSS custom-property token layer in `app.css`
  (`:root`), three URL-dispatched layout modes (`api/ui_context.py`: global /
  project / workspace), a left-aligned topbar with brand mark + favicon (replacing
  the floating right nav), a widened 264px sidebar with inline line icons
  (`partials/_icons.html`), dashboard **project cards** and per-volume progress
  cards (replacing the dense table), QA **stat tiles**, a segmented sub-nav, and a
  standardized `_page_header` breadcrumb on every page including 404 / error. No
  backend, schema, or HTMX-contract change; all DOM hooks preserved.
- **Terminology** (Phase E) — user-facing "QA" wording is now "Quality" across the
  cockpit (nav, report page, badges button, pre-export check, advisories). The `/qa`
  routes and `qa-*` element IDs are unchanged.
- **Docs** — the Cal.com design study (`DESIGN.md`) and hybrid-layout guide
  (`DESIGN_GUIDE.md`) are distilled into a single concise `docs/DESIGN_NOTES.md`;
  completed-phase plans (B, D) and point-in-time reports (RC1, MVP stabilization)
  were retired to git history.

### Fixed

- **External browser launch** (Phase E) — `weaver serve` now opens the URL in the
  OS-default browser instead of an editor's embedded "Simple Browser". The launcher
  (`cli/open_browser.py`) temporarily clears an editor-injected `$BROWSER` so the
  real default browser is used; the server still binds `127.0.0.1` only.

## [0.7.3] - 2026-07-27

Performance & reliability release. Closes the v0.7.2 post-release audit ledger
(A1–A8) plus the measured audit findings N1–N8. Schema moves to **v14**
(forward-only, idempotent); no CLI or route contract breaks.

> **Known gap — no live provider validation.** This release was verified against
> the deterministic `fake` provider, the full offline test suite (1733 passed),
> the performance budgets, and the AC-1…AC-9 acceptance gate — but **not against
> a live LLM endpoint**. The gated Gemini and Ollama integration tests ship with
> the release and have never been run. The `gemini-2.5-flash` shim default and
> the `…/v1beta/openai` base_url are therefore unproven in production, and the
> concurrency speed-up figure comes from simulated latency, not a network. The
> maintainer accepted this risk knowingly. `[translation] max_concurrent`
> defaults to `1`, so the least-tested path is off unless you opt in, and any
> endpoint or model can be overridden per connection without a new release.

### Added

- **Opt-in bounded translate concurrency** (ADR 020) — `[translation] max_concurrent`
  (1–4, **default 1** = previous sequential behavior bit-for-bit), exposed as
  `weaver translate --max-concurrent` and a 1–4 select on the cockpit chapter
  translate form. New `services/segment_runner.py` owns the worker window; each
  worker owns and closes its own SQLite connection. Measured **2.78× at 3 workers**
  on the latency-simulating FakeProvider bench (budget ≥ 2.4×).
- **Enforcement provenance** persisted on `translations` (migration v14) — violations
  JSON where `NULL` means "not evaluated" (distinct from `[]` = "evaluated clean"),
  plus `repair_attempted` / `repair_outcome` and dedicated repair token columns.
  Surfaced through the CLI, job result JSON, attempt history, and `/translations`.
- **Input-safety guards** — the `MAX_UPLOAD_BYTES` cap (256 MiB) now applies to
  `/projects/epub-preview`; a declared-uncompressed ceiling (`MAX_UNCOMPRESSED_BYTES`,
  1 GiB) is checked from the zip central directory *before* parsing; malformed
  chapter XHTML degrades per chapter via `DocumentIR.read_issues` instead of failing
  the whole import.
- **Bench coverage** — rolling-window flat-cost probe, cockpit render budgets, and a
  concurrency scaling budget in `bench/run_performance_budgets.py`.
- **Gated live provider tests** — `tests/integration/providers/test_gemini_live.py`
  (`requires_cloud`) and `test_ollama_live.py` (first-ever `requires_ollama` usage).
  Both drive the shipped legacy-shim defaults, so a pass proves the real endpoint
  rather than a test-local constant. Not yet run against live endpoints.
- **Version drift guard** — `tests/unit/test_version.py` and
  `desktop/scripts/check-version.ps1` now compare `src/weaver/__init__.py` against
  `pyproject.toml` (the single source of truth) and `desktop/tauri.conf.json`.

### Changed

- SQLite `PRAGMA synchronous = NORMAL` plus read-only pragmas on read paths
  (commit cost was 1.325 ms at `FULL` vs 0.031 ms at `NORMAL`, with ≥ 2 commits
  per segment).
- `transaction()` now opens `BEGIN IMMEDIATE`. Load-bearing under concurrency: a
  `DEFERRED` transaction whose first statement reads takes a SHARED lock and races
  to upgrade, and SQLite reports that race as instant `SQLITE_BUSY` **without**
  consulting `busy_timeout` (measured 121/160 failures before, 0/160 after).
- The O(n²) rolling-window CTE is scoped to the chapter at **both** call sites
  (including `list_export_segment_states`). Per-segment cost is now flat across the
  10k-segment fixture (**1.96× → 0.74×** last-100 vs first-100).
- `list_connections` and the secret store parse each TOML file once per render;
  project discovery and queue polling dedupe under the existing 5 s cache
  (≤ 1 DB open per project per render).
- Token estimation is CJK-aware (~1 token/char for Japanese instead of `chars // 4`,
  which undercounted ~3×); `MAX_CONTEXT_TOKENS` recalibrated 600 → **1000** honest
  tokens so the typical 5-pair context window is preserved.
- `[provider] max_retries` is now explicit on the OpenAI client (default 2), making
  the SDK's hidden transport retries a visible, per-connection number.
- Enforcement **detection** no longer requires `enforce_repair` — verdicts are
  recorded even when automatic repair is off.
- `weaver inspect` resolves the provider through routing instead of the legacy
  `[provider]` block.
- The `gemini` legacy-shim default model is `gemini-2.5-flash`; `gemini-1.5-flash`
  was retired upstream and would 404 on first call.
- Glossary matching hoists casefold work, batches writes with `executemany`, and
  gains `idx_glossary_candidates_project` (migration v13).

### Fixed

- **`weaver --version` and `GET /version` reported `0.7.0`** through both the v0.7.1
  and v0.7.2 releases — `src/weaver/__init__.py` was never bumped and no test or
  release check compared it to `pyproject.toml`.
- **The performance bench silently measured nothing** (audit N1) — the harness
  string-replaced `type = "deepseek"`, but v0.7.2 `weaver init` writes
  `[provider] type = ""`, so the translate/export budgets no-oped. Both harnesses
  now write the fake provider block explicitly. Every pre-M1 baseline claim was
  unfounded.
- Corrupt `connections.toml` / `secrets.toml` is no longer silently destroyed. A
  tolerant read returning `{}` paired with an unguarded rewrite meant the next save
  rebuilt from the empty view; writes now go through
  `core/toml_write.guard_unparseable_toml` (move-aside backup + a `ConfigError`
  naming the backup file).
- A dead primary connection with a healthy fallback completes the run instead of
  aborting pre-flight (`translation.preflight_provider_chain`); the warning is
  carried on the plan, result, summary, CLI echo, and job terminal events.
- Hand-serialized TOML values escape control characters — four separate incomplete
  private `_escape` copies were folded into one shared `escape_toml_string`.
- The legacy provider brand (`deepseek`/`gemini`/`ollama`) is recorded in attempt
  history again instead of being flattened to `openai_chat`.
- Token accounting reconciles by construction: the attempt row stores the primary
  call's usage, repair spend lives in its own columns, and `sum(rows) == summary`
  exactly (test-pinned). A JSON-parse repair round-trip now sums usage across both
  calls and is counted in the run summary.
- The dead `[translation] max_retries` key is no longer written by `weaver init`.

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
