<!-- Generated: 2026-06-13 | Files scanned: src/weaver/**/*.py, desktop/src/*.rs, pyproject.toml, remote origin/main:docs/{ARCHITECTURE,DECISIONS,SIDECAR_CONTRACT,INSTALL_DESKTOP}.md | Token estimate: ~950 -->
# Architecture

## Shape
Single Python package: Typer CLI + FastAPI/Jinja2/HTMX web cockpit + per-project SQLite + optional Tauri desktop host. Local/offline-first JP→EN translation workbench; not SaaS, not SPA.

```txt
CLI (`weaver`) / FastAPI cockpit (`weaver serve`) / Tauri host (`desktop/`)
  -> services/*       domain orchestration; all writes live here
  -> storage/*        SQLite WAL, schema/migrations, no ORM
  -> readers/*        EPUB/TXT/HTML -> DocumentIR and EPUB structure inspection
  -> renderers/*      DB/IR -> EPUB/TXT/HTML/DOCX artifacts
  -> providers/*      LLM transport adapters + registry (`translate`, `complete`)
  -> qa/*             deterministic checks; no provider calls
  -> core/*           config, IR/value types, secrets, templates
api/* is the only FastAPI/Jinja2/HTMX-coupled layer.
```

## Entry Points
- `pyproject.toml` script: `weaver = weaver.cli.main:app`.
- `src/weaver/cli/main.py` -> CLI commands (`doctor/init/new/inspect/translate/edit/validate/export/serve/...`).
- `src/weaver/api/app.py:create_api_app()` -> FastAPI app, 27 registered routers, `/` redirects to `/ui`.
- `desktop/src/main.rs` + `desktop/src/launch_config.rs` -> Tauri 2 host launches `weaver serve` sidecar.

## Active ADR Boundary Map
- `001`: docs cleanup / active ADR reset.
- `002`: CLI / web / shared-core split; services own state transitions.
- `004`, `007`: FastAPI + server-rendered Jinja2/HTMX only; Flask removed; no SPA/build.
- `008`, `013`: QA reuses deterministic checks; severity contract is `info|warning|critical`.
- `009`: HTMX-first + Tauri-sidecar-ready pivot; supersedes npm wrapper plan.
- `010`: SQLite-backed in-process persistent jobs; no Celery/Redis/RQ/external queue.
- `012`: image preview read-only security gate; OCR remains contract-only.
- `014`: provider `complete()` is domain-agnostic; glossary suggestion is service-owned and explicit POST only.

## Hard Boundaries
- Shared/core (`services`, `storage`, `core`, `providers`, `readers`, `renderers`, `qa`) must not import web frameworks, hold Request/Response, render templates, or print CLI output.
- CLI/web routers are thin adapters; they do not own SQLite writes.
- One project DB is source of truth. No global mutable cross-project store without ADR.
- Cross-project workspace reads use `services/workspace_index.py` pattern; read paths must not migrate DBs, reset jobs, hash source files, call providers, or run QA.
- Provider prompts/parsers live in services; provider adapters stay transport-only.

## Current Service Clusters
- Project/source: `project.py`, `project_discovery.py`, `project_tree.py`, `project_overview.py`, `import_source.py`, `source_browser.py`, `source_intake.py`, `epub_reparse.py`.
- Workspace/edit/translate: `chapter_workspace.py`, `workspace_context.py`, `segment_listing.py`, `workspace_edit.py`, `workspace_translate.py`, `translation.py`, `batch_translate.py`, `manual_edit.py`, `segment_history.py`, `segment_review.py`.
- Glossary/characters/TM: `glossary.py`, `glossary_review.py`, `glossary_terms.py`, `glossary_diff.py`, `glossary_suggestion.py`, `characters.py`, `character_draft.py`, `translation_memory.py`, `candidate_generation.py`, `candidate_apply.py`.
- QA/export: `qa.py`, `translation_qa.py`, `export_book.py` (canonical UI/API exporter), `export.py` (CLI legacy), `export_bundle.py`, `export_gate.py`, `export_ledger.py`.
- Runtime/hubs: `workspace_index.py`, `workspace_queue.py`, `workspace_resources.py`, `workspace_providers.py`, `workspace_exports.py`, `project_analytics.py`, `job_store.py`, `runtime_env.py`, `app_paths.py`, `logging_setup.py`, `provider_config.py`, `config_writer.py`, `doctor.py`, `wizard.py`.
- EPUB/image: `epub_structure_preview.py`, `epub_snapshot.py`, `epub_export_fidelity.py`, `image_preview.py`, `ocr_contract.py`.

## Data Flow
```txt
import: source file -> readers -> DocumentIR -> volume-scoped ids -> storage schema v12
translate: pending segments -> context/glossary/characters/TM -> provider -> translations (1 segment = 1 txn)
review: candidates/drafts -> approve/edit/reject -> glossary_terms / characters
QA: storage -> deterministic qa modules -> reports/UI badges/preflight (read-only)
export: storage -> export_book/renderers -> output artifacts + export_history ledger
workspace hubs: project DBs -> read-only workspace_index/services -> HTML hubs
desktop: Tauri host -> spawn sidecar -> /healthz -> /ui with X-Weaver-Session
```

## Sidecar Contract
`weaver serve` on `127.0.0.1`, random port allowed, WebView opens `/ui`, health poll `/healthz`, runtime status `/runtime/status`, session header `X-Weaver-Session`. Desktop env uses `WEAVER_ENV=desktop`, `WEAVER_DATA_DIR`, `WEAVER_BOOKS_DIR`, `WEAVER_SESSION_TOKEN`, `WEAVER_DOCS=false`. Current contract correction: env var `WEAVER_ENV`, not stale `--env desktop`; console tail is `sidecar.console.log`.

## Phase F EPUB Package Inspection
Parallel read-only inspection path — does not replace the production import/export path:
- `readers/epub.read_epub()` remains the import/translation/export reader (→ `DocumentIR`).
- `readers/epub.parse_epub_structure()` → `core/epub_structure.ParsedEpub`: OPF metadata, manifest/resources, spine, NAV/NCX, image metadata, validation issues, preservation context.
- `readers/epub_validation.py` owns deterministic non-fatal EPUB structure validation.
- `services/epub_structure_preview.py` serializes `ParsedEpub` for read-only JSON + UI preview; no SQLite writes, no image bytes.
- `services/epub_export_fidelity.py` compares source/export EPUB structures (passed checks, warnings, critical gaps, missing assets, counts).
- OCR/vision: contract-only via `services/ocr_contract.py`; future implementation requires separate ADR + dependency/credential approval.

## Export Path Boundary
`services/export_book.py` is canonical for every UI/cockpit and FastAPI export surface (per-volume EPUB/TXT/HTML/DOCX + optional ZIP bundle via `services/export_bundle.py`). `services/export.py` is CLI-only legacy (Markdown / single-EPUB for `weaver export`); not wired into any web/UI route. New export work targets `export_book`; do not add UI callers to `services/export.py`.

## Reality Corrections From Remote Docs
- Remote CLI docs say EPUB-only import and Markdown/EPUB-only export; current code includes TXT/HTML readers and EPUB/TXT/HTML/DOCX renderers, while CLI export remains legacy.
- Remote sidecar doc shows `--env desktop`; current CLAUDE + desktop contract uses `WEAVER_ENV` env.
- Remote docs are historical context; current source + CLAUDE.md are authority where they disagree.
