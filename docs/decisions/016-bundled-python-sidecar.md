# ADR 016 - Bundled Python sidecar for Windows desktop alpha

**Status:** Accepted (2026-06-14)

## Context

Sprint O produced a Windows packaged desktop alpha that builds, launches, starts
the cockpit, writes logs, handles crash display, and shuts down cleanly. Its
remaining release-blocking condition is sidecar delivery: the packaged
`weaver-desktop.exe` still resolves `weaver serve` from `PATH`, so a tester needs
the repo virtual environment or another installed `weaver` command available.

Sprint P exists to remove that `.venv\Scripts`-on-`PATH` dependency while keeping
the existing architecture intact:

- FastAPI remains the sidecar.
- Tauri remains the host shell.
- The app remains local-first and offline-capable.
- No telemetry, hosted service, collaboration layer, or cloud dependency is added.
- Windows is the only target for this decision.

The sidecar contract already defines the boundary the host depends on:
`serve`, loopback binding, random port support, `/healthz`, `/runtime/status`,
`X-Weaver-Session`, logs under the app data directory, documented exit codes, and
host-owned shutdown. Sprint P should package that existing sidecar rather than
replacing it.

## P1 audit finding

Sprint P P1 audited the current desktop launch path before implementation. The
audit found that `bundle.externalBin` is necessary but not sufficient:

- `desktop/src/launch_config.rs` resolves the sidecar through
  `resolve_weaver_exe()`.
- `WEAVER_DESKTOP_SIDECAR` wins when set and non-empty.
- Without that override, the launcher returns `PathBuf::from("weaver")`.
- `desktop/src/sidecar.rs` launches that value with
  `std::process::Command::new(cfg.weaver_exe)`.
- Therefore the packaged Sprint O app still resolves `weaver` through `PATH`.
- Tauri `bundle.externalBin` can stage a sidecar executable into the package, but
  the current Weaver launcher does not automatically discover or use that staged
  binary.

The accepted Sprint P scope is therefore not just "PyInstaller + externalBin".
It is:

```text
PyInstaller onedir sidecar artifact
+ Tauri externalBin staging
+ minimal Rust bundled-sidecar resolver
```

## Decision

Bundle a Windows Python sidecar executable with the Tauri app, register it
through Tauri `bundle.externalBin`, and add the smallest Rust runtime resolver
needed to prefer the bundled sidecar in packaged builds.

The bundled executable must expose the same effective runtime behavior as the
current `weaver serve` command. The Rust host should continue to launch a local
child process and poll `/healthz`; the Python FastAPI app should continue to own
the cockpit, routing, provider boundaries, translation workflow, storage, logging,
and shutdown behavior.

The accepted resolver order is:

1. `WEAVER_DESKTOP_SIDECAR` override wins.
2. Bundled sidecar path is preferred when available.
3. Bare `weaver` on `PATH` remains as a development and diagnostics fallback.

The resolver must not change the sidecar contract: it still launches `serve` on
loopback with the current environment variables, session token, log behavior,
health polling, crash handling, and shutdown semantics.

## Options considered

### A. PyInstaller onefile/onedir sidecar

Package the existing Python CLI entrypoint into a Windows executable and include
that executable as a Tauri external binary.

**Pros:**

- Mature and common Python-to-executable toolchain.
- Works with existing Python application shape without rewriting FastAPI.
- Keeps desktop packaging work inside `desktop/` and build orchestration.
- Compatible with a short Windows-first alpha sprint.
- Supports both onefile and onedir tradeoffs.

**Cons:**

- Hidden imports and package data can be missed.
- Onefile startup may be slower because of extraction.
- Output is larger than the current PATH-dependent shell.
- Requires build-step discipline and documented artifact verification.

### B. Keep external `weaver` on `PATH`

Keep Sprint O behavior and require users to install Python plus Weaver separately.

**Pros:**

- No new build tool.
- Small desktop executable.
- Existing behavior already validated in Sprint O.
- Easy rollback path.

**Cons:**

- Does not satisfy Sprint P's objective.
- Poor tester experience for a packaged desktop alpha.
- Makes the desktop package dependent on a mutable external environment.
- Keeps the biggest Sprint O condition open.

### C. Embedded Python distribution

Ship a Python embedded distribution or portable venv with Weaver installed, and
configure the Tauri host to launch the installed `weaver` script or Python module.

**Pros:**

- More transparent runtime layout than a single packed executable.
- Potentially easier to inspect and patch during support.
- Avoids some PyInstaller hidden-import behavior.

**Cons:**

- Larger and more complex file tree.
- More paths to configure and validate.
- More likely to blur install/runtime boundaries.
- Higher maintenance burden for a Windows alpha.

### D. PyOxidizer/Nuitka/future alternatives

Use a more advanced Python compiler/packager to create a smaller or faster binary.

**Pros:**

- Potential for better startup or smaller artifacts.
- May become attractive for release-grade builds after alpha validation.

**Cons:**

- Higher integration risk.
- More likely to expose compatibility issues with Python packages and native
  extensions.
- Too large a toolchain change for the immediate Windows-first alpha objective.
- Not necessary until PyInstaller has been tested and found insufficient.

## Recommended option

Option A, PyInstaller, is accepted for Sprint P, with **onedir** as the first
artifact shape.

Use PyInstaller onedir first because P1/P2 need inspectable packaging evidence
and a lower startup-risk path than onefile. Onefile remains a future optimization
only after the onedir path passes the sidecar contract and packaged-launch gates.

- Build the sidecar artifact in P2 and direct-test it before Tauri wiring.
- Stage the artifact for `bundle.externalBin` in P3.
- Add a minimal Rust resolver in P3 so the host can find the staged binary.
- Keep `WEAVER_DESKTOP_SIDECAR` as the highest-priority override.
- Keep bare `weaver` on `PATH` as fallback for dev and diagnostics.

The current PATH-dependent model remains the rollback path, not the target state.

## Why PyInstaller is proposed for Sprint P

PyInstaller is proposed because Sprint P needs the smallest credible path from
the current validated Sprint O architecture to a self-contained Windows desktop
alpha. It packages the existing FastAPI sidecar instead of creating a new runtime
architecture. That keeps the sprint focused on sidecar delivery and validation,
not on provider behavior, translation workflow, schema changes, or UI redesign.

PyInstaller onedir also gives Sprint P a practical experiment surface:

- Build an executable sidecar.
- Run it directly with the existing `serve` contract.
- Measure artifact size and startup time.
- Register it with Tauri `bundle.externalBin`.
- Resolve the staged binary from the Rust host.
- Validate the packaged app without `.venv\Scripts` on `PATH`.

If PyInstaller fails the launch, security, or lifecycle gates, Sprint P can roll
back to the Sprint O PATH-sidecar baseline and reopen the decision with embedded
Python, Nuitka, PyOxidizer, or another future alternative.

## Consequences

- The desktop alpha can become self-contained for Windows testers.
- Desktop packaging gains a Python sidecar build step.
- Artifact size will increase beyond the Sprint O 3.1 MB shell.
- The release process must validate sidecar package data, static assets, and
  template availability from the bundled executable.
- Build failures now include Python packager failures, not only Rust/Tauri
  failures.
- P3 includes a small Rust resolver change; config-only `externalBin` wiring is
  explicitly insufficient.
- The sidecar contract remains the architectural boundary.

## Security considerations

- Provider secrets must not be bundled into the executable or build artifacts.
- Provider API keys must remain environment/local-secret inputs only.
- `WEAVER_SESSION_TOKEN` must remain runtime-generated and must not appear in
  logs, crash output, or packaged assets.
- The bundled sidecar must bind only to loopback in desktop mode.
- The host must continue to inject `X-Weaver-Session` for protected routes.
- Crash output must remain bounded to a small console tail and must avoid secret
  disclosure.
- No telemetry, update ping, analytics, remote logging, or hosted dependency is
  introduced.
- Build artifacts should be generated from the local source tree and reviewed
  before distribution.

## Packaging / size tradeoffs

Expected tradeoffs to measure in Sprint P:

| Packaging shape | Expected size | Startup | Notes |
| --- | --- | --- | --- |
| PyInstaller onefile | Medium/high | Slower cold start | Simpler distribution, but extraction can exceed health budget |
| PyInstaller onedir | Higher on disk | Faster than onefile | More files, better startup/debuggability |
| PATH sidecar | Small shell | Fast | Not self-contained; rollback only |
| Embedded Python | High | Medium | More explicit runtime tree; more install complexity |

Sprint P should record the actual sidecar artifact size, packaged app size, and
startup behavior in the P2 and P6 handoffs.

## Operational risks

- Missing templates/static files can produce a launched backend with a broken UI.
- Hidden imports can fail only after specific routes are hit.
- Onefile extraction can make `/healthz` exceed the host startup budget.
- Antivirus or SmartScreen may treat the packed executable as suspicious.
- Process naming may make orphan checks less obvious than the Sprint O `weaver`
  process name.
- Tauri `externalBin` naming conventions can differ by platform and target.
- Tauri `externalBin` staging may not expose the runtime path expected by the
  current `std::process::Command` launcher without resolver code.
- Adding `tauri-plugin-shell` would expand dependencies and capability surface;
  Sprint P should avoid it unless the minimal resolver cannot work.
- CI/build machines may lack the required Windows packaging toolchain.

## Rollback plan

Rollback returns to the Sprint O baseline:

1. Remove the Tauri `bundle.externalBin` configuration.
2. Remove or disable the minimal bundled-sidecar resolver.
3. Remove or disable the desktop-local PyInstaller build tooling.
4. Restore the host behavior that resolves `WEAVER_DESKTOP_SIDECAR` or `weaver`
   from `PATH`.
5. Rebuild the desktop package.
6. Re-run the Sprint O packaged smoke with `.venv\Scripts` on `PATH`.
7. Record Sprint P as BLOCKED or PASS-WITH-CONDITIONS with failure evidence.

Rollback must not modify provider code, translation pipeline, schema, QA/export,
or cockpit UI.

## Acceptance criteria

This ADR is accepted for Sprint P implementation under these constraints:

- PyInstaller onedir is the first Windows sidecar packaging candidate.
- The PATH-dependent Sprint O behavior is retained as rollback and fallback, not
  as the final Sprint P target.
- P1 proved a minimal Rust resolver is required; P3 may touch only the resolver
  surface needed to locate the bundled sidecar.
- PyInstaller work remains isolated to desktop packaging/build surfaces.
- `bundle.externalBin` wiring is delayed until after a direct sidecar artifact
  smoke passes.
- Security checks cover secrets, session token leakage, loopback binding, and
  crash-log bounds.

Sprint P can be considered successful when:

- Packaged Windows desktop app launches without `.venv\Scripts` or an external
  `weaver` command on `PATH`.
- The bundled sidecar serves `/healthz` and `/ui`.
- The cockpit loads without a 401 loop.
- Logs are generated in `%APPDATA%\Weaver\logs\`.
- Crash screen still works on startup failure.
- Window close leaves no attributable sidecar orphan.
- `uv run ruff check .` and `uv run pyright` pass.
- Final P6 gate report records artifact sizes, validation evidence, known risks,
  and rollback instructions.

## Related files

- `docs/superpowers/plans/2026-06-14-sprint-p-bundled-sidecar.md`
- `docs/SIDECAR_CONTRACT.md`
- `docs/INSTALL_DESKTOP.md`
- `desktop/README.md`
- `desktop/tauri.conf.json`
- `desktop/src/launch_config.rs`
- `desktop/src/sidecar.rs`
- `desktop/src/lib.rs`
