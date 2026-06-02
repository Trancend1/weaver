# Cockpit Workflow

The web cockpit is a **local, single-user** browser UI for the same translator workflow the CLI drives. It is the **primary development focus** going forward.

> **Stack status.** The cockpit runs on **Flask (sync) + vendored HTMX + Jinja2** today — the shipped, working baseline. The chosen forward direction is **FastAPI** (typed Pydantic schemas, `APIRouter`, ASGI/Uvicorn) per [ADR 004](decisions/004-fastapi-cockpit-technical-direction.md). Migration is **staged, route-by-route**; Flask is **not** deleted until FastAPI reaches parity. Until then, this doc describes the Flask cockpit.

## Purpose

Kill the CLI's daily friction points: long project paths, provider/model switching, weak progress monitoring, multi-step flow, glossary review. Everything below works in the browser with **no path typing**.

## Run it
```bash
pip install 'weaver[web]'
weaver serve                          # http://127.0.0.1:8765, opens a browser
weaver serve --port 9000 --no-browser
weaver serve --books-dir ~/novels     # discover projects under another root
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
| Provider/model config | Write project `[provider]` or global default from a dropdown; API key writes to the secret store only. |
| Translate | Start (first-N / retry-failed), live **SSE** progress, cooperative **stop** (committed segments stay). |
| Glossary review | Paginated approve / edit / reject of pending candidates; approved-term conflicts + per-chapter coverage diff shown read-only. |
| Export | Trigger Markdown or EPUB export (**legacy single-project** exporter, `services/export.py`). Volume-aware EPUB/TXT/HTML export is the FastAPI surface — see below. |

## Request/UI flow (Flask today)
```
browser → Flask route blueprint (web/routes_*.py)
        → services/* (project_discovery, translation, glossary_review, export, config_writer)
        → storage/* (SQLite)
long jobs: routes_translate → web/job_manager (single background thread) → SSE stream → htmx-updated page
```
HTMX provides liveness (progress, partial updates) without a JS build step.

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

Export renders translated content to a **per-volume artifact** (EPUB / TXT / HTML) as **one background job** with per-volume progress. Logic lives in `services/export_book.py` (`prepare_export` → `run_export`); the `api/jobs.py` `JobRegistry` owns a separate `ExportJob` lifecycle (`submit_export`/`get_export`). Translation, TM, and provider paths are **untouched**.

> **Surface split (web-first MVP).** This FastAPI export is the **volume-aware** exporter for the Novel→Volume→Chapter model (one artifact per volume, EPUB/TXT/HTML). The **CLI `export` command** and the Flask "Export" page above drive the **legacy single-project exporter** (`services/export.py`, Markdown/single-EPUB) and are not back-ported to the volume model — exporting full novels is a cockpit workflow. This is an accepted MVP boundary, not a gap.

| Method | Path | Notes |
|---|---|---|
| POST | `/projects/{name}/export/novel` | Export every volume to its own artifact (no cross-EPUB merge). Body: optional `target` ∈ `{epub, txt, html}` (defaults `epub`). → `202` `{job_id, status, scope, scope_id, target}`. |
| POST | `/projects/{name}/export/volumes/{volume_id}` | Export one volume. → `202`. |
| POST | `/projects/{name}/export/chapters/{chapter_id}` | Export one chapter. → `202`. |
| GET | `/projects/{name}/export/jobs/{job_id}` | Poll: `status`, per-volume `progress` (`volumes_total/done`, `current_volume_*`, `translated_segments`/`fallback_segments`), `result` (once done: per-volume `artifacts[]` with `output_path` + `fallback_by_status`), `error`. |
| POST | `/projects/{name}/export/jobs/{job_id}/cancel` | Cooperative cancel — worker stops before the next volume; already-written artifacts stay. Idempotent. |
| GET | `/projects/{name}/export/jobs/{job_id}/events` | SSE: `progress` per volume, then one terminal event (`done`/`cancelled`/`error`). Single-consumer. |

- **Publishable rule** (from 8A): a segment exports its latest translation only when status is `translated`/`manual` and `source_hash` matches; otherwise **source fallback** (counted in `fallback_by_status`). Export never blocks/blanks/drops and writes no translations.
- **Distinct id namespace.** Export jobs live under `/export/jobs/`; an export `job_id` is **not** resolvable via the chapter `/jobs/` or batch `/batch/jobs/` routes.
- **No external queue.** Single-process thread worker, same as chapter/batch jobs.
- Errors: unknown project / volume / chapter → `404`; unsupported `target` (e.g. `docx`) → `422`; unknown job → `404`.
- **EPUB / TXT / HTML** output (Sprint 8A/8C; TXT/HTML build from the DB, one file per volume under `output/<target>/`). DOCX output, a combined single-EPUB, ZIP packaging, and the export UI are deferred.

## FastAPI consistency-data API (Sprint 5/6 — glossary · character DB · translation memory)

Project-scoped data that feeds the prompt and reuse layer. Each router is a thin adapter over a framework-agnostic service (`services/glossary_terms.py`, `services/characters.py`, `services/translation_memory.py`); Japanese path params decode (e.g. `魔王`, `エリナ`).

| Method | Path | Notes |
|---|---|---|
| GET/POST/PATCH/DELETE | `/projects/{name}/glossary[/{source}]` | Project glossary term CRUD (same `glossary_terms` rows injected into the prompt). POST → `201`; not found → `404`; invalid → `422`. |
| GET/POST/PATCH/DELETE | `/projects/{name}/characters[/{jp_name}]` | Character DB CRUD (jp_name / en_name required; gender/role/notes optional). Keyed by `jp_name`; injected as the `<characters>` prompt block. |
| GET | `/projects/{name}/memory` | Translation-memory overview: `total_entries`, `exact_hits`, `reused_from_memory`, `entries[]`. |
| DELETE | `/projects/{name}/memory/{source_hash}` | Delete one TM entry (the `translation_memory` row only). → `204`; unknown hash → `404`. Translation history, manual edits, glossary, and character data are **never** touched. |

- **Translation memory** is keyed by the stored `segment.source_hash` (project-scoped). `translate_one_segment` looks it up before the provider call: exact match → reuse + record a `memory`-tagged attempt + skip the model; miss → call the model and save the result. **Manual edits are the source of truth** — manual saves write to TM and provider saves never overwrite a `manual` row. Explicit retranslate bypasses the lookup but still refreshes provider entries. Reuse count surfaces as `reused_from_memory` in job status, the SSE `done` event, the Flask job summary, and the CLI translate output.

## Boundary rules (ADR 002 / 004)
- `web/` holds HTTP + templates + job lifecycle only. **Zero** translation/glossary/export logic — all of it is in `services/`, shared with the CLI.
- No long-running translation inside a request handler — it runs behind the job/progress boundary (`job_manager`).
- The FastAPI migration must preserve every behavior above and keep Pydantic at the boundary only.

## Not yet in the cockpit (MVP gaps → [MVP_SCOPE.md](MVP_SCOPE.md))
Novel/Volume/Chapter navigation, TXT/HTML import, two-column workspace with auto-save/revisions, character DB UI, translation-memory UI, batch monitor **UI** (the batch API exists — Sprint 7), export **UI** (the EPUB/TXT/HTML export API exists — Sprint 8B/8C), DOCX export output.
