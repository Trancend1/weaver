# Sprint P3b — Bundled sidecar startup readiness + diagnostics

**Verdict:** PASS (packaged PATH-free launch now reaches `/healthz 200` then `/ui 200`).

## Root cause

`desktop/src/lib.rs` polled `/healthz` with a 5 s `HEALTH_BUDGET` tuned for a
warm PATH/venv `weaver serve`. The bundled PyInstaller onedir sidecar
(16.4 MB exe + 171 MB / 784-file `_internal`) has a slower cold start; on some
packaged runs it had not answered `/healthz` within 5 s. When the deadline
elapsed, `boot()` transitioned straight to the crash screen and **never called
`open_cockpit()`** — so the WebView never requested `/ui`. That is why P3 saw
`/healthz 200` (sometimes, at the budget edge) but never `/ui 200`: a
startup-readiness race, not a WebView/session/static problem. P2's direct and
override smokes already proved `/ui 200` works when the sidecar is given time.

The second contributor was diagnostics: the crash payload did not report which
sidecar/resolver-source was used or the elapsed wait, so the failure modes
(failed-to-start vs slow-start vs nav-failed) could not be told apart.

## Fix

- Widened `HEALTH_BUDGET` 5 s → **20 s** (bounded; a child that *exits* is still
  surfaced immediately via `Poll::Exited`, so this only delays the
  never-became-ready case). Single budget, also used by the fast dev PATH sidecar.
- Added `SidecarSource` (`Override` / `Bundled` / `Path`) to `LaunchConfig`,
  recorded by `resolve_weaver_exe()`. Override precedence and PATH fallback are
  unchanged.
- `boot()` now writes `[host]` diagnostic lines to `sidecar.console.log`
  (resolved source + path + budget at start; `/healthz` ready + elapsed; or
  spawn-failed / exited / timed-out with elapsed). Visible in the same log a
  packaged smoke inspects, with no secret/token disclosure.
- Crash screen (`crash_payload` + `dist/crash.html`) now shows `Sidecar:` source,
  `Path:`, and `Waited: <ms>`.
- `/healthz` handler and API readiness behavior were **not** touched.

## Files changed

- `desktop/src/lib.rs` — `HEALTH_BUDGET` 20 s; `CONSOLE_LOG` const; `boot()`
  diagnostics + `boot_start` elapsed; `StartupDiag`; `crash_payload` extended;
  hardcoded "5 seconds" text now derives from the budget.
- `desktop/src/launch_config.rs` — `SidecarSource` enum + `sidecar_source` field;
  `resolve_weaver_exe()` returns `(PathBuf, SidecarSource)`.
- `desktop/src/sidecar.rs` — `append_host_log()` helper (`[host]`-tagged append).
- `desktop/dist/crash.html` — renders `sidecarSource` / `sidecarPath` / `waitedMs`.
- Docs: `docs/SIDECAR_CONTRACT.md` (§1 + §6 budget 5 s → 20 s + readiness note;
  §7 shutdown grace left at 5 s), `desktop/README.md`,
  `docs/DESKTOP_SMOKE_CHECKLIST.md` (4.4), `docs/INSTALL_DESKTOP.md`.

No Python runtime, provider, translation, QA/export, schema, or cockpit-UI
changes. No PyInstaller strategy change. No signing/auto-update/installer/
cross-platform work. No commit created.

## Validation (commands run)

```
cargo check                         # PASS (3 pre-existing sidecar.rs dead-code warns)
cargo tauri build                   # PASS (1m52s) → target/release/weaver-desktop.exe (3.27 MB)
                                    #   + bundled weaver.exe (17.2 MB) + _internal (784 files)
uv run ruff check .                 # All checks passed
uv run pyright                      # 0 errors, 0 warnings
```

PATH-free packaged smoke (`.venv\Scripts` removed from PATH,
`WEAVER_DESKTOP_SIDECAR` unset, isolated `WEAVER_DATA_DIR`):

```
[host] startup: sidecar source=bundled path=...\release\weaver.exe health-budget=20s
[out] INFO: 127.0.0.1:... - "GET /healthz HTTP/1.1" 200 OK
[host] startup: /healthz ready after 2653 ms; opening cockpit
[out] INFO: 127.0.0.1:... - "GET /ui HTTP/1.1" 200 OK
logs: backend.log, export.log, job.log, provider.log, runtime.log, sidecar.console.log
401_count = 0
```

| Check | Result |
| --- | --- |
| `.venv\Scripts` excluded from PATH | PASS (`venv_on_path=False`) |
| `WEAVER_DESKTOP_SIDECAR` unset | PASS (empty) |
| Bundled sidecar selected | PASS (`source=bundled`, release `weaver.exe`) |
| `/healthz 200` | PASS (ready 2653 ms) |
| `/ui 200` | PASS |
| No repeated 401 | PASS (`401_count = 0`) |
| Logs generated | PASS (6 files incl. `runtime.log` + `sidecar.console.log`) |
| Close window → no orphan | PASS — after WM_CLOSE to the host window, no `weaver`/`python`/`uvicorn` remained |
| Bad override → crash screen | PASS — `source=override`, `spawn failed: ...os error 3`, no sidecar spawned, desktop stays alive (crash window) |

Note on the no-orphan check: a programmatic `CloseMainWindow()` did **not** fire
the `CloseRequested` handler (the known P2/P5 automation artifact). Sending a real
`WM_CLOSE` to the host's main window did fire it — `shutdown_sidecar()` cleaned
the sidecar tree and no orphan remained. A human X-button close should still be
owner-confirmed (consistent with how Sprint N N4 / Sprint O were confirmed).

## Status

- **P3 can now be marked PASS** — packaged PATH-free launch reaches `/healthz 200`
  then `/ui 200` with no 401 loop and no orphan.
- **P4/P5 are unblocked.** Their remaining value is the owner-confirmed human
  window-close lifecycle pass and the formal P6 gate matrix.

**Recommended next step:** Owner runs the packaged exe, confirms the X-button
close leaves no orphan, then proceed to P6 gate report (record artifact sizes,
the 20 s budget decision, and the cold-start timing).
