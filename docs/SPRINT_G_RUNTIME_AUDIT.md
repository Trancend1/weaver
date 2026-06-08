# Sprint G1 — Runtime Audit (read-only)

> **Scope.** Catalogue every dev-only assumption, hardcoded path/host/port, scattered logger, and missing runtime contract that a Tauri sidecar (Sprint N) or any post-Phase-F sprint would trip over. **No code changes in G1.** The fixes belong to G2–G7; G8 is the gate.
>
> **Method.** `rtk grep` / `rtk read` over `src/weaver`, `tests/`. Cross-checked against the Sprint G in-scope list in [`weaver_next_plan.md`](weaver_next_plan.md) and CLAUDE.md §2.3.
>
> **Verdict (one line).** The FastAPI runtime is functional but **implicitly bound to the developer's CWD and home dir**, has **no app-data abstraction**, **one health endpoint named `/health` not `/healthz`**, **no `/runtime/status`**, **no env-mode dispatch**, **no structured log surface**, and **no desktop security baseline** beyond a hardcoded `127.0.0.1` bind. Each is a discrete G2–G7 task; none requires schema or product change.

---

## A. Inventory by category

### A.1 Runtime endpoints — what exists vs Sprint G contract

| Endpoint (G contract) | Status today | Evidence |
|---|---|---|
| `GET /healthz` | **Missing.** `/health` (no `z`) exists. | `src/weaver/api/routers/system.py:13` returns `HealthResponse(status="ok")`; no `ts`, no version field. |
| `GET /version` | **Partial.** Returns `{name, version}`; no git sha, no python version, no env mode. | `src/weaver/api/routers/system.py:19-22`. |
| `GET /runtime/status` | **Missing.** | No router exists. |

**G3 implications.** `/health` must remain (do not silently rename — soak script, doctor checks, and any maintainer muscle memory rely on it). Add `/healthz` as the alias the sidecar contract names, and shape its payload as `{ok, ts}` per plan. `/runtime/status` is new code — return env mode, host, port, resolved app-data dir, log dir.

### A.2 App-data — every place that names a path

The codebase **does** have a partial abstraction at the project-paths layer (`services/project_paths.py`) but **not** at the app-data layer. Two distinct concepts:

- **Project paths** = `<base_dir>/.weaver/<name>/` — derived from books-dir and project name. Already centralised.
- **App-data paths** = user-machine state (config, secrets, cache, logs, exports) — **not** centralised. Each consumer reaches into `Path.home()` directly.

#### Hardcoded `~/.weaver/` references (already on the user machine)

| File:line | What it owns | Sprint G action |
|---|---|---|
| `src/weaver/core/secret_store.py:40` | `~/.weaver/secrets.toml` (mode `0o600`) | **Preserve verbatim.** ADR `004` + ADR `0017` carry-forward + CLAUDE.md §3 invariant. G2's `services/app_paths.py` must expose `secrets_path` as a property that resolves to the same place under default settings, and `apply_secrets_to_env()` must keep working when `WEAVER_DATA_DIR` is unset. |
| `src/weaver/core/global_config.py:18` | `~/.weaver/config.toml` (global defaults) | **Preserve location**; surface as `config_path` on `AppPaths`. |
| `src/weaver/services/epubcheck.py:13-19` | Hunts for `epubcheck.jar` in `~/.local/share/epubcheck/` and `%LOCALAPPDATA%/epubcheck/` | Out of scope for G — this is a third-party tool location, not Weaver app-data. Note only. |

#### `Path.cwd()` reach-ins (the real risk)

`Path.cwd()` is used as a fallback "where is the user" in 13 places under `src/weaver`. **All of them are reachable from a Tauri sidecar that has no controlled CWD.**

| File:line | Why it calls `Path.cwd()` | Risk class |
|---|---|---|
| `src/weaver/api/app.py:49` | `base_dir = (base_dir or Path.cwd()).resolve()` — the books-dir fallback | **Sidecar critical.** When Tauri spawns FastAPI, CWD is unpredictable. G2 must allow `WEAVER_DATA_DIR` (app-data) and a separate `WEAVER_BOOKS_DIR` (or equivalent CLI flag); `Path.cwd()` is fine only as a final fallback in dev. |
| `src/weaver/cli/main.py:847` | `weaver validate --epub`: builds export path relative to CWD | Low — CLI-only. |
| `src/weaver/cli/main.py:1203` | `serve --books-dir` does `os.chdir(books_dir.resolve())` **before** uvicorn imports the factory | **Process-global side effect.** Works today because we own the process. Under a sidecar, the shell may set CWD and we'd silently override it. G2 should pass `base_dir` to the factory directly and stop relying on chdir. |
| `src/weaver/services/doctor.py:79` | doctor falls back to CWD for DB WAL check | Low — opt-in CLI. |
| `src/weaver/services/export.py:41,87` | Both export-path resolvers | Medium — already accept `cwd=` param; web layer always passes `base_dir`. Fine. |
| `src/weaver/services/glossary.py:191` | Hardcoded `Path.cwd()` — **no `cwd=` parameter** | **Bug-shaped.** Inconsistent with peers (`glossary_review.py:316`, `glossary_diff.py:49` accept `cwd`). Flag for G2 review; small refactor to take `cwd` parameter. |
| `src/weaver/services/glossary_diff.py:49` | `cwd or Path.cwd()` | Fine — accepts override. |
| `src/weaver/services/glossary_review.py:316` | `cwd or Path.cwd()` | Fine. |
| `src/weaver/services/import_source.py:59` | `cwd or Path.cwd()` | Fine. |
| `src/weaver/services/preview.py:55` | `cwd or Path.cwd()` | Fine. |
| `src/weaver/services/project.py:77,161,248` | `cwd or Path.cwd()` × 3 (init / delete / list) | Fine. |
| `src/weaver/services/project_paths.py:29,56` | `cwd or Path.cwd()` | Fine. |
| `src/weaver/services/qa.py:46` | `cwd or Path.cwd()` | Fine. |
| `src/weaver/services/translation.py:231` | `cwd or Path.cwd()` | Fine. |

**G2 conclusion:** the `cwd=` pattern is consistent enough — the gap is at the **boundary** (`app.py` and `cli/main.py`'s `serve`). G2 adds `AppPaths` and threads it through the factory; the service-layer `cwd=Path.cwd()` defaults stay (they're a separate concern: books-dir, not app-data).

### A.3 Host / port assumptions

| File:line | Behavior | Notes |
|---|---|---|
| `src/weaver/cli/main.py:1216` | Uvicorn `host="127.0.0.1"` hardcoded | Correct today (ADR `0017`), but **G5 must lift it to an env-mode dispatch** that *refuses* `0.0.0.0` in `desktop` and allows it (with warning) in `dev`. Test mode is irrelevant — TestClient does not bind. |
| `src/weaver/cli/main.py:1233-1236, 1269-1272` | Two `--port` defaults: `serve`=8765, `serve-api`=8000 | Plan default is **8765** for both. `serve-api` carries an 8000 default. G5 reconciliation: keep both defaults (no breaking change), document the discrepancy; both honour `WEAVER_PORT`. |
| `src/weaver/cli/main.py:1205-1207` | `console.print(f"...{url}...")` after start | This stays — it's a startup hint. G6 should make sure the **same** start event also lands in `runtime.log` JSON-lines. |
| `src/weaver/providers/ollama.py:22` | `DEFAULT_BASE_URL = "http://localhost:11434"` | **Provider default**, not the cockpit host. Out of scope for G. Note only. |
| `src/weaver/services/project.py:122` | `OLLAMA_BASE_URL = "http://localhost:11434"` | Same as above. Out of scope. |

### A.4 Static / template asset hardening

| Asset surface | Today | Sprint G action |
|---|---|---|
| HTMX bundle | Vendored, mounted at `/static` (`src/weaver/api/templating.py:24-27`). | OK. |
| Template `hx-get` / `hx-post` paths | All **root-relative** (e.g. `hx-post="/ui/projects/{{ name }}/..."` in `workspace.html:15`, `project.html:9,21,35,49,59`, `glossary.html:42`, `partials/_browse.html:8,16`, `qa.html:14`). | OK — `WEAVER_PORT=0` works because no template hardcodes a port or host. |
| Absolute `http://` / `https://` in templates | One match: an inline SVG `xmlns` in `base.html:7`. Not a route. | OK. |
| External CDN | None (HTMX vendored). | OK. |

**G4 action:** add one integration test that boots on `WEAVER_PORT=0` and asserts `/ui` reaches `200` plus one HTMX endpoint reaches `200`. The audit shows there's nothing to *fix* — only to *prove*.

### A.5 Logging surface

| File | Reaches stdlib `logging`? | Effect |
|---|---|---|
| Whole `src/weaver/` | **No matches** for `import logging`, `getLogger`, `logger.`. | **Weaver has no structured logging at all.** Diagnostic output goes through `typer.echo` (CLI) or `console.print` (Rich, CLI), or is swallowed. Uvicorn's access log is the only non-CLI stream. |
| `console.print` in routers | None — UI/JSON routers are silent. | A failed translate job surfaces only in the HTTP response and the in-memory job state. Post-restart, the failure is invisible. |

**G6 action:** ship `services/logging_setup.py` per plan. Five named files: `runtime.log` (start/stop/health), `backend.log` (FastAPI exceptions middleware), `job.log` (one line per job transition), `export.log`, `provider.log`. Critical invariant from CLAUDE.md §4.2: **`provider.log` must never contain an API key.** G6 regression test = greenfield, easy.

### A.6 Desktop security baseline

| Concern | Today | Sprint G action (G5) |
|---|---|---|
| Bind interface | Hardcoded `127.0.0.1` (`cli/main.py:1216`) | Env-mode dispatch; desktop refuses `0.0.0.0`; dev warns. |
| CORS | **No `add_middleware` / `CORSMiddleware` anywhere** (`rtk grep` returns nothing). | Add same-origin-only middleware that activates in `desktop`; off in `dev` (FastAPI defaults are fine). |
| `/docs` / `/redoc` | Always on (FastAPI default; `create_api_app` doesn't disable). | Disable when `WEAVER_DOCS=false` (auto-false in desktop). |
| Session token | **None.** | `X-Weaver-Session` middleware; required in desktop, optional in dev. Token is generated by the sidecar at start (sidecar passes it via env var). |

### A.7 `JobRegistry` and the Sprint I boundary

| File:line | What it is | Sprint G touch? |
|---|---|---|
| `src/weaver/api/jobs.py:8-10` | The `# Single-process thread worker only.` comment. | **Do not weaken in G.** ADR `010` formalises it before Sprint I. G must not introduce SQLite job persistence — that's Sprint I scope. |
| `src/weaver/api/jobs.py` (G0 WIP, already on this branch) | Adds `find_running()` and `drain_updated_segment_ids()` — in-memory only. | **Allowed under G.** Pure ergonomics (refresh-safe re-attach + OOB single-segment swap). No SQLite, no schema. Stays. |

### A.8 Process-global state and shutdown

| Surface | Today | Sprint G action |
|---|---|---|
| Startup lifecycle | None registered (no `@app.on_event("startup")` / FastAPI lifespan handler). | G2/G6 introduce a lifespan: resolve `AppPaths`, initialise logging, write a `runtime.log` start line. |
| Shutdown lifecycle | None. | G6 logs shutdown; G7 sidecar contract names the SIGTERM → grace period → SIGKILL ladder Tauri must implement (not built in G, but documented). |
| `apply_secrets_to_env()` call sites | `cli/main.py:104` + `api/app.py:42`. | OK. |
| `os.chdir(books_dir)` in `serve` | `cli/main.py:1203` | G2 plan: stop relying on chdir; pass `base_dir` directly to factory via env var that the factory reads. Today the factory accepts `base_dir: Path | None` but Uvicorn's `factory=True` invocation passes nothing. G2 introduces `WEAVER_BOOKS_DIR` (or `--books-dir` → env) so the factory reads it without chdir. |

### A.9 Exit codes (Sprint G7 sidecar contract)

| Exit code (plan) | Class | Today |
|---|---|---|
| `0` | clean exit | Uvicorn default — OK. |
| `64` | config error | **Not implemented.** CLI uses `1` (generic) or `7` (`ConfigError`) — `cli/main.py:1168-1171`. G7 documents the **sidecar** exit map; G can leave CLI codes alone (they're a separate contract). |
| `65` | port in use | **Not implemented.** Uvicorn raises and crashes; no specific code. |
| `66` | data-dir error | **Not implemented.** |

**G7 action:** the exit-code map lives in `docs/SIDECAR_CONTRACT.md` and is implemented inside the `serve` entry point's exception handler — small, contained.

---

## B. Files that must change in G2–G7

Grouped by stage so G8 reads a clean diff.

### G2 — App-data contract

- **New:** `src/weaver/services/app_paths.py` — single OS-aware resolver returning `workspace_dir / database_dir / cache_dir / export_dir / logs_dir / temp_dir / config_dir / secrets_path`. Reads `WEAVER_DATA_DIR` override. Preserves `~/.weaver/secrets.toml` location and mode.
- **Edit:** `src/weaver/api/app.py:49` — read `WEAVER_BOOKS_DIR` env var as a fallback before `Path.cwd()`; thread `AppPaths` onto `app.state`.
- **Edit:** `src/weaver/cli/main.py:_run_fastapi_cockpit` — stop calling `os.chdir`; export `WEAVER_BOOKS_DIR` from `--books-dir` instead.
- **Edit:** `src/weaver/services/glossary.py:191` — accept `cwd=` parameter for consistency with peers (the only outlier).
- **Tests:** `tests/unit/services/test_app_paths.py` (resolver shape, env override, OS branches monkeypatched); path-leak regression test (no workflow writes outside `AppPaths.workspace_dir` when one is configured).

### G3 — Runtime endpoints

- **New:** `src/weaver/api/routers/runtime.py` — `/healthz` (`{ok, ts}`), `/runtime/status` (env, host, port, app-data, log dir).
- **Edit:** `src/weaver/api/routers/system.py` — extend `/version` payload with git sha (best-effort; absent = empty string), python version.
- **Edit:** `src/weaver/api/app.py` — include `runtime_router`.
- **Edit:** `src/weaver/api/schemas.py` — add `HealthZResponse`, `RuntimeStatusResponse`; widen `VersionResponse`.
- **Tests:** `tests/unit/api/test_runtime.py` — cold response < 50 ms (smoke), payload shape, no secret leakage.

### G4 — Relative-route + asset hardening

- **No source edits expected** (audit found no offenders).
- **New test:** `tests/integration/test_runtime_random_port.py` — launches Uvicorn with `port=0`, hits `/ui` + one HTMX endpoint; proves UI is port-agnostic.

### G5 — Desktop security baseline

- **New:** `src/weaver/services/runtime_env.py` — parses `WEAVER_ENV` ∈ {`dev`, `desktop`, `test`} with a single source of truth.
- **Edit:** `src/weaver/api/app.py` — apply CORS only in `desktop`; disable `/docs` + `/redoc` when `WEAVER_DOCS=false`; install `X-Weaver-Session` middleware when `WEAVER_SESSION_TOKEN` is set.
- **Edit:** `src/weaver/cli/main.py:_run_fastapi_cockpit` — refuse `host != 127.0.0.1` when `WEAVER_ENV=desktop`; exit code `64`.
- **Tests:** `tests/unit/api/test_desktop_security.py` — bind refusal, `/docs` 404, CORS rejection, session-token enforcement.

### G6 — Structured logging

- **New:** `src/weaver/services/logging_setup.py` — five named JSON-lines files in `AppPaths.logs_dir`, rotation `10 MiB × 5`. No formatter exposes raw `**kwargs` to avoid accidental secret leakage; explicit allowlist per log.
- **Edit:** `src/weaver/api/app.py` — FastAPI lifespan installs the logging stack; writes one `runtime.log` start line + one shutdown line.
- **Edit:** `src/weaver/api/jobs.py` — emit one line per job status transition to `job.log` (project + chapter id + kind + status + duration; **no segment text**).
- **Edit:** `src/weaver/services/export.py` — emit one line per export attempt to `export.log`.
- **Edit:** `src/weaver/providers/*` — emit one line per request to `provider.log` (provider + model + endpoint + latency; **never the prompt, never the key**).
- **Tests:** `tests/unit/services/test_logging_setup.py` — file creation, JSON lines, rotation simulation, **provider.log scrub regression** (greenfield).

### G7 — Sidecar contract doc

- **New:** `docs/SIDECAR_CONTRACT.md` — start → poll `/healthz` → open webview → send session token → graceful shutdown; stdout/stderr conventions; exit code map `0/64/65/66`.
- **Edit:** `CLAUDE.md` §1 — add the contract to the doc map.
- **Edit:** `src/weaver/cli/main.py:_run_fastapi_cockpit` — translate the two known startup failures (port-in-use → `65`, data-dir → `66`) into their sidecar exit codes.

### G8 — Final gate

- Full test suite green (target: 843 + new G tests; expect ~870).
- Pyright basic: 0.
- Ruff + format: clean.
- Clean wheel build.
- Append "Sprint G complete" row to CLAUDE.md §2.5 with: list of new endpoints, app-data abstraction in place, log files written, sidecar contract published.

---

## C. What this audit explicitly does **not** touch

Each item below is in Sprint H–O scope or out of project scope. Flagged so they aren't dragged in by accident.

- Schema migration / `volumes.status` column → Sprint H (ADR `011`).
- Persistent jobs / SQLite `jobs` table → Sprint I (ADR `010`).
- EPUB snapshot persistence → Sprint J.
- Export fidelity wiring → Sprint K.
- Candidate review / Character Page text → Sprint L.
- Image bytes / OCR / thumbnail endpoint → Sprint M (ADR `012`).
- Tauri Rust workspace, `.msi`/`.dmg`, code signing → Sprints N, O.
- npm `@weaver/cli` wrapper → **deferred legacy** (ADR `009` supersedes).
- `weaver.providers.ollama` / `services.project.OLLAMA_BASE_URL` — provider config, not cockpit runtime.

---

## D. Blockers for Sprint H — none

After G8 completes, Sprint H (Project & Volume lifecycle + Novel → Project consolidation) has every prerequisite: stable runtime, app-data root, structured logs to track status transitions, and a sidecar contract that downstream packaging will need but H does not consume.

No latent issue surfaced in this audit that would block H.

---

## E. Risk register (carried into G2–G7)

| Risk | Likelihood | Mitigation in this sprint |
|---|---|---|
| Moving the app-data root breaks existing local DBs. | Medium (single-user project, but the maintainer has live DBs). | G2 detects a legacy `.weaver/` in CWD and emits a one-time warning to `runtime.log` + a CLI hint. **No auto-migration in G.** |
| Logging breaks the soak script (`scripts/soak_13a5.py`). | Low. | Keep stdout summary; JSON goes to file. Soak parses stdout. |
| Session-token middleware breaks existing tests. | Medium. | Middleware activates only when `WEAVER_SESSION_TOKEN` is set; tests opt-in. |
| Stopping `os.chdir(books_dir)` regresses test fixtures that rely on CWD. | Low. | Tests use `monkeypatch.chdir(tmp_path)` (see `tests/`), independent of the new env var path. |
| `/docs` toggle confuses developers. | Low. | Auto-on in `dev` (default mode) → matches existing behaviour. |

---

## F. Quick-reference: env vars Sprint G introduces

```text
WEAVER_ENV           dev | desktop | test    (default: dev)
WEAVER_HOST          default 127.0.0.1       (refused != 127.0.0.1 in desktop)
WEAVER_PORT          default 8765            (0 → auto-assigned)
WEAVER_DOCS          true | false            (auto false in desktop)
WEAVER_DATA_DIR      override OS-default app-data root (G2)
WEAVER_BOOKS_DIR     override Path.cwd() books root for the API factory (G2)
WEAVER_SESSION_TOKEN required in desktop; optional in dev (G5)
```

`WEAVER_SECRETS_PATH` (pre-existing, `core/secret_store.py:26`) is unchanged.

---

*This document is read-only output from G1. G2–G7 produce the code; G8 produces the readiness report and updates CLAUDE.md §2.5.*
