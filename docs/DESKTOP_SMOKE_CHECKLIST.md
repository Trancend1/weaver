# Desktop Sidecar Smoke Checklist (Q2F)

> **Purpose.** The first real validation path for the Tauri desktop shell. Q2F
> Commit 1 found the biggest open risk: the Rust/Tauri host in `desktop/` is
> architecturally complete but had never been compiled or run. This checklist
> defines the exact commands, expected evidence, and pass/fail criteria for
> taking the shell from "scaffold" to "smoke-verified", Windows-first.
>
> **Scope.** Compile + dependency-resolution + a single manual launch smoke.
> **Out of scope:** installer, code signing, auto-update, cross-platform
> packaging final. See [§7 Deferred](#7-deferred-not-part-of-this-smoke).
>
> **Contract.** Every check below maps to a clause in
> [`SIDECAR_CONTRACT.md`](SIDECAR_CONTRACT.md). The host implementation lives in
> `desktop/src/` (`lib.rs`, `sidecar.rs`, `webview_session.rs`,
> `launch_config.rs`); the build/runtime story is in
> [`../desktop/README.md`](../desktop/README.md) and
> [`INSTALL_DESKTOP.md`](INSTALL_DESKTOP.md).

---

## 0. Status of record

| Stage | What it proves | Status | Evidence |
|---|---|---|---|
| **A. Toolchain present** | rustc / cargo / tauri-cli / node installed | ✅ verified | §1 commands below |
| **B. Compiles (`cargo check`)** | Rust host type-checks incl. Windows COM code | ✅ verified 2026-06-14 | `0 errors, 3 warnings` |
| **C. Version pins resolve** | `webview2-com` / `windows` match what Tauri pulls | ✅ verified 2026-06-14 | `webview2-com 0.38.2`, `windows 0.61.3`, `tauri 2.11.2` |
| **D. Runtime launch (`cargo tauri dev`)** | Real sidecar spawn → WebView → shutdown | ✅ owner-confirmed 2026-06-14 | N1–N6 passed (§4) |

> **Gate reading (2026-06-14):** ✅ **PASS.** Stage D closed — the owner ran
> `cargo tauri dev` and confirmed all six smoke checks (N1–N6) in §4. Q2F is
> promoted from pass-with-conditions to **PASS**; Sprint O packaging is unblocked.
> The pre-promotion note below is retained for history.
>
> **(historical) pass-with-conditions:** The shell now compiles cleanly and
> the previously-`UNVERIFIED` Windows crate pins resolve exactly as declared in
> `Cargo.toml`. The remaining condition is the manual runtime launch in §4,
> which needs a real desktop (GUI) session and `weaver` on `PATH` — it cannot be
> driven from a headless/automation context. The signed-off gate report is
> [`superpowers/handoffs/2026-06-14-q2f-sidecar-readiness-gate.md`](superpowers/handoffs/2026-06-14-q2f-sidecar-readiness-gate.md).

---

## 1. Toolchain prerequisites (Windows-first)

Run from any shell. All four must succeed before stages B–D mean anything.

```powershell
rustup --version          # rustup 1.29.0+
cargo --version           # cargo 1.96.0+ (rustc >= 1.77 required by Cargo.toml)
cargo tauri --version     # tauri-cli 2.x  (install: cargo install tauri-cli --version "^2")
node --version            # only needed if a frontend build step is later added; not today
```

Also required but not a CLI version check:

- **MSVC C++ Build Tools** — Visual Studio Build Tools → "Desktop development
  with C++". Provides the linker WebView2/Tauri need. Without it, `cargo check`
  passes but `cargo build`/`cargo tauri dev` fails at the link step.
- **WebView2 runtime** — present on Windows 11 by default; required at runtime
  for the native WebView.

**Verified on this machine (2026-06-14):**

```text
rustup 1.29.0 (28d1352db 2026-03-05)
rustc  1.96.0 (ac68faa20 2026-05-25)
cargo  1.96.0 (30a34c682 2026-05-25)
tauri-cli 2.11.2
node v24.15.0
```

**If the toolchain is missing**, this is **blocked-by-toolchain**, not a fail.
Install path:

```powershell
winget install Rustlang.Rustup          # then restart shell
cargo install tauri-cli --version "^2"
# MSVC: install "Visual Studio Build Tools" → Desktop development with C++
```

---

## 2. Compile + dependency resolution (safe, non-packaging)

These do **not** spawn the app, open a window, or build an installer. Safe to run
in any context.

```powershell
cd desktop
cargo check                              # type-check the whole crate (incl. cfg(windows))
cargo tree -p webview2-com               # confirm the resolved webview2-com version
cargo tree -i windows                    # confirm the resolved `windows` crate version
```

### Expected pass evidence

- `cargo check` → `Finished` with **0 errors**. Warnings are acceptable (see
  note below) but must be reviewed.
- `cargo tree` → the resolved `webview2-com` and `windows` versions **match the
  pins in `desktop/Cargo.toml`**. A mismatch is the classic first-compile
  failure in `src/webview_session.rs` (`PlatformWebview::controller()` types
  won't line up) — if versions differ, re-pin `Cargo.toml` to the resolved
  numbers and re-run `cargo check`.

### Actual result (2026-06-14)

```text
cargo check  → 0 errors, 3 warnings
  warning: const `POLL_INTERVAL` never used        (src/sidecar.rs:23)
  warning: field `log_path` never read             (src/sidecar.rs:39)
  warning: method `log_path` never used            (src/sidecar.rs:122)

cargo tree   → webview2-com 0.38.2   (matches Cargo.toml pin)
               windows      0.61.3   (matches Cargo.toml pin)
               tauri        2.11.2
```

The three warnings are **pre-existing dead code** in `sidecar.rs` (an unused
poll-interval constant and an unused `log_path` accessor); they do not block the
smoke. They are cleanup candidates for the audit phase, not a Commit-5 concern.

> The `UNVERIFIED VERSION PIN` comment in `Cargo.toml` (lines 38–42) is now
> **verified**: the declared pins are exactly what Tauri 2.11.2 resolves on this
> machine. Leave the comment until a maintainer decides to update it, or note the
> verification beside it in a later cleanup commit.

---

## 3. (Optional) full build — `cargo build`

Not required for the smoke; `cargo check` already type-checks everything. Run
this only when you want the actual binary to exist before §4. It needs the MSVC
linker.

```powershell
cd desktop
cargo build                              # debug binary at target/debug/
```

Pass = `Finished` with 0 errors and `target/debug/weaver-desktop.exe` present.

---

## 4. Runtime launch smoke — `cargo tauri dev`

**This is the check that turns "compiles" into "works".** It spawns the real
sidecar, polls `/healthz`, opens the cockpit WebView, and exercises shutdown.
It needs **an interactive desktop (GUI) session** and `weaver` on `PATH` — do
not attempt it from a headless/CI/automation context (the WebView cannot open;
per `INSTALL_DESKTOP.md` known-limitation #6 the app exits before graceful
shutdown and can orphan the sidecar).

```powershell
# 1. weaver must be importable / on PATH in the SAME environment
$env:PATH = "D:\DevSpace\Projects\weaver\.venv\Scripts;$env:PATH"
weaver --version

# 2. launch the dev shell (file watcher + fast compile)
cd desktop
cargo tauri dev
```

### Pass/fail evidence (each maps to a contract clause)

| # | Check | Contract | Pass evidence | Fail symptom |
|---|---|---|---|---|
| 4.1 | **Loading window first** | host UX (N1) | branded `loading.html` paints immediately on launch | blank window / long black screen |
| 4.2 | **Sidecar spawn** | §1, §2 | `weaver serve` child process appears; `sidecar.console.log` created in `%APPDATA%\Weaver\logs\` | crash screen "Weaver could not start" |
| 4.3 | **Random port + session token** | §2, §6 | host picked a free loopback port; `WEAVER_SESSION_TOKEN` (64 hex) set in the child env, never in any log | port-in-use crash (exit 65) |
| 4.4 | **`/healthz` polling, ≤20s** | §3, §6 | `GET /healthz 200 OK` in `sidecar.console.log` within the 20s budget (bundled PyInstaller cold start is slower than a PATH sidecar); loading → cockpit transition | crash "did not respond in time" |
| 4.5 | **WebView loads `/ui`** | §1, §3 | cockpit renders; `GET /ui 200 OK` (not 401) in console log | blank WebView / `GET /ui 401` |
| 4.6 | **Session header on every request** | §1 | every request in the console log is 200 (no 401); `X-Weaver-Session` attached by `webview_session.rs` interceptor | intermittent 401 on HTMX/XHR/subresources |
| 4.7 | **Shutdown cleanup, no orphan** | §7 (N3) | after closing the window, no `weaver`/`python`/`uvicorn` survives | orphan process left running |
| 4.8 | **Log files generated** | §4 (N4) | `runtime.log` (cockpit) **and** `sidecar.console.log` (host tee) both present in `logs_dir` | missing log files |
| 4.9 | **Crash screen on startup failure** | §4, §5 | force a failure (e.g. remove `weaver` from PATH) → crash window shows mapped exit code + ≤50 stderr lines | silent exit / no diagnostic surface |

Post-close orphan check + log verification (copy from `INSTALL_DESKTOP.md`):

```powershell
Get-Content "$env:APPDATA\Weaver\logs\sidecar.console.log" -Tail 10
Get-Process | Where-Object { $_.ProcessName -match "weaver|python|uvicorn" }   # → nothing
Get-ChildItem "$env:APPDATA\Weaver\logs\runtime.log"
```

Expected sidecar console tail:

```text
GET /healthz HTTP/1.1" 200 OK
GET /ui HTTP/1.1" 200 OK
GET /static/app.css HTTP/1.1" 200 OK
GET /static/htmx.min.js HTTP/1.1" 200 OK
```

> **Until §4 is run on a real desktop with the orphan check passing, the desktop
> shell is "compile-verified, runtime-unverified" — do not claim N1–N4 as met.**

---

## 5. Exit-code expectations (`SIDECAR_CONTRACT.md` §5)

The host maps these in `src/lib.rs::exit_meaning`. Confirm the crash screen text
matches when forcing each failure:

| Code | Meaning | Status |
|---|---|---|
| `0` | clean shutdown (unexpected during startup) | mapped |
| `64` | configuration error (refused bind / missing extra / invalid flags) | mapped |
| `65` | port already in use | mapped |
| `66` | data-directory error (cannot write `WEAVER_DATA_DIR`) | **reserved** — not yet raised by the cockpit (future `services/app_paths.ensure_runtime_dirs`); the host already maps it |

---

## 6. POSIX note

`src/webview_session.rs` header injection and the `taskkill /T`/`/F` shutdown
path are **Windows-only** today. macOS (WKWebView) / Linux (WebKitGTK) header
injection and POSIX `SIGTERM` graceful shutdown are **Sprint O** — the
interceptor is a no-op there. This checklist is therefore Windows-first by
design; a POSIX smoke is deferred until the cross-platform path lands.

---

## 7. Deferred (not part of this smoke)

These are explicitly **out of scope** for the Q2F desktop smoke and must not be
treated as gaps in it:

- Final installer (NSIS `.exe`) — `INSTALL_DESKTOP.md` §Installer release.
- Code signing — Windows SmartScreen warning is expected until a cert is added.
- Auto-update — manual download + reinstall for now.
- Cross-platform packaging final — Windows-first; macOS/Linux are Sprint O.
- POSIX `SIGTERM` graceful shutdown — deferred with the cross-platform path (§6).
- Bundled Python sidecar (single `.exe`) — PATH dependency today; PyInstaller is
  the evaluated next step (`INSTALL_DESKTOP.md` §Sidecar bundling plan).

---

## 8. Quick-run summary

```powershell
# Stages A–C (safe, runnable anywhere with the toolchain):
rustup --version; cargo --version; cargo tauri --version
cd desktop
cargo check
cargo tree -p webview2-com
cargo tree -i windows

# Stage D (interactive desktop session only):
$env:PATH = "D:\DevSpace\Projects\weaver\.venv\Scripts;$env:PATH"
weaver --version
cargo tauri dev
# …then close the window and run the orphan + log checks in §4.
```
