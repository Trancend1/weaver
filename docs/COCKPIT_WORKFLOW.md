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

## Boundary rules (ADR 002 / 004)
- `web/` holds HTTP + templates + job lifecycle only. **Zero** translation/glossary/export logic — all of it is in `services/`, shared with the CLI.
- No long-running translation inside a request handler — it runs behind the job/progress boundary (`job_manager`).
- The FastAPI migration must preserve every behavior above and keep Pydantic at the boundary only.

## Not yet in the cockpit (MVP gaps → [MVP_SCOPE.md](MVP_SCOPE.md))
Novel/Volume/Chapter navigation, TXT/HTML import, two-column workspace with auto-save/revisions, character DB UI, translation-memory UI, batch volume/novel monitor, TXT/HTML/DOCX export.
