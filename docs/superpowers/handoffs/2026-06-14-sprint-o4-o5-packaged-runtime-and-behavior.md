# Sprint O4–O5 — Packaged Runtime Smoke, Logs, Crash & Uninstall Behavior

**Date:** 2026-06-14
**Branch:** `feat/sprint-o-desktop-packaging`
**Plan:** [Sprint O](../plans/2026-06-14-sprint-o-desktop-packaging-installer-alpha.md) — commits O4 (smoke) + O5 (behavior docs)
**Type:** Docs only. No app/runtime/bundle-config or Python changes.

---

## 1. O4 — packaged runtime smoke result (✅ PASS, owner-confirmed)

The **packaged** `weaver-desktop.exe` (built in O3, 3.1 MB, `target/release/`) was
launched on Windows with `.venv\Scripts` on `PATH` and exercised end-to-end.

| Check | Result | Evidence |
|---|---|---|
| **O-V2** launch + loading → cockpit `/ui` | ✅ | loading screen transitioned to the cockpit |
| **O-V4** `/healthz` 200 → `/ui` 200, no 401 loop | ✅ | `sidecar.console.log`: `GET /healthz 200`, `GET /ui 200`, static assets `200`, **no repeated 401** |
| **O-V5** clean shutdown, no orphan | ✅ | clean-baseline retry: no lingering `weaver.exe`/`python.exe` after closing the app |
| **O-V6** logs generated | ✅ | `runtime.log` + `sidecar.console.log` under `%APPDATA%\Weaver\logs\` |
| **O-V7** forced-failure crash screen | ✅ | bad `WEAVER_DESKTOP_SIDECAR` → crash window: *"Weaver could not start" / "could not start the cockpit … os error 3"* + showed the `sidecar.console.log` path |

**O-V1** (build) was closed in O3. This makes the packaged-exe lifecycle equivalent
to the Sprint N dev-shell lifecycle (N1–N6) — now reproduced from the **built
binary**, not `cargo tauri dev`.

> Validation type: **owner-confirmed**. Visual checks (O-V2, O-V7) and the
> orphan/log checks were observed/run by the owner; artifacts were not pasted into
> the repo. Sufficient for an alpha gate; a future hardening pass can attach the
> raw `sidecar.console.log` tail + orphan-check output.

---

## 2. Log locations (O5)

The packaged shell writes to the standard Windows app-data location. Two writers,
by design (see `desktop/README.md` "Why the host writes `sidecar.console.log`"):

| File | Writer | Contents |
|---|---|---|
| `%APPDATA%\Weaver\logs\runtime.log` | cockpit (Python) | structured cockpit runtime events (rotating handler) |
| `%APPDATA%\Weaver\logs\sidecar.console.log` | host (Tauri) | tee of the sidecar child's stdout/stderr — `GET /healthz 200`, `GET /ui 200`, tracebacks on failure |

Other cockpit log files defined by the Sidecar Contract (§8) — `backend.log`,
`job.log`, `export.log`, `provider.log` — are produced by the child as activity
occurs; they live in the same `logs_dir`. **API keys never appear in any log file**
(contract §8.5, regression-tested).

Inspect:

```powershell
Get-Content "$env:APPDATA\Weaver\logs\sidecar.console.log" -Tail 20
Get-ChildItem "$env:APPDATA\Weaver\logs\" | Select-Object Name,Length
```

---

## 3. Crash behavior (O5)

On any startup failure the host shows a **crash window** (`dist/crash.html`) with a
mapped exit code and the last ≤50 stderr lines, plus the `sidecar.console.log`
path. Verified in O-V7 by pointing `WEAVER_DESKTOP_SIDECAR` at a non-existent path:

```text
Weaver could not start
could not start the cockpit … os error 3      (Windows: file not found)
<path to sidecar.console.log>
```

Exit-code mapping (host `lib.rs::exit_meaning`, contract §5): `0` clean · `64`
config/bind · `65` port-in-use · `66` data-dir (reserved). The "could not start …
os error 3" case is a spawn failure (binary not found) — surfaced before an exit
code exists, so the crash screen shows the OS error text instead of a mapped code.

---

## 4. Uninstall / cleanup expectations — alpha (O5)

| Item | Alpha behavior | Rationale |
|---|---|---|
| App binary | Portable `weaver-desktop.exe`: delete the file. NSIS installer (if later built): standard uninstall removes the binary. | No installer is a Sprint O gate; portable exe is self-contained. |
| Running processes | Closing the window before uninstall leaves **no orphan** (O-V5). Uninstalling while running is not expected; close first. | Graceful `taskkill /T`→`/F` path owns shutdown. |
| **User data + logs** | `%APPDATA%\Weaver\` (projects, DB, logs) **remains** after uninstall unless the user removes it manually. | **Intentional, acceptable for alpha** — this directory holds the user's novels/translations; an alpha must never silently delete user data. |
| Python sidecar | Not installed by the package (PATH dependency); uninstall does not touch the user's Python/venv. | Sidecar is external in the alpha (see §5). |

Manual data removal (user's choice): `Remove-Item "$env:APPDATA\Weaver" -Recurse`.

---

## 5. Current limitation — external sidecar (G2) (O5)

The packaged alpha still **depends on `weaver` being resolvable** — either
`.venv\Scripts` on `PATH` or `WEAVER_DESKTOP_SIDECAR` pointing at the binary. On a
clean machine **without** the Python side installed, launch fails into the crash
screen ("could not start the cockpit … os error 3"), exactly as O-V7 demonstrated.

- **Acceptable for alpha**, but must be stated plainly to testers.
- **Standalone bundled Python** (PyInstaller → `bundle.externalBin`) is **future
  work**, not Sprint O. It is the headline follow-up that turns this into a true
  single-install distributable.

---

## 6. Gap status after O4–O5

| Gap (from O1) | Status |
|---|---|
| G1 build unproven | ✅ closed (O3) |
| G6 Cargo.lock | ✅ closed (O3) |
| G2 PATH-only sidecar | 🟡 **documented** (this doc §5); resolution = future bundled-Python sprint |
| G3 uninstall data-retention | ✅ **documented** (§4) — data preserved by design |
| G4 no `bundle.windows` block | 🟡 defaults validated by O4 run; documented |
| G5 no NSIS target | 🟡 portable exe is the gate; NSIS optional/deferred |
| G7 `INSTALL_DESKTOP.md` drift | ✅ reconciled — runtime-validated note + uninstall line added |

---

## Handoff

**Track:** T9/T0 (Sprint O), behavior-docs stage
**Scope:** Record the packaged runtime smoke (O4) and document logs/crash/uninstall/limitations (O5).
**Files/Areas Touched:** this doc; targeted additions to `INSTALL_DESKTOP.md`. No code/config.
**What Changed:** O4 PASS evidence recorded; log/crash/uninstall/limitation behavior documented; `INSTALL_DESKTOP.md` reconciled with actual validated behavior.
**What Was Intentionally Not Changed:** `tauri.conf.json`, `desktop/src/*.rs`, Python core, schema, cockpit UI. No signing/auto-update/bundled-Python/cross-platform work.
**Validation Performed:** O4 owner-confirmed PASS (O-V2/4/5/6/7); `uv run ruff check .` + `uv run pyright` clean (no Python touched).
**Known Risks:** G2 — alpha crashes on a machine without an external `weaver`; this is the gating condition for the O6 verdict.
**Recommended Next Role / Next Step:** O6 — finalize the Sprint O gate report; expected verdict **PASS-WITH-CONDITIONS** (launches/runs, but PATH-sidecar + no signing/auto-update/installer-final remain).
