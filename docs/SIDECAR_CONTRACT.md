# Weaver Sidecar Contract (Sprint G7)

> **Status.** Active. Governs the boundary between any external launcher (the Tauri shell in Sprint N, an integration test harness, or a future host) and the FastAPI cockpit running as a child process.
>
> **Sprint scope.** This document is **descriptive**: it specifies what the cockpit *promises* the host can rely on, and what the host must *do* to launch and shut down cleanly. The Tauri shell itself is not implemented in Sprint G — only the contract it will bind against.
>
> **Reference ADRs.** [`009`](decisions/009-htmx-first-fastapi-stable-tauri-sidecar-ready.md) (strategic pivot), [`004`](decisions/004-fastapi-cockpit-technical-direction.md) (FastAPI direction), [`007`](decisions/007-fastapi-ui-stack.md) (UI stack). The persistent-job and Project-rename contracts ([`010`](decisions/010-persistent-job-core-sqlite-in-process.md), [`011`](decisions/011-project-terminology-consolidation.md)) layer **on top** of this one and do not change it.

---

## 1. Lifecycle

```text
host                     cockpit (FastAPI sidecar)
 │
 ├── spawn                  weaver serve \
 │                            --env desktop \
 │                            --host 127.0.0.1 \
 │                            --port 0 \
 │                            --no-browser
 │
 │   stdout (JSON line, optional summary line)
 │ ◄───────────────────────  "Weaver cockpit (FastAPI UI) on http://127.0.0.1:<port>"
 │
 │   GET http://127.0.0.1:<port>/healthz
 │ ───────────────────────►  poll (≤ 100 ms cadence, ≤ 5 s budget)
 │ ◄───────────────────────  200 {"ok": true, "ts": "..."}
 │
 │   open WebView at http://127.0.0.1:<port>/ui
 │   inject  X-Weaver-Session: <token>  on every request
 │
 │   ... user activity ...
 │
 │   close request: POSIX SIGTERM / Windows CTRL_BREAK_EVENT
 │ ───────────────────────►  graceful shutdown (Uvicorn)
 │ ◄───────────────────────  process exits with code 0
 │
 │   (if exit > 0): inspect exit code map below
 ▼
```

**Explicit non-goals.** Long-lived host↔cockpit channels (websocket, IPC bridge, named pipe) are **not** in the contract. SSE for jobs uses ordinary HTTP from inside the WebView and does not need a separate channel.

---

## 2. Launch arguments

The host invokes the published `weaver` CLI (Sprint O packages it as a sidecar binary). Only these flags participate in the contract:

| Flag | Required in desktop? | Notes |
|---|---|---|
| `serve` | yes | The runtime entry point. `serve-api` is reserved for headless integration. |
| `--env desktop` | yes | Toggles the desktop security baseline (Sprint G5). |
| `--host 127.0.0.1` | recommended | Default; any other value is **rejected** in desktop mode (exit `64`). |
| `--port <int>` | optional | `0` requests an OS-assigned random port; the host reads the chosen port from the startup line and from `GET /runtime/status`. |
| `--books-dir <path>` | optional | Overrides the projects root for this run. Persists for the cockpit lifetime via `WEAVER_BOOKS_DIR`. |
| `--no-browser` | yes | The host is responsible for opening the WebView. |

Environment the host sets before spawn:

```text
WEAVER_ENV=desktop                   (matches --env)
WEAVER_DATA_DIR=<host-managed path>  (override OS app-data root, optional)
WEAVER_BOOKS_DIR=<projects root>     (alternative to --books-dir)
WEAVER_SESSION_TOKEN=<random>        (required in desktop; opaque, ≥ 32 bytes recommended)
WEAVER_DOCS=false                    (auto-applied in desktop; explicit for clarity)
```

The host **must not** set `DEEPSEEK_API_KEY`, `GEMINI_API_KEY`, or any other provider key in the spawn environment unless the user has explicitly stored them in the host's secret vault. Provider keys flow only through env or `~/.weaver/secrets.toml` (CLAUDE.md §3, ADR `004`/`0020`).

---

## 3. Runtime endpoints the host depends on

```text
GET /healthz             {ok: bool, ts: ISO-8601}      (≤ 50 ms cold)
GET /version             {name, version}
GET /runtime/status      {env, host, port, app_data_dir, logs_dir, books_dir}
```

`/healthz`, `/health`, `/version`, and `/static/*` are **public** even when `WEAVER_SESSION_TOKEN` is set. Every other route, including `/runtime/status` and `/ui`, requires the `X-Weaver-Session` header.

The host must **not** parse or display the body of `/runtime/status` to the end user verbatim — paths are reported as plain strings and are intended for diagnostics, not UI.

---

## 4. Stdout / stderr conventions

The cockpit writes structured logs to **files** in `app_paths.logs_dir` (see G6) and a **minimal summary** to stdout/stderr:

```text
stdout
  Weaver cockpit (FastAPI UI) on http://127.0.0.1:<port> (Ctrl+C to stop)
  If no window opens, paste http://127.0.0.1:<port> into your browser.

stderr
  Uvicorn / Python tracebacks on unrecoverable failure
  CLI guard rejection messages (host-mode bind violations, missing extras)
```

The host should:

- Pipe stdout/stderr into `runtime.log` for forensics. Stdout lines are not JSON; they are user-facing strings.
- Never parse the stdout summary line as a contract. Use `GET /healthz` + `GET /runtime/status` instead.
- Truncate any captured stderr to ≤ 50 lines for the crash-screen view (Sprint N implements this).

---

## 5. Exit code map

| Code | Meaning | Where raised |
|---|---|---|
| `0` | Clean shutdown (signal received, Uvicorn finished). | Uvicorn default. |
| `64` | Configuration error: refused to bind, missing extra, invalid CLI flags. | `cli/main.py` desktop bind guard; `ConfigError` translated by `_exit_with_error`. |
| `65` | Port already in use. | `cli/main.py:_run_fastapi_cockpit` `OSError` translation. |
| `66` | Data-directory error: cannot write to `WEAVER_DATA_DIR`. | Reserved; future implementation in `services/app_paths.ensure_runtime_dirs`. |

Codes outside this table are **not** part of the contract — the host should treat them as `unknown failure`. CLI exit codes for non-`serve` commands (`1`, `3`–`7`) are a separate contract used by tooling and tests; the sidecar codes overlap intentionally only at `0`.

---

## 6. Boot poll algorithm (host-side reference)

```text
spawn cockpit; record stdout/stderr; record child exit_code if it dies early
deadline = now + 5_000 ms
while now < deadline and child is alive:
  try: GET http://127.0.0.1:<port>/healthz
  except connection refused / timeout (200 ms): sleep 50 ms; continue
  if status == 200 and json.ok == true: return ready
sleep 50 ms

if child died before deadline:
  read child exit_code; map via §5; surface to crash screen with last 50 lines of stderr.
if deadline elapsed:
  treat as exit 65 equivalent (port may be ours but never bound).
```

**Random ports.** When `--port 0` is used, the host reads the chosen port from the stdout summary line **only as a hint**. The authoritative source is `GET /runtime/status` once `/healthz` returns 200. Implementations should bind a free port on the host side first (e.g. by opening a temporary socket on `127.0.0.1:0`, recording the port, closing the socket, and passing it as `--port`) — that is more deterministic than parsing stdout.

---

## 7. Graceful shutdown

The host requests shutdown by:

- POSIX: send `SIGTERM` to the child process.
- Windows: send `CTRL_BREAK_EVENT` to the child's process group, or `taskkill /T /PID <pid>` (no `/F`).

Uvicorn handles the signal, drains active connections, and exits `0`. The host should:

- Wait up to **5 s** for the process to exit.
- After 5 s, send `SIGKILL` / `taskkill /F`. Log the forced termination as a `runtime.log` event in the host's own audit trail.
- Never assume `/healthz` answering means the cockpit is still alive — close the WebView first, then signal, then poll the OS process state.

The cockpit does **not** expose a shutdown endpoint. Adding one would make the WebView a privileged shutdown actor; the host owns the lifecycle.

---

## 8. Stability guarantees the contract grants

These behaviors are **stable** for the duration of ADR `009` (i.e. through Sprint O) and may not be changed without superseding this document:

1. The set of public-without-token paths: `/healthz`, `/health`, `/version`, `/static/*`.
2. The exit code map in §5.
3. The five log-file names in `logs_dir`: `runtime.log`, `backend.log`, `job.log`, `export.log`, `provider.log`.
4. The session-header name `X-Weaver-Session`.
5. The promise that **API keys never appear in any log file** (G6 regression test in `tests/unit/services/test_logging_setup.py::test_provider_log_contains_no_api_keys_regression`).

These behaviors are **not** stable and may change between sprints:

- The exact JSON schema of `runtime.log` events (additive only; new fields may appear).
- The set of available HTMX endpoints under `/ui`.
- The contents of `/runtime/status` beyond the documented top-level fields (additive only).

---

## 9. Test surface

Sprint G ships these tests as the executable form of the contract:

| Test | Asserts |
|---|---|
| `tests/unit/api/test_runtime.py::test_healthz_*` | `/healthz` shape, public access, < 50 ms cold. |
| `tests/unit/api/test_desktop_security.py` | Desktop docs-off, CORS, session-token enforcement, public paths bypass token. |
| `tests/unit/api/test_desktop_security.py::test_serve_refuses_non_loopback_in_desktop` | Exit code `64` on bind violation. |
| `tests/integration/test_runtime_random_port.py` | UI works on `--port 0`, no template hardcodes a host. |
| `tests/unit/services/test_logging_setup.py::test_provider_log_contains_no_api_keys_regression` | Provider log is key-free. |

Adding a new contract guarantee requires both updating this document **and** landing a regression test under the table above.

---

## 10. Cross-references

- [CLAUDE.md §1](../CLAUDE.md) — doc map.
- [`docs/SPRINT_G_RUNTIME_AUDIT.md`](SPRINT_G_RUNTIME_AUDIT.md) — the read-only audit that motivated each Sprint G stage.
- [`docs/weaver_next_plan.md`](weaver_next_plan.md) Sprint N — describes how the Tauri shell will *consume* this contract.
- ADR [`009`](decisions/009-htmx-first-fastapi-stable-tauri-sidecar-ready.md), [`010`](decisions/010-persistent-job-core-sqlite-in-process.md), [`011`](decisions/011-project-terminology-consolidation.md).
