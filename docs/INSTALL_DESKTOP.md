# Installing Weaver Desktop

> **Sprint O — Production Desktop Packaging.**
> Windows portable app + NSIS installer path. macOS deferred until Windows is stable.

---

## What you get

A Tauri desktop shell that launches the FastAPI cockpit as a local sidecar:

- Native WebView2 window (no external browser)
- Automatic sidecar lifecycle (spawn → health poll → WebView → graceful shutdown)
- Session-token injection on every request (`X-Weaver-Session`)
- Crash screen on backend-start failure with console tail + log path
- App-data and logs in `%APPDATA%\Weaver\` (standard Windows location)

**The Python backend is still required.** The desktop shell resolves `weaver serve` via `PATH`. This is the Sprint O baseline; full sidecar bundling (single `.exe` with embedded Python) is evaluated and documented below.

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

### Installer release — `cargo tauri build --target nsis`

Produces an `.exe` installer (requires NSIS):

1. In `tauri.conf.json`, change `"targets": ["app"]` → `"targets": ["nsis"]`
2. Ensure `bundle.windows.nsis` block exists (see `desktop/tauri.conf.json`)
3. Run: `cargo tauri build`
4. Output: `desktop\target\release\bundle\nsis\Weaver_0.7.0_x64-setup.exe`

---

## Smoke test

After any build, verify the five critical paths:

```powershell
# 1. Launch
$env:PATH = "D:\DevSpace\Projects\weaver\.venv\Scripts;$env:PATH"
Start-Process .\target\release\weaver-desktop.exe

# Wait ~5 s for the loading screen → cockpit transition

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

## Sidecar bundling plan

**Current (Sprint O): PATH dependency.**
The desktop shell assumes `weaver serve` is available on `PATH`. This is the same model as `cargo tauri dev` — the user installs Python + weaver once, then runs the desktop app anytime.

**Future options evaluated for a single-file distributable:**

| Approach | Size | Startup | Complexity | Verdict |
|---|---|---|---|---|
| **PyInstaller** `.exe` | ~25–40 MB | Slow (unpack to temp) | Low | **Recommended next step** — standard Python→exe tool; bundle as Tauri sidecar |
| **uv portable venv** | ~60–100 MB | Medium | Medium | Create `uv venv` + `uv pip install` into a folder; Tauri launches `.venv\Scripts\weaver.exe` |
| **PyOxidizer** | ~15–25 MB | Fast | High | Complex; may fail on compiled extensions (sqlite3, lxml); overkill for a developer tool |
| **PATH dependency** (current) | 0 | Fast | None | Fine for developer audience; poor for end-user distribution |

**Recommendation:** Land PyInstaller first — it is the industry standard for packaging Python CLI tools into distributable `.exe` files. The resulting `weaver.exe` becomes a Tauri-managed sidecar binary (`tauri.conf.json` `bundle.externalBin`), producing a single installer that contains both the shell and the backend.

**Blocker for PyInstaller:** Requires a separate build step and CI integration; not in Sprint O scope.

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

The app resolves `weaver` via `PATH`. Ensure the venv Scripts directory is on PATH before launch:

```powershell
$env:PATH = "D:\DevSpace\Projects\weaver\.venv\Scripts;$env:PATH"
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

## Known limitations (Sprint O)

1. **No bundled Python.** The user must install Python + weaver separately. Single-file distribution requires PyInstaller (see Sidecar bundling plan).
2. **No code signing.** Windows SmartScreen may warn on first run. Signing requires a certificate (out of scope).
3. **No auto-updater.** Updates are manual download + reinstall.
4. **No macOS package.** Windows-only in Sprint O; macOS requires `darwin` target + `.app` bundle tweaks.
5. **NSIS not installed by default.** The portable `app` target works without NSIS; the `.exe` installer requires it.
6. **Headless environment orphans.** In CI/headless environments (no display), the WebView cannot open and the app exits before the graceful-shutdown path runs, leaving sidecar processes. This does **not** affect real desktop use — window-close triggers `taskkill /T`.

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
