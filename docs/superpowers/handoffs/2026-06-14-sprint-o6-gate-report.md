# Sprint O — Desktop Packaging / Installer Alpha — Gate Report (O6)

**Date:** 2026-06-14
**Branch:** `feat/sprint-o-desktop-packaging` (stacked on `chore/tauri-sidecar-readiness`)
**Predecessor:** Q2F PASS · Sprint N complete
**Verdict:** 🟡 **PASS-WITH-CONDITIONS** *(final — owner sign-off 2026-06-14)*

---

## 1. Executive summary

Sprint O produced a **Windows-first packaged desktop alpha**. The portable
`weaver-desktop.exe` (3.1 MB) **builds** (O3) and **runs end-to-end** (O4): it
spawns the FastAPI sidecar, loads the cockpit, writes logs, shuts down without
orphans, and shows a crash screen on failure. The alpha is **usable for testing**.

It is **not** a finished product: the packaged exe still depends on an **external
`weaver`** (`.venv\Scripts` on `PATH`), and signing / auto-update / final installer
are out of scope. Hence **PASS-WITH-CONDITIONS**, not PASS.

---

## 2. Commit sequence executed

| # | Commit | Status |
|---|---|---|
| O1 | `docs(desktop): audit packaging config and toolchain status` (`4576247`) | ✅ |
| O2 | metadata validation — folded into O1 (identity `Weaver`/`0.7.0`/`dev.weaver.desktop` already matches `pyproject`) | ✅ (no-op) |
| O3 | `chore(desktop): windows app build verified; commit Cargo.lock` (`8a1c68e`) | ✅ |
| O4 | packaged runtime smoke — owner-confirmed PASS (this report §3) | ✅ |
| O5 | packaged runtime/logs/crash/uninstall behavior docs | ✅ |
| O6 | this gate report | ✅ |

---

## 3. Validation matrix — evidence

| ID | Check | Result | Source |
|---|---|---|---|
| O-V1 | `cargo tauri build` → `weaver-desktop.exe` | ✅ PASS (exit 0, 4.63s, 3.1 MB) | O3 |
| O-V2 | launch → loading → cockpit `/ui` | ✅ PASS | O4 |
| O-V3 | sidecar spawns from packaged context | ✅ PASS (implied by O-V4 logs) | O4 |
| O-V4 | `/healthz` 200 → `/ui` 200, no 401 loop | ✅ PASS | O4 |
| O-V5 | clean shutdown, no orphan | ✅ PASS (clean-baseline retry) | O4 |
| O-V6 | `runtime.log` + `sidecar.console.log` present | ✅ PASS | O4 |
| O-V7 | crash screen on forced failure | ✅ PASS ("os error 3" + log path) | O4 |
| O-V8 | uninstall: no orphan, data retained | 🟡 documented, not executed (no installer built) | O5 §4 |
| O-V9 | SmartScreen behavior | 🟡 expected/documented (unsigned alpha) | O5 / known-limits |

Validation type: **owner-confirmed** (visual + process/log checks run by the owner;
raw artifacts not archived in-repo — acceptable for alpha).

---

## 4. Conditions remaining (why not full PASS)

1. **External sidecar (G2).** Packaged exe needs `weaver` on `PATH` /
   `WEAVER_DESKTOP_SIDECAR`. Clean machine without Python → crash screen. Resolution:
   bundled-Python (PyInstaller) — **future sprint**.
2. **No code signing.** SmartScreen warns on first run. Cert + signing deferred.
3. **No auto-update.** Manual download + reinstall.
4. **No final installer.** Portable `app` exe is the gate; NSIS optional, not built.
5. **O-V8 not executed.** Uninstall behavior is documented (data retained by design)
   but not run against a real installer (none built this sprint).

---

## 5. Scope adherence

- ✅ No change to provider logic, translation pipeline, QA, export, schema, or cockpit UI.
- ✅ No `desktop/src/*.rs` runtime change; Sprint N contract intact.
- ✅ Only config touched: `desktop/.gitignore` (un-ignore Cargo.lock) + added
  `desktop/Cargo.lock`. `tauri.conf.json` unchanged (defaults validated by O4).
- ✅ FastAPI remains the sidecar; local-first / no telemetry preserved.
- ✅ `uv run ruff check .` + `uv run pyright` clean (Python untouched).

---

## 6. Known gaps / deferred (post-Sprint O)

- **Bundled-Python standalone sidecar** (PyInstaller → `bundle.externalBin`) — #1 follow-up.
- **Code signing** (Authenticode).
- **Auto-update** (Tauri updater + signed feed).
- **NSIS installer** + real **O-V8 uninstall** run.
- **Cross-platform** (macOS WKWebView / Linux WebKitGTK header injection).
- **`sidecar.rs` dead-code cleanup** (`POLL_INTERVAL`, `log_path`) — audit-phase item.

---

## 7. Recommendation

Sprint O accepted as **PASS-WITH-CONDITIONS** (owner sign-off 2026-06-14): the
Windows packaged alpha installs (as a portable exe), launches, runs the cockpit, and
cleans up — sufficient for internal alpha testing. The remaining conditions are the
external `weaver` PATH dependency and the deferred signing / auto-update / final
installer.

**Next sprint: Sprint P — Bundled Sidecar / Standalone Desktop Alpha.** Goal: remove
the `.venv\Scripts`-on-PATH requirement via a bundled-Python standalone sidecar
(PyInstaller → `bundle.externalBin`). This closes the single biggest condition (G2)
and is the prerequisite for any "release"-grade installer, signing, and auto-update
work — none of which start before the sidecar is self-contained.

> **Status updated 2026-06-14:** CLAUDE.md / AGENTS.md §2 mark Sprint O
> **PASS-WITH-CONDITIONS** with Sprint P as next.
