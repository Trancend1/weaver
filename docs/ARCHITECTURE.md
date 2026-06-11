# Architecture

Compact map of the codebase and its boundaries. Deep pre-reset detail (full IR types, SQLite schema, provider interface prose) lives in git history; this doc is the current, maintained overview.

## Layers (ADR 002)

Binding layers. The split is the project's key asset (ADR 004): only `api/` (FastAPI) is framework-coupled; shared/core stays framework-agnostic. (The legacy Flask cockpit `web/` was removed in Sprint 13B; the FastAPI cockpit is now the only web surface.)

```
src/weaver/
├── cli/          ← CLI surface (typer). Terminal I/O only.
├── api/          ← FastAPI cockpit (`weaver serve`/`serve-api`). HTTP + JSON + Jinja2/HTMX UI.
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

**`services/`** — `project.py` (init/inspect), `translation.py` (resumable orchestrator), `workspace_translate.py` (chapter/selection translate + safe-retranslate), `batch_translate.py` (chapter/volume/novel batch planning + run), `translation_memory.py`, `characters.py`, `glossary.py`, `glossary_review.py`, `glossary_diff.py`, `glossary_terms.py`, `export.py` (markdown + epub), `manual_edit.py`, `preview.py`, `qa.py` (legacy `weaver validate`), `translation_qa.py` (read-only scope-aware QA reports — novel/volume/chapter, ADR 008), `doctor.py`, `epubcheck.py`, `wizard.py`, `config_writer.py` (atomic provider/model writer), `project_discovery.py` (cockpit project listing), `source_browser.py` (sandboxed source-file browsing + upload sanitize/store; consumed by the FastAPI create/browse endpoints), `provider_config.py` (redacted read + write of provider/model config + secret store orchestration; reuses `config_writer` + `core/secret_store`; never returns key values).

**`api/`** (FastAPI cockpit) — `app.py` (`create_api_app` factory), `jobs.py` (`JobRegistry` + `TranslationJob`/`BatchJob`/`ExportJob`, single-process thread workers + SSE), `schemas.py` (Pydantic boundary DTOs), routers `routers/{system,projects,translate,batch,export,glossary,glossary_review,characters,translation_memory,config,qa}.py` (thin adapters over `services/*`) plus presentation-only UI routers `routers/{ui,ui_admin,ui_qa}.py` (Jinja2 + HTMX, ADR 007). `routers/qa.py` is the read-only QA report API (`GET …/qa`, `…/volumes/{id}/qa`, `…/chapters/{id}/qa`, Phase B); `routers/ui_qa.py` renders the QA report pages + the advisory pre-export preflight (`…/export/preflight`) — both over `services/translation_qa.py`, no QA logic in the web layer. `routers/projects.py` covers list/tree/import plus **create-novel + sandboxed source browser** (`POST /projects/create`, `GET /projects/browse`, Sprint 10B); `routers/config.py` is the **provider/model + secret config** surface (`GET/PATCH /config`, `POST/DELETE /config/secrets/{env_name}`, Sprint 10C — key values never returned); `routers/glossary.py` is direct term CRUD and `routers/glossary_review.py` is the **candidate-review flow** (`…/glossary/candidates[/{id}/{approve,edit,reject}]`, `…/glossary/conflicts`, `…/glossary/diff`, Sprint 10D — approve/edit write the same `glossary_terms` rows; no second store).

**`storage/`** — `db.py`, `schema.sql`, `migrations.py`, `projects.py`, `volumes.py`, `segments.py` (incl. ordered chapter-id helpers for batch scope), `translations.py`, `glossary.py`, `characters.py`, `translation_memory.py`.

**`core/`** — `ir.py` (DocumentIR), `segment.py` (segment + deterministic IDs), `config.py` (project.toml), `global_config.py` (`~/.weaver/config.toml` precedence), `templates.py` (genre presets), `secret_store.py` (`~/.weaver/secrets.toml`).

**`providers/`** — `registry.py` (registry-driven types), `base.py`, `types.py`, `parser.py` (JSON parse + repair), `prompts.py`, and adapters `deepseek.py`, `gemini.py`, `ollama.py`, `fake.py`. `custom` (OpenAI-compatible) is registry-driven.

**`readers/`** — `epub.py`, `txt.py`, `html.py` (EPUB/TXT/HTML → IR) with `read_source` dispatch; shared `html_blocks.py` + `synthetic_document.py`.
**`renderers/`** — `epub.py` (EPUB write-back), `epub_synthesis.py` (synthesize EPUB for TXT/HTML-sourced volumes), `txt.py` + `html.py` (plain-text / HTML output), `docx.py` (Word output via a custom minimal OOXML writer — no `python-docx`, no new dependency; synthesized from the DB, no write-back), and `rendered_document.py` (shared `RenderChapter` + `block_to_html`). Volume-aware export orchestration lives in `services/export_book.py`; legacy Markdown/single-EPUB export in `services/export.py`. **Export surface split (web-first MVP):** the **FastAPI cockpit** (`api/routers/export.py` → `services/export_book.py`) is the volume-aware EPUB/TXT/HTML/DOCX exporter for the Novel→Volume→Chapter model; the **CLI `export` command** still drives the **legacy single-project exporter** (`services/export.py` → `export_epub_project`/`export_markdown_project`). The legacy path is intentionally not back-ported to the volume model — exporting full novels is a cockpit workflow. An optional **ZIP bundle** of the per-volume artifacts is written by `services/export_bundle.py` when requested; a *merged-omnibus* single EPUB is deferred.

## Data / project flow

**Chapter/segment identity is volume-scoped.** Reader ids (`core/segment.compute_chapter_id`/`compute_segment_id`, blake2b) carry no volume component, so a freshly-read `DocumentIR` is passed through `core/ir.scope_document_to_volume` **once** at every read→persist boundary (init, import, CLI translate re-read, legacy + volume-aware export write-back). This keeps two volumes of identical source content from colliding/re-parenting on the `chapters.id`/`segments.id` upsert, and lets a re-read source join 1:1 with persisted rows. `sync_document_segments` stores ids as-given (scope exactly once). No schema change — purely the id assigned at sync time.

```
init:      EPUB → readers/epub → DocumentIR → scope_document_to_volume → storage (segments, glossary candidates) → .weaver/<name>/weaver.db
translate: pending segments → services/translation (context + glossary injection) → provider → storage (one segment = one txn)
review:    glossary candidates → services/glossary_review → approved terms (injected into prompts)
export:    storage → services/export_book → renderers/{epub | epub_synthesis | txt | html | docx} → output/<target>/<per-volume>.<ext>   (+ optional services/export_bundle → output/<target>/bundle-<target>.zip; legacy: services/export → markdown/single-epub)
qa (CLI):  storage → qa/checks → services/qa → report (JSON, schema_version 1; `weaver validate`)
qa (web):  storage → qa/{checks,consistency_checks,scope_checks} → services/translation_qa → QAReport (novel/volume/chapter; read-only, schema_version 2) → api/routers/{qa,ui_qa}
```

**Export path boundary (QF-15 / WV-012, Q12):** `services/export_book.py` is the **canonical** exporter for every UI/cockpit and FastAPI export surface (per-volume EPUB/TXT/HTML/DOCX via `renderers/*`, plus `services/export_bundle.py` for ZIP bundles). `services/export.py` is a **CLI-only legacy** path (markdown / single-EPUB) retained for the `weaver export` command; it is **not** wired into any web/UI route and is a candidate for removal post-Sprint Q. New export work targets `export_book`; do not add UI callers to `services/export.py`.

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

## Not yet in the model (MVP gaps → ADR 003; live gap list: [.docs/audit/ISSUE_BACKLOG.md](../.docs/audit/ISSUE_BACKLOG.md))

- **Merged-omnibus single EPUB for novel scope** — per-volume EPUB/TXT/HTML/DOCX export (`services/export_book.py`) + a combined **ZIP bundle** (`services/export_bundle.py`) + FastAPI export endpoints + the export UI all ship; merging a novel's volumes into one EPUB is deferred.

Shipped since the reset baseline: Volume tier (schema v3), character database (`storage/characters.py`, schema v4), translation memory (`storage/translation_memory.py` + `services/translation_memory.py`, schema v5), the FastAPI two-column workspace with per-segment save + revision history, **batch translation at chapter/volume/novel scope** (`services/batch_translate.py` + `api/routers/batch.py` + `BatchJob` in `api/jobs.py`, Sprint 7), **volume-aware EPUB export** (`services/export_book.py` orchestrator + `renderers/epub_synthesis.py`, Sprint 8A), and **DOCX export output** (`renderers/docx.py`, custom minimal OOXML writer, Phase D).

## Dependencies

Core: typer, rich, pydantic v2, ebooklib, openai SDK, google-generativeai, jinja2, httpx, sqlite3/tomllib (stdlib). Optional extras: `web` (FastAPI + uvicorn), `tui` (textual), `wizard` (questionary). See [pyproject.toml](../pyproject.toml).

## Phase F EPUB package inspection

Phase F adds a parallel EPUB package-inspection path without replacing the
production import/export path:

- `readers/epub.read_epub()` remains the import, translation, and export source
  reader and still returns `DocumentIR`.
- `readers/epub.parse_epub_structure()` returns `ParsedEpub` from
  `core/epub_structure.py` for OPF metadata, manifest/resources, spine,
  NAV/NCX, image metadata, validation issues, and preservation context.
- `readers/epub_validation.py` owns deterministic non-fatal EPUB structure
  validation used by the parser contract.
- `services/epub_structure_preview.py` serializes `ParsedEpub` for read-only JSON
  and UI preview surfaces; it does not write SQLite or expose image bytes.
- `services/epub_export_fidelity.py` compares source/export EPUB structures and
  reports passed checks, warnings, critical gaps, missing assets, and counts.
- OCR/vision extraction is not implemented; future OCR must be adapter-based and
  separately approved if it adds dependencies, providers, credentials, or image
  output behavior.

## Cockpit UI conventions

The server-rendered cockpit (`api/`) follows a small set of fixed conventions (absorbed from the former `DESIGN_NOTES.md`). Forward UI work (Sprint P) must hold these:

- **Stack constraints:** Jinja2 + HTMX, no SPA/client framework/build step; no web fonts (system UI stack only); no backend logic in templates (routes call `services/*`, templates only present); motion ≤140 ms with `prefers-reduced-motion` honored.
- **Design tokens — single source:** `api/static/app.css` `:root` (color/type-scale/spacing/radius/shadow/layout/z-index). No magic numbers in templates.
- **Layout modes (URL-dispatched in `api/ui_context.py`):** `global` (`/ui`, `/ui/new`, `/ui/config` — topbar only), `project` (project/glossary/characters/memory/quality — topbar + 264px sidebar), `workspace` (chapter editor — topbar + 56px icon rail). (The audit's [PAGE_LAYOUT_BLUEPRINT](../.docs/audit/PAGE_LAYOUT_BLUEPRINT.md) targets a unified global Workspace sidebar in Sprint P+.)
- **Do not rename/remove these HTMX hooks** (swaps + UI tests depend on them): `#tree`, `#ws-grid`, `#job-panel`, `#export-panel`, `#browser`, `#selected_source`, `#source_path`, `#qa-badge-status`, `#qa-issues`, `id="seg-{id}"`, and the `qa-badge-vol-*` / `qa-badge-ch-*` slots.
- **States & a11y:** hover / `:active` / `:focus-visible` / `:disabled` defined; empty (`_empty_state.html`), error (`.error role="alert"`), loading (HTMX indicator + native `<progress>`); no toasts/`alert()`; semantic HTML; `aria-current` on active nav; breadcrumb via `_page_header.html` on every page incl. 404/error.
- **UI copy/structure is pinned by tests:** `tests/unit/api/test_ui_shell.py`, `test_ui_layout.py`, `test_ui_qa.py`, `test_ui_delete.py`. Update them when intentionally changing user-facing strings or layout markers.
