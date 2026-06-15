# Installing Weaver Desktop

> **Desktop Installer & Release Hardening (ADR 017).**
> Windows NSIS installer (per-user) + portable app, signing-ready release pipeline,
> and an opt-in notification-only update check. macOS/Linux deferred (CLAUDE.md §2.1.1).

---

## What you get

A Tauri desktop shell that launches the FastAPI cockpit as a local sidecar:

- Native WebView2 window (no external browser)
- Automatic sidecar lifecycle (spawn → health poll → WebView → graceful shutdown)
- Session-token injection on every request (`X-Weaver-Session`)
- Crash screen on backend-start failure with console tail + log path
- App-data and logs in `%APPDATA%\Weaver\` (standard Windows location)

**The backend ships bundled (Sprint P).** A packaged build includes the FastAPI sidecar as a PyInstaller `weaver.exe` staged via Tauri `bundle.externalBin`, so it runs with no external `weaver` on `PATH`. The resolver order is `WEAVER_DESKTOP_SIDECAR` override → bundled sidecar → bare `weaver` on `PATH` (dev/diagnostics fallback). See the bundling section below and [ADR 016](decisions/016-bundled-python-sidecar.md).

---

## Prerequisites

### 1. Rust toolchain

Install from <https://rustup.rs/>:

```powershell
# In PowerShell
winget install Rustlang.Rustup
# or download rustup-init.exe and follow prompts
```

Then add the Tauri CLI:

```bash
cargo install tauri-cli --version "^2"
```

Required: Rust ≥ 1.77, MSVC C++ Build Tools (installed with Visual Studio Build Tools or full VS).

### 2. Python backend

The desktop shell needs `weaver` on `PATH`:

```bash
# From the repo root
cd D:\DevSpace\Projects\weaver
uv sync --all-extras
uv pip install -e .
```

Verify:

```bash
weaver serve --help
```

### 3. (Optional) NSIS — for Windows installer

Only needed if building `.exe` installers instead of the portable app:

```powershell
winget install NSIS.NSIS
```

The portable `app` target (single `.exe`) does **not** need NSIS.

---

## Build

### Development — `cargo tauri dev`

Fast compile + file watcher. Ideal for iterating on the Rust host:

```powershell
cd D:\DevSpace\Projects\weaver\desktop
$env:PATH = "D:\DevSpace\Projects\weaver\.venv\Scripts;$env:PATH"
cargo tauri dev
```

### Portable release — `cargo tauri build --target app`

Produces `target\release\weaver-desktop.exe` (~3.2 MB), a standalone portable executable:

```powershell
cd D:\DevSpace\Projects\weaver\desktop
$env:PATH = "D:\DevSpace\Projects\weaver\.venv\Scripts;$env:PATH"
cargo tauri build
```

Output: `desktop\target\release\weaver-desktop.exe`

### Installer release — NSIS (default target since ADR 017)

`bundle.targets` is `["app", "nsis"]`, so a normal build now also produces the
NSIS installer (requires NSIS installed). Sync the version first so the installer
metadata matches `pyproject.toml` (the single source of truth):

```powershell
cd D:\DevSpace\Projects\weaver
./desktop/scripts/sync-version.ps1        # pyproject -> tauri.conf.json
./desktop/scripts/build-sidecar.ps1       # PyInstaller onedir sidecar
cd desktop
cargo tauri build
```

Output: `desktop\target\release\bundle\nsis\Weaver_<version>_x64-setup.exe`
(per-user install: no admin prompt, Start-menu entry + uninstaller).
The portable `weaver-desktop.exe` is still produced by the `app` target.

---

## Smoke test

> **Validated 2026-06-14 (Sprint P, PASS).** The packaged `weaver-desktop.exe`
> (3.27 MB) with its bundled sidecar `weaver.exe` (17.2 MB) passed the full smoke
> with **no external `weaver` on `PATH`**: loading → cockpit `/ui`, `GET /healthz
> 200` → `GET /ui 200` with no 401 loop, all logs generated, no orphan after the
> owner-confirmed native window close, and the crash screen on a forced bad
> sidecar path. See `docs/superpowers/handoffs/2026-06-14-sprint-p6-gate-report.md`.

After any build, verify the five critical paths:

```powershell
# 1. Launch (bundled sidecar; no PATH setup needed since Sprint P)
Start-Process .\target\release\weaver-desktop.exe

# Wait for the loading screen → cockpit transition (host startup budget is 20 s;
# a bundled PyInstaller sidecar cold-starts slower than a PATH `weaver`)

# 2. Verify sidecar console log shows healthz + /ui 200 OK
Get-Content "$env:APPDATA\Weaver\logs\sidecar.console.log" -Tail 10

# 3. Close the window (or Alt+F4 the WebView)
# 4. Verify no orphan weaver/python/uvicorn processes:
Get-Process | Where-Object { $_.ProcessName -match "weaver|python|uvicorn" }
# → should return nothing

# 5. Verify runtime.log exists
Get-ChildItem "$env:APPDATA\Weaver\logs\runtime.log"
```

Expected sidecar console tail:

```text
GET /healthz HTTP/1.1" 200 OK
GET /ui HTTP/1.1" 200 OK
GET /static/app.css HTTP/1.1" 200 OK
GET /static/htmx.min.js HTTP/1.1" 200 OK
```

---

## Sidecar bundling

**Shipped (Sprint P, ADR 016).** The FastAPI sidecar is bundled with the app: a
PyInstaller onedir `weaver.exe` is staged through Tauri `bundle.externalBin`, and
the Rust host resolves it in order `WEAVER_DESKTOP_SIDECAR` override → bundled
sidecar → bare `weaver` on `PATH` (dev/diagnostics fallback). A packaged launch
needs **no external `weaver` on `PATH`**. The decision, options analysis, sizes,
and rollback live in [ADR 016](decisions/016-bundled-python-sidecar.md); the build
tooling is `desktop/scripts/build-sidecar.ps1` + `desktop/sidecar/weaver-sidecar.spec`.

---

## Updates (opt-in, notification only)

Weaver does **not** check for updates by default — the offline-first stance holds
out of the box (ADR 017 D3). If you opt in, the app does **one** version check on
launch and, if a newer release exists, shows a non-blocking "update available"
window that links to the releases page. It **never** downloads or installs
anything — you update by downloading the new installer yourself. A failed check
(offline, etc.) is silent.

Enable it either way:

```powershell
# Per-launch, for testing:
$env:WEAVER_DESKTOP_UPDATE_CHECK = "1"; .\weaver-desktop.exe

# Persistent: %APPDATA%\Weaver\desktop\settings.json
#   { "update_check": true }
```

The env var wins over the settings file. Manifest checked:
`https://github.com/Trancend1/weaver/releases/latest/download/latest.json`.

## Upgrading

Run a newer `Weaver_<version>_x64-setup.exe` over your existing install — no need
to uninstall first. Your data in `%APPDATA%\Weaver` (projects, DB, logs) is
preserved across both upgrade and uninstall. See the upgrade-compatibility test
in `docs/superpowers/handoffs/2026-06-15-upgrade-test.md`.

## Releasing (maintainer)

Releases are automated by `.github/workflows/release.yml` on a `v*` tag push
(windows runner): version guard → sidecar build → NSIS installer → sign **iff**
the `WINDOWS_CERTIFICATE_THUMBPRINT` secret exists (else unsigned, no failure) →
`latest.json` → GitHub Release with both attached. Bump `pyproject.toml`, run
`sync-version.ps1`, commit, then tag `vX.Y.Z` (must equal the version or the
guard fails). See `docs/MAINTENANCE.md`.

---

## App identity

| Field | Value |
|---|---|
| Product name | Weaver |
| Version | 0.7.0 (matches `pyproject.toml`) |
| Identifier | `dev.weaver.desktop` |
| Icons | `desktop/icons/32x32.png`, `128x128.png`, `icon.ico` |
| Brand mark | Ink hand + gold/green fate-web (see `src/weaver/api/static/weaver-mark.svg`) |

---

## Troubleshooting

### `cargo tauri build` fails with "could not find cargo tauri"

Install the Tauri CLI:

```bash
cargo install tauri-cli --version "^2"
```

### WebView2 COM version mismatch

Run `cargo update` from `desktop/` to re-resolve versions after any `Cargo.toml` change.

### Sidecar not found on launch

A packaged build bundles `weaver.exe` beside the shell, so this should not happen.
The resolver order is `WEAVER_DESKTOP_SIDECAR` override → bundled sidecar → bare
`weaver` on `PATH`. If you run an unbundled/dev build, either point the override
at a `weaver` binary or put one on `PATH`:

```powershell
$env:WEAVER_DESKTOP_SIDECAR = "C:\path\to\weaver.exe"
.\weaver-desktop.exe
```

### Orphan processes after force-kill

If the app is killed via Task Manager (`taskkill /F`), the sidecar may survive because the graceful-shutdown path is bypassed. Use `taskkill /T /PID <pid>` first (tree termination), then `/F` if needed.

### Crash screen shows "The cockpit stopped during startup"

Read `sidecar.console.log` in `%APPDATA%\Weaver\logs\` for the exit code and last stderr lines. Common causes:

- `exit 64`: `weaver serve` refused to bind (port conflict or non-loopback host)
- `exit 65`: port already in use
- Missing `weaver` on PATH

### WebView shows blank / 401 Unauthorized

The session-header interceptor (`install_session_header`) must register before navigation. This is handled by building the window with `loading.html` first, then navigating. If you see 401s, check the sidecar console log for `GET /ui 401` — it means the interceptor missed the race.

---

## Known limitations

1. **Unsigned installer (until a cert is procured).** The pipeline is
   signing-ready (ADR 017 D2) — it signs automatically once the
   `WINDOWS_CERTIFICATE_THUMBPRINT` CI secret exists. Until then builds are
   unsigned and Windows SmartScreen may warn on first run.
2. **Update check is notification-only and opt-in.** No background download/
   install; default OFF (see Updates above).
3. **No macOS/Linux package.** Windows-only; macOS/Linux are a separate planned
   sprint (CLAUDE.md §2.1.1).
4. **NSIS required for the installer.** The portable `app` target works without
   NSIS; the `.exe` installer requires `winget install NSIS.NSIS`.
5. **Headless environment orphans.** In CI/headless environments (no display),
   the WebView cannot open and the app exits before the graceful-shutdown path
   runs, leaving sidecar processes. This does **not** affect real desktop use —
   window-close triggers `taskkill /T`.

---

## Uninstall & data retention

| What | Behavior |
|---|---|
| **App binary** | Portable build: delete `weaver-desktop.exe`. NSIS installer (if built): standard Windows uninstall removes the binary. |
| **Running processes** | Close the window first — graceful `taskkill /T`→`/F` leaves no orphan. Do not uninstall while the app is running. |
| **User data + logs** | `%APPDATA%\Weaver\` (projects, database, logs) **is preserved** after uninstall. This is intentional — it holds your novels and translations. Remove it manually only if you want a clean slate: `Remove-Item "$env:APPDATA\Weaver" -Recurse`. |
| **Python sidecar** | The package does not install Python; uninstall does not touch your venv/Python. |

---

## Files

- `desktop/` — Tauri workspace (Rust shell)
- `desktop/tauri.conf.json` — bundle config, app identity
- `desktop/Cargo.toml` — crate manifest
- `desktop/src/lib.rs` — window lifecycle, sidecar spawn, crash screen
- `desktop/src/sidecar.rs` — health poll, console tee, shutdown
- `desktop/src/webview_session.rs` — `X-Weaver-Session` header injection
- `desktop/dist/loading.html` — branded loading splash
- `desktop/dist/crash.html` — crash screen with payload
- `docs/SIDECAR_CONTRACT.md` — runtime contract between host and backend
