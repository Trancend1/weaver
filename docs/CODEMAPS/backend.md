<!-- Generated: 2026-06-13 | Files scanned: src/weaver/api/app.py, src/weaver/api/routers/*.py, src/weaver/services/*.py, src/weaver/cli/main.py, remote origin/main:docs/{CLI_WORKFLOW,WEB_WORKFLOW,TRANSLATION_PIPELINE,MAINTENANCE}.md | Token estimate: ~950 -->
# Backend

## CLI Flow
`weaver doctor -> init/new -> inspect -> glossary review/conflicts -> translate --dry-run/sample -> preview -> translate -> edit -> validate -> export`.
- CLI source: `src/weaver/cli/main.py`; script entry: `weaver`.
- Existing commands/flags stay wire-compatible; new behavior must be additive only.
- CLI stays terminal-only and service-backed. No web imports, no SQLite access, no business logic.
- CLI export is legacy single-project Markdown/EPUB path (`services/export.py`); volume-aware EPUB/TXT/HTML/DOCX export is cockpit/API via `services/export_book.py`.

## CLI Command Reference
```bash
weaver doctor [--healthcheck]                                   # env check; --healthcheck adds live provider probe
weaver init <epub> [--from-template light-novel]                # creates .weaver/<name>/ + DB + glossary candidates
weaver new                                                      # interactive wizard (weaver[wizard] extra)
weaver inspect <project.toml>                                   # segment/candidate counts + cost estimate
weaver glossary review <project.toml>                           # [a]pprove [e]dit [r]eject [s]kip [f]ind [u]ndo [q]uit
weaver glossary conflicts <project.toml>                        # unresolved approved-term conflicts (exit 6)
weaver translate <project.toml> [--first-N N] [--dry-run] [--retry-failed] [--provider P --model M]
weaver preview <project.toml> [--chapter N]
weaver edit <project.toml> [--first-failed|--next-stale|--recent|<hex-id>]
weaver validate <project.toml> [--json] [--epub]                # 6 deterministic checks; exit 1 = critical
weaver export <project.toml> [--mode markdown|epub]             # legacy single-source path only
```
Aliases: `tx`=translate, `ins`=inspect, `gl`=glossary. `--debug` prints full traceback.
Limitations: import is EPUB-only via CLI; volume-aware EPUB/TXT/HTML/DOCX export and character DB/TM management require the web cockpit.

## Web Security Model
- Binds `127.0.0.1` only; desktop mode (`WEAVER_ENV=desktop`) rejects non-loopback binding (exit `64`).
- No authentication in browser mode; `WEAVER_SESSION_TOKEN` required in desktop env only.
- Sandboxed file browser: rooted at `--books-dir`; `..` traversal rejected; filtered to dirs + `.epub/.txt/.html`.
- Upload cap: `.epub` only, max 256 MiB (`MAX_UPLOAD_BYTES`); staged to `.weaver/_uploads/`, never executed.
- Secrets never appear in rendered HTML, SSE events, logs, or config responses.

## Routers (27 registered in `api/app.py:147-178`)
14 JSON routers (OpenAPI-visible) + 13 HTML/UI routers (`include_in_schema=False`).

| File | Prefix | Role |
| --- | --- | --- |
| `api/routers/system.py` | — | `/health`, `/version` |
| `api/routers/runtime.py` | — | `/healthz`, `/runtime/status` sidecar contract |
| `api/routers/projects.py` | `/projects` | list/tree/browse/import/create/inspect/preview |
| `api/routers/jobs.py` | `/projects` | job list/detail |
| `api/routers/translate.py` | `/projects` | chapter/segment translate + SSE + cancel |
| `api/routers/batch.py` | `/projects` | novel/volume/chapter batch + SSE |
| `api/routers/export.py` | `/projects` | novel/volume/chapter export + SSE |
| `api/routers/glossary.py` | `/projects` | term CRUD |
| `api/routers/glossary_review.py` | `/projects` | candidates, conflicts, diff, suggest, approve/edit/reject |
| `api/routers/candidates.py` | `/projects` | candidate review, character drafts |
| `api/routers/characters.py` | `/projects` | character CRUD |
| `api/routers/translation_memory.py` | `/projects` | TM overview + delete |
| `api/routers/config.py` | `/config` | provider/model + secrets; no key values returned |
| `api/routers/qa.py` | `/projects` | QA report (novel/volume/chapter) |
| `api/routers/ui*.py` | `/ui` | dashboard, workspace, jobs, hubs, explorer, review, QA, analytics, admin |

## HTML Cockpit Surface
```txt
/ui                                                 -> dashboard/global shell
/ui/empty, /ui/new, /ui/browse, /ui/epub-preview    -> project create/inspect
/ui/projects/{name}                                 -> project overview
/ui/projects/{name}/chapters/{chapter_id}           -> workspace editor
/ui/projects/{name}/volumes/{id}/structure          -> Content Explorer v2
/ui/projects/{name}/volumes/{id}/preview
/ui/projects/{name}/chapters/{id}/preview           -> reading preview
/ui/projects/{name}/volumes/{id}/review             -> review queue
/ui/queue, /ui/resources, /ui/providers, /ui/exports -> cross-project hubs
/ui/projects/{name}/analytics                       -> project analytics
/ui/projects/{name}/exports                         -> export history
/ui/projects/{name}/jobs[/{id}/detail]              -> job dashboard
/ui/projects/{name}/qa                              -> QA report
```

## Translation Pipeline
```txt
source import -> segment IDs/source_hash -> glossary candidates
approved glossary + characters + TM + prompt templates
  -> provider.translate/complete -> parser/validation
  -> translation rows + status/source_hash -> manual edit/retry/resume
  -> deterministic QA -> export preflight -> renderer + export_history
```
- Prompt design lives in `providers/prompts.py` and services. Glossary is injected before translation; skipping glossary review lowers output quality.
- Manual status survives `--retry-failed`; stale/source-hash mismatch prevents unsafe publish and falls back on export.
- QA is deterministic and read-only; no provider calls in QA or render/list/hub paths.

## Service Mapping
- Routers call services; services own workflow decisions and writes.
- `api/jobs.py` + `services/job_store.py` implement SQLite-backed in-process persistent jobs (ADR `010`). No external queue.
- Provider calls flow through `providers/registry.py`; prompts/parsers live in services (ADR `014`).
- Templates consume service DTOs; templates carry no business logic.
- `services/export_book.py` is canonical for UI/API export; `services/export.py` is CLI-only legacy.

## Error and Exit Discipline
- Domain errors derive from `src/weaver/errors.py` (`WeaverError` hierarchy).
- CLI/web boundaries convert errors to user-visible responses: what failed / likely cause / next command.
- Provider/export/QA/write failures are surfaced visibly; no silent fallback.
- Sidecar host inspects exit classes from the CLI process; desktop-mode host rejects non-localhost binding.

## Sprint R Additions (ADR `014`)
- `provider.complete(prompt, system, max_output_tokens) -> Completion` is domain-agnostic on `LLMProvider`.
- Four provider adapters implement it; `FakeProvider` returns deterministic output for CI/dev.
- `POST /projects/{name}/glossary/candidates/{id}/suggest` -> `services/glossary_suggestion.py` (prompt + strict JSON validation).
- Suggestions are ephemeral: fill editable target only; no DB persistence/migration.

## Verification Anchors
- Pytest mirrors source tree under `tests/`.
- Maintenance remote doc requires: ruff, pyright basic, pytest; no live LLMs in CI.
- Gate B1 audits: render/list/hub paths must not call provider, run QA, hash source files, or migrate DBs.
- Secret safety uses rendered-HTML + log grep tests.
