# Sprint O3 — Windows `app` Build Result + Cargo.lock Decision

**Date:** 2026-06-14
**Branch:** `feat/sprint-o-desktop-packaging`
**Plan:** [Sprint O](../plans/2026-06-14-sprint-o-desktop-packaging-installer-alpha.md) — commit O3
**Closes:** audit gap **G1** (build unproven) and **G6** (Cargo.lock ambiguity).

---

## 1. What was run

```powershell
cd desktop
cargo tauri build        # release profile + `app` (portable exe) bundle target
```

Non-interactive (build only, no window). Toolchain: tauri-cli 2.11.2, rustc 1.96.0,
MSVC linker present.

---

## 2. Result — ✅ PASS (O-V1)

```text
Finished `release` profile [optimized] target(s) in 4.63s
Info application at: D:\DevSpace\Projects\weaver\desktop\target\release\weaver-desktop.exe
weaver-desktop.exe → 3.1 MB
exit code 0
```

- **G1 closed:** the **MSVC link step works** and a real portable executable is
  produced. `cargo check` (Q2F) → `cargo tauri build` (O3) now both green.
- **`app` target = the exe itself.** Tauri 2's `app` target emits
  `target/release/weaver-desktop.exe` directly; there is **no** `bundle/` subtree
  (that appears only for `nsis`/`msi`/`dmg` targets). The ~3.1 MB size matches the
  estimate in `INSTALL_DESKTOP.md`.
- **3 warnings** — the pre-existing dead code in `sidecar.rs` (`POLL_INTERVAL`
  unused; `log_path` field/accessor unused). They do **not** affect the build and
  are an audit-phase cleanup item, **not** an O3 concern (no Rust code changed here).

> This proves the package **builds and exists**. It does **not** yet prove it
> **installs/launches/runs** on a clean machine — that is the O4 install-launch
> smoke (O-V2–O-V7), still pending, and is gated by the G2 PATH-sidecar reality.

---

## 3. Cargo.lock decision — committed (G6 resolved)

**Before:** `desktop/Cargo.lock` was **ignored** (in `desktop/.gitignore`) **and
untracked** — inconsistent for a crate that produces a distributable binary.

**Decision (owner-approved):** **commit it.** A shipped binary must build from a
reproducible, pinned dependency graph across machines.

**Change:** removed the `Cargo.lock` ignore line in `desktop/.gitignore` (replaced
with a comment explaining why it is tracked) and added `desktop/Cargo.lock`.

- Locked graph: **436 packages**.
- Key pins (match O1 audit + Q2F `cargo tree`): `tauri 2.11.2`,
  `webview2-com 0.38.2`, `windows 0.61.3`.

---

## 4. Updated gap status (from O1)

| Gap | O1 state | After O3 |
|---|---|---|
| G1 — `cargo tauri build` never run | open (H) | ✅ **closed** — exe builds, 3.1 MB |
| G6 — Cargo.lock ignored-but-tracked | open (L) | ✅ **closed** — committed, reproducible |
| G2 — PATH-only sidecar | open (H) | still open → O5 doc / next sprint |
| G3 — uninstall data-retention | open (H) | still open → O5 |
| G4 — no `bundle.windows` block | open (M) | still open (defaults OK for alpha) → O5 doc |
| G5 — no NSIS target | open (L) | still open (portable exe is the gate) |
| G7 — `INSTALL_DESKTOP.md` drift | open (M) | still open → O5 reconcile |

---

## Handoff

**Track:** T9 (Sprint O), build stage
**Scope:** Run the first real `cargo tauri build`; settle the Cargo.lock policy.
**Files/Areas Touched:** `desktop/.gitignore` (un-ignore Cargo.lock),
`desktop/Cargo.lock` (now tracked), this doc. **No** `src/`, **no** `tauri.conf.json`,
**no** `desktop/src/*.rs`.
**What Changed:** proved the Windows `app` build (exe at `target/release/`); committed
the lockfile for reproducibility.
**What Was Intentionally Not Changed:** app/runtime code, bundle config, Python core.
The 3 `sidecar.rs` dead-code warnings were left as-is (audit cleanup, not O3).
**Validation Performed:** `cargo tauri build` exit 0, 4.63s, `weaver-desktop.exe` 3.1 MB
present; lockfile pins cross-checked (tauri/webview2-com/windows).
**Known Risks:** build ≠ runs-on-clean-machine. G2 (PATH sidecar) means the alpha will
crash on a machine without `weaver` on PATH — the O4 smoke must be run with the venv on
PATH, and O5 must document the prerequisite.
**Recommended Next Role / Next Step:** O4 — run the **install-launch smoke** against
`target/release/weaver-desktop.exe` (O-V2–O-V7), with `weaver` on PATH, and capture the
log/orphan evidence.
