# Sprint O — Desktop Packaging / Installer Alpha

**Date opened:** 2026-06-14
**Branch (proposed):** `feat/sprint-o-desktop-packaging`
**Predecessor:** Q2F **PASS** · Sprint N runtime smoke **complete** (N1–N6 owner-confirmed)
**Owner role:** Release Captain (T9) + Backend/Desktop (T3 within `desktop/`)
**Type:** **Planning only.** This document defines scope; it does **not** implement packaging.

---

## 1. Executive summary

Sprint N proved the Tauri shell **runs**: it spawns the FastAPI sidecar, loads the
cockpit, injects the session header, shuts down without orphans, writes logs, and
shows a crash screen. Sprint O turns that working dev shell into a **Windows-first
installable alpha** — a package a user can install, launch, and uninstall cleanly,
with the sidecar lifecycle intact.

**Alpha, not release.** The goal is a *distributable that works*, not a signed,
auto-updating, cross-platform product. Code signing, auto-update, and macOS/Linux
remain deferred (see [§4](#4-non-goals)). Weaver stays **local-first, no telemetry**;
FastAPI stays the **sidecar** (no rewrite). Much of the operator knowledge already
exists in [`INSTALL_DESKTOP.md`](../../INSTALL_DESKTOP.md) — Sprint O **validates and
hardens** it rather than re-inventing it.

---

## 2. Current readiness baseline (from Q2F + Sprint N)

| Surface | State entering Sprint O | Source |
|---|---|---|
| Rust host compiles | ✅ `cargo check` 0 errors; pins resolve (`webview2-com 0.38.2`, `windows 0.61.3`, `tauri 2.11.2`) | Q2F gate report |
| Runtime lifecycle | ✅ N1–N6 owner-confirmed (`cargo tauri dev`) | Sprint N |
| `tauri.conf.json` | `bundle.active: true`, `targets: ["app"]`, `productName "Weaver"`, `version "0.7.0"`, `identifier dev.weaver.desktop`, 3 icons declared | `desktop/tauri.conf.json` |
| Capabilities | `core:default` only; windows `loading`/`main`/`crash`; no IPC bridge | `desktop/capabilities/default.json` |
| Icons | `32x32.png`, `128x128.png`, `icon.ico` present | `desktop/icons/` |
| Sidecar resolution | `weaver` via `PATH` (or `WEAVER_DESKTOP_SIDECAR`); **no bundled Python yet** | `desktop/README.md`, `sidecar.rs` |
| Installer doc | Portable `app` + NSIS path, smoke test, bundling plan already drafted | `INSTALL_DESKTOP.md` |

**Key gap Sprint O must confront:** the package launches `weaver` from `PATH`. An
installed alpha on a clean machine has **no `weaver` on PATH** unless the user
installed the Python side separately. Sprint O must explicitly choose and document
the alpha's sidecar-delivery assumption (see [§6](#6-installerpackage-assumptions)).

---

## 3. Sprint O goals

A Windows-first packaged desktop alpha that can:

1. **Install** — produce a portable `.exe` (and optionally an NSIS installer) from
   `cargo tauri build`.
2. **Launch** — double-click starts the shell; loading window appears.
3. **Start the sidecar** — the packaged shell finds and spawns `weaver serve`.
4. **Load the cockpit** — WebView reaches `/ui` with the session header (no 401).
5. **Write logs** — `runtime.log` + `sidecar.console.log` in `%APPDATA%\Weaver\logs\`.
6. **Shut down cleanly** — window close → no orphan `weaver`/`python`/`uvicorn`.
7. **Uninstall cleanly** — removal leaves no running process; app-data removal is
   documented (data is the user's, so uninstall should not silently delete novels).

---

## 4. Non-goals

Explicitly **out of scope** for Sprint O (fence against scope creep):

- **No auto-update final** — no updater endpoint, no signing-key infra.
- **No code-signing final** — SmartScreen warning is accepted for the alpha; signing
  is *planned/documented* only.
- **No cross-platform final** — Windows-first; macOS/Linux deferred.
- **No provider rewrite**, **no translation-pipeline change**, **no QA/export change**,
  **no schema change**, **no cockpit redesign**.
- **No new runtime dependency** in Python core. Packaging tooling lives in `desktop/`
  / CI, not in `src/weaver/`.
- **No telemetry / phone-home** introduced by the installer.

---

## 5. Commit sequence (O1–O6)

One concern per commit. T0 docs run alongside; T6/T7/T8 gate before the O6 report.

| # | Commit (conventional) | Scope | Likely files | Gate |
|---|---|---|---|---|
| **O1** | `docs(desktop): audit packaging config and toolchain status` | Read-only audit of `tauri.conf.json`, `Cargo.toml`, `capabilities/`, `build.rs`, icons, `INSTALL_DESKTOP.md`; record what's ready vs missing for a build | new `docs/superpowers/handoffs/…-sprint-o-packaging-audit.md` | T0 |
| **O2** | `docs(desktop): validate bundle metadata and icons` | Verify `productName`/`version`/`identifier` match `pyproject.toml`; confirm icon set is complete for the `app` target; document any `cargo tauri icon` regen needed | `docs/…`, *(only if a mismatch: `desktop/tauri.conf.json` metadata — minimal)* | T0/T6 |
| **O3** | `chore(desktop): windows installer alpha config` | The one build-config commit: confirm/adjust `bundle.targets` (`app`, optional `nsis`), NSIS block if used, output naming. **No app logic.** | `desktop/tauri.conf.json` *(bundle block only)* | T6/T7 |
| **O4** | `docs(desktop): install-launch smoke checklist` | A packaged-binary analog of `DESKTOP_SMOKE_CHECKLIST.md` §4 — install → launch → sidecar → `/ui` → logs → shutdown, run against `target/release/weaver-desktop.exe` | new `docs/DESKTOP_INSTALL_SMOKE.md` (or section in `INSTALL_DESKTOP.md`) | T6 |
| **O5** | `docs(desktop): logs, crash, and uninstall behavior` | Document log locations, crash-screen behavior in a packaged context, and uninstall/data-retention semantics; reconcile `INSTALL_DESKTOP.md` known-limitations | `INSTALL_DESKTOP.md` | T0/T7 |
| **O6** | `docs(desktop): sprint O gate report` | Final verdict: PASS / PASS-WITH-CONDITIONS / BLOCKED, with the §7 matrix evidence | new `docs/superpowers/handoffs/…-sprint-o-gate.md` | T9 |

> O1, O2, O4, O5, O6 are **docs**. Only **O3** touches config, and only the
> `bundle` block of `tauri.conf.json`. No `src/weaver/` or `desktop/src/` changes
> are planned; a packaging bug requiring a Rust edit triggers the §9 fix policy.

---

## 6. Installer / package assumptions

Decisions to lock in **O1**, documented in **O5**:

1. **Target format (alpha):** portable `app` `.exe` first (`cargo tauri build` →
   `target/release/weaver-desktop.exe`). NSIS installer is *optional* and only if
   NSIS is installed; it is not a Sprint O gate.
2. **Sidecar delivery (the load-bearing choice):** the alpha assumes **`weaver` on
   `PATH`** (same model as `cargo tauri dev`). Bundled-Python (PyInstaller →
   `bundle.externalBin`) is **evaluated and documented but not built** in Sprint O —
   it is the headline candidate for the *next* sprint. The alpha's README must state
   the prerequisite plainly so a tester isn't surprised by a "sidecar not found" crash.
3. **App-data location:** `%APPDATA%\Weaver\` (already used by the shell). Uninstall
   must **not** delete this by default — it holds the user's projects.
4. **Identity:** `productName Weaver`, `identifier dev.weaver.desktop`, `version`
   tracks `pyproject.toml` (currently `0.7.0`). O2 confirms they match.
5. **Permissions:** keep `core:default` only — no new capability/IPC surface for the
   alpha (security stance preserved).

---

## 7. Windows-first validation matrix

Run against the **packaged binary** (not `cargo tauri dev`). Maps to Sidecar Contract
clauses; reuses the N-pattern from Sprint N.

| ID | Check | Method | Pass evidence |
|---|---|---|---|
| **O-V1** | `cargo tauri build` produces `weaver-desktop.exe` | build | `target/release/weaver-desktop.exe` exists; link step OK (MSVC) |
| **O-V2** | Installed/portable exe launches; loading window appears | run | window paints (≈ N1) |
| **O-V3** | Sidecar spawns from the packaged context | run + log | `weaver serve` child appears; `sidecar.console.log` created |
| **O-V4** | Cockpit `/ui` loads, no 401 | log | `GET /healthz 200` → `GET /ui 200`, zero `401` (≈ N2/N3) |
| **O-V5** | Clean shutdown, no orphan | process | `Get-Process` finds no `weaver`/`python`/`uvicorn` after close (≈ N4) |
| **O-V6** | Logs present | file | `runtime.log` + `sidecar.console.log` in `%APPDATA%\Weaver\logs\` (≈ N5) |
| **O-V7** | Crash screen when sidecar missing | run | bad/empty PATH → crash window with mapped exit code (≈ N6) |
| **O-V8** | Uninstall leaves no process; data retained | run | no orphan post-uninstall; `%APPDATA%\Weaver\` projects preserved |
| **O-V9** | SmartScreen behavior documented | run | unsigned-warning path noted (expected; not a fail) |

---

## 8. Risk register

| Risk | Sev | Mitigation | Status |
|---|---|---|---|
| Installed exe has no `weaver` on PATH → instant crash | **H** | Document prerequisite loudly (O5); crash screen already explains "sidecar not found"; bundled-Python is next sprint | Open |
| MSVC linker missing on a build machine | M | `cargo tauri build` blocked-by-toolchain; document install step | Open |
| `bundle.active`/targets drift vs docs (already seen in Q2F) | M | O2 reconciles config ↔ `INSTALL_DESKTOP.md`; single source of truth | Open |
| Uninstall deletes user projects in `%APPDATA%\Weaver\` | **H** | Uninstall must not touch data dir by default; document explicitly (O5) | Open |
| SmartScreen blocks unsigned alpha on testers' machines | M | Expected for alpha; document the "More info → Run anyway" path; signing deferred | Accepted |
| NSIS not installed → installer target fails | L | Portable `app` is the gate; NSIS optional | Open |
| Packaging changes accidentally touch `src/weaver/` | M | Scope fence: Sprint O edits live in `desktop/` + docs only | Open |

---

## 9. Minimal fix policy

- A validation failure is fixed with the **smallest change in the owning area**:
  build/link → toolchain doc; metadata mismatch → `tauri.conf.json` field; sidecar
  resolution → `desktop/src/` (justified, ≤ small), never Python core.
- **No feature work, no refactors, no new deps.** Adjusting `bundle` config or a
  version field is configuration, not a new dependency.
- Any edit to `desktop/src/*.rs` requires a one-line justification in the O6 report
  and must not change the runtime contract validated in Sprint N.
- Toolchain-class failures = **blocked-by-toolchain** with the install command, not
  a code fix.
- Re-run the affected O-V check **plus O-V5 (orphan)** as regression after any fix.

---

## 10. Definition of Done

Sprint O is **Done** when:

- [ ] O-V1–O-V7 green against the **packaged** binary, with evidence captured.
- [ ] O-V8 (uninstall: no orphan, data retained) verified and documented.
- [ ] O-V9 SmartScreen behavior documented (expected, not blocking).
- [ ] `tauri.conf.json` bundle config + `INSTALL_DESKTOP.md` reconciled (no drift).
- [ ] Sidecar-delivery assumption for the alpha stated plainly in the install doc.
- [ ] No change to `src/weaver/` provider/translation/QA/export/schema/cockpit-UI.
- [ ] `uv run ruff check .` + `uv run pyright` still clean (Python untouched, confirm).
- [ ] O6 gate report written with verdict + known gaps.
- [ ] CLAUDE.md/AGENTS.md §2 updated to Sprint O status at the gate.

**Verdict definitions:** **PASS** = O-V1–O-V8 green on a packaged alpha ·
**PASS-WITH-CONDITIONS** = launches + runs but a documented gap remains (e.g.
PATH-dependent sidecar) · **BLOCKED** = build/toolchain prevents a package.

---

## 11. What remains after Sprint O

Deferred to **future sprints** (named here so they're not silently dropped):

- **Bundled-Python sidecar** (PyInstaller → `bundle.externalBin`) — single-file
  install with no separate Python prerequisite. Highest-value follow-up.
- **Code signing** (Authenticode cert) — removes SmartScreen warning.
- **Auto-update** — Tauri updater + signed release feed.
- **Cross-platform** — macOS `.app` (WKWebView header injection) + Linux WebKitGTK;
  the `webview_session.rs` no-op becomes real work here.
- **Production release hardening** — versioned release notes, CI build pipeline,
  reproducible builds.

---

## Handoff

**Track:** T9 (Release & Final Gate), planning stage
**Scope:** Define — not implement — the Windows-first desktop packaging alpha.
**What changed:** This plan only. No code, no config.
**What was intentionally not changed:** All of `src/weaver/`, `desktop/src/`,
`tauri.conf.json` (O3 will touch only the bundle block, in execution).
**Validation performed:** Baseline read of `tauri.conf.json`, `capabilities/default.json`,
`build.rs`, icons, `INSTALL_DESKTOP.md`; cross-checked against Q2F gate report + Sprint N.
**Known risks:** §8 — PATH-dependent sidecar and uninstall-data-retention are the two
high-severity items to resolve before calling the alpha usable.
**Recommended next step:** Open the branch `feat/sprint-o-desktop-packaging` and start
**O1 (packaging audit)** — read-only, no build — to lock the §6 assumptions.
