# Sprint P1 - Sidecar Launch Path and `externalBin` Audit

**Verdict:** PASS

P1 was a read-only audit. It closed the launch-path question before any
PyInstaller or Tauri wiring work.

## Finding

The initial assumption that Sprint P could be implemented with only
`PyInstaller + bundle.externalBin` was incomplete.

Current launch path:

1. `LaunchConfig::resolve()` calls `resolve_weaver_exe()`.
2. `WEAVER_DESKTOP_SIDECAR` wins when set and non-empty.
3. Without the override, `resolve_weaver_exe()` returns `PathBuf::from("weaver")`.
4. `Sidecar::spawn()` launches that value through
   `std::process::Command::new(cfg.weaver_exe)`.
5. `Command::new("weaver")` resolves through `PATH`.

Therefore the Sprint O packaged app still depends on external `weaver` from
`.venv\Scripts` or another installation on `PATH`.

## `externalBin` implication

Tauri `bundle.externalBin` can stage a sidecar executable into the package, but
Weaver's current launcher does not automatically discover that staged binary.
Config-only `externalBin` wiring would package the artifact while the runtime
still tries `Command::new("weaver")`.

Sprint P implementation must therefore be:

```text
PyInstaller onedir sidecar artifact
+ Tauri externalBin staging
+ minimal Rust bundled-sidecar resolver
```

## Accepted resolver order

1. `WEAVER_DESKTOP_SIDECAR` override wins.
2. Bundled sidecar path is preferred when available.
3. Bare `weaver` on `PATH` remains for development and diagnostics.

## Expected P2 artifact

P2 remains small and does not wire Tauri yet:

```text
desktop/target/sidecar/weaver/weaver.exe
```

P2 validates the artifact directly through `WEAVER_DESKTOP_SIDECAR` before P3
touches `bundle.externalBin` or resolver code.

## Expected P3 change

P3 is no longer config-only. It must:

- Stage the sidecar for Tauri `bundle.externalBin`.
- Add the minimal Rust resolver needed to prefer the bundled sidecar.
- Preserve the existing sidecar contract and override behavior.
- Avoid provider, translation, QA, export, schema, and cockpit UI changes.

`tauri-plugin-shell` is not selected for Sprint P unless the minimal resolver
fails with evidence, because it would add dependency and capability surface.

## Validation focus

PATH-free launch validation must prove:

- `.venv\Scripts` is absent from `PATH`.
- `WEAVER_DESKTOP_SIDECAR` is unset for the normal packaged launch.
- Packaged app opens.
- `/healthz` returns 200.
- `/ui` returns 200 with no 401 loop.
- `runtime.log` and `sidecar.console.log` are generated.
- Window close leaves no attributable `weaver`/`python`/`uvicorn` process.
- Forced bad override still shows the crash screen.

## Handoff

**Track:** T0/T9 audit closeout
**Scope:** Close P1 read-only audit and revise Sprint P architecture before implementation.
**Files/Areas Touched:** Documentation only.
**What Changed:** ADR 016 accepted with the bundled-sidecar resolver requirement; Sprint P plan updated so P3 includes `externalBin` plus runtime resolver.
**What Was Intentionally Not Changed:** No PyInstaller implementation, no Rust code, no Python code, no manifests, no lockfiles, no Tauri config, no provider/translation/QA/export/schema/cockpit UI.
**Validation Performed:** Source inspection of `desktop/src/launch_config.rs`, `desktop/src/sidecar.rs`, `desktop/src/lib.rs`, `desktop/tauri.conf.json`, `desktop/Cargo.toml`, ADR 016, and the Sprint P plan.
**Known Risks:** Exact packaged sidecar runtime path still must be proven in P3; PyInstaller package-data completeness remains a P2 risk.
**Recommended Next Role / Next Step:** P2 - build the PyInstaller onedir sidecar artifact at `desktop/target/sidecar/weaver/weaver.exe` and direct-test it via `WEAVER_DESKTOP_SIDECAR`; do not wire Tauri yet.
