# Sprint O1 — Packaging Config & Toolchain Audit

**Date:** 2026-06-14
**Branch:** `feat/sprint-o-desktop-packaging` (stacked on `chore/tauri-sidecar-readiness`)
**Type:** Read-only audit. No build run, no config changed.
**Plan:** [Sprint O](../plans/2026-06-14-sprint-o-desktop-packaging-installer-alpha.md) — commit O1.

---

## 1. Purpose

Establish the factual starting state for Windows packaging: what is already
configured for a `cargo tauri build` (`app` target), and what is missing or
must be decided before the alpha can install/launch on a tester's machine.
Grounds the §6 assumptions in the Sprint O plan with concrete file evidence.

---

## 2. Config inventory (actual, as read 2026-06-14)

| File | Relevant fields | Value |
|---|---|---|
| `desktop/tauri.conf.json` | `productName` / `version` / `identifier` | `Weaver` / `0.7.0` / `dev.weaver.desktop` |
| | `build.frontendDist` | `./dist` |
| | `app.windows` / `withGlobalTauri` / `security.csp` | `[]` (created at runtime) / `false` / `null` |
| | `bundle.active` / `bundle.targets` | `true` / `["app"]` |
| | `bundle.icon` | `32x32.png`, `128x128.png`, `icon.ico` |
| `desktop/capabilities/default.json` | `permissions` / `windows` | `core:default` / `loading`,`main`,`crash` |
| `desktop/build.rs` | — | stock `tauri_build::build()` |
| `desktop/Cargo.toml` | `[profile.release]` | `lto`, `strip`, `panic="abort"`, `opt-level="s"`, `codegen-units=1` |
| | Windows pins | `webview2-com 0.38.2`, `windows 0.61.3` (Q2F-verified resolve) |
| `desktop/icons/` | files | `32x32.png`, `128x128.png`, `icon.ico` — present |
| `desktop/dist/` | files | `loading.html`, `crash.html` — present, force-committed |
| `pyproject.toml` | `name` / `version` / entry | `weaver` / `0.7.0` / `weaver = "weaver.cli.main:app"` |

---

## 3. Ready for a Windows `app` build

- ✅ **Rust host compiles** (`cargo check` 0 errors, Q2F) and pins resolve.
- ✅ **Runtime validated** end-to-end (Sprint N N1–N6).
- ✅ **`bundle.active: true`** with the **`app`** (portable exe) target set.
- ✅ **Icon set complete** for the `app` target (`32`, `128`, `.ico`).
- ✅ **`frontendDist` assets committed** — `loading.html` + `crash.html` are
  force-included despite the root `dist/` ignore (correct; the shell needs them).
- ✅ **Identity matches `pyproject`** — `Weaver` / `0.7.0` / `dev.weaver.desktop`;
  no O2 metadata edit needed unless `pyproject` version bumps.
- ✅ **Minimal capability surface** — `core:default` only, no IPC; security stance
  from Sprint N preserved into packaging.
- ✅ **Release profile optimized** — `lto` + `strip` + `panic=abort` → small exe.

---

## 4. Missing / to decide before the alpha is usable

| # | Gap | Severity | Resolved in |
|---|---|---|---|
| G1 | **`cargo tauri build` never run** — `cargo check` passed but the **link step** (needs MSVC C++ Build Tools) and a real exe are unproven (O-V1 open) | H | O3/O4 |
| G2 | **Sidecar delivery is PATH-only** — no `externalBin`/bundled Python; a clean machine without `weaver` on PATH crashes at startup | H | O5 (document) / next sprint (bundle) |
| G3 | **Uninstall + data-retention semantics undocumented** — must guarantee `%APPDATA%\Weaver\` projects are **not** deleted on uninstall | H | O5 |
| G4 | **No `bundle.windows` block** — WebView2 install mode and exe naming use Tauri defaults; fine for alpha but should be documented | M | O3 (confirm) / O5 (doc) |
| G5 | **No NSIS target configured** (`targets: ["app"]` only) — portable exe is the gate; NSIS installer optional | L | O3 (optional) |
| G6 | **`Cargo.lock` is `.gitignore`d yet tracked** in `desktop/` — reproducibility ambiguity for packaged builds | L | O3 note (decide: commit lock or not) |
| G7 | **`INSTALL_DESKTOP.md` may drift from actual config** (already saw `bundle.active` drift in Q2F) — needs reconcile against this inventory | M | O5 |

---

## 5. Findings → decisions to lock (feeds Sprint O §6)

1. **Alpha format:** portable `app` `.exe` is the gate; NSIS optional (G5). ✅ matches plan.
2. **Sidecar:** ship PATH-dependent, **document the prerequisite loudly** (G2); bundled
   Python is the next sprint, not Sprint O.
3. **Uninstall:** must preserve `%APPDATA%\Weaver\` data by default (G3) — highest-risk
   user-facing behavior.
4. **Cargo.lock (G6):** decide in O3 whether to commit it for reproducible packaged
   builds (recommended for a distributable) — currently ignored-but-tracked, which is
   inconsistent.
5. **Build proof (G1):** the single most important next executable step is a real
   `cargo tauri build` to produce `target/release/weaver-desktop.exe` and confirm the
   MSVC link path. Scheduled for O3/O4, not run in this read-only audit.

---

## Handoff

**Track:** T9/T0 (Sprint O, audit stage)
**Scope:** Read-only audit of packaging config + toolchain readiness.
**Files/Areas Touched:** this doc only. No config, no build, no `src/`.
**What Changed:** nothing in code/config — inventory + gap list recorded.
**What Was Intentionally Not Changed:** `tauri.conf.json`, `Cargo.toml`, `src/weaver/`,
`desktop/src/`. No `cargo tauri build` executed (deferred to O3/O4 per plan).
**Validation Performed:** direct read of `tauri.conf.json`, `capabilities/default.json`,
`build.rs`, `Cargo.toml`, `icons/`, `dist/`, `.gitignore`, `pyproject.toml`; identity
cross-check (Weaver/0.7.0/dev.weaver.desktop) confirmed matching.
**Known Risks:** G1–G3 are the high-severity items (unbuilt, PATH-sidecar, uninstall data).
**Recommended Next Role / Next Step:** O2 — validate bundle metadata/icons (likely a
no-op confirmation given identity already matches), then O3 to run the first real
`cargo tauri build` and lock the Cargo.lock decision.
