# Sprint P4/P5 — Packaged Standalone Smoke + Regression Audit

**P4 verdict:** PASS — packaged Windows alpha is self-contained; all Sprint P
acceptance criteria met.
**P5 verdict:** PASS (findings only; no code fix required).

P4 is the owner-facing packaged-desktop validation review. P5 is the
bundled-sidecar regression audit (startup, shutdown, logs, crash, token/security,
orphan risk, PATH-free launch). No code was changed in P4/P5: every acceptance
criterion was already satisfied by P1–P3b.

## Environment

- Build: `cargo tauri build` → `desktop/target/release/weaver-desktop.exe`.
- Validation against the **packaged** release exe (not `cargo tauri dev`).
- Two runs: an isolated `WEAVER_DATA_DIR` run (P3b) and a real
  `%APPDATA%\Weaver\logs` run (P4, this session).

## Artifact sizes

| Artifact | Size |
| --- | --- |
| `weaver-desktop.exe` (Tauri host) | 3,274,752 B (3.27 MB) |
| `weaver.exe` (bundled PyInstaller sidecar, release root) | 17,214,723 B (17.2 MB) |
| `_internal` onedir payload (release root) | 784 files |
| PyInstaller onedir total (P2 source) | 171,175,979 B / 785 files |

## P4 — acceptance-criteria review (validation matrix)

| ID | Check | Result | Evidence |
| --- | --- | --- | --- |
| P-V1 | ADR accepted before impl | PASS | ADR 016 Status: Accepted |
| P-V2 | Sidecar artifact builds | PASS | P2 onedir; sizes above |
| P-V3 | Direct sidecar `/healthz 200` | PASS | P2 direct + override smoke |
| P-V4 | Tauri package includes sidecar | PASS | release `weaver.exe` 17.2 MB + `_internal` 784 files |
| P-V5 | PATH-free packaged launch | PASS | `venv_on_path=False`, override empty, `source=bundled` (both runs) |
| P-V6 | No 401 loop | PASS | this-run `/ui 200`, 0 new 401 (see P5 finding F1) |
| P-V7 | Logs exist + safe | PASS | default `%APPDATA%\Weaver\logs`: 6 logs; `NO_SECRET_TOKEN_MATCHES` |
| P-V8 | No orphan on close | PASS (WM_CLOSE); human X-close = owner-confirm | both runs WM_CLOSE → NONE |
| P-V9 | Crash screen on failure | PASS | bad override → `source=override`, `spawn failed os error 3`, no sidecar, window stays |
| P-V10 | ruff + pyright | PASS | both clean (P3b) |
| P-V11 | Scope fence held | PASS | `git status -- src/weaver` = none |

PATH-free default-dir run tail (`%APPDATA%\Weaver\logs\sidecar.console.log`):

```
[host] startup: sidecar source=bundled path=...\release\weaver.exe health-budget=20s
[out] INFO: 127.0.0.1:... - "GET /healthz HTTP/1.1" 200 OK
[host] startup: /healthz ready after 2102 ms; opening cockpit
[out] INFO: 127.0.0.1:... - "GET /ui HTTP/1.1" 200 OK
[out] INFO: 127.0.0.1:... - "GET /static/app.css HTTP/1.1" 200 OK
[out] INFO: 127.0.0.1:... - "GET /static/htmx.min.js HTTP/1.1" 200 OK
[out] INFO: 127.0.0.1:... - "GET /static/weaver-mark-mono.svg HTTP/1.1" 200 OK
```

## P5 — regression audit findings

### Startup
- Bundled resolver selected in both runs (`source=bundled`, release `weaver.exe`).
- `/healthz` ready in **2653 ms** (isolated) and **2102 ms** (default dir) — both
  well inside the 20 s budget; the P3b widen (5→20 s) gives headroom for a colder
  first launch (AV scan / cold disk cache) without hiding a real failure.
- Resolver order intact: override → bundled → PATH. PATH fallback preserved for
  dev/diagnostics; `WEAVER_DESKTOP_SIDECAR` override still wins.

### Shutdown / orphan
- WM_CLOSE on the host window fired `CloseRequested` → `shutdown_sidecar()`
  (taskkill `/T` then `/F /T`). After close: **NONE** — no `weaver`/`python`/
  `uvicorn` process remained, in both the isolated and default-dir runs.
- **Finding F2 (caveat, not a defect):** programmatic `CloseMainWindow()` does
  not deliver WM_CLOSE to the WebView2 window and leaves the tree alive (the P2/P5
  automation artifact). A real WM_CLOSE / human X-button close is correct. Human
  X-button close should be owner-confirmed, consistent with Sprint N N4 / O.

### Logs
- Default `%APPDATA%\Weaver\logs` produced all 6 files: `runtime.log`,
  `sidecar.console.log`, `backend.log`, `export.log`, `job.log`, `provider.log`.
- Host `[host]` diagnostics land in `sidecar.console.log` (source/path/budget,
  ready+elapsed) — no secret content.

### Crash handling
- Bad `WEAVER_DESKTOP_SIDECAR` → host logs `spawn failed: ... (os error 3)`,
  spawns no sidecar, desktop stays alive showing the crash window with the
  mapped failure, sidecar source/path, and console path.

### Token / security
- Scan over all run logs (isolated + default), patterns `X-Weaver-Session`,
  `WEAVER_SESSION_TOKEN`, provider key names, and any 64-hex sequence:
  **`NO_SECRET_TOKEN_MATCHES`**. The runtime-generated session token never
  appears in any log file. Provider keys are never set in the spawn environment.
- Loopback-only bind retained (`--host 127.0.0.1`); docs disabled; same-origin.

### Orphan-process risk
- PyInstaller **onedir** does not re-exec (unlike onefile), so `weaver.exe` is the
  Python process itself; `taskkill /T` on its PID kills the tree. No nested
  bootloader child to orphan. Confirmed NONE after close.

### PATH-free launch
- Confirmed with `.venv\Scripts` filtered out of PATH and override unset, in both
  the isolated and the real `%APPDATA%` runs.

### Finding F1 — historical 401s in the accumulated default log
- `sidecar.console.log` in the default dir is append-only across sessions. It
  contained 4 × `GET /ui … 401` at lines L8/L17/L26/L35 (top of a 170-line file =
  oldest), scattered (≈9 lines apart), interleaved with successful requests — old
  sessions, **not a loop**. The current run's tail shows `/ui 200` with **0 new
  401s**. The P3b isolated run was `401_count=0`. No regression.

## Findings summary

| # | Finding | Severity | Action |
| --- | --- | --- | --- |
| F1 | 4 historical 401s in accumulated default log; 0 new 401 this run | Info | None — not a loop, not current behavior |
| F2 | Programmatic `CloseMainWindow()` leaves tree alive; real/human close is clean | Low | Owner-confirm human X-button close (deferred condition) |

No finding requires a code fix. P5 introduced no code changes.

## Handoff

**Track:** T6/T7/T8 packaged regression + T9 review
**Scope:** P4 owner-facing acceptance review + P5 bundled-sidecar regression audit.
**Files/Areas Touched:** this handoff (docs only).
**What Changed:** validation evidence only; no code.
**What Was Intentionally Not Changed:** no `.rs`, `dist/*.html`, `tauri.conf.json`,
build scripts, or any `src/weaver/` code.
**Validation Performed:** default-dir PATH-free launch (`/healthz 200`, `/ui 200`,
static 200), secret scan (`NO_SECRET_TOKEN_MATCHES`), 401 line analysis, WM_CLOSE
no-orphan (NONE) on both runs, bad-override crash, `git status -- src/weaver`.
**Known Risks:** human X-button close not owner-confirmed (F2); cold first-launch
timing not reproduced (warm-cache runs were ~2.1–2.7 s, well under 20 s budget).
**Recommended Next Role / Next Step:** Release Captain — write the P6 gate report
with verdict PASS-WITH-CONDITIONS.
