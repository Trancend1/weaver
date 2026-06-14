# Q2F — Tauri Sidecar Readiness Gate Report

**Date:** 2026-06-14
**Branch:** `chore/tauri-sidecar-readiness`
**Scope:** Validate that the Weaver desktop shell (Tauri host in `desktop/`) and the
FastAPI cockpit honor the [Sidecar Contract](../../SIDECAR_CONTRACT.md) well enough
to move from "scaffold" to "smoke-verified".
**Verdict:** 🟡 **PASS-WITH-CONDITIONS** — see [§7](#7-gate-verdict).

---

## 1. Executive summary

Q2F closed the largest desktop risk surfaced in Commit 1: the Rust/Tauri host was
**architecturally complete but never compiled or run**. Across Commits 2–5 the
Python/FastAPI side of the contract is now covered by real-HTTP tests, and the
Rust side **compiles cleanly** with its previously-`UNVERIFIED` Windows crate pins
resolving exactly as declared.

**What is proven:**

- The FastAPI sidecar honors the contract over real HTTP — `/healthz` shape +
  budget, random-port binding, session-token enforcement, public-path bypass,
  startup diagnostics, and the exit-code map (`64`/`65`). **32 tests pass.**
- The Tauri host **type-checks** end-to-end including the Windows-only WebView2
  COM interceptor (`cargo check` → 0 errors), and the `webview2-com` / `windows`
  pins match what Tauri 2.11.2 resolves.

**What is not yet proven (the conditions):**

- The **runtime** launch — `cargo tauri dev` spawning the real sidecar, opening
  the WebView, injecting the session header on every request, and the no-orphan
  shutdown — has **not** been executed. It needs an interactive desktop (GUI)
  session and cannot be driven headlessly. Sprint N exit criteria **N1–N4 remain
  unverified.**

The desktop shell is therefore **compile-verified, runtime-unverified**. This is a
conditional pass, not a full pass.

---

## 2. Evidence table — Commits 1–5

| Commit | Subject | Artifact | Evidence | Status |
|---|---|---|---|---|
| **1** | Audit sidecar contract | `docs/SIDECAR_CONTRACT.md` review | Found the open risk: Rust host build/runtime-unverified | ✅ done |
| **2** | `/healthz` readiness over real HTTP | `tests/integration/test_runtime_random_port.py` (`HealthZ` cases: shape, public, ≤budget, no-provider, no-mutation) | part of **32 passed** below | ✅ verified |
| **3** | Random port + session token contract | `tests/integration/test_runtime_random_port.py` (`test_ui_works_on_random_port`, `runtime/status` env/host/port/paths, token-required vs public routes) | part of **32 passed** | ✅ verified |
| **4** | Startup diagnostics + exit codes | `tests/unit/api/test_desktop_security.py` (`test_serve_exits_65_when_port_in_use`, `test_serve_refuses_non_loopback_in_desktop` → exit 64, `test_serve_stdout_summary_line_contains_host_and_port`) | part of **32 passed** | ✅ verified |
| **5** | Desktop smoke checklist + compile proof | `docs/DESKTOP_SMOKE_CHECKLIST.md`; `cargo check`; `cargo tree` | `cargo check` 0 errors / 3 dead-code warnings; pins resolve (§4 below) | ✅ verified |
| **6** | This readiness gate report | `docs/superpowers/handoffs/2026-06-14-q2f-sidecar-readiness-gate.md` | this document | ✅ done |

**Test run (2026-06-14):**

```text
uv run pytest tests/integration/test_runtime_random_port.py \
              tests/unit/api/test_desktop_security.py -q
32 passed, 1 warning in 17.53s
```

(The single warning is an upstream `starlette.testclient`/`httpx` deprecation —
not a Weaver issue.)

---

## 3. Python / FastAPI sidecar contract status — ✅ VERIFIED

| Contract clause (`SIDECAR_CONTRACT.md`) | Verified by |
|---|---|
| §3 `/healthz` 200 `{ok,ts}`, public, ≤50 ms cold | `HealthZ` tests |
| §2/§6 random port (`--port 0`), `/runtime/status` authoritative | `test_ui_works_on_random_port`, `runtime/status` tests |
| §2 session-token required; §3 public-path bypass (`/healthz`,`/health`,`/version`,`/static/*`) | token-required / public-route tests |
| §2 desktop docs-off baseline | `test_docs_disabled_in_desktop_mode` |
| §5 exit `64` (non-loopback bind), exit `65` (port in use) | `test_serve_refuses_non_loopback_in_desktop`, `test_serve_exits_65_when_port_in_use` |
| §4 stdout summary line carries host+port | `test_serve_stdout_summary_line_contains_host_and_port` |
| §6 no template hardcodes host/port | `test_no_template_uses_hardcoded_loopback_url`, `test_no_template_uses_absolute_http_url_in_hx_attrs` |

No Python code was modified in Q2F — these are validation tests against existing
behavior.

---

## 4. Rust / Tauri compile status — ✅ VERIFIED (build) / pins confirmed

Toolchain present on the dev machine (2026-06-14):

```text
rustup 1.29.0 · rustc 1.96.0 · cargo 1.96.0 · tauri-cli 2.11.2 · node 24.15.0
```

```text
cd desktop
cargo check  → Finished, 0 errors, 3 warnings
  warning: const  `POLL_INTERVAL` never used   (src/sidecar.rs:23)
  warning: field  `log_path`      never read   (src/sidecar.rs:39)
  warning: method `log_path`      never used   (src/sidecar.rs:122)

cargo tree   → webview2-com 0.38.2   (matches Cargo.toml pin)
               windows      0.61.3   (matches Cargo.toml pin)
               tauri        2.11.2
```

- `cargo check` compiles the `cfg(windows)` WebView2 COM code in
  `src/webview_session.rs`, so the `UNVERIFIED VERSION PIN` note in `Cargo.toml`
  is now **empirically correct**.
- The 3 warnings are **pre-existing dead code** in `sidecar.rs` (unused
  `POLL_INTERVAL`; unused `log_path` field/accessor). Cleanup candidates for the
  audit phase — **out of scope for Q2F**, no Rust code changed here.

---

## 5. Runtime smoke status — ⬜ NOT RUN (condition)

`cargo tauri dev` was **not** executed. It spawns the real sidecar and opens a
native WebView, which requires an interactive desktop session and `weaver` on
`PATH`; per `INSTALL_DESKTOP.md` limitation #6 a headless launch can orphan the
sidecar. The full pass/fail path (loading window → spawn → `/healthz` poll →
WebView `/ui` → session header on every request → no-orphan shutdown → log files
→ crash screen) is documented in
[`DESKTOP_SMOKE_CHECKLIST.md` §4](../../DESKTOP_SMOKE_CHECKLIST.md#4-runtime-launch-smoke--cargo-tauri-dev).

**Until §4 is run on a real desktop with the orphan-check and log evidence
captured, N1–N4 must not be claimed met.**

---

## 6. Known deferred items

Explicitly out of scope for Q2F; not gaps in this gate:

| Item | State |
|---|---|
| Final installer / NSIS `.exe` | deferred — `INSTALL_DESKTOP.md` §Installer release |
| Code signing | deferred — SmartScreen warning expected until a cert exists |
| Auto-update | deferred — manual download + reinstall |
| Cross-platform packaging final | deferred — Windows-first; macOS/Linux = Sprint O |
| POSIX `SIGTERM` graceful shutdown | deferred — Windows `taskkill /T`/`/F` only today; POSIX path with the cross-platform work |
| Bundled-Python sidecar (single `.exe`) | deferred — PATH dependency today; PyInstaller evaluated as next step |
| Exit code `66` (data-dir error) | **reserved** — host maps it (`lib.rs::exit_meaning`); cockpit does not yet raise it (future `services/app_paths.ensure_runtime_dirs`) |

---

## 7. Gate verdict

> 🟡 **PASS-WITH-CONDITIONS**

- **PASS** would require the `cargo tauri dev` runtime smoke (§5) to have run
  successfully **with orphan/log evidence** — it has not.
- **BLOCKED** would apply only if the build/toolchain failed — it did not
  (`cargo check` is green, pins resolve, 32 Python tests pass).

**Condition remaining to reach full PASS:** execute
[`DESKTOP_SMOKE_CHECKLIST.md` §4](../../DESKTOP_SMOKE_CHECKLIST.md#4-runtime-launch-smoke--cargo-tauri-dev)
on an interactive Windows desktop and record:

1. loading → cockpit transition (N1),
2. `GET /healthz 200` then `GET /ui 200` (not 401) in `sidecar.console.log`,
3. zero orphan `weaver`/`python`/`uvicorn` after window close (N3),
4. both `runtime.log` and `sidecar.console.log` present in `logs_dir` (N4),
5. crash screen with mapped exit code + ≤50 stderr lines on a forced failure.

---

## 8. Next recommended sprint after Q2F

**Sprint N runtime validation (N1–N4)** is the immediate next step — run the §4
smoke and promote this gate to PASS. Only after N1–N4 are green with evidence
should **Sprint O — Production Desktop Packaging** (installer, signing,
auto-update, bundled-Python sidecar) be opened. Do not start Sprint O packaging
on a runtime-unverified shell.

---

## Handoff

**Track:** T9 (Release & Final Gate) supported by T6/T7
**What changed:** Docs only — this report, plus minor doc-drift fixes in
`desktop/README.md` (status note + `bundle.active` description) and a
cross-reference in `SIDECAR_CONTRACT.md` (Commit 5). No Python/Rust/test/schema/UI
code touched in Q2F.
**Validation:** `cargo check` 0 errors; `cargo tree` pins confirmed;
`pytest` 32 passed; `ruff`/`pyright` clean.
**Known risk:** runtime behavior (N1–N4) still unverified — compile passing does
not guarantee the WebView/session/shutdown path works on a real desktop.
**Next step:** run `DESKTOP_SMOKE_CHECKLIST.md` §4 on a Windows desktop and
capture the orphan/log evidence.
