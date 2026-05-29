# Web Cockpit — Architecture

**Phase:** 12 · **Status:** Draft (planning) · **Pending ADRs:** `0016`–`0019`
**Companion docs:** [web-feature-plan.md](web-feature-plan.md) · [web-execution-blueprint.md](web-execution-blueprint.md) · [master plan](2026-05-29-web-cockpit-phase-12.md)

This doc owns the **how it's built**. Why/scope lives in [web-feature-plan.md](web-feature-plan.md); build order lives in [web-execution-blueprint.md](web-execution-blueprint.md).

---

## 1. Principle

A **thin web layer over the existing service core**. Flask routes call the same `services/` functions the CLI uses. The web layer holds **zero translation/glossary/export logic** — it only routes HTTP, manages job lifecycle, and renders HTML. CLI and web are two front-ends over one core.

New pieces: `JobManager` (in-memory, threaded, one-job-at-a-time), `config_writer` service, `project_discovery`, `file_browser`.

---

## 2. Layered view

<div class="arch-wrap"><style scoped>.arch-wrap{font-family:system-ui,sans-serif;max-width:980px;margin:0 auto;}.arch-layer{border-radius:12px;padding:14px 16px;margin:10px 0;border:1px solid rgba(0,0,0,.08);}.arch-layer.user{background:#eff6ff;border-color:#bfdbfe;}.arch-layer.app{background:#ecfdf5;border-color:#a7f3d0;}.arch-layer.svc{background:#faf5ff;border-color:#e9d5ff;}.arch-layer.data{background:#fffbeb;border-color:#fde68a;}.arch-layer.ext{background:#f8fafc;border-color:#cbd5e1;border-style:dashed;}.arch-title{font-size:13px;font-weight:700;margin-bottom:10px;color:#334155;letter-spacing:.02em;}.arch-grid{display:grid;gap:8px;}.g2{grid-template-columns:repeat(2,1fr);}.g3{grid-template-columns:repeat(3,1fr);}.g4{grid-template-columns:repeat(4,1fr);}.arch-box{background:rgba(255,255,255,.85);border:1px solid rgba(0,0,0,.08);border-radius:8px;padding:9px 10px;font-size:12px;color:#1f2937;text-align:center;}.arch-box small{color:#64748b;font-size:10px;}.arch-box.hl{border-color:#6366f1;box-shadow:0 0 0 1px #6366f1 inset;font-weight:600;}.arch-flow{text-align:center;color:#94a3b8;font-size:18px;margin:-2px 0;}</style><div class="arch-layer user"><div class="arch-title">USER LAYER — Browser (127.0.0.1:8765)</div><div class="arch-grid g4"><div class="arch-box hl">Dashboard<br><small>project list</small></div><div class="arch-box">New Project<br><small>browse + upload</small></div><div class="arch-box hl">Project Cockpit<br><small>status + actions</small></div><div class="arch-box">Glossary Review<br><small>approve/edit</small></div></div><div class="arch-box" style="margin-top:8px">HTMX + Jinja2 templates + vendored htmx.min.js + minimal CSS (no build step)</div></div><div class="arch-flow">HTTP / SSE &#8595;&#8593;</div><div class="arch-layer app"><div class="arch-title">APPLICATION LAYER — Flask (sync, threaded=True, 127.0.0.1)</div><div class="arch-grid g4"><div class="arch-box">routes_projects<br><small>discover/view</small></div><div class="arch-box">routes_new<br><small>browse/upload/init</small></div><div class="arch-box">routes_translate<br><small>start/stop/SSE</small></div><div class="arch-box">routes_config<br><small>provider/model</small></div></div><div class="arch-grid g3" style="margin-top:8px"><div class="arch-box">routes_glossary</div><div class="arch-box">routes_export</div><div class="arch-box hl">JobManager<br><small>1 job, threading, queue</small></div></div></div><div class="arch-flow">function calls &#8595;</div><div class="arch-layer svc"><div class="arch-title">SERVICE LAYER — existing core (shared with CLI)</div><div class="arch-grid g4"><div class="arch-box">translate_project<br><small>+ cancel hook (new)</small></div><div class="arch-box">initialize_project</div><div class="arch-box">glossary_review<br><small>+ stateless ops (new)</small></div><div class="arch-box">export_markdown/epub</div></div><div class="arch-grid g3" style="margin-top:8px"><div class="arch-box hl">config_writer<br><small>NEW: atomic TOML write</small></div><div class="arch-box hl">project_discovery<br><small>NEW: scan .weaver/*</small></div><div class="arch-box hl">file_browser<br><small>NEW: sandboxed listing</small></div></div></div><div class="arch-flow">reads / writes &#8595;</div><div class="arch-layer data"><div class="arch-title">DATA LAYER</div><div class="arch-grid g4"><div class="arch-box">SQLite WAL<br><small>weaver.db</small></div><div class="arch-box">project.toml<br><small>[provider] etc</small></div><div class="arch-box">~/.weaver/config.toml<br><small>global default</small></div><div class="arch-box">glossary TSV</div></div></div><div class="arch-flow">provider API &#8595;</div><div class="arch-layer ext"><div class="arch-title">EXTERNAL — providers (unchanged)</div><div class="arch-grid g4"><div class="arch-box">deepseek</div><div class="arch-box">gemini</div><div class="arch-box">ollama</div><div class="arch-box">fake</div></div></div></div>

---

## 3. New modules (one concept per file, <400 lines each)

| Path | Concern |
|------|---------|
| `src/weaver/web/__init__.py` | package marker |
| `src/weaver/web/app.py` | Flask app factory + blueprint registration + `127.0.0.1` bind |
| `src/weaver/web/routes_projects.py` | dashboard, project discovery list, project cockpit view |
| `src/weaver/web/routes_new.py` | file browser + upload + init trigger |
| `src/weaver/web/routes_translate.py` | start/stop job, SSE event stream |
| `src/weaver/web/routes_config.py` | set provider/model (project or global) |
| `src/weaver/web/routes_glossary.py` | paginated candidate list + approve/edit/reject |
| `src/weaver/web/routes_export.py` | trigger markdown/epub export |
| `src/weaver/web/job_manager.py` | in-memory job registry, threading, single-job lock, progress queue |
| `src/weaver/web/file_browser.py` | sandboxed directory listing, `.epub` filter |
| `src/weaver/web/templates/*.html` | Jinja2 templates (dashboard, new, cockpit, glossary) |
| `src/weaver/web/static/*` | vendored `htmx.min.js`, CSS |
| `src/weaver/services/config_writer.py` | **NEW** atomic writer for `[provider]` in `project.toml` + global config |
| `src/weaver/services/project_discovery.py` | **NEW** scan `.weaver/*/project.toml`, return summaries (reusable by a future CLI `--active`) |

CLI gains one command: `weaver serve [--port 8765] [--books-dir PATH] [--no-browser]` in `cli/main.py`.

---

## 4. HTTP routes

| Method | Path | Action | Service called |
|--------|------|--------|----------------|
| GET | `/` | Dashboard: discovered projects + global provider default | `project_discovery` |
| GET | `/new` | New-project page (file browser + upload form) | `file_browser` |
| GET | `/api/browse?dir=` | JSON dir listing (sandboxed, `.epub` filter) | `file_browser` |
| POST | `/new/init` | Init from browsed path or uploaded file (upload → `.weaver/_uploads/`) | `initialize_project` |
| GET | `/project/<name>` | Cockpit: status, provider/model, action buttons | `inspect_project` |
| POST | `/project/<name>/config` | Set provider/model (scope=project\|global) | `config_writer` |
| POST | `/project/<name>/translate` | Start translate job (retry/first-N options) | `JobManager` → `translate_project` |
| POST | `/project/<name>/translate/stop` | Cooperative cancel | `JobManager` |
| GET | `/project/<name>/events` | **SSE** live progress stream | `JobManager` queue |
| GET | `/project/<name>/glossary` | Paginated pending candidates | `glossary_review` (stateless) |
| POST | `/project/<name>/glossary/<id>` | approve/edit/reject one candidate | `glossary_review` (stateless) |
| POST | `/project/<name>/export` | Export markdown or epub | `export_markdown/epub_project` |

---

## 5. SSE contract (`text/event-stream`)

- `event: progress` → `{current, total, segment_id, status, input_tokens, output_tokens}`
- `event: done` → `{selected, translated, failed, pending, stale, input_tokens, output_tokens}`
- `event: error` → `{message}`

`JobManager` owns a thread-safe queue. The translate worker thread pushes progress; the SSE route drains the queue to the client. One job at a time: a second start request while a job runs is rejected with a clear message + link to the running job.

---

## 6. Required service-core changes (additive, wire-compatible)

The only changes outside the new `web/` package. Each is additive; the CLI keeps its current behavior.

1. **`services/translation.py` — cancel hook.** `translate_project` currently runs to completion with no cancel path. Add optional `should_cancel: Callable[[], bool] | None`, checked between segments. CLI passes `None` (no behavior change). Web passes the JobManager flag. Needed for the stop button.
2. **`services/glossary_review.py` — stateless ops.** Current `GlossaryReviewSession` is a context manager shaped for the CLI interactive loop. Add stateless helpers: `list_pending(project_toml, *, offset, limit)` and `act_on_candidate(project_toml, candidate_id, action, target=None, notes=None)`. CLI loop stays untouched.
3. **`services/wizard.py` / `services/project.py` — fix discarded provider (PP2 bug).** `weaver new` collects provider then drops it; generated `project.toml` hardcodes `deepseek` + a stray ollama `base_url`. `config_writer` + `initialize_project(provider=...)` fixes both.

---

## 7. Security model (ADR `0017`)

- Bind **`127.0.0.1` only** — never `0.0.0.0`. No remote access.
- Single-user, **no auth** (local desktop tool).
- File browser **sandboxed** to the `--books-dir` root; reject `..` traversal escapes.
- Upload: size + type (`.epub`) limits; copy to `.weaver/_uploads/` staging then init.
- **API keys stay env-only** (CLAUDE.md §4.2). Never write keys to `project.toml`/global config; never render keys to a page or log.

---

## 8. Concurrency model

- **One translate job at a time**, enforced by a `JobManager` global lock.
- SQLite WAL already supports concurrent read while the worker writes — the dashboard reads status during a run without blocking.
- One segment translation = one transaction (existing invariant, unchanged).
- Cooperative cancel only — no thread kill; the worker checks `should_cancel` between segments and stops cleanly, leaving state consistent.
