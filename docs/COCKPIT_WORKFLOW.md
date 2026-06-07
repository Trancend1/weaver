# Cockpit Workflow

The web cockpit is a **local, single-user** browser UI for the same translator workflow the CLI drives. It is the **primary development focus** going forward.

> **Stack status (Sprint 13B, 2026-06-04).** `weaver serve` runs the **FastAPI cockpit** (Jinja2 + vendored HTMX UI + typed JSON API, ASGI/Uvicorn) per [ADR 004](decisions/004-fastapi-cockpit-technical-direction.md) — the only web cockpit. `weaver serve-api` runs the same FastAPI app headless (no browser). The legacy Flask cockpit was **removed in Sprint 13B** (after the 12B default flip + a real-workflow soak proved the FastAPI default stable; `weaver serve-flask` and `src/weaver/web/**` no longer exist). Decommission-readiness + soak evidence are in git history.

## Purpose

Kill the CLI's daily friction points: long project paths, provider/model switching, weak progress monitoring, multi-step flow, glossary review. Everything below works in the browser with **no path typing**.

## Run it
```bash
pip install 'weaver[web]'
weaver serve                          # FastAPI cockpit, http://127.0.0.1:8765, opens a browser
weaver serve --port 9000 --no-browser
weaver serve --books-dir ~/novels     # discover projects under another root
weaver serve-api                      # same FastAPI app, headless (no browser), :8000
```

## Security model (carried forward from archived ADR 0017 → ADR 004)
- **Binds `127.0.0.1` only.** Never `0.0.0.0`. No remote access, no LAN exposure.
- **No authentication.** Single-user loopback tool; auth would add friction with no threat to mitigate.
- **Sandboxed file browser.** Listing rooted at `--books-dir`; `..` traversal rejected; filtered to dirs + `.epub`.
- **Upload limits.** `.epub` only, size-capped; staged to `.weaver/_uploads/`, never executed.
- **Secrets never exposed.** API keys read from env / secret store only; never written to project/global config, never rendered, never in an SSE event. UI shows env-var **name + present/absent**, never the value.

## Key pages / actions
| Page | Does |
|---|---|
| Dashboard | Lists every discovered project under `--books-dir` (no path typing). |
| Cockpit (per project) | Read-only status mirror of `weaver inspect`; entry to actions below. |
| New project | Browse the sandboxed books dir **or** upload an EPUB; pick provider + template; run `init`. |
| EPUB structure preview | Read-only uploaded/sandboxed EPUB preview for metadata, resource counts, reading order, navigation, image roles, short untranslated chapter excerpts, and validation issues with a safe/warnings/errors readiness badge. Linked from the source browser ("preview" on `.epub` entries). |
| Provider/model config | Write project `[provider]` or global default from a dropdown; API key writes to the secret store only. |
| Translate | Start (first-N / retry-failed), live **SSE** progress, cooperative **stop** (committed segments stay). |
| Glossary review | Paginated approve / edit / reject of pending candidates; approved-term conflicts + per-chapter coverage diff shown read-only. |
| Export | Trigger **volume-aware** EPUB/TXT/HTML/DOCX export (one artifact per volume) — see the FastAPI export surface below. (The CLI `export` command still drives the legacy single-project exporter, `services/export.py`.) |

## Request/UI flow
```
browser → FastAPI UI router (api/routers/ui*.py)
        → services/* (project_discovery, chapter_workspace, translation, glossary_review, export, provider_config)
        → storage/* (SQLite)
long jobs: api/routers/{translate,batch,export} → api/jobs.py (JobRegistry, single-process thread workers) → SSE stream → htmx-updated panel
```
HTMX provides liveness (progress, partial updates) without a JS build step.

## EPUB structure preview (Phase F)

Phase F adds a read-only preview surface for inspecting EPUB package structure
before deeper import/export integration:

| Method | Path | Service | Notes |
|---|---|---|---|
| POST | `/projects/epub-preview` | `epub_structure_preview.preview_epub_structure` | Accepts an uploaded EPUB or sandboxed `source_path`; returns metadata, counts, resources, spine, navigation, images, chapter excerpts, validation issues (flat and grouped by scope), and readiness flags. No SQLite writes, no image bytes, no OCR, no translation. |
| GET | `/ui/epub-preview?source_path=...` | `epub_structure_preview.preview_epub_structure` | Minimal server-rendered preview page for the same read-only structure data. |

The preview parser uses `parse_epub_structure()` and does not replace
`read_epub()` in the import, translation, or export workflow.

## FastAPI browser UI (Sprint 11 — `src/weaver/api/`, ADR `007`)

The FastAPI cockpit (`weaver serve` since Sprint 12B; also `weaver serve-api`
headless) serves a server-rendered browser UI **alongside** its JSON
API. Stack: **Jinja2 + HTMX, no build, no SPA** (ADR `007`); HTMX is vendored at
`api/static/htmx.min.js` (pinned 1.9.12, no CDN). The UI is **presentation only**
— `routers/ui.py` is a thin adapter over the same services the JSON routers use
(no business logic, no storage access). All HTML lives under **`/ui`**; `GET /`
redirects there; the JSON API surface is unchanged and UI routes are excluded
from the OpenAPI schema.

**Sprint 12B default flip → Sprint 13B decommission:** 12B flipped `weaver serve`
to the FastAPI cockpit (Flask kept temporarily as `serve-flask`); after a real
multi-format/multi-volume workflow soak proved the FastAPI default stable,
**Sprint 13B removed Flask entirely** — `serve-flask`, `src/weaver/web/**`, the
Flask-only tests, and the `flask` dependency are gone. `weaver serve` (UI) and
`weaver serve-api` (headless) are the only web entry points. (The Flask→FastAPI
parity audits + soak results are in git history.)

**Sprint 11A — shell (shipped):** dashboard/home (project list + global provider
default), project view (Novel→Volume→Chapter tree), navigation, and the read-screen
state primitives (loading/empty/error/404).

**Sprint 11B-1 — create/import + browser (shipped):** new-project form (upload **or**
browsed source + optional provider/template), sandboxed source browser (HTMX
fragment), and volume import on the project view with **HTMX tree refresh** on
success. UI create/import reuse the same services as the JSON endpoints via
`services/source_intake.resolve_intake_source` (no logic in the UI layer).

**Sprint 11B-2 — workspace read/save/history (shipped):** the project tree links each
chapter to a two-column JP/EN workspace; per-segment save (status → `manual`) swaps
the refreshed segment row via HTMX; per-segment translation history loads on demand.
Reuses `services/chapter_workspace`, `services/workspace_edit.save_segment_translation`,
`services/segment_history` (no logic in the UI).

**Sprint 11B-3 — translate/retranslate + jobs + export (shipped):** the workspace has a
**Translate** button and a **Retranslate** mode select (`skip_existing` ·
`retranslate_non_manual` · `force_selected`, the last only when explicitly chosen); the
project page has an **Export** control (EPUB/TXT/HTML/DOCX). Both start a background job via the
same JSON-router start helpers (`translate._start_job`, `export._start_export`) over the
shared `JobRegistry` + services — and render a **self-polling HTMX panel** (`hx-trigger="load
delay:1s"`) that shows live progress, a **Cancel** button, and the terminal result (translate
counts / export artifact paths). Terminal panels drop the poll trigger.

**Sprint 11C — consistency/admin (shipped, `routers/ui_admin.py`):** glossary term CRUD +
candidate review (approve/edit/reject, conflicts, coverage diff), character DB CRUD,
translation-memory read/delete, and provider/model + secret config. Each mutation re-renders
its HTMX fragment. Reuses `glossary_terms`, `glossary_review`, `glossary_diff`, `characters`,
`translation_memory`, `provider_config` (no logic in UI). **API-key values are accepted only by
the secret-set form and are never rendered back** (presence/names only). Provider/secret config
lives at `/ui/config` (global + per-project scope); project pages link to glossary/characters/memory.

| Method | Path | Renders |
|---|---|---|
| GET/POST | `/ui/projects/{name}/glossary` · `…/glossary/terms[/{source}/update\|delete]` | glossary page · `_glossary_terms` fragment |
| GET/POST | `…/glossary/candidates[/{id}/{approve\|edit\|reject}]` · `…/glossary/diff` | `_glossary_candidates` · `_glossary_diff` fragments |
| GET/POST | `/ui/projects/{name}/characters[/{jp_name}/update\|delete]` | characters page · `_characters` fragment |
| GET/POST | `/ui/projects/{name}/memory` · `…/memory/{source_hash}/delete` | memory page · `_memory` fragment |
| GET/POST | `/ui/config` · `/ui/config/secrets[/{env_name}/delete]` | config page · `_config_form` / `_secrets` fragments (no key value) |

| Method | Path | Renders | Notes |
|---|---|---|---|
| GET | `/` | → 307 `/ui` | Redirect to the UI home. |
| GET | `/ui` | `dashboard.html` | Project list + global provider/model default; empty state + "New novel" link. |
| GET | `/ui/projects/{name}` | `project.html` | Tree (`partials/_tree.html`, chapters link to the workspace) + import panel + browser; unknown → 404 HTML, error → 422 HTML. |
| GET | `/ui/projects/{name}/chapters/{chapter_id}` | `workspace.html` | Two-column JP/EN workspace (`partials/_segment.html` per segment); unknown chapter → 404 HTML. |
| POST | `/ui/projects/{name}/chapters/{chapter_id}/segments/{segment_id}` | `partials/_segment.html` | Save translation (status → `manual`); returns the refreshed segment row (HTMX `outerHTML`). Empty text → row re-rendered with an error; unknown → 404. |
| GET | `/ui/projects/{name}/chapters/{chapter_id}/segments/{segment_id}/history` | `partials/_history.html` | Full attempt history for a segment (HTMX fragment). |
| POST | `/ui/projects/{name}/chapters/{chapter_id}/translate` | `partials/_job.html` | Start a translate job (skip already-translated/manual); returns a self-polling job panel. |
| POST | `/ui/projects/{name}/chapters/{chapter_id}/retranslate` | `partials/_job.html` | Start a retranslate job under `mode` (skip_existing / retranslate_non_manual / force_selected). |
| GET | `/ui/projects/{name}/jobs/{job_id}` | `partials/_job.html` | Poll translate-job progress (self-refresh until terminal). |
| POST | `/ui/projects/{name}/jobs/{job_id}/cancel` | `partials/_job.html` | Cooperative cancel; renders current state. |
| POST | `/ui/projects/{name}/export` | `partials/_export_job.html` | Start a novel-scope export job for `target` ∈ {epub,txt,html,docx}. |
| GET | `/ui/projects/{name}/export/jobs/{job_id}` | `partials/_export_job.html` | Poll export-job progress; terminal shows per-volume artifact paths. |
| POST | `/ui/projects/{name}/export/jobs/{job_id}/cancel` | `partials/_export_job.html` | Cooperative cancel; renders current state. |
| GET | `/ui/new` | `new.html` | Create form + source browser. |
| POST | `/ui/new` | → 303 to project view | Create from upload/browsed source (reuses `resolve_intake_source` + `initialize_project`); duplicate/no-source/bad-source → form re-render with error (400). |
| GET | `/ui/browse?dir=` | `partials/_browse.html` | Sandboxed listing fragment (dirs navigate via HTMX; files set the hidden `source_path`). Escape/missing → inline error. |
| POST | `/ui/projects/{name}/import` | `partials/_tree.html` | Import a volume (reuses `resolve_intake_source` + `import_volume`); returns the refreshed `#tree`. Errors → `partials/_import_error.html` with `HX-Retarget: #import_error` so the tree is preserved. |
| GET | `/static/*` | vendored assets | `htmx.min.js` (1.9.12), `app.css`. |

## FastAPI project management API (Sprint 2C + 10B — `src/weaver/api/`)

Project discovery, creation, import, and a sandboxed source browser. The browser
and create endpoints (Sprint 10B) let you *create / select* projects entirely in
the browser. All paths are sandboxed to the cockpit
`base_dir` (ADR `0017`) — `..` traversal and absolute paths are rejected.

| Method | Path | Service | Notes |
|---|---|---|---|
| GET | `/projects` | `discover_projects` | List discovered projects + summaries. |
| GET | `/projects/{name}/tree` | `project_tree` | Novel → Volume → Chapter tree. |
| GET | `/projects/browse?dir=<rel>` | `source_browser.list_directory` | Sandboxed listing: sub-dirs first, then importable sources (`.epub`/`.txt`/`.html`/`.htm`). `dir` is relative to `base_dir`; `""` is root. Escape/missing → `422`. |
| POST | `/projects/create` | `initialize_project` (+ `source_browser`) | Create a novel from an uploaded `file` **or** a browsed `source_path` (multipart; upload preferred). Optional `provider`/`template`. Name derives from the source stem. → `201` `{project_name, chapter_count, segment_count, glossary_candidate_count}`. No source → `422`; duplicate name → `409`; bad source/provider → `422`. **Sourceless creation is unsupported** (the source defines the project name + initial volume). |
| POST | `/projects/{name}/import` | `import_volume` | Import another source as a new volume (upload only). → `201`. |

## FastAPI glossary candidate-review API (Sprint 10D — `src/weaver/api/`)

Exposes the existing candidate-review flow (the same one the CLI `glossary review`
uses) over JSON. Thin adapter over `services/glossary_review`
+ `services/glossary_diff`. **Approve/edit write into the project `glossary_terms`
table** — the same rows direct glossary CRUD reads and `build_context` injects.
There is **no second glossary store**; direct CRUD (`routers/glossary.py`) is
unchanged. The candidate routes (`…/glossary/candidates/…`, `…/glossary/conflicts`,
`…/glossary/diff`) do not shadow the CRUD term routes (`…/glossary`,
`…/glossary/{source}`).

| Method | Path | Service | Notes |
|---|---|---|---|
| GET | `/projects/{name}/glossary/candidates?offset=&limit=&find=` | `glossary_review.list_pending` | Page of pending candidates + queue `counts` (`pending`/`approved`/`rejected`) + `total_pending`. `find` filters by source substring. |
| POST | `/projects/{name}/glossary/candidates/{candidate_id}/approve` | `act_on_candidate` | Approve → writes the term into `glossary_terms`. → `{candidate_id, action, counts}`. Unknown id → `404`. |
| POST | `/projects/{name}/glossary/candidates/{candidate_id}/edit` | `act_on_candidate` | Body `{target, notes?}`: edit then approve. Empty target → `422`; unknown id → `404`. |
| POST | `/projects/{name}/glossary/candidates/{candidate_id}/reject` | `act_on_candidate` | Reject (no term written). Unknown id → `404`. |
| GET | `/projects/{name}/glossary/conflicts` | `list_project_glossary_conflicts` | Approved-term conflicts: `[{source, targets[]}]` (sources mapped to >1 target). |
| GET | `/projects/{name}/glossary/diff?a=&b=` | `glossary_diff` | Approved-term coverage diff between chapters `a` and `b` (1-indexed): `only_in_a`/`only_in_b`/`in_both`. Out-of-range/missing → `422`. |

## FastAPI provider/secret config API (Sprint 10C — `src/weaver/api/`)

Persists provider/model config and API-key secrets from the API. Thin adapter
over `services/provider_config.py`,
which reuses `services/config_writer` (provider/model write) + `core/secret_store`
(secrets). **API-key values are accepted only by `POST /config/secrets/{env_name}`
and are never returned by any endpoint** — responses carry key *presence* (a bool)
and stored secret *names* only (CLAUDE.md §4.2, ADR `0017`/`0020`).

| Method | Path | Service | Notes |
|---|---|---|---|
| GET | `/config` | `provider_config.read_config` | Redacted view: global defaults + stored secret **names**. `?project=<name>` also returns that project's `[provider]` block (`provider_type`/`model`/`base_url`/`api_key_env`) + `api_key_set` bool. Unknown project → `404`. **No key value.** |
| PATCH | `/config` | `provider_config.write_config` | Persist provider/model. Body: `scope` (`project`\|`global`), `project` (required if `scope=project`), `provider_type`/`model`/`base_url`/`api_key_env`. **No key value accepted here** (only the env-var *name*). Global scope writes `[defaults]` (provider+model only). Unknown provider/scope, missing project → `422`. |
| POST | `/config/secrets/{env_name}` | `provider_config.store_secret` | Store one API-key secret under env-var name `{env_name}` in `~/.weaver/secrets.toml` (`0o600`). Body `{value}`. → `201` `{name, is_set: true}`; value never echoed. Invalid name / empty value → `422`. |
| DELETE | `/config/secrets/{env_name}` | `provider_config.remove_secret` | Remove the secret. → `{name, is_set: false}`; unknown → `404`. |

> Secrets are keyed by **env-var name** (e.g. `DEEPSEEK_API_KEY`), not by provider
> — this is the existing secret-store abstraction (`core/secret_store`), shared
> with the CLI `secrets` group and the cockpit `/config` route. The provider config's
> `api_key_env` field names which env var holds its key.

## FastAPI workspace API (Sprint 3 — `src/weaver/api/`)

The FastAPI cockpit (`weaver serve-api`) exposes the translation workspace as JSON. Routers are thin adapters; all logic lives in `services/*` and writes go through `storage/*` + `transaction()`.

| Method | Path | Service | Notes |
|---|---|---|---|
| GET | `/projects/{name}/chapters/{chapter_id}/workspace` | `chapter_workspace` | Source segments + **latest** translation per segment (read-only). |
| PATCH | `/projects/{name}/chapters/{chapter_id}/segments/{segment_id}/translation` | `save_segment_translation` | Save one segment. Preserves source; one new attempt; status → `manual`; returns `saved_at`. |
| GET | `/projects/{name}/chapters/{chapter_id}/segments/{segment_id}/translations` | `segment_translation_history` | Full revision history: all attempts oldest-first + `current_translation`. |

Errors: unknown project / chapter / segment (or segment not in the named chapter) → `404`; empty save text → `422`.

### Save-state & autosave contract (UI debounce deferred)

Revision history needs no separate table — every save is a row in `translations` keyed by `(segment_id, attempt)`; the **latest attempt is the current translation**. The save endpoint is the contract a future autosave UI builds on:

- **Idempotent shape, append semantics.** Each successful PATCH appends a new attempt (monotonic `attempt`); prior attempts are immutable history. The save response (`segment_id`, `status`, `translated_text`, `saved_at`) is what the client renders for the dirty → saving → saved transition.
- **Client states (planned, not yet built):** `dirty` (local edit pending) → `saving` (PATCH in flight) → `saved` (200, store `saved_at`) → `error` (non-2xx, keep buffer, surface `detail`). The UI owns debounce/throttle timing; the server stays stateless per request.
- **No coalescing server-side.** Three rapid saves = three attempts. If the UI wants to collapse keystrokes into one revision, it debounces before calling PATCH — the server does not merge.
- **Latest-only read stays cheap.** The workspace endpoint never returns the attempt list; clients fetch `/translations` on demand (e.g. opening a revision panel).

Debounce timing, conflict handling, and the revision panel UI are later work; the API surface above is stable for them to target.

## FastAPI AI translation API (Sprint 4A/4B — `src/weaver/api/`)

AI translation runs as a **background job** on a single worker thread; the request returns immediately with a job id. Logic lives in `services/workspace_translate.py` (`prepare_chapter_translation` → `run_translation`); the in-memory `api/jobs.py` `JobRegistry` owns job lifecycle.

| Method | Path | Notes |
|---|---|---|
| POST | `/projects/{name}/chapters/{chapter_id}/translate` | Translate the chapter's untranslated segments. Body: optional `provider`/`model` override. → `202` `{job_id, status, chapter_id, mode}`. |
| POST | `/projects/{name}/chapters/{chapter_id}/translate-segments` | Translate a chosen `segment_ids` list (each must belong to the chapter). Same body extras; → `202`. |
| POST | `/projects/{name}/chapters/{chapter_id}/retranslate` | Re-translate the chapter under an explicit `mode` (see below). Body adds `mode`; → `202`. |
| POST | `/projects/{name}/chapters/{chapter_id}/retranslate-segments` | Re-translate a chosen `segment_ids` list under `mode`. → `202`. |
| GET | `/projects/{name}/jobs/{job_id}` | Poll: `status` (`running`/`done`/`failed`/`cancelled`), live `progress` (`current`/`total`/`translated`/`failed`), `result` (once finished), `error`. |
| POST | `/projects/{name}/jobs/{job_id}/cancel` | Cooperative cancel — worker stops after the current segment; committed segments stay. Idempotent; returns current status. |
| GET | `/projects/{name}/jobs/{job_id}/events` | Optional SSE stream: `progress` events per segment, then one terminal event (`done`/`cancelled`/`error`). Single-consumer. |

- **Provider/model selection** is per-request (`{"type": provider, "model": model}` merged onto `[provider]`); omit to use the project default. Keys resolve from env / secret store (applied at API startup), never from config.
- **Skip already-translated (plain translate).** `/translate` and `/translate-segments` only touch `pending`/`failed`/`stale`; `translated`/`manual` are left untouched (`skipped` count reports them).
- **Retranslate modes (4C).** `/retranslate*` take a `mode`:
  - `skip_existing` (default) — same as plain translate; never overwrites.
  - `retranslate_non_manual` — also re-translates `translated` segments; **`manual` is protected** (skipped).
  - `force_selected` — translates every target, **including `manual`** (the only way to overwrite a hand edit).
  Invalid `mode` → `422`. Every retranslate **appends** a new `translations` attempt; prior attempts (including the overwritten manual text) remain as immutable history — overwrite is non-destructive.
- **No external queue.** `JobRegistry` is a single-process thread worker by design; no Celery/Redis/RQ/etc.
- Errors: unknown project / chapter / segment → `404`; empty selection → `422`; unhealthy provider → `502`; unknown job → `404`.

## FastAPI batch translation API (Sprint 7 — chapter/volume/novel jobs)

Batch translation runs the per-chapter pipeline across many chapters as **one background job** with aggregate progress. Logic lives in `services/batch_translate.py` (`prepare_batch_translation` → `run_batch_translation`, reusing `run_translation`); the `api/jobs.py` `JobRegistry` owns a separate `BatchJob` lifecycle (`submit_batch`/`get_batch`). The per-chapter `/translate*` + `/retranslate*` endpoints are **untouched**.

| Method | Path | Notes |
|---|---|---|
| POST | `/projects/{name}/batch/novel` | Translate every chapter in the novel (reading order). Body: optional `mode`, `provider`, `model`. → `202` `{job_id, status, scope, scope_id, mode}`. |
| POST | `/projects/{name}/batch/volumes/{volume_id}` | Translate every chapter in one volume. → `202`. |
| POST | `/projects/{name}/batch/chapters/{chapter_id}` | Batch scoped to one chapter (uniform batch-progress shape). → `202`. |
| GET | `/projects/{name}/batch/jobs/{job_id}` | Poll: `status`, aggregate `progress` (scope/mode/provider/model + `chapters_total/done`, `segments_total/done`, `translated`/`reused_from_memory`/`skipped`/`failed`, `current_chapter_id`), `result` (once done), `error`. |
| POST | `/projects/{name}/batch/jobs/{job_id}/cancel` | Cooperative cancel — worker stops after the current segment, before the next chapter; committed segments stay. Idempotent. |
| GET | `/projects/{name}/batch/jobs/{job_id}/events` | SSE: `progress` per snapshot, then one terminal event (`done`/`cancelled`/`error`). Single-consumer. |

- **Validate once.** Provider is built + healthchecked a **single time** at prepare (before the `202`), and glossary/characters load once — not per chapter.
- **Mode** defaults to `skip_existing`; `retranslate_non_manual` / `force_selected` apply only when sent. **Manual protection + TM semantics are unchanged** (inherited from the chapter pipeline).
- **Result** carries per-chapter outcomes (with `input_tokens`/`output_tokens`), aggregate counts, and timing (`started_at`/`finished_at`/`duration_seconds`). Invariant: `translated` includes `reused_from_memory`; `translated + failed == segments_total`; `skipped` is separate.
- **Empty scope** (novel/volume with no chapters) → `202` + a job that finishes immediately with zero counts (not an error).
- **Distinct id namespace.** Batch jobs live under `/batch/jobs/`; a batch `job_id` is **not** resolvable via the chapter `/jobs/{job_id}` route (and vice-versa).
- **No external queue.** Single-process thread worker, same as the chapter jobs.
- Errors: unknown project / volume / chapter → `404`; invalid `mode` → `422`; unhealthy provider → `502`; unknown job → `404`.

## FastAPI export API (Sprint 8B — novel/volume/chapter EPUB jobs)

Export renders translated content to a **per-volume artifact** (EPUB / TXT / HTML / DOCX) as **one background job** with per-volume progress. Logic lives in `services/export_book.py` (`prepare_export` → `run_export`); the `api/jobs.py` `JobRegistry` owns a separate `ExportJob` lifecycle (`submit_export`/`get_export`). Translation, TM, and provider paths are **untouched**.

> **Surface split (web-first MVP).** This FastAPI export is the **volume-aware** exporter for the Novel→Volume→Chapter model (one artifact per volume, EPUB/TXT/HTML/DOCX). The **CLI `export` command** drives the **legacy single-project exporter** (`services/export.py`, Markdown/single-EPUB) and is not back-ported to the volume model — exporting full novels is a cockpit workflow. This is an accepted MVP boundary, not a gap.

| Method | Path | Notes |
|---|---|---|
| POST | `/projects/{name}/export/novel` | Export every volume to its own artifact (no cross-EPUB merge). Body: optional `target` ∈ `{epub, txt, html, docx}` (defaults `epub`) + optional `bundle` (default `false`; when true, also writes `output/<target>/bundle-<target>.zip`, reported as `result.bundle_path`). → `202` `{job_id, status, scope, scope_id, target}`. |
| POST | `/projects/{name}/export/volumes/{volume_id}` | Export one volume. → `202`. |
| POST | `/projects/{name}/export/chapters/{chapter_id}` | Export one chapter. → `202`. |
| GET | `/projects/{name}/export/jobs/{job_id}` | Poll: `status`, per-volume `progress` (`volumes_total/done`, `current_volume_*`, `translated_segments`/`fallback_segments`), `result` (once done: per-volume `artifacts[]` with `output_path` + `fallback_by_status`), `error`. |
| POST | `/projects/{name}/export/jobs/{job_id}/cancel` | Cooperative cancel — worker stops before the next volume; already-written artifacts stay. Idempotent. |
| GET | `/projects/{name}/export/jobs/{job_id}/events` | SSE: `progress` per volume, then one terminal event (`done`/`cancelled`/`error`). Single-consumer. |

- **Publishable rule** (from 8A): a segment exports its latest translation only when status is `translated`/`manual` and `source_hash` matches; otherwise **source fallback** (counted in `fallback_by_status`). Export never blocks/blanks/drops and writes no translations.
- **Distinct id namespace.** Export jobs live under `/export/jobs/`; an export `job_id` is **not** resolvable via the chapter `/jobs/` or batch `/batch/jobs/` routes.
- **No external queue.** Single-process thread worker, same as chapter/batch jobs.
- Errors: unknown project / volume / chapter → `404`; unsupported `target` (e.g. `pdf`) → `422`; unknown job → `404`.
- **EPUB / TXT / HTML / DOCX** output (Sprint 8A/8C + Phase D; TXT/HTML/DOCX build from the DB, one file per volume under `output/<target>/`). DOCX is a custom minimal OOXML writer (no `python-docx`, no new dependency) synthesized from the DB — no write-back.
- **Combined ZIP bundle** (Phase D): an optional `bundle` flag also packages a novel's per-volume artifacts into `output/<target>/bundle-<target>.zip` (any target). Off by default; the per-volume files are still written; the result/job carries `bundle_path`; skipped on cancel or empty export. A *merged-omnibus* single EPUB is not built — the ZIP-of-per-volume-files is the chosen safe form.

## FastAPI translation QA API + UI (Phase B — read-only, report-first)

Deterministic, **read-only** quality/consistency reports surfaced before export. No mutation, no provider call, no auto-fix, no semantic/vector analysis (ADR 008). Logic lives in `services/translation_qa.py` and reuses the `qa/checks.py` primitives — **no parallel QA system**. Severity is `info | warning | critical`; the UI may label `critical` as "Error" (presentation only). The legacy CLI `weaver validate` is unchanged.

**JSON API** (`api/routers/qa.py`, thin adapter):

| Method | Path | Notes |
|---|---|---|
| GET | `/projects/{name}/qa` | Whole-novel report (per-volume + per-chapter roll-ups). |
| GET | `/projects/{name}/volumes/{volume_id}/qa` | One volume (per-chapter roll-up). |
| GET | `/projects/{name}/chapters/{chapter_id}/qa` | One chapter. |

Response (`QAReportResponse`): `schema_version` (2), `scope`, `scope_id`, `total_segments`, `total_issues`, `info_count`/`warning_count`/`critical_count`, `badge` ∈ `{clean, warnings, errors}`, `issues[]` (`rule`, `category`, `severity`, `message`, `segment_id?`, `chapter_id?`), `summary_by_category`, `summary_by_chapter`, `summary_by_volume`. Unknown project/volume/chapter → `404`; non-integer `volume_id` → `422`. **No `error` severity is emitted** — `critical` is the highest value.

**Deterministic rules:** failed / empty / untranslated-Japanese (critical); stale / suspiciously-short / glossary-mismatch / untranslated-segment / character-name-missing / repeated-identical-translation / fallback-heavy-chapter (warning); mixed-status-chapter (info).

**UI** (`api/routers/ui_qa.py`, presentation-only Jinja2 + HTMX): report pages `/ui/projects/{name}/qa`, `…/volumes/{id}/qa`, `…/chapters/{id}/qa` with badge + counts, severity/category filter, and issue links to the affected chapter/segment. The project page and the workspace link to QA. **The project tree never runs QA on render** (Gate B1): badges are **opt-in**. A "Load QA badges" button on the project page GETs `/ui/projects/{name}/qa/tree-badges`, which runs the novel QA **once** and returns out-of-band (`hx-swap-oob`) badge spans that HTMX injects into per-volume/per-chapter slots (`qa-badge-vol-<id>` / `qa-badge-ch-<id>`). So the tree page stays cheap and badges load only on demand (Phase D).

**Pre-export QA warning (advisory).** The project export form first GETs `/ui/projects/{name}/export/preflight?target=…`, which renders the novel QA summary (errors/warnings + failed-stale / untranslated-fallback / glossary / character advisories) with a **Review QA report** link and an **Export anyway** action. **Export is never blocked**: the action posts to the unchanged `POST /ui/projects/{name}/export`, and a failed/unavailable QA check is non-fatal. The preflight is advisory only and is format-agnostic (it forwards the chosen `target` verbatim, including `docx`).

## FastAPI consistency-data API (Sprint 5/6 — glossary · character DB · translation memory)

Project-scoped data that feeds the prompt and reuse layer. Each router is a thin adapter over a framework-agnostic service (`services/glossary_terms.py`, `services/characters.py`, `services/translation_memory.py`); Japanese path params decode (e.g. `魔王`, `エリナ`).

| Method | Path | Notes |
|---|---|---|
| GET/POST/PATCH/DELETE | `/projects/{name}/glossary[/{source}]` | Project glossary term CRUD (same `glossary_terms` rows injected into the prompt). POST → `201`; not found → `404`; invalid → `422`. |
| GET/POST/PATCH/DELETE | `/projects/{name}/characters[/{jp_name}]` | Character DB CRUD (jp_name / en_name required; gender/role/notes optional). Keyed by `jp_name`; injected as the `<characters>` prompt block. |
| GET | `/projects/{name}/memory` | Translation-memory overview: `total_entries`, `exact_hits`, `reused_from_memory`, `entries[]`. |
| DELETE | `/projects/{name}/memory/{source_hash}` | Delete one TM entry (the `translation_memory` row only). → `204`; unknown hash → `404`. Translation history, manual edits, glossary, and character data are **never** touched. |

- **Translation memory** is keyed by the stored `segment.source_hash` (project-scoped). `translate_one_segment` looks it up before the provider call: exact match → reuse + record a `memory`-tagged attempt + skip the model; miss → call the model and save the result. **Manual edits are the source of truth** — manual saves write to TM and provider saves never overwrite a `manual` row. Explicit retranslate bypasses the lookup but still refreshes provider entries. Reuse count surfaces as `reused_from_memory` in job status, the SSE `done` event, and the CLI translate output.

## Boundary rules (ADR 002 / 004)
- `web/` holds HTTP + templates + job lifecycle only. **Zero** translation/glossary/export logic — all of it is in `services/`, shared with the CLI.
- No long-running translation inside a request handler — it runs behind the job/progress boundary (`job_manager`).
- The FastAPI migration must preserve every behavior above and keep Pydantic at the boundary only.

## Not yet in the cockpit (MVP gaps → [MVP_SCOPE.md](MVP_SCOPE.md))
Novel/Volume/Chapter navigation, TXT/HTML import, two-column workspace with auto-save/revisions, character DB UI, translation-memory UI, batch monitor **UI** (the batch API exists — Sprint 7). A *merged-omnibus* single EPUB (one EPUB spanning all volumes) is deferred; EPUB/TXT/HTML/DOCX per-volume export and a combined **ZIP bundle** both ship.
