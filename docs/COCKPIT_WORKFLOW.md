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
| Export | Trigger Markdown or EPUB export. |

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

## Boundary rules (ADR 002 / 004)
- `web/` holds HTTP + templates + job lifecycle only. **Zero** translation/glossary/export logic — all of it is in `services/`, shared with the CLI.
- No long-running translation inside a request handler — it runs behind the job/progress boundary (`job_manager`).
- The FastAPI migration must preserve every behavior above and keep Pydantic at the boundary only.

## Not yet in the cockpit (MVP gaps → [MVP_SCOPE.md](MVP_SCOPE.md))
Novel/Volume/Chapter navigation, TXT/HTML import, two-column workspace with auto-save/revisions, character DB UI, translation-memory UI, batch volume/novel monitor, TXT/HTML/DOCX export.
