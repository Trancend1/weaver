# Upgrade Compatibility Test — Desktop Installer (ADR 017, Stage S7)

> **Status: ✅ PASS (2026-06-15, owner machine).** Executed: installed 0.7.0,
> seeded `%APPDATA%\Weaver\projects\sentinel.txt`, ran the 0.7.1 installer over it
> (no prior uninstall) → **1** Apps entry at **0.7.1** (no duplicate), binary
> replaced, sentinel preserved with original content; final uninstall preserved
> the data dir. Evidence summarized in the gate report
> (`2026-06-15-installer-release-gate-report.md`). The step table below is the
> reusable procedure for future upgrades.

## Purpose

Prove that installing version **N+1** over an existing version **N**:
1. replaces the binary (Apps list shows the new version, no duplicate entry), and
2. preserves user data in `%APPDATA%\Weaver` (projects, DB, logs) — the
   data-retention promise (ADR 017 D1, `docs/INSTALL_DESKTOP.md`).

## Pre-req

- A machine with: Rust ≥ 1.77 + MSVC build tools, Tauri CLI v2, NSIS
  (`winget install NSIS.NSIS`), and Python for the sidecar build.

## Procedure

| # | Step | Command / Action | Expected | Result |
|---|---|---|---|---|
| 1 | Build N | `desktop/scripts/build-sidecar.ps1` then `cargo tauri build` (from `desktop/`) | `desktop/target/release/bundle/nsis/Weaver_0.7.0_x64-setup.exe` | ☐ |
| 2 | Install N | Run the setup exe | Installs per-user, **no UAC prompt**; Start-menu "Weaver" | ☐ |
| 3 | Create data | Launch; create a project; add a volume/segment | Data written under `%APPDATA%\Weaver` (db, projects) | ☐ |
| 4 | Note data | `Get-ChildItem "$env:APPDATA\Weaver" -Recurse \| Measure-Object` | Record file count / a known project name | ☐ |
| 5 | Bump version | Edit `pyproject.toml` version → `0.7.1`; run `desktop/scripts/sync-version.ps1` | `tauri.conf.json` version == `0.7.1`; `check-version.ps1` → `Version OK: 0.7.1` | ☐ |
| 6 | Build N+1 | `build-sidecar.ps1` then `cargo tauri build` | `Weaver_0.7.1_x64-setup.exe` | ☐ |
| 7 | Upgrade in place | Run the N+1 setup **without uninstalling N first** | Installs over N; no error | ☐ |
| 8 | Verify binary | Settings → Apps | One "Weaver" entry, version **0.7.1** (no duplicate 0.7.0) | ☐ |
| 9 | Verify data intact | Launch N+1; open the project from step 3 | Project + segments from step 3 present; data count matches step 4 | ☐ |
| 10 | Uninstall | Settings → Apps → Weaver → Uninstall | Program files removed | ☐ |
| 11 | Verify retention | `Test-Path "$env:APPDATA\Weaver"` | **`True`** — data preserved after uninstall | ☐ |

> After running, revert the temporary `pyproject.toml`/`tauri.conf.json` version
> bump from step 5 (or roll it into the real next release), and confirm
> `check-version.ps1` is green and the tree is clean.

## Pass criteria

All of steps 7–9 and 11 pass: upgrade replaces the binary, data survives the
upgrade, and data survives uninstall. Record evidence (screenshots / command
output) inline above and summarize PASS/FAIL in the gate report.
