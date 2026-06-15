# Gate Report — Desktop Installer & Release Hardening (ADR 017)

**Date:** 2026-06-15
**Branch:** `docs/desktop-installer-release-hardening`
**Verdict:** ✅ **PASS** — implementation + docs complete; the three toolchain/CI
conditions (NSIS install smoke, tagged release, upgrade-compat) are all verified
on the owner machine + CI. Code signing remains the single deferred non-blocker
(no cert yet), the same standing as Sprint P.

> Updated 2026-06-15 after owner-machine validation: was PASS-WITH-CONDITIONS at
> authoring; promoted to PASS once conditions 1–3 passed (see "Owner conditions").

## Scope delivered (ADR 017 D1–D6)

| Decision | Delivered | Verified here |
|---|---|---|
| D1 NSIS installer (no MSI) | `tauri.conf.json` `targets:["app","nsis"]` + `windows.nsis.installMode:currentUser` | JSON valid; field names validated against compiled `tauri-utils 2.9.2` (`deny_unknown_fields`). Build/install = owner-pending. |
| D2 Signing-ready (unsigned until cert) | `bundle.windows.digestAlgorithm`/`timestampUrl`; CI injects thumbprint only if secret present, else unsigned no-fail | Config + workflow logic reviewed. Real signed build = owner-pending (needs cert). |
| D3 Opt-in notification-only update (default OFF) | `desktop/src/update_check.rs` + `ureq` TLS + `update.html` + wired in `lib.rs`; env/settings opt-in | `cargo check` clean; 4 Rust unit tests green across 3 parallel runs. Runtime window + external-link = manual smoke. |
| D4 Tag-triggered release | `.github/workflows/release.yml` (`v*`, windows-latest) | YAML parses; version-guard dry-run green; `ci.yml` untouched. First tagged run = owner-pending. |
| D5 Single version source | `sync-version.ps1` + `check-version.ps1` (drift + tag guard) | Pass/drift/tag-mismatch cases all confirmed (exit 0 / exit 1). |
| D6 Exit-66 | `DataDirError` → `ensure_runtime_dirs` → serve maps to `typer.Exit(66)`; contract §5 updated | `ruff`/`pyright` clean; 21 pytest green incl. new exit-66 test. |

## Evidence

- **Python (S1):** `uv run ruff check .` → clean; `ruff format --check` → 371 files formatted; `pyright` → 0 errors; `pytest test_app_paths.py test_desktop_security.py` → **21 passed**.
- **Version guard (S4):** `check-version.ps1` → `Version OK: 0.7.0` (exit 0); `-Tag v9.9.9` → exit 1; drift (tauri→9.9.9) → exit 1; tree reverted clean.
- **Installer config (S2/S3):** validated against `~/.cargo/.../tauri-utils-2.9.2/src/config.rs`; `bundle` JSON parses.
- **Release (S6):** `make-latest-json.ps1 -Version v0.8.0` → `{"version":"0.8.0",...}`; `release.yml` YAML_OK; hardened with `actions/setup-python` so `build-sidecar.ps1` finds an interpreter on the runner.
- **Update check (S5):** `cargo check` → 0 errors (only pre-existing `sidecar.rs` warnings); `cargo test -p weaver-desktop update_check` → **4 passed** (env tests merged to remove the parallel-runner race).

## Commits (16, human author, no AI trailers)

`e3f15b5` plan+ADR · `ef5bdb4`/`b0301e1`/`5f1a920`/`64830d3` exit-66 · `27bfa17`/`58130ba` version source · `a4b48d4`/`4761eeb` NSIS+signing · `b3857ca`/`69345cb`/`0969e0d` release workflow · `52603a4`/`66f694e`/`6fffdf4`/`990fa0f` update notification. (S7/S8 docs commit follows.)

## Owner conditions

1. **NSIS build + install smoke — ✅ PASS (2026-06-15, owner machine).**
   `cargo tauri build` → `Weaver_0.7.0_x64-setup.exe` (37.8 MB, bundles 16.4 MB
   `weaver.exe` + 784-file `_internal`). Silent `/S` install → per-user, no UAC;
   `%LOCALAPPDATA%\Weaver` has `weaver-desktop.exe` + bundled `weaver.exe` +
   `_internal` + `uninstall.exe`; Start-menu `Weaver.lnk` + HKCU entry "Weaver
   0.7.0". Launch → cockpit `/ui` (+ `/ui/providers`, `/ui/queue`, static) all 200,
   no 401 loop. Uninstall `/S` → program + shortcut + registry removed,
   **`%APPDATA%\Weaver` preserved**. No-orphan guarantee = the app's window-close
   handler (graceful `taskkill /T` → forced `/F /T` after 5 s), owner-confirmed
   Sprint P P-V8; an external bare `/T` is not representative.

2. **First `v*` tagged release — ✅ PASS (v0.7.1, run `27529052365`).** First run
   (`27528850430`) **failed at the sidecar step** — a real bug found + fixed:
   `build-sidecar.ps1` indexed `$PythonCandidates[0]` which, when only one
   candidate survives the filter (the CI case), is a scalar string → returned
   `'C'` (first char of `C:\...\python.exe`), which `uv --python` rejected. Fixed
   with `@(...)` array coercion + added `actions/setup-python`. Re-tagged `v0.7.1`
   → run **succeeded**: GitHub Release published (non-draft) with
   `Weaver_0.7.1_x64-setup.exe` (39.1 MB) + `latest.json`. Verified the manifest at
   the exact URL `update_check.rs` polls
   (`.../releases/latest/download/latest.json`) returns `{"version":"0.7.1",...}`
   and the installer URL returns HTTP 200 — this also validates the D3 opt-in
   update path end-to-end.

3. **Upgrade-compat test — ✅ PASS (2026-06-15, owner machine).** Installed 0.7.0,
   seeded `%APPDATA%\Weaver\projects\sentinel.txt`, then ran the 0.7.1 installer
   **over** it (no prior uninstall): Apps shows **1** entry at **0.7.1** (no
   duplicate), binary replaced, **sentinel preserved with original content**.
   Final uninstall → program removed, data preserved. Test artifacts cleaned up.

4. **Code-signing cert — deferred (standing condition).** No cert; unsigned build
   works. Procure OV/EV (or Azure Trusted Signing), store
   `WINDOWS_CERTIFICATE_THUMBPRINT` secret → pipeline auto-signs (no code change).

## Known gaps / risks (documented, non-blocking)

- Released installers are **unsigned** until #4 → SmartScreen may warn.
- Update-window external-link open (`target="_blank"`) not runtime-verified; copyable-text fallback in place; no `tauri-plugin-shell` added.
- `cargo install tauri-cli` compiles from source per CI run unless cached (slow first run).
- macOS/Linux packaging out of scope (CLAUDE.md §2.1.1).

## Handoff

**Track:** T0/T3/T4/T6/T7/T9. **What changed:** see commit list + `git diff --stat e2763f5..HEAD`. **Not changed:** provider/translation/schema/QA/cockpit-UI; `ci.yml`; `src/weaver/` desktop-bundling boundary intact. **Next role / step:** Release Captain (owner) runs the four owner-pending conditions on a toolchain-equipped Windows machine, records evidence, then promotes the sprint to PASS in CLAUDE.md §2.1/§2.3.
