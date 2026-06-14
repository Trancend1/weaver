# Sprint N — Desktop Runtime Validation

**Date opened:** 2026-06-14
**Branch:** `chore/tauri-sidecar-readiness` (or `feat/sprint-n-runtime-validation`)
**Predecessor:** Q2F — [readiness gate](../handoffs/2026-06-14-q2f-sidecar-readiness-gate.md) → PASS-WITH-CONDITIONS
**Owner role:** Release Captain (T9) + QA (T6)
**Type:** Validation-only. **No build tracks. No new code unless a smoke failure demands the smallest fix.**

---

## 1. Executive summary

Q2F proved the desktop shell **compiles** (`cargo check` 0 errors, Windows pins
resolve) and the FastAPI sidecar **honors the contract over HTTP** (32 tests). The
one open condition is the **interactive runtime smoke**: `cargo tauri dev` has
never spawned the real sidecar, opened the native WebView, and exercised the
no-orphan shutdown. Sprint N executes
[`DESKTOP_SMOKE_CHECKLIST.md` §4](../../DESKTOP_SMOKE_CHECKLIST.md#4-runtime-launch-smoke--cargo-tauri-dev)
on a real Windows desktop, captures evidence for N1–N5, and — if green — promotes
Q2F from **PASS-WITH-CONDITIONS** to **PASS**.

**Scope fence (non-goals):** no installer / NSIS, no code signing, no auto-update,
no bundled-Python sidecar, no cross-platform (macOS/Linux) work, no provider /
translation / QA / export / schema / cockpit-UI change. This sprint only *observes
and records* runtime behavior; it does not add features.

**Execution constraint:** N1, N2 (transition), and N5 require a human watching the
native window. N2 (HTTP codes), N3 (orphan check), and N4 (log files) can be
verified programmatically from logs/processes. The split is called out per item.

---

## 2. Smoke test checklist N1–N5

| ID | Criterion | Contract | How verified | Observer |
|---|---|---|---|---|
| **N1** | Native window opens; loading screen transitions to cockpit `/ui` | §1 lifecycle | watch the window: `loading.html` paints, then cockpit renders | 👁 human |
| **N2** | `/healthz 200` then `/ui 200`, **no 401 loop** | §1, §3 | tail `sidecar.console.log`: `GET /healthz 200` → `GET /ui 200`, zero `401` | 🤖 log / 👁 |
| **N3** | Closing the window kills the sidecar — **no orphan** | §7 (graceful→force) | after close: `Get-Process` shows no `weaver`/`python`/`uvicorn` | 🤖 process |
| **N4** | Both `runtime.log` **and** `sidecar.console.log` generated in `logs_dir` | §4 | `Get-ChildItem "$env:APPDATA\Weaver\logs\"` shows both | 🤖 file |
| **N5** | Forced failure shows crash screen with **mapped exit code** | §4, §5 | remove `weaver` from PATH → relaunch → crash window shows exit code + ≤50 stderr lines | 👁 human |

Pass = all five green with captured evidence. Any red → §5 failure matrix → §6 fix policy.

---

## 3. Exact commands to run

**Setup (once):**

```powershell
# weaver must resolve in the SAME shell that launches the dev build
$env:PATH = "D:\DevSpace\Projects\weaver\.venv\Scripts;$env:PATH"
weaver --version            # expect: weaver 0.7.0
cd D:\DevSpace\Projects\weaver\desktop
```

**N1–N4 — happy path:**

```powershell
cargo tauri dev
# WATCH: loading window → cockpit /ui transition (N1)
# …interact briefly, then CLOSE the window…
```

After close, in a second shell:

```powershell
# N2 — health then UI, no 401
Get-Content "$env:APPDATA\Weaver\logs\sidecar.console.log" -Tail 20

# N3 — no orphan
Get-Process | Where-Object { $_.ProcessName -match "weaver|python|uvicorn" }   # → nothing

# N4 — both logs present
Get-ChildItem "$env:APPDATA\Weaver\logs\" | Select-Object Name,Length
```

**N5 — forced failure (crash screen):**

```powershell
# In a shell WITHOUT weaver on PATH (or temporarily rename the venv weaver.exe):
$env:WEAVER_DESKTOP_SIDECAR = "C:\does\not\exist\weaver.exe"
cargo tauri dev
# EXPECT: crash window "Weaver could not start" / "stopped during startup"
#         with a mapped exit code (64/65/unknown) + console tail.
Remove-Item Env:\WEAVER_DESKTOP_SIDECAR
```

---

## 4. Evidence to capture

Record each in the Sprint N closure note (append to the Q2F gate report or a new
handoff):

- **N1:** screenshot or one-line confirmation "loading → cockpit transition seen".
- **N2:** the `sidecar.console.log` tail showing `GET /healthz 200` → `GET /ui 200`
  with **no `401`** lines.
- **N3:** the (empty) output of the `Get-Process` orphan check.
- **N4:** the `Get-ChildItem` listing showing `runtime.log` + `sidecar.console.log`.
- **N5:** screenshot/transcript of the crash window with the exit code + console tail.
- The exact `cargo tauri dev` first-build duration (informs N1 launch-time budget).

---

## 5. Failure classification matrix

| Symptom | Likely class | Root area | First diagnostic |
|---|---|---|---|
| `cargo tauri dev` fails at **link** step | toolchain | missing MSVC C++ Build Tools | install "Desktop development with C++"; re-run |
| Compile error in `webview_session.rs` (`controller()` types) | dependency pin | `webview2-com`/`windows` mismatch | `cargo tree -p webview2-com -p windows`; re-pin `Cargo.toml` |
| Window never opens, no log dir | host config | `LaunchConfig::resolve` (port/token/data dir) | check crash window text; verify `%APPDATA%\Weaver` writable |
| Blank WebView, `GET /ui 401` loop | session header race | `webview_session.rs` interceptor registers after navigation | confirm window built with `loading.html` first, then `navigate` |
| Crash "did not respond in time" | sidecar boot | `weaver serve` slow / not on PATH | inspect `sidecar.console.log`; raise `HEALTH_BUDGET` only with evidence |
| Crash exit `65` | port conflict | another process on the picked port | re-run; verify `pick_free_port` |
| Crash exit `64` | bind guard | non-loopback host / missing extra | check spawn env (`WEAVER_HOST=127.0.0.1`) |
| Orphan `weaver` after close | shutdown | `Sidecar::shutdown` / window-event wiring | confirm `taskkill /T` then `/F`; check `on_window_event` label logic |
| App killed via Task Manager leaves orphan | known limitation | graceful path bypassed | not a failure — `INSTALL_DESKTOP.md` limitation #6 |

---

## 6. Minimal fix policy

- A smoke failure is fixed with the **smallest change in the owning area only**
  (the matrix names it). One failure → one fix → re-run the affected N-check.
- **No refactors, no feature work, no dependency additions.** A version re-pin in
  `Cargo.toml` to match `cargo tree` is allowed (it is a correction, not a new dep).
- Toolchain-class failures (missing MSVC) are **blocked-by-toolchain**, documented
  with the install command — not a code fix and not a fail of the shell.
- Any Rust edit beyond a re-pin requires a one-line justification in the closure
  note and stays within `desktop/src/`. Python core is untouched.
- After each fix, re-run only the failed check plus N3 (orphan) as a regression.

---

## 7. Definition of Done

Sprint N is **Done** when:

- [ ] N1–N5 all green with the §4 evidence captured.
- [ ] First-build duration recorded; N1 launch feels acceptable (no hard budget,
      but note it).
- [ ] No orphan processes in the happy-path **and** forced-failure runs.
- [ ] Any fix applied was within the matrix's owning area, minimal, and re-verified.
- [ ] Q2F gate report updated: **PASS-WITH-CONDITIONS → PASS** (or the specific
      N-item left red with a blocker + smallest-fix proposal).
- [ ] `uv run ruff check .` + `uv run pyright` still clean (no Python touched, but
      confirm).
- [ ] Closure handoff written; **next sprint = Sprint O (packaging)** only if PASS.

**Partial / Blocked:** if the toolchain link step blocks (no MSVC), record
**BLOCKED-by-toolchain** with the install command — Q2F stays PASS-WITH-CONDITIONS,
do not regress it to BLOCKED (compile + contract already passed).
