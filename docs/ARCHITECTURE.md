# Architecture

Compact map of the codebase and its boundaries. Deep pre-reset detail (full IR types, SQLite schema, provider interface prose) lives in [archive/SYSTEM_ARCHITECTURE.md](archive/SYSTEM_ARCHITECTURE.md); this doc is the current, maintained overview.

## Layers (ADR 002)

Binding layers. The split is the project's key asset for the Flask→FastAPI migration (ADR 004): only `api/` (FastAPI) and `web/` (legacy Flask) are framework-coupled; shared/core stays framework-agnostic.

```
src/weaver/
├── cli/          ← CLI surface (typer). Terminal I/O only.
├── api/          ← FastAPI cockpit (default `weaver serve`/`serve-api`). HTTP + JSON + Jinja2/HTMX UI.
├── web/          ← legacy Flask cockpit (`weaver serve-flask`, fallback). HTTP + templates only.
├── services/     ← shared/core: domain orchestration
├── storage/      ← shared/core: SQLite (WAL, no ORM)
├── core/         ← shared/core: value types, config, secret store
├── providers/    ← shared/core: LLM provider registry + adapters
├── readers/      ← shared/core: source → IR
├── renderers/    ← shared/core: IR + translations → output
├── qa/           ← shared/core: deterministic validation checks
├── tui/          ← read-only Textual dashboard (optional extra)
└── errors.py     ← WeaverError hierarchy
```

**Rule:** shared/core (`services`, `storage`, `core`, `providers`, `readers`, `renderers`, `qa`) must not import a web framework, hold `Request`/`Response`, render templates, or print CLI output. CLI and web are thin callers of services. State writes go through services only — neither surface touches SQLite directly.

## Module inventory (current)

**`services/`** — `project.py` (init/inspect), `translation.py` (resumable orchestrator), `workspace_translate.py` (chapter/selection translate + safe-retranslate), `batch_translate.py` (chapter/volume/novel batch planning + run), `translation_memory.py`, `characters.py`, `glossary.py`, `glossary_review.py`, `glossary_diff.py`, `glossary_terms.py`, `export.py` (markdown + epub), `manual_edit.py`, `preview.py`, `qa.py`, `doctor.py`, `epubcheck.py`, `wizard.py`, `config_writer.py` (atomic provider/model writer), `project_discovery.py` (cockpit project listing), `source_browser.py` (sandboxed source-file browsing + upload sanitize/store; shared by Flask `web/file_browser.py` re-export and the FastAPI create/browse endpoints), `provider_config.py` (redacted read + write of provider/model config + secret store orchestration; reuses `config_writer` + `core/secret_store`; never returns key values).

**`api/`** (FastAPI cockpit) — `app.py` (`create_api_app` factory), `jobs.py` (`JobRegistry` + `TranslationJob`/`BatchJob`/`ExportJob`, single-process thread workers + SSE), `schemas.py` (Pydantic boundary DTOs), routers `routers/{system,projects,translate,batch,export,glossary,glossary_review,characters,translation_memory,config}.py` (thin adapters over `services/*`). `routers/projects.py` covers list/tree/import plus **create-novel + sandboxed source browser** (`POST /projects/create`, `GET /projects/browse`, Sprint 10B); `routers/config.py` is the **provider/model + secret config** surface (`GET/PATCH /config`, `POST/DELETE /config/secrets/{env_name}`, Sprint 10C — key values never returned); `routers/glossary.py` is direct term CRUD and `routers/glossary_review.py` is the **candidate-review flow** (`…/glossary/candidates[/{id}/{approve,edit,reject}]`, `…/glossary/conflicts`, `…/glossary/diff`, Sprint 10D — approve/edit write the same `glossary_terms` rows; no second store).

**`storage/`** — `db.py`, `schema.sql`, `migrations.py`, `projects.py`, `volumes.py`, `segments.py` (incl. ordered chapter-id helpers for batch scope), `translations.py`, `glossary.py`, `characters.py`, `translation_memory.py`.

**`core/`** — `ir.py` (DocumentIR), `segment.py` (segment + deterministic IDs), `config.py` (project.toml), `global_config.py` (`~/.weaver/config.toml` precedence), `templates.py` (genre presets), `secret_store.py` (`~/.weaver/secrets.toml`).

**`providers/`** — `registry.py` (registry-driven types), `base.py`, `types.py`, `parser.py` (JSON parse + repair), `prompts.py`, and adapters `deepseek.py`, `gemini.py`, `ollama.py`, `fake.py`. `custom` (OpenAI-compatible) is registry-driven.

**`web/`** (legacy Flask, `weaver serve-flask` fallback) — `app.py` (factory, `127.0.0.1` bind), `job_manager.py` (single-job + SSE), route blueprints `routes_{projects,translate,new,config,export,glossary}.py`, `file_browser.py` (sandboxed), `templates/*.html`, vendored `static/htmx.min.js`. **Sprint 12B flip:** default `weaver serve` now runs the FastAPI cockpit (`api/`); Flask stays available as `serve-flask` (not removed/deprecated).

**`readers/`** — `epub.py`, `txt.py`, `html.py` (EPUB/TXT/HTML → IR) with `read_source` dispatch; shared `html_blocks.py` + `synthetic_document.py`.
**`renderers/`** — `epub.py` (EPUB write-back), `epub_synthesis.py` (synthesize EPUB for TXT/HTML-sourced volumes), `txt.py` + `html.py` (plain-text / HTML output), and `rendered_document.py` (shared `RenderChapter` + `block_to_html`). Volume-aware export orchestration lives in `services/export_book.py`; legacy Markdown/single-EPUB export in `services/export.py`. **Export surface split (web-first MVP):** the **FastAPI cockpit** (`api/routers/export.py` → `services/export_book.py`) is the volume-aware EPUB/TXT/HTML exporter for the Novel→Volume→Chapter model; the **CLI `export` command** (and Flask "Export") still drives the **legacy single-project exporter** (`services/export.py` → `export_epub_project`/`export_markdown_project`). The legacy path is intentionally not back-ported to the volume model — exporting full novels is a cockpit workflow. *DOCX output + export UI are MVP gaps (deferred).*

## Data / project flow

**Chapter/segment identity is volume-scoped.** Reader ids (`core/segment.compute_chapter_id`/`compute_segment_id`, blake2b) carry no volume component, so a freshly-read `DocumentIR` is passed through `core/ir.scope_document_to_volume` **once** at every read→persist boundary (init, import, CLI translate re-read, legacy + volume-aware export write-back). This keeps two volumes of identical source content from colliding/re-parenting on the `chapters.id`/`segments.id` upsert, and lets a re-read source join 1:1 with persisted rows. `sync_document_segments` stores ids as-given (scope exactly once). No schema change — purely the id assigned at sync time.

```
init:      EPUB → readers/epub → DocumentIR → scope_document_to_volume → storage (segments, glossary candidates) → .weaver/<name>/weaver.db
translate: pending segments → services/translation (context + glossary injection) → provider → storage (one segment = one txn)
review:    glossary candidates → services/glossary_review → approved terms (injected into prompts)
export:    storage → services/export_book → renderers/{epub | epub_synthesis | txt | html} → output/<target>/<per-volume>.<ext>   (legacy: services/export → markdown/single-epub)
qa:        storage → qa/checks → report (JSON, schema_version 1)
```

Per-project on-disk layout:

```
.weaver/<name>/
├── project.toml            # config: [provider] type/model/base_url/api_key_env, [translation], [glossary], [qa]
├── weaver.db               # SQLite WAL — source of truth for run state
├── glossary_candidates.tsv # pending review
├── glossary.tsv            # approved terms
├── logs/                   # rotated daily
└── output/{markdown,epub}/
```

## Not yet in the model (MVP gaps → ADR 003 / MVP_SCOPE.md)

- **DOCX export output + export UI** — EPUB/TXT/HTML output (`services/export_book.py`) + FastAPI export endpoints (`api/routers/export.py` + `ExportJob`, Sprint 8B) + Markdown exist; DOCX output and the export UI are not built (deferred).

Shipped since the reset baseline: Volume tier (schema v3), character database (`storage/characters.py`, schema v4), translation memory (`storage/translation_memory.py` + `services/translation_memory.py`, schema v5), the FastAPI two-column workspace with per-segment save + revision history, and **batch translation at chapter/volume/novel scope** (`services/batch_translate.py` + `api/routers/batch.py` + `BatchJob` in `api/jobs.py`, Sprint 7), and **volume-aware EPUB export** (`services/export_book.py` orchestrator + `renderers/epub_synthesis.py`, Sprint 8A).

## Dependencies

Core: typer, rich, pydantic v2, ebooklib, openai SDK, google-generativeai, jinja2, httpx, sqlite3/tomllib (stdlib). Optional extras: `web` (flask → FastAPI target), `tui` (textual), `wizard` (questionary). See [pyproject.toml](../pyproject.toml).
