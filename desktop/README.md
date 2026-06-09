# Weaver Desktop Shell (Sprint N — Tauri Shell Alpha)

A minimal [Tauri 2](https://v2.tauri.app/) host that runs the existing Weaver
FastAPI cockpit as a **sidecar**. It does not reimplement any UI — it launches
`weaver serve` on loopback, waits for the backend to be healthy, then opens the
cockpit in a native WebView.

This subtree is **isolated**: it is not a Python dependency and does not change
`src/weaver/` (template diff = 0). The runtime contract it binds against is
[`../docs/SIDECAR_CONTRACT.md`](../docs/SIDECAR_CONTRACT.md).

> **Status: scaffold complete, build/runtime validation pending toolchain.**
> The Rust toolchain (cargo/rustc) and MSVC C++ build tools are not installed on
> the dev machine, so this has **not** been compiled or run yet. Sprint N exit
> criteria N1–N4 (launch time, no orphan, crash screen) remain **unverified**
> until the toolchain is installed. See "Before the first build" below.

## What it does (lifecycle)

```
resolve config ─► loading window ─► spawn `weaver serve` ─► poll /healthz (≤5s)
                                                              │
                              ready ◄─────────────────────────┤
                                │                              ├─► exited / timeout
                   open cockpit WebView                        │
                   (+ X-Weaver-Session interceptor)       crash window
                   close loading window                   (exit code + console tail)
```

On window close or app exit the sidecar is shut down: `taskkill /T` (graceful),
wait 5s, then `taskkill /F /T` (forced) — so no orphan `weaver` process is left
(N3).

## Contract mapping (host ↔ cockpit)

| Contract requirement | Where implemented |
| --- | --- |
| Spawn `weaver serve --host 127.0.0.1 --port <n> --no-browser` | `src/sidecar.rs` `Sidecar::spawn` |
| Desktop baseline via env (`WEAVER_ENV=desktop`, no `--env` flag exists) | `src/sidecar.rs` env block |
| Reserve a free port host-side (§6) | `src/launch_config.rs` `pick_free_port` |
| Session token, ≥32 bytes (§2) | `src/launch_config.rs` `generate_token` (32 bytes / 64 hex) |
| Poll `/healthz`, 200 + `{ok:true}`, 5s budget (§6) | `src/sidecar.rs` `health_ok`, `src/lib.rs` `boot` |
| Inject `X-Weaver-Session` on **every** request (§1) | `src/webview_session.rs` (WebView2 `WebResourceRequested`) |
| Pipe sidecar console to `logs_dir` (§4) | `src/sidecar.rs` `spawn_tee` → `sidecar.console.log` |
| Graceful shutdown then force, ≤5s (§7) | `src/sidecar.rs` `Sidecar::shutdown` |
| Crash screen with last ≤50 stderr lines (§4) | `src/lib.rs` `show_crash` + `dist/crash.html` |
| Exit-code map (§5) | `src/lib.rs` `exit_meaning` |

### Why the host writes `sidecar.console.log`, not `runtime.log`

The cockpit owns `runtime.log` through a long-lived rotating file handler
(`weaver.services.logging_setup`). A second writer would break that handler's
rotation rename on Windows, so the host tees the child's stdout/stderr into a
**separate** `sidecar.console.log` in the same `logs_dir`. The cockpit's own
structured logs (including `runtime.log`) are still produced by the child — so
N4's "sidecar logs land in `logs_dir`" holds, without a double-writer hazard.

## Environment the host sets for the sidecar

`WEAVER_ENV=desktop`, `WEAVER_SESSION_TOKEN=<random>`, `WEAVER_HOST=127.0.0.1`,
`WEAVER_PORT=<port>`, `WEAVER_DOCS=false`, `WEAVER_DATA_DIR=<resolved data dir>`.
Provider API keys are **never** set in the spawn environment.

Override the sidecar binary with `WEAVER_DESKTOP_SIDECAR=<path-to-weaver>`;
otherwise `weaver` is resolved from `PATH`.

## Before the first build

1. **Install Rust** — <https://rustup.rs> (`rustup-init`, user-space).
2. **Install MSVC C++ build tools** — Visual Studio Build Tools →
   "Desktop development with C++" (provides the linker WebView2/Tauri need).
3. **Pin Windows crates** — `webview2-com` and `windows` in `Cargo.toml` must
   match the versions Tauri resolves. After the first `cargo fetch`, run
   `cargo tree -p webview2-com -p windows` and adjust the pins; a mismatch is
   the usual first-compile error in `src/webview_session.rs`.
4. **Generate icons (only for packaging)** — `cargo tauri icon <logo.png>`.
   `bundle.active` is `false` until Sprint O, so dev runs don't need them.
5. **Install the Tauri CLI** — `cargo install tauri-cli --version "^2"`.

## Run (after toolchain install)

```powershell
# `weaver` must be importable/on PATH in the same environment
weaver --version

cd desktop
cargo tauri dev
```

## Out of scope (Sprint N)

Installer, code signing, auto-update, a JS↔Rust command bridge, any UI rewrite,
and cross-platform header injection (macOS WKWebView / Linux WebKitGTK header
injection is **Sprint O** — `src/webview_session.rs` is a no-op there today).
