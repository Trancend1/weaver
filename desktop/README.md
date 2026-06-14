# Weaver Desktop Shell (Sprint N — Tauri Shell Alpha)

A minimal [Tauri 2](https://v2.tauri.app/) host that runs the existing Weaver
FastAPI cockpit as a **sidecar**. It does not reimplement any UI — it launches
`weaver serve` on loopback, waits for the backend to be healthy, then opens the
cockpit in a native WebView.

This subtree is **isolated**: it is not a Python dependency and does not change
`src/weaver/` (template diff = 0). The runtime contract it binds against is
[`../docs/SIDECAR_CONTRACT.md`](../docs/SIDECAR_CONTRACT.md).

> **Status: runtime-verified; bundled sidecar shipped (Sprint P, ✅ PASS).**
> Sprint N N1–N6 are owner-confirmed via `cargo tauri dev`. Sprint O packaged the
> shell; Sprint P bundled the sidecar so the packaged app launches **without an
> external `weaver` on `PATH`** — `/healthz` 200 → `/ui` 200, logs in
> `%APPDATA%\Weaver\logs`, crash screen on failure, no orphan after close. The
> Windows crate pins resolve as declared (`webview2-com 0.38.2`, `windows 0.61.3`,
> `tauri 2.11.2`). Human native X-button close owner-confirmed 2026-06-14 (no
> orphan). Deferred (not blockers): signing / auto-update / final installer /
> cross-platform. Full validation path:
> [`../docs/DESKTOP_SMOKE_CHECKLIST.md`](../docs/DESKTOP_SMOKE_CHECKLIST.md);
> gate report `../docs/superpowers/handoffs/2026-06-14-sprint-p6-gate-report.md`.

## What it does (lifecycle)

```
resolve config ─► loading window ─► spawn `weaver serve` ─► poll /healthz (≤20s)
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
| Poll `/healthz`, 200 + `{ok:true}`, 20s budget (§6, P3b) | `src/sidecar.rs` `health_ok`, `src/lib.rs` `boot` |
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

The sidecar binary is resolved in this order (Sprint P / ADR 016):
1. `WEAVER_DESKTOP_SIDECAR=<path-to-weaver>` override, when set and non-empty.
2. The bundled sidecar staged via Tauri `bundle.externalBin` (the normal packaged
   path — `weaver.exe` beside the host with its `_internal` payload).
3. Bare `weaver` on `PATH` (development / diagnostics fallback only).

## Before the first build

1. **Install Rust** — <https://rustup.rs> (`rustup-init`, user-space).
2. **Install MSVC C++ build tools** — Visual Studio Build Tools →
   "Desktop development with C++" (provides the linker WebView2/Tauri need).
3. **Pin Windows crates** — `webview2-com` and `windows` in `Cargo.toml` must
   match the versions Tauri resolves. After the first `cargo fetch`, run
   `cargo tree -p webview2-com -p windows` and adjust the pins; a mismatch is
   the usual first-compile error in `src/webview_session.rs`.
4. **Generate icons (only for packaging)** — `cargo tauri icon <logo.png>`.
   `bundle.active` is `true` in `tauri.conf.json` (Sprint O packaging is enabled),
   but `cargo tauri dev` does not build the bundle, so dev runs don't need icons.
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
