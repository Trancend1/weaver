# Desktop Installer & Release Hardening — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the Sprint-P portable desktop exe into a production-ready, installable Windows app: NSIS installer, signing-ready release pipeline, opt-in update notification, single version source, and the implemented exit-66 data-dir code.

**Architecture:** Builds on ADR 016 (PyInstaller onedir sidecar + Tauri `externalBin` + Rust resolver) — none of that changes. Adds: a Tauri NSIS bundle target, signing-ready `bundle.windows` config injected by CI, a desktop-only opt-in update-notification module (plain HTTPS GET, notification only), a version-sync guard, a tag-triggered GitHub Actions release workflow, and the reserved exit-66 implementation in the Python sidecar. Governed by **ADR 017**.

**Tech Stack:** Tauri 2 (Rust), NSIS, GitHub Actions (`windows-latest`), `ureq` (+rustls TLS), PyInstaller, Python 3.11 / Typer, pytest.

**Sprint name:** Desktop Installer & Release Hardening (descriptive; not an alphabet letter — CLAUDE.md §2.1.1).

**Non-goals (scope fence):** No MSI/WiX. No auto-download/auto-install. No `tauri-plugin-updater`. No macOS/Linux packaging. No onedir→onefile change. No provider/translation/schema/QA/cockpit-UI changes. No bundling logic inside `src/weaver/` (stays in `desktop/` + CI per ADR 016).

**Stage → branch/PR:** one PR per stage (CLAUDE.md §4.4).

**Execution order (owner-directed 2026-06-15):** version single-source is the foundation — the chain `pyproject → tauri version → release tag → latest.json` must derive from one source of truth *before* anything that embeds a version. Run the stages by name in this order (plan stage numbers in parentheses are stable references; they do not change):

1. Exit-66 data-dir handling (plan S1)
2. **Single version source + guard (plan S4)** ← moved up
3. NSIS installer (plan S2)
4. Signing-ready hooks (plan S3)
5. Release workflow (plan S6)
6. Update notification (plan S5)
7. Upgrade testing (plan S7)
8. Docs + ADR registration + gate report (plan S8)

Each run-step is dispatched as one implementer subagent (all tasks in that stage, TDD, commit per task) followed by spec-compliance then code-quality review.

---

## File Structure

| File | Responsibility | Stage |
|---|---|---|
| `src/weaver/errors.py` | `DataDirError` added to hierarchy | S1 |
| `src/weaver/services/app_paths.py` | `ensure_runtime_dirs` raises `DataDirError` | S1 |
| `src/weaver/cli/main.py` | map `DataDirError` → exit 66 in serve path | S1 |
| `tests/unit/services/test_app_paths.py` | `ensure_runtime_dirs` failure test | S1 |
| `tests/unit/api/test_desktop_security.py` | serve exit-66 test (joins 64/65) | S1 |
| `docs/SIDECAR_CONTRACT.md` | §5: 66 reserved → implemented | S1 |
| `desktop/tauri.conf.json` | `bundle.targets` + `bundle.windows.nsis` + signing-ready fields | S2, S3 |
| `desktop/scripts/sync-version.ps1` | derive tauri version from pyproject | S4 |
| `desktop/scripts/check-version.ps1` | guard: pyproject == tauri (== tag) | S4 |
| `desktop/Cargo.toml` | `ureq` TLS feature; `update_check` module wired | S5 |
| `desktop/src/update_check.rs` | opt-in settings read + version compare + notify | S5 |
| `desktop/src/lib.rs` | call update check after cockpit opens | S5 |
| `desktop/capabilities/default.json` | notification window label | S5 |
| `.github/workflows/release.yml` | tag-triggered build/sign/publish | S6 |
| `desktop/scripts/make-latest-json.ps1` | generate the D3 update manifest | S6 |
| `docs/INSTALL_DESKTOP.md` | installer/signing/update sections | S8 |
| `docs/MAINTENANCE.md` | desktop release process | S8 |
| `CLAUDE.md` | §2.1/§2.3/§2.4 sprint open→close; §2.5 carry-forward | S8 |

---

## Stage 1 — Exit-66 data-dir handling (Python, TDD)

**Tracks:** T3 (backend) + T4 (storage) + T6 (QA). **Gate B1:** N/A (startup path, not a render path).

### Task 1.1: Add `DataDirError`

**Files:**
- Modify: `src/weaver/errors.py`

- [ ] **Step 1: Add the error class** (after `ConfigError`, errors.py:9)

```python
class DataDirError(WeaverError):
    """Runtime data directory cannot be created or written (sidecar exit 66)."""
```

- [ ] **Step 2: Commit**

```bash
git add src/weaver/errors.py
git commit -m "feat(errors): add DataDirError for sidecar exit 66"
```

### Task 1.2: `ensure_runtime_dirs` raises `DataDirError` (TDD)

**Files:**
- Test: `tests/unit/services/test_app_paths.py`
- Modify: `src/weaver/services/app_paths.py:86-93`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/services/test_app_paths.py
from pathlib import Path

import pytest

from weaver.errors import DataDirError
from weaver.services.app_paths import AppPaths


def test_ensure_runtime_dirs_raises_datadir_error_when_unwritable(monkeypatch, tmp_path):
    paths = AppPaths(root=tmp_path / "weaver-data")

    def _boom(self, *args, **kwargs):
        raise PermissionError("read-only volume")

    monkeypatch.setattr(Path, "mkdir", _boom)

    with pytest.raises(DataDirError) as exc:
        paths.ensure_runtime_dirs()
    assert "data" in str(exc.value).lower()
```

- [ ] **Step 2: Run it, verify it fails**

Run: `uv run pytest tests/unit/services/test_app_paths.py::test_ensure_runtime_dirs_raises_datadir_error_when_unwritable -v`
Expected: FAIL (raises `PermissionError`, not `DataDirError`).

- [ ] **Step 3: Implement**

Replace `ensure_runtime_dirs` body (app_paths.py:86-93). Add `from weaver.errors import DataDirError` at the top of the file (after the stdlib imports, app_paths.py:28).

```python
    def ensure_runtime_dirs(self) -> None:
        """Create the runtime-required directories. Idempotent.

        Only directories the runtime writes to are created here. ``root`` and
        ``config_dir`` are the same; the rest are content-owning subdirs. A
        filesystem failure is surfaced as :class:`DataDirError` so the sidecar
        can exit with code 66 (SIDECAR_CONTRACT.md §5) instead of crashing
        unmapped.
        """
        for path in (self.root, self.logs_dir, self.cache_dir, self.temp_dir):
            try:
                path.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise DataDirError(
                    f"Cannot create the Weaver data directory at {path}. "
                    "Likely cause: the location is read-only or permission was denied. "
                    "Next command: set WEAVER_DATA_DIR to a writable path, or fix the "
                    "permissions on the directory above."
                ) from exc
```

- [ ] **Step 4: Run it, verify it passes**

Run: `uv run pytest tests/unit/services/test_app_paths.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/weaver/services/app_paths.py tests/unit/services/test_app_paths.py
git commit -m "feat(app-paths): raise DataDirError on unwritable runtime dir"
```

### Task 1.3: Map `DataDirError` → exit 66 in the serve path (TDD)

**Files:**
- Modify: `src/weaver/cli/main.py:1303-1366` (`_run_fastapi_cockpit`)
- Test: `tests/unit/api/test_desktop_security.py`

Read the existing 64/65 tests first (`test_desktop_security.py`) and the `_make_fake_uvicorn` helper (CLAUDE.md §2.5 references it) to match the established pattern.

- [ ] **Step 1: Write the failing test** (mirror the existing 64/65 tests)

```python
def test_serve_exits_66_when_data_dir_unwritable(monkeypatch):
    """ensure_runtime_dirs failure maps to sidecar exit code 66."""
    import typer

    from weaver.errors import DataDirError

    def _boom() -> None:
        raise DataDirError("data dir read-only")

    # Patch ensure_runtime_dirs as called from the serve path.
    monkeypatch.setattr(
        "weaver.services.app_paths.AppPaths.ensure_runtime_dirs",
        lambda self: _boom(),
    )

    with pytest.raises(typer.Exit) as exc:
        _run_fastapi_cockpit(
            host="127.0.0.1",
            port=0,
            books_dir=None,
            open_browser=False,
            reload=False,
        )
    assert exc.value.exit_code == 66
```

> Match the import path / call signature actually used in `test_desktop_security.py` (it already imports `_run_fastapi_cockpit` for the exit-64 test). If that test constructs args differently, copy its style verbatim.

- [ ] **Step 2: Run it, verify it fails**

Run: `uv run pytest tests/unit/api/test_desktop_security.py::test_serve_exits_66_when_data_dir_unwritable -v`
Expected: FAIL (no exit 66 path yet).

- [ ] **Step 3: Implement**

In `_run_fastapi_cockpit`, after the desktop bind guard (main.py:1319-1326) and before `uvicorn.run`, ensure the data dir exists and map its failure. Add the import locally with the other service imports (main.py:1315):

```python
    from weaver.services.app_paths import BOOKS_DIR_ENV, resolve_app_paths
```

Then, just before `url = f"http://{host}:{port}"` (main.py:1334):

```python
    try:
        resolve_app_paths().ensure_runtime_dirs()
    except DataDirError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=66) from exc
```

Add `from weaver.errors import ConfigError, DataDirError` to the existing errors import at the top of `cli/main.py` (locate the current `from weaver.errors import ...` line and extend it).

- [ ] **Step 4: Run it, verify it passes + 64/65 still pass**

Run: `uv run pytest tests/unit/api/test_desktop_security.py -v`
Expected: PASS (66 new; 64/65 unchanged).

- [ ] **Step 5: Commit**

```bash
git add src/weaver/cli/main.py tests/unit/api/test_desktop_security.py
git commit -m "feat(serve): map DataDirError to sidecar exit code 66"
```

### Task 1.4: Update the contract doc

**Files:**
- Modify: `docs/SIDECAR_CONTRACT.md:116` (§5 table row for 66)

- [ ] **Step 1: Edit the table row**

Change:
```
| `66` | Data-directory error: cannot write to `WEAVER_DATA_DIR`. | Reserved; future implementation in `services/app_paths.ensure_runtime_dirs`. |
```
to:
```
| `66` | Data-directory error: cannot create/write the runtime data dir. | `services/app_paths.ensure_runtime_dirs` raises `DataDirError`; `cli/main.py:_run_fastapi_cockpit` maps it to exit 66. |
```

- [ ] **Step 2: Add the test row to §9** (after the 64 row)

```
| `tests/unit/api/test_desktop_security.py::test_serve_exits_66_when_data_dir_unwritable` | Exit code `66` on data-dir failure. |
```

- [ ] **Step 3: Commit**

```bash
git add docs/SIDECAR_CONTRACT.md
git commit -m "docs(sidecar-contract): exit 66 reserved -> implemented"
```

**Stage 1 verification:** `uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run pytest tests/unit/services/test_app_paths.py tests/unit/api/test_desktop_security.py -q`

---

## Stage 2 — NSIS installer config

**Track:** desktop packaging. Requires NSIS installed locally for the build verify (`winget install NSIS.NSIS`).

### Task 2.1: Add NSIS target + per-user install config

**Files:**
- Modify: `desktop/tauri.conf.json:16-28`

- [ ] **Step 1: Replace the `bundle` block**

```json
  "bundle": {
    "active": true,
    "targets": ["app", "nsis"],
    "externalBin": ["sidecar/weaver"],
    "resources": {
      "sidecar/_internal": "_internal"
    },
    "icon": [
      "icons/32x32.png",
      "icons/128x128.png",
      "icons/icon.ico"
    ],
    "windows": {
      "nsis": {
        "installMode": "currentUser",
        "languages": ["English"]
      }
    }
  }
```

> `installMode: currentUser` matches the per-user `%APPDATA%\Weaver` data dir and needs no admin elevation. NSIS does **not** delete `%APPDATA%\Weaver` on uninstall — Tauri NSIS only removes installed program files — so the data-retention promise (INSTALL_DESKTOP.md) holds without extra config. Do **not** add a `deleteAppDataOnUninstall`-style flag.

- [ ] **Step 2: Build the sidecar then the installer**

Run (PowerShell, from `desktop/`):
```powershell
.\scripts\build-sidecar.ps1
$env:PATH = "D:\DevSpace\Projects\weaver\.venv\Scripts;$env:PATH"
cargo tauri build
```
Expected: exit 0; output includes
`desktop\target\release\bundle\nsis\Weaver_<version>_x64-setup.exe`.

- [ ] **Step 3: Manual install smoke** (record evidence for the gate report)

1. Run the setup exe → installs without an admin prompt.
2. Start-menu "Weaver" shortcut exists and launches → cockpit `/ui` loads.
3. Settings → Apps lists "Weaver" with the correct version + uninstaller.

- [ ] **Step 4: Commit**

```bash
git add desktop/tauri.conf.json
git commit -m "feat(desktop): add NSIS per-user installer target"
```

---

## Stage 3 — Signing-ready hooks (no-op until cert exists)

**Track:** desktop packaging + release security (T7).

### Task 3.1: Add secret-free signing config

**Files:**
- Modify: `desktop/tauri.conf.json` (`bundle.windows`)

- [ ] **Step 1: Add timestamp + digest to `bundle.windows`** (siblings of `nsis`)

```json
    "windows": {
      "digestAlgorithm": "sha256",
      "timestampUrl": "http://timestamp.digicert.com",
      "nsis": {
        "installMode": "currentUser",
        "languages": ["English"]
      }
    }
```

> No `certificateThumbprint` / `signCommand` in the repo. Tauri signs only when a thumbprint/sign command is supplied; with none present the build is unsigned and does **not** fail. The thumbprint is injected by CI (Stage 6) via `tauri build --config` override only when the signing secret exists.

- [ ] **Step 2: Verify the unsigned build still succeeds**

Run: `cargo tauri build` (from `desktop/`, sidecar already built).
Expected: exit 0, unsigned installer produced (no signing attempted).

- [ ] **Step 3: Commit**

```bash
git add desktop/tauri.conf.json
git commit -m "feat(desktop): signing-ready windows bundle config (unsigned until cert)"
```

---

## Stage 4 — Single version source + guard

**Track:** release tooling.

### Task 4.1: `sync-version.ps1` (pyproject → tauri.conf.json)

**Files:**
- Create: `desktop/scripts/sync-version.ps1`

- [ ] **Step 1: Write the script**

```powershell
# Derive the desktop version from pyproject.toml (the single source of truth,
# ADR 017 D5) and write it into tauri.conf.json. Run before any packaged build.
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$DesktopDir = Split-Path -Parent $ScriptDir
$RepoRoot = Split-Path -Parent $DesktopDir
$Pyproject = Join-Path $RepoRoot "pyproject.toml"
$TauriConf = Join-Path $DesktopDir "tauri.conf.json"

$versionLine = Select-String -Path $Pyproject -Pattern '^version\s*=\s*"([^"]+)"' | Select-Object -First 1
if (-not $versionLine) { throw "Could not read version from $Pyproject" }
$version = $versionLine.Matches[0].Groups[1].Value

$conf = Get-Content -Raw -LiteralPath $TauriConf | ConvertFrom-Json
$conf.version = $version
$conf | ConvertTo-Json -Depth 32 | Set-Content -LiteralPath $TauriConf -Encoding UTF8

Write-Host "Synced desktop version -> $version"
```

- [ ] **Step 2: Run it; verify tauri.conf.json version matches pyproject**

Run: `.\scripts\sync-version.ps1` (from `desktop/`).
Expected: prints `Synced desktop version -> 0.7.0`; `tauri.conf.json` `version` == `pyproject.toml` `version`.

- [ ] **Step 3: Commit**

```bash
git add desktop/scripts/sync-version.ps1 desktop/tauri.conf.json
git commit -m "feat(release): sync desktop version from pyproject (single source)"
```

### Task 4.2: `check-version.ps1` (drift guard)

**Files:**
- Create: `desktop/scripts/check-version.ps1`

- [ ] **Step 1: Write the script**

```powershell
# Guard: pyproject version must equal tauri.conf.json version. With -Tag, also
# assert both equal the release tag (vX.Y.Z -> X.Y.Z). Exits non-zero on drift.
param([string]$Tag)
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$DesktopDir = Split-Path -Parent $ScriptDir
$RepoRoot = Split-Path -Parent $DesktopDir

$py = (Select-String -Path (Join-Path $RepoRoot "pyproject.toml") -Pattern '^version\s*=\s*"([^"]+)"' | Select-Object -First 1).Matches[0].Groups[1].Value
$conf = Get-Content -Raw -LiteralPath (Join-Path $DesktopDir "tauri.conf.json") | ConvertFrom-Json
$tauri = $conf.version

if ($py -ne $tauri) { throw "Version drift: pyproject=$py tauri=$tauri" }

if ($Tag) {
    $tagVersion = $Tag.TrimStart("v")
    if ($py -ne $tagVersion) { throw "Tag mismatch: tag=$tagVersion pyproject=$py" }
}

Write-Host "Version OK: $py"
```

- [ ] **Step 2: Run it; verify it passes, then prove it catches drift**

Run: `.\scripts\check-version.ps1`  → `Version OK: 0.7.0`.
Temporarily edit `tauri.conf.json` version to `9.9.9`, re-run → throws "Version drift"; revert.

- [ ] **Step 3: Commit**

```bash
git add desktop/scripts/check-version.ps1
git commit -m "feat(release): version drift guard (pyproject vs tauri vs tag)"
```

---

## Stage 5 — Opt-in update notification (desktop-only)

**Track:** desktop + security (T7). **Default OFF.** Notification only — never downloads/installs.

### Task 5.1: Enable HTTPS in `ureq`

**Files:**
- Modify: `desktop/Cargo.toml:31`

- [ ] **Step 1: Add TLS to the `ureq` features**

Change:
```toml
ureq = { version = "2", default-features = false, features = ["json"] }
```
to:
```toml
# "json" for /healthz; "tls" (rustls) for the opt-in HTTPS update check (ADR 017 D3).
ureq = { version = "2", default-features = false, features = ["json", "tls"] }
```

- [ ] **Step 2: Verify it compiles**

Run: `cargo check` (from `desktop/`).
Expected: exit 0.

- [ ] **Step 3: Commit**

```bash
git add desktop/Cargo.toml desktop/Cargo.lock
git commit -m "feat(desktop): enable ureq TLS for opt-in update check"
```

### Task 5.2: `update_check` module — settings + version compare (TDD via Rust unit tests)

**Files:**
- Create: `desktop/src/update_check.rs`
- Modify: `desktop/src/lib.rs:15-17` (add `mod update_check;`)

- [ ] **Step 1: Write the module with unit tests for the pure logic first**

```rust
//! Opt-in, notification-only update check (ADR 017 D3). DEFAULT OFF.
//!
//! When (and only when) the user opts in, this performs ONE HTTPS GET to the
//! release manifest, compares the latest version to the running build, and shows
//! a non-blocking notification with the release URL. It never downloads,
//! executes, or installs anything. Any failure is a silent no-op — a failed
//! update check must never affect launch.
//!
//! Opt-in resolution order: WEAVER_DESKTOP_UPDATE_CHECK env (1/true | 0/false)
//! wins; else %APPDATA%/Weaver/desktop/settings.json {"update_check": bool};
//! else false.

use std::path::Path;
use std::time::Duration;

const MANIFEST_URL: &str =
    "https://github.com/Trancend1/weaver/releases/latest/download/latest.json";
const RELEASES_URL: &str = "https://github.com/Trancend1/weaver/releases/latest";
const CHECK_TIMEOUT: Duration = Duration::from_secs(4);
const CURRENT_VERSION: &str = env!("CARGO_PKG_VERSION");

/// Opt-in flag: env override wins; else settings.json; else false (default OFF).
pub fn update_check_enabled(data_dir: &Path) -> bool {
    if let Ok(v) = std::env::var("WEAVER_DESKTOP_UPDATE_CHECK") {
        match v.trim().to_ascii_lowercase().as_str() {
            "1" | "true" | "yes" | "on" => return true,
            "0" | "false" | "no" | "off" => return false,
            _ => {}
        }
    }
    let settings = data_dir.join("desktop").join("settings.json");
    let Ok(text) = std::fs::read_to_string(settings) else {
        return false;
    };
    serde_json::from_str::<serde_json::Value>(&text)
        .ok()
        .and_then(|v| v.get("update_check").and_then(serde_json::Value::as_bool))
        .unwrap_or(false)
}

/// Compare dotted numeric versions (e.g. "0.8.0"). `true` if `latest` > `current`.
/// Non-numeric/malformed input returns `false` (treat as "no update").
pub fn is_newer(latest: &str, current: &str) -> bool {
    let parse = |s: &str| -> Option<Vec<u64>> {
        s.trim()
            .trim_start_matches('v')
            .split('.')
            .map(|p| p.parse::<u64>().ok())
            .collect()
    };
    match (parse(latest), parse(current)) {
        (Some(a), Some(b)) => a > b,
        _ => false,
    }
}

/// Fetch the manifest and return the latest version string, if reachable.
fn fetch_latest_version() -> Option<String> {
    let resp = ureq::get(MANIFEST_URL)
        .timeout(CHECK_TIMEOUT)
        .set("User-Agent", "weaver-desktop")
        .call()
        .ok()?;
    if resp.status() != 200 {
        return None;
    }
    let body = resp.into_json::<serde_json::Value>().ok()?;
    body.get("version")
        .and_then(serde_json::Value::as_str)
        .map(str::to_owned)
}

/// Result of a completed check: `Some(url)` means notify with this release URL.
pub fn check_for_update(data_dir: &Path) -> Option<String> {
    if !update_check_enabled(data_dir) {
        return None;
    }
    let latest = fetch_latest_version()?;
    if is_newer(&latest, CURRENT_VERSION) {
        Some(RELEASES_URL.to_string())
    } else {
        None
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn newer_versions_detected() {
        assert!(is_newer("0.8.0", "0.7.0"));
        assert!(is_newer("1.0.0", "0.9.9"));
        assert!(is_newer("v0.7.1", "0.7.0"));
    }

    #[test]
    fn same_or_older_is_not_newer() {
        assert!(!is_newer("0.7.0", "0.7.0"));
        assert!(!is_newer("0.6.9", "0.7.0"));
    }

    #[test]
    fn malformed_versions_are_not_newer() {
        assert!(!is_newer("garbage", "0.7.0"));
        assert!(!is_newer("0.7.0", ""));
    }

    #[test]
    fn disabled_by_default_without_settings() {
        let dir = std::env::temp_dir().join("weaver-update-test-empty");
        let _ = std::fs::create_dir_all(&dir);
        std::env::remove_var("WEAVER_DESKTOP_UPDATE_CHECK");
        assert!(!update_check_enabled(&dir));
    }

    #[test]
    fn env_override_enables_and_disables() {
        let dir = std::env::temp_dir().join("weaver-update-test-env");
        let _ = std::fs::create_dir_all(&dir);
        std::env::set_var("WEAVER_DESKTOP_UPDATE_CHECK", "1");
        assert!(update_check_enabled(&dir));
        std::env::set_var("WEAVER_DESKTOP_UPDATE_CHECK", "0");
        assert!(!update_check_enabled(&dir));
        std::env::remove_var("WEAVER_DESKTOP_UPDATE_CHECK");
    }
}
```

- [ ] **Step 2: Register the module** — add to `desktop/src/lib.rs` after `mod sidecar;` (lib.rs:16):

```rust
mod update_check;
```

- [ ] **Step 3: Run the Rust unit tests, verify they pass**

Run: `cargo test -p weaver-desktop update_check` (from `desktop/`).
Expected: the 5 `update_check::tests::*` pass.

- [ ] **Step 4: Commit**

```bash
git add desktop/src/update_check.rs desktop/src/lib.rs
git commit -m "feat(desktop): opt-in update-check logic (default off, notify only)"
```

### Task 5.3: Wire the check after the cockpit opens + notification window

**Files:**
- Modify: `desktop/src/lib.rs` (`open_cockpit`, after the loading window closes)
- Create: `desktop/dist/update.html` (tiny notification page)
- Modify: `desktop/capabilities/default.json` (add `"update"` window)

- [ ] **Step 1: Add the notification window** to `capabilities/default.json:5`

```json
  "windows": ["loading", "main", "crash", "update"],
```

- [ ] **Step 2: Create `desktop/dist/update.html`** (payload baked in via init script, same pattern as crash.html)

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>Weaver — update available</title>
    <style>
      body { font: 14px/1.5 system-ui, sans-serif; margin: 0; padding: 24px; background: #14110e; color: #e9e2d5; }
      h1 { font-size: 16px; margin: 0 0 8px; }
      a { color: #d9b35c; }
      button { margin-top: 16px; padding: 8px 14px; border: 0; border-radius: 6px; background: #3a6b4a; color: #fff; cursor: pointer; }
    </style>
  </head>
  <body>
    <h1>A newer version of Weaver is available</h1>
    <p>You can download the latest installer from the releases page.</p>
    <p><a id="link" href="#" target="_blank" rel="noopener">Open releases page</a></p>
    <button onclick="window.close()">Dismiss</button>
    <script>
      const url = window.__WEAVER_UPDATE_URL__ || "https://github.com/Trancend1/weaver/releases/latest";
      document.getElementById("link").href = url;
    </script>
  </body>
</html>
```

- [ ] **Step 3: Add the notify helper + call it from `boot`/`open_cockpit`**

In `lib.rs`, add a function and call it on a background thread *after* the cockpit is healthy so a slow/failed check never delays first paint. In `open_cockpit`, after the loading window is closed (lib.rs:277), add:

```rust
                let data_dir = cfg.data_dir.clone();
                let notify_handle = handle.clone();
                std::thread::spawn(move || {
                    if let Some(url) = update_check::check_for_update(&data_dir) {
                        show_update_notice(&notify_handle, &url);
                    }
                });
```

Add the window builder near `show_crash` (lib.rs:298):

```rust
/// Non-blocking "update available" window (ADR 017 D3). Notification only — it
/// links to the releases page and never downloads or installs.
fn show_update_notice(handle: &AppHandle, url: &str) {
    let handle = handle.clone();
    let url = url.to_string();
    let _ = handle.clone().run_on_main_thread(move || {
        if handle.get_webview_window("update").is_some() {
            return;
        }
        let script = format!("window.__WEAVER_UPDATE_URL__ = {};", serde_json::json!(url));
        let _ = WebviewWindowBuilder::new(&handle, "update", WebviewUrl::App("update.html".into()))
            .title("Weaver — update available")
            .inner_size(460.0, 240.0)
            .center()
            .initialization_script(&script)
            .build();
    });
}
```

> `target="_blank"` opens the system browser via Tauri's default external-link handling. No `shell` plugin is added (consistent with ADR 016 — no `tauri-plugin-shell`). If external-link open is not granted by `core:default`, fall back to rendering the URL as selectable text for manual copy — do **not** add a shell-open capability for this.

- [ ] **Step 4: Compile + dev smoke with the flag forced on**

Run: `cargo check` then a manual `cargo tauri dev` with `WEAVER_DESKTOP_UPDATE_CHECK=1` against a `latest.json` advertising a higher version (host a temp file or point `MANIFEST_URL` at a local fixture during dev) → the update window appears; with the flag unset → no window, no network call.

- [ ] **Step 5: Commit**

```bash
git add desktop/src/lib.rs desktop/dist/update.html desktop/capabilities/default.json
git commit -m "feat(desktop): show opt-in update-available notice after launch"
```

---

## Stage 6 — GitHub Actions release pipeline (tag-triggered)

**Track:** release automation (T9) + security (T7, signing secret handling).

### Task 6.1: `make-latest-json.ps1`

**Files:**
- Create: `desktop/scripts/make-latest-json.ps1`

- [ ] **Step 1: Write the script**

```powershell
# Generate the opt-in update manifest (ADR 017 D3) consumed by update_check.rs.
param([Parameter(Mandatory = $true)][string]$Version, [string]$OutFile = "latest.json")
$ErrorActionPreference = "Stop"
$manifest = [ordered]@{
    version = $Version.TrimStart("v")
    url     = "https://github.com/Trancend1/weaver/releases/latest"
    pub_date = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
}
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $OutFile -Encoding UTF8
Write-Host "Wrote $OutFile for version $($manifest.version)"
```

- [ ] **Step 2: Run it; verify shape matches `update_check.rs` (`version` field)**

Run: `.\scripts\make-latest-json.ps1 -Version 0.8.0 -OutFile $env:TEMP\latest.json` then inspect → contains `"version": "0.8.0"`.

- [ ] **Step 3: Commit**

```bash
git add desktop/scripts/make-latest-json.ps1
git commit -m "feat(release): generate latest.json update manifest"
```

### Task 6.2: Release workflow

**Files:**
- Create: `.github/workflows/release.yml`

- [ ] **Step 1: Write the workflow**

```yaml
name: Release (Windows desktop)

on:
  push:
    tags: ["v*"]

permissions:
  contents: write

jobs:
  release:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v3
        with:
          enable-cache: true

      - name: Set up Python 3.11
        run: uv python install 3.11

      - name: Version guard (tag == pyproject == tauri)
        shell: pwsh
        run: ./desktop/scripts/check-version.ps1 -Tag "${{ github.ref_name }}"

      - name: Rust toolchain
        uses: dtolnay/rust-toolchain@stable

      - name: Cargo cache
        uses: Swatinem/rust-cache@v2
        with:
          workspaces: desktop

      - name: Build sidecar (PyInstaller onedir)
        shell: pwsh
        run: ./desktop/scripts/build-sidecar.ps1

      - name: Install Tauri CLI
        run: cargo install tauri-cli --version "^2" --locked

      - name: Build NSIS installer
        shell: pwsh
        working-directory: desktop
        env:
          # Signing is injected ONLY when the secret exists (ADR 017 D2).
          # When empty, Tauri builds unsigned and the job still succeeds.
          WINDOWS_CERTIFICATE_THUMBPRINT: ${{ secrets.WINDOWS_CERTIFICATE_THUMBPRINT }}
        run: |
          if ($env:WINDOWS_CERTIFICATE_THUMBPRINT) {
            cargo tauri build --config "{`"bundle`":{`"windows`":{`"certificateThumbprint`":`"$env:WINDOWS_CERTIFICATE_THUMBPRINT`"}}}"
          } else {
            Write-Host "No signing secret present — building UNSIGNED."
            cargo tauri build
          }

      - name: Generate latest.json
        shell: pwsh
        run: ./desktop/scripts/make-latest-json.ps1 -Version "${{ github.ref_name }}" -OutFile latest.json

      - name: Publish GitHub Release
        uses: softprops/action-gh-release@v2
        with:
          files: |
            desktop/target/release/bundle/nsis/*-setup.exe
            latest.json
          generate_release_notes: true
```

> The sidecar build needs Python on the runner; `build-sidecar.ps1` prefers a `Python312` path then falls back to `python` on PATH. Confirm `windows-latest` provides a compatible Python (it does — the hosted image ships 3.x). If `build-sidecar.ps1`'s hardcoded `Python312` candidate misses, it already falls back to `Get-Command python`. Verify on the first tagged run.

- [ ] **Step 2: Dry-run the version guard locally**

Run: `pwsh ./desktop/scripts/check-version.ps1 -Tag "v0.7.0"` → `Version OK: 0.7.0`.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/release.yml
git commit -m "ci(release): tag-triggered windows installer build + publish"
```

- [ ] **Step 4: First real release validation** (after merge — needs a tag)

Push a throwaway pre-release tag on a branch or use the next real version bump; confirm the workflow builds, attaches `*-setup.exe` + `latest.json`, and the version guard blocks a deliberately mismatched tag.

---

## Stage 7 — Upgrade compatibility testing

**Track:** QA (T6).

### Task 7.1: Upgrade test procedure + evidence

**Files:**
- Create: `docs/superpowers/handoffs/2026-06-15-upgrade-test.md` (evidence log)

- [ ] **Step 1: Execute the upgrade matrix and record results**

1. Install version N (the current `*-setup.exe`).
2. Launch; create a project; confirm data lands in `%APPDATA%\Weaver`.
3. Bump `pyproject.toml` to N+1, run `sync-version.ps1`, rebuild the installer.
4. Install N+1 over N (do not uninstall first).
5. Verify: app launches as N+1; the project + DB from step 2 are intact; the
   binary is replaced (version in Apps list updated); no duplicate install entry.
6. Uninstall N+1; verify `%APPDATA%\Weaver` is preserved.

- [ ] **Step 2: Record pass/fail + screenshots/log paths in the evidence file. Commit.**

```bash
git add docs/superpowers/handoffs/2026-06-15-upgrade-test.md
git commit -m "test(desktop): record installer upgrade-compatibility evidence"
```

---

## Stage 8 — Docs, ADR registration, sprint open/close

**Track:** T0 (docs & source of truth).

### Task 8.1: Register ADR 017

**Files:**
- Modify: `docs/DECISIONS.md` (Active table, after the 016 row)

- [ ] **Step 1: Add the row**

```
| [017](decisions/017-desktop-installer-and-release-hardening.md) | Desktop Installer & Release Hardening | NSIS installer (no MSI); signing-ready CI (unsigned until cert); opt-in notification-only update check (default OFF, narrowly supersedes ADR 016's "no update ping" clause); single version source; exit-66 implemented; tag-triggered release workflow. |
```

- [ ] **Step 2: Commit** — `git add docs/DECISIONS.md && git commit -m "docs(adr): register ADR 017"`

### Task 8.2: Update INSTALL_DESKTOP + MAINTENANCE

**Files:**
- Modify: `docs/INSTALL_DESKTOP.md` (installer is now the default path; update the Known-limitations list: installer ✅, signing = unsigned-until-cert, update = opt-in notification; add an "Updates" + "Upgrading" section).
- Modify: `docs/MAINTENANCE.md` §"Release / baseline process" (add the desktop release: tag push → `release.yml`; version single-source; signing-ready note).

- [ ] **Step 1: Edit both; keep them factual and short (no marketing).**
- [ ] **Step 2: Commit** — `git commit -am "docs: desktop installer/update/release operational docs"`

### Task 8.3: Open then close the sprint in CLAUDE.md

**Files:**
- Modify: `CLAUDE.md` §2.1 (status row → in-progress, then PASS/PARTIAL), §2.3 (active phase), §2.4 (exit criteria = ADR 017 acceptance list), §2.5 (carry-forward: signing-on-cert-arrival; macOS/Linux still deferred).

- [ ] **Step 1: At sprint start**, set the row to 🟡 in-progress and write §2.3/§2.4 from ADR 017's acceptance criteria.
- [ ] **Step 2: At sprint end**, set status (PASS or PASS-WITH-CONDITIONS — "unsigned until cert" is the expected standing condition), add the §2.5 carry-forward, write the §8 handoff.
- [ ] **Step 3: Commit** — `git commit -am "docs(claude): open/close Desktop Installer & Release Hardening sprint"`

### Task 8.4: Final gate report (Release Captain)

**Files:**
- Create: `docs/superpowers/handoffs/2026-06-15-installer-release-gate-report.md`

- [ ] Record: installer size, signed/unsigned status, update-check default-off proof, exit-66 test pass, upgrade-test evidence, release-workflow run link, known gaps (signing cert, macOS/Linux), and the §8 handoff block.

---

## Self-Review

**Spec coverage (ADR 017 acceptance):** NSIS installer → S2; per-user + uninstall preserves data → S2.1 step 1+3; signing-ready → S3 + S6.2; update opt-in/notify/silent-fail → S5; single version source → S4; release workflow → S6; exit-66 → S1; upgrade test → S7; lint/type/test green → per-stage verification + S1; gate report → S8.4. All covered.

**Placeholder scan:** every code step contains complete code; commands have expected output. The one runtime unknown (runner Python path for `build-sidecar.ps1`) is called out with the existing fallback, not left as TODO.

**Type/name consistency:** `latest.json` field is `version` in both `make-latest-json.ps1` (S6.1) and `fetch_latest_version`/`is_newer` (S5.2). `WEAVER_DESKTOP_UPDATE_CHECK` env name consistent S5.2 ↔ ADR. `DataDirError` consistent S1.1↔1.2↔1.3. `check-version.ps1 -Tag` consistent S4.2↔S6.2. `update` window label consistent S5.3 (capabilities ↔ builder).

**Known risk to verify during execution:** Tauri 2 NSIS `installMode`/`windows.nsis` schema field names — confirm against the installed Tauri CLI's `tauri.conf.json` schema before S2 build; adjust to the exact schema if names differ (the build will reject unknown keys, which is a fast signal).
