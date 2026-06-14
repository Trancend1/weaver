## Handoff: Release Captain
**Track:** T8/T9
**Scope:** Sprint P P3 - stage PyInstaller sidecar for Tauri externalBin and add the minimal bundled-sidecar resolver.
**Files/Areas Touched:** `.gitignore`, `desktop/tauri.conf.json`, `desktop/src/launch_config.rs`, `desktop/scripts/build-sidecar.ps1`, `desktop/scripts/stage-sidecar.ps1`
**What Changed:**
- Added sidecar staging to copy `desktop/target/sidecar/weaver/weaver.exe` to `desktop/sidecar/weaver-x86_64-pc-windows-msvc.exe`.
- Added staging for the PyInstaller `_internal` directory under `desktop/sidecar/_internal`.
- Ignored generated staged binaries/dependency trees in git.
- Added Tauri `bundle.externalBin` for `sidecar/weaver`.
- Added Tauri resource mapping so `sidecar/_internal` is copied to release-root `_internal`, beside the emitted `weaver.exe`.
- Added resolver order in `desktop/src/launch_config.rs`:
  1. `WEAVER_DESKTOP_SIDECAR` override.
  2. bundled sidecar, preferring release-root `weaver.exe` with packaged `_internal` present.
  3. PATH fallback `weaver`.
**What Was Intentionally Not Changed:**
- No Python runtime code, provider logic, translation pipeline, QA, export, schema, or cockpit UI changes.
- No `tauri-plugin-shell` adoption.
- No signing, auto-update, installer final, or cross-platform packaging.
- No generated `desktop/target` output or staged sidecar binaries are intended for git.
**Validation Performed:**
- `rustc -Vv` -> host `x86_64-pc-windows-msvc`.
- `.\desktop\scripts\stage-sidecar.ps1` -> staged `desktop/sidecar/weaver-x86_64-pc-windows-msvc.exe` at 17,214,723 bytes.
- `cargo fmt` from `desktop/`.
- `cargo check` from `desktop/` -> PASS with existing `sidecar.rs` dead-code warnings.
- `cargo tauri build` from `desktop/` -> PASS; release output includes `desktop/target/release/weaver.exe` and release-root `_internal`.
- PATH-free packaged smoke with `.venv\Scripts` excluded and `WEAVER_DESKTOP_SIDECAR` unset:
  - bundled sidecar starts from release-root `weaver.exe`;
  - `/healthz` returned 200 in `p3-pathfree-20260614-155512`;
  - logs generated under the isolated `WEAVER_DATA_DIR`;
  - no `.venv\Scripts` in PATH;
  - no sidecar/desktop orphan after close in elevated process checks.
- Bad override smoke:
  - missing `WEAVER_DESKTOP_SIDECAR` path is still honored first;
  - desktop stays open for crash surface;
  - no sidecar process is spawned.
- `uv run ruff check .` -> PASS.
- `uv run pyright` -> PASS.
**Known Risks:**
- P3 is not a full runtime PASS yet. Automated packaged smokes did not observe a WebView `/ui` request or `/ui 200` in `sidecar.console.log`.
- PyInstaller startup can exceed the existing desktop `HEALTH_BUDGET` of 5 seconds; one longer run showed sidecar startup output but no desktop health poll before shutdown/crash transition.
- Changing startup budget or boot transition diagnostics is outside this P3 resolver-only change and should be handled explicitly before declaring P4/P5 unblocked.
**Recommended Next Role / Next Step:** Decide whether Sprint P needs a small Rust startup-readiness adjustment before P4, then rerun the PATH-free packaged smoke requiring `/healthz 200`, WebView `/ui 200`, no 401, logs generated, and no orphan.
