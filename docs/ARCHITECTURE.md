# Architecture

Compact map of the codebase and its boundaries. Deep pre-reset detail (full IR types, SQLite schema, provider interface prose) lives in [archive/SYSTEM_ARCHITECTURE.md](archive/SYSTEM_ARCHITECTURE.md); this doc is the current, maintained overview.

## Layers (ADR 002)

Three binding layers. The split is the project's key asset for the Flask→FastAPI migration (ADR 004): only `web/` is framework-coupled.

```
src/weaver/
├── cli/          ← CLI surface (typer). Terminal I/O only.
├── web/          ← Web cockpit (Flask today; FastAPI target). HTTP + templates only.
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

**`services/`** — `project.py` (init/inspect), `translation.py` (resumable orchestrator), `glossary.py`, `glossary_review.py`, `glossary_diff.py`, `export.py` (markdown + epub), `manual_edit.py`, `preview.py`, `qa.py`, `doctor.py`, `epubcheck.py`, `wizard.py`, `config_writer.py` (atomic provider/model writer), `project_discovery.py` (cockpit project listing).

**`storage/`** — `db.py`, `schema.sql`, `migrations.py`, `projects.py`, `segments.py`, `translations.py`, `glossary.py`.

**`core/`** — `ir.py` (DocumentIR), `segment.py` (segment + deterministic IDs), `config.py` (project.toml), `global_config.py` (`~/.weaver/config.toml` precedence), `templates.py` (genre presets), `secret_store.py` (`~/.weaver/secrets.toml`).

**`providers/`** — `registry.py` (registry-driven types), `base.py`, `types.py`, `parser.py` (JSON parse + repair), `prompts.py`, and adapters `deepseek.py`, `gemini.py`, `ollama.py`, `fake.py`. `custom` (OpenAI-compatible) is registry-driven.

**`web/`** (Flask) — `app.py` (factory, `127.0.0.1` bind), `job_manager.py` (single-job + SSE), route blueprints `routes_{projects,translate,new,config,export,glossary}.py`, `file_browser.py` (sandboxed), `templates/*.html`, vendored `static/htmx.min.js`.

**`readers/`** — `epub.py` **only** (EPUB → IR). *TXT/HTML readers are MVP gaps — not yet built.*
**`renderers/`** — `epub.py` **only**. Markdown export lives in `services/export.py`. *TXT/HTML/DOCX renderers are MVP gaps.*

## Data / project flow

```
init:      EPUB → readers/epub → DocumentIR → storage (segments, glossary candidates) → .weaver/<name>/weaver.db
translate: pending segments → services/translation (context + glossary injection) → provider → storage (one segment = one txn)
review:    glossary candidates → services/glossary_review → approved terms (injected into prompts)
export:    storage → services/export (markdown) / renderers/epub (epub) → output/
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

- **Batch at volume/novel scope** — translate is per-project resumable; web job manager is single-job.

Shipped since the reset baseline: Volume tier (schema v3), character database (`storage/characters.py`, schema v4), translation memory (`storage/translation_memory.py` + `services/translation_memory.py`, schema v5), and the FastAPI two-column workspace with per-segment save + revision history.

## Dependencies

Core: typer, rich, pydantic v2, ebooklib, openai SDK, google-generativeai, jinja2, httpx, sqlite3/tomllib (stdlib). Optional extras: `web` (flask → FastAPI target), `tui` (textual), `wizard` (questionary). See [pyproject.toml](../pyproject.toml).
