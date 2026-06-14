# Sprint P - Bundled Sidecar / Standalone Desktop Alpha Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Windows desktop alpha self-contained by bundling the FastAPI sidecar as a Tauri-managed executable, removing the `.venv\Scripts`-on-`PATH` requirement from Sprint O.

**Architecture:** Keep the current Tauri shell and FastAPI sidecar boundary. Sprint P changes only desktop packaging and the minimal Rust sidecar-resolution surface accepted by ADR 016: produce an experimental Python sidecar executable, stage it through Tauri `bundle.externalBin`, add a bundled-sidecar resolver, then prove the packaged app launches on Windows without `weaver` on `PATH`.

**Tech Stack:** Windows-first Tauri 2 desktop shell, existing FastAPI/Jinja2/HTMX cockpit, Python 3.11+, uv, PyInstaller onedir as the accepted Sprint P packaging candidate, existing Rust sidecar lifecycle.

---

## 1. Scope

Sprint P is a packaging-hardening sprint. It does not change the product workflow,
provider layer, translation pipeline, storage schema, QA/export logic, or cockpit
UI. The only user-facing outcome is that the packaged Windows desktop alpha can
start its local FastAPI cockpit without requiring an external `weaver` command on
`PATH`.

**Status before implementation:** P1 audit complete. ADR 016 is accepted with the
bundled-sidecar resolver requirement. P2 is next and remains limited to building
and direct-testing a PyInstaller onedir sidecar artifact.

**Tracks active:**

| Track | Owner role | Scope |
| --- | --- | --- |
| T0 | Documentation / Handoff Writer | Execution plan, ADR, risk register, validation evidence, final gate report |
| T3 | Backend/Desktop Engineer | Packaging-only sidecar artifact and Tauri sidecar registration |
| T6 | QA / Validation Engineer | Packaged binary smoke and regression checks |
| T7 | Security / Safety Engineer | Secret/log/process/path boundary review |
| T8 | Performance / Reliability Engineer | Startup time, size, shutdown, no-orphan checks |
| T9 | Release Captain | Final PASS / PASS-WITH-CONDITIONS / BLOCKED verdict |

## 2. Non-goals

- No signing.
- No auto-update.
- No production installer final.
- No cross-platform final.
- No provider changes.
- No translation pipeline changes.
- No cockpit redesign.
- No schema changes.
- No production-code refactor outside the minimum desktop packaging surface.
- No telemetry or phone-home behavior.
- No replacement of FastAPI as the sidecar.

## 3. Files and responsibilities

Planned implementation files after ADR acceptance:

| File / area | Planned responsibility |
| --- | --- |
| `docs/decisions/016-bundled-python-sidecar.md` | Architectural decision for the bundled sidecar strategy |
| `docs/superpowers/plans/2026-06-14-sprint-p-bundled-sidecar.md` | This Sprint P execution plan |
| `docs/superpowers/handoffs/2026-06-14-sprint-p1-sidecar-launch-audit.md` | P1 audit evidence and launch-path map |
| `docs/superpowers/handoffs/2026-06-14-sprint-p2-pyinstaller-experiment.md` | P2 artifact evidence, size, startup notes, failures |
| `docs/superpowers/handoffs/2026-06-14-sprint-p4-p5-packaged-standalone-smoke.md` | P4/P5 packaged standalone smoke evidence |
| `docs/superpowers/handoffs/2026-06-14-sprint-p6-gate-report.md` | Final Sprint P gate report |
| `desktop/sidecar/weaver-sidecar.spec` | PyInstaller onedir spec for the `weaver` CLI sidecar, created in P2 |
| `desktop/scripts/build-sidecar.ps1` | Windows build wrapper that writes sidecar artifacts under `desktop/target/sidecar/` |
| `desktop/tauri.conf.json` | Add `bundle.externalBin` only after P3, no earlier |
| `desktop/src/launch_config.rs` or a focused desktop resolver module | Minimal P3 resolver so packaged builds prefer the bundled sidecar while preserving override + PATH fallback |
| `src/weaver/` | Out of scope; must remain unchanged unless a critical packaging bug is proven and approved separately |

Do not edit `pyproject.toml`, `uv.lock`, `Cargo.toml`, `Cargo.lock`, or
`tauri.conf.json` during planning. During implementation, `tauri.conf.json` may
be edited only in P3 after P2 direct sidecar validation.

## 4. Execution sequence

### P1: Audit current sidecar launch path and Tauri `externalBin` expectations - ✅ complete

**Purpose:** Prove exactly how the host resolves and launches `weaver` today, then
map the minimum packaging change needed for a bundled executable.

**Files:**
- Read: `desktop/src/launch_config.rs`
- Read: `desktop/src/sidecar.rs`
- Read: `desktop/src/lib.rs`
- Read: `desktop/tauri.conf.json`
- Read: `desktop/README.md`
- Read: `docs/SIDECAR_CONTRACT.md`
- Create: `docs/superpowers/handoffs/2026-06-14-sprint-p1-sidecar-launch-audit.md`

- [x] **Step 1: Check branch and WIP**

Run:

```powershell
rtk git status --short --branch
```

Expected: branch is the Sprint P branch and there are no unexpected overlapping
changes in `desktop/`, `docs/decisions/`, or `docs/superpowers/`.

- [x] **Step 2: Read the current launcher and sidecar code**

Run:

```powershell
rtk read --level minimal --max-lines 220 desktop/src/launch_config.rs
rtk read --level minimal --max-lines 260 desktop/src/sidecar.rs
rtk read --level minimal --max-lines 340 desktop/src/lib.rs
```

Expected: audit identifies the current resolution order, `WEAVER_DESKTOP_SIDECAR`
override behavior, `weaver serve` arguments/env, console tee, shutdown behavior,
and crash-screen path.

- [x] **Step 3: Read Tauri bundle config and docs**

Run:

```powershell
rtk read --level minimal --max-lines 220 desktop/tauri.conf.json
rtk read --level minimal --max-lines 180 desktop/README.md
rtk read --level minimal --max-lines 220 docs/SIDECAR_CONTRACT.md
```

Expected: audit records whether `bundle.externalBin` is absent today, what target
layout Tauri expects on Windows, and which sidecar contract points must not change.

- [x] **Step 4: Write the P1 handoff**

Create `docs/superpowers/handoffs/2026-06-14-sprint-p1-sidecar-launch-audit.md`
with:

- Current spawn path.
- Current environment boundary.
- Current PATH dependency.
- Expected `externalBin` artifact name and location.
- Whether Rust runtime code is avoidable.
- Any blockers before P2.

- [ ] **Step 5: Commit P1**

Run:

```powershell
git add docs/superpowers/handoffs/2026-06-14-sprint-p1-sidecar-launch-audit.md
git commit -m "docs(desktop): audit sprint p sidecar launch path"
```

Expected: docs-only commit. No production code touched. Skipped in this closeout
because the orchestrator explicitly requested no commit.

**P1 closeout:** PASS. The audit found that `bundle.externalBin` is not sufficient
by itself because the launcher still resolves `Command::new("weaver")` through
`PATH`. Sprint P now explicitly requires PyInstaller onedir artifact +
`externalBin` staging + a minimal Rust bundled-sidecar resolver. See
`docs/superpowers/handoffs/2026-06-14-sprint-p1-sidecar-launch-audit.md`.

### P2: Build experimental PyInstaller sidecar artifact

**Purpose:** Produce a local Windows sidecar executable candidate and prove it can
run `serve` with the existing sidecar contract before wiring it into Tauri.

**Files:**
- Create or modify only under `desktop/` build tooling after ADR acceptance
- Create: `docs/superpowers/handoffs/2026-06-14-sprint-p2-pyinstaller-experiment.md`
- Do not modify: `src/weaver/`, provider code, translation pipeline, schema, cockpit templates

- [ ] **Step 1: Confirm ADR 016 is accepted**

Run:

```powershell
rtk grep -n "Status" docs/decisions/016-bundled-python-sidecar.md
```

Expected: ADR status is no longer `Proposed`. If still `Proposed`, stop before
installing or wiring PyInstaller.

- [ ] **Step 2: Add the smallest experimental PyInstaller build surface**

Allowed implementation shape after ADR acceptance:

- Create `desktop/sidecar/weaver-sidecar.spec`.
- Create `desktop/scripts/build-sidecar.ps1`.
- Write generated sidecar output to `desktop/target/sidecar/weaver/weaver.exe`.
- Do not commit generated binaries.
- No change to Python application logic.
- No dependency lockfile edit unless the accepted ADR explicitly approves it.

Expected artifact: `desktop/target/sidecar/weaver/weaver.exe`, a Windows onedir
executable that behaves like `weaver` for the `serve` subcommand and can be
launched directly by path.

- [ ] **Step 3: Run the bundled sidecar directly**

Run the candidate executable with the current sidecar contract arguments and env:

```powershell
$env:WEAVER_ENV = "desktop"
$env:WEAVER_DOCS = "false"
$env:WEAVER_SESSION_TOKEN = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
$env:WEAVER_DATA_DIR = "$env:TEMP\weaver-sprint-p-data"
.\desktop\target\sidecar\weaver\weaver.exe serve --host 127.0.0.1 --port 0 --no-browser
```

Expected: process starts the FastAPI cockpit, prints the local startup line, and
responds to `/healthz`. Stop the process after recording evidence.

- [ ] **Step 4: Record artifact evidence**

The P2 handoff must include:

- Exact build command.
- Artifact path.
- Artifact size.
- Startup time observation.
- `/healthz` result.
- Any hidden imports or bundled-data issues encountered.
- Whether secrets appeared in logs or console output.

- [ ] **Step 5: Commit P2**

Run:

```powershell
git add desktop docs/superpowers/handoffs/2026-06-14-sprint-p2-pyinstaller-experiment.md
git commit -m "build(desktop): add experimental bundled sidecar artifact"
```

Expected: commit contains only desktop build tooling plus the handoff.

### P3: Stage Tauri `bundle.externalBin` and add bundled-sidecar resolver

**Purpose:** Make Tauri include the bundled sidecar and make the Rust host prefer
that packaged binary at runtime.

**Files:**
- Modify: `desktop/tauri.conf.json`
- Modify under `desktop/` build tooling only if required by Tauri sidecar naming
- Modify: `desktop/src/launch_config.rs` or a focused desktop resolver module,
  limited to bundled sidecar path discovery and fallback order

- [ ] **Step 1: Register the sidecar as `bundle.externalBin`**

Edit only the Tauri bundle configuration needed to include the sidecar executable.
Keep the current app identity, permissions, windows, and bundle targets unchanged
unless the accepted ADR requires otherwise.

- [ ] **Step 2: Add the minimal bundled-sidecar resolver**

Implement the accepted resolver order:

1. `WEAVER_DESKTOP_SIDECAR` override wins.
2. Bundled sidecar path is preferred when available.
3. Bare `weaver` on `PATH` remains for dev and diagnostics.

Do not change sidecar arguments, environment, health polling, crash payload,
logging, shutdown, provider behavior, translation workflow, schema, QA/export, or
cockpit UI.

- [ ] **Step 3: Build the desktop package**

Run:

```powershell
cd desktop
cargo tauri build
```

Expected: Tauri build includes the sidecar artifact and produces the Windows
desktop executable without requiring a Python virtualenv on `PATH`.

- [ ] **Step 4: Commit P3**

Run:

```powershell
git add desktop/tauri.conf.json desktop/src desktop
git commit -m "build(desktop): bundle python sidecar with tauri"
```

Expected: packaging plus the minimal resolver only.

### P4: Validate packaged app launches without `.venv\Scripts` on `PATH`

**Purpose:** Prove Sprint O's primary condition is closed.

**Files:**
- Create or update: `docs/superpowers/handoffs/2026-06-14-sprint-p4-p5-packaged-standalone-smoke.md`

- [ ] **Step 1: Launch in a sanitized PATH session**

Run from a fresh PowerShell where `.venv\Scripts` is not prepended:

```powershell
cd D:\DevSpace\Projects\weaver\desktop
$env:PATH -split ";" | Select-String "\\.venv\\Scripts"
$env:WEAVER_DESKTOP_SIDECAR
Start-Process .\target\release\weaver-desktop.exe
```

Expected: the `Select-String` command returns no `.venv\Scripts` entry,
`WEAVER_DESKTOP_SIDECAR` is empty/unset, and the app still launches from the
bundled sidecar.

- [ ] **Step 2: Verify cockpit load**

Run:

```powershell
Get-Content "$env:APPDATA\Weaver\logs\sidecar.console.log" -Tail 20
```

Expected: log shows `GET /healthz` 200 followed by `GET /ui` 200 and no repeated
401 loop.

- [ ] **Step 3: Record P4 evidence**

Add the sanitized PATH check, launch result, log tail, and whether any external
Python process path reveals dependency on the repo venv.

### P5: Validate logs, crash, shutdown, no orphan

**Purpose:** Prove bundling did not regress Sprint N/O lifecycle guarantees.

**Files:**
- Update: `docs/superpowers/handoffs/2026-06-14-sprint-p4-p5-packaged-standalone-smoke.md`

- [ ] **Step 1: Validate logs**

Run:

```powershell
Get-ChildItem "$env:APPDATA\Weaver\logs"
Get-Content "$env:APPDATA\Weaver\logs\sidecar.console.log" -Tail 20
```

Expected: `runtime.log` and `sidecar.console.log` exist; logs do not contain API
keys or session tokens.

- [ ] **Step 2: Validate no orphan after close**

Close the Weaver window, then run:

```powershell
Get-Process | Where-Object { $_.ProcessName -match "weaver|python|uvicorn" }
```

Expected: no running Weaver sidecar, Python, or Uvicorn process attributable to
the launched app.

- [ ] **Step 3: Validate crash screen behavior**

Use the existing override path to force a startup failure:

```powershell
$env:WEAVER_DESKTOP_SIDECAR = "D:\definitely-missing\weaver.exe"
Start-Process .\target\release\weaver-desktop.exe
```

Expected: crash screen appears with mapped failure text and a path to
`sidecar.console.log`. Clear `WEAVER_DESKTOP_SIDECAR` after the check.

- [ ] **Step 4: Commit P4/P5 evidence**

Run:

```powershell
git add docs/superpowers/handoffs/2026-06-14-sprint-p4-p5-packaged-standalone-smoke.md
git commit -m "docs(desktop): validate standalone sidecar smoke"
```

Expected: evidence-only commit.

### P6: Final gate report

**Purpose:** Decide PASS / PASS-WITH-CONDITIONS / BLOCKED for Sprint P.

**Files:**
- Create: `docs/superpowers/handoffs/2026-06-14-sprint-p6-gate-report.md`
- Update: `docs/INSTALL_DESKTOP.md` only if P4/P5 changed install or smoke instructions
- Update phase ledger only after the gate verdict, if requested by the orchestrator

- [ ] **Step 1: Run Python verification**

Run:

```powershell
uv run ruff check .
uv run pyright
```

Expected: both pass.

- [ ] **Step 2: Run desktop build verification**

Run:

```powershell
cd desktop
cargo tauri build
```

Expected: packaged Windows desktop binary builds with bundled sidecar included.

- [ ] **Step 3: Complete validation matrix**

Use the matrix in §7 and mark each P-V check PASS / FAIL / NOT RUN with concrete
evidence. A PASS requires P-V1 through P-V9 green.

- [ ] **Step 4: Write gate report**

The P6 report must include:

- Final verdict.
- Files changed.
- Exact commands run.
- Artifact sizes.
- Known gaps.
- Rollback path.
- Next sprint recommendation.

- [ ] **Step 5: Commit P6**

Run:

```powershell
git add docs/superpowers/handoffs/2026-06-14-sprint-p6-gate-report.md docs/INSTALL_DESKTOP.md
git commit -m "docs(desktop): close sprint p bundled sidecar gate"
```

Expected: final docs commit. If `docs/INSTALL_DESKTOP.md` did not change, omit it
from `git add`.

## 5. Commit sequence

| # | Commit | Scope | Expected files |
| --- | --- | --- | --- |
| P0 | `docs(desktop): plan sprint p bundled sidecar` | Planning and ADR proposal only | `docs/superpowers/plans/2026-06-14-sprint-p-bundled-sidecar.md`, `docs/decisions/016-bundled-python-sidecar.md` |
| P1 | `docs(desktop): audit sprint p sidecar launch path` | Read-only launch path and `externalBin` audit | P1 handoff |
| P2 | `build(desktop): add experimental bundled sidecar artifact` | Desktop-local PyInstaller experiment | desktop build tooling/spec, P2 handoff |
| P3 | `build(desktop): bundle python sidecar with tauri` | `bundle.externalBin` staging + minimal bundled-sidecar resolver | `desktop/tauri.conf.json`, desktop build tooling, focused desktop resolver code |
| P4/P5 | `docs(desktop): validate standalone sidecar smoke` | Packaged standalone smoke evidence | P4/P5 handoff |
| P6 | `docs(desktop): close sprint p bundled sidecar gate` | Final gate report and install-doc reconciliation | P6 handoff, optional `docs/INSTALL_DESKTOP.md` |

No commit is created during planning unless explicitly requested.

## 6. Risk register

| Risk | Severity | Mitigation | Gate |
| --- | --- | --- | --- |
| PyInstaller misses hidden imports or package data needed by FastAPI/Jinja2/static assets | High | P2 runs the sidecar directly and validates `/healthz`; P4 validates `/ui` and static assets from packaged context | P2, P4 |
| Bundled executable starts too slowly for the 5s host health budget | High | Measure startup in P2; if onefile unpack is too slow, switch to onedir before P3 or mark blocked | P2, P4 |
| Artifact size grows beyond alpha-acceptable bounds | Medium | Record onefile/onedir sizes; accept a larger alpha only with documented tradeoff | P2, P6 |
| Tauri `externalBin` naming/path does not match Windows expectations | High | P1 audits Tauri expectations before wiring; P3 build proves inclusion | P1, P3 |
| Config-only `externalBin` does not remove PATH dependency | High | P1 confirmed this; P3 now includes minimal Rust resolver work | P3, P4 |
| `tauri-plugin-shell` expands dependency/capability surface | Medium | Do not choose it for Sprint P unless the minimal resolver fails with evidence | P3 |
| Packaging changes leak secrets or session token into console/logs | High | P5 scans `sidecar.console.log` and runtime logs; preserve existing provider-key boundary | P5 |
| Bundled sidecar leaves orphan child processes | High | P5 repeats no-orphan check after packaged launch and forced failure | P5 |
| Crash screen regresses when sidecar fails before bind | Medium | P5 forces bad `WEAVER_DESKTOP_SIDECAR` and records crash UI behavior | P5 |
| PyInstaller adds an unaccepted build dependency | Medium | ADR 016 must be accepted before dependency/build-tool changes; no dependency edits in planning | P2 |
| Desktop work crosses into Python runtime/provider/translation/schema/UI | High | Scope fence; inspect `git diff --stat` before every commit | All |
| Windows-only solution gets mistaken for cross-platform final | Medium | Plan and ADR state Windows-first only; macOS/Linux remain deferred | P6 |

## 7. Validation matrix

Run against the packaged Windows desktop app, not `cargo tauri dev`.

| ID | Check | Method | Pass evidence |
| --- | --- | --- | --- |
| P-V1 | ADR accepted before PyInstaller implementation | `rtk grep -n "Status" docs/decisions/016-bundled-python-sidecar.md` | Status is accepted before P2 starts |
| P-V2 | Sidecar artifact builds | PyInstaller build command from P2 | Artifact path exists and size recorded |
| P-V3 | Bundled sidecar direct launch works | Run candidate sidecar with `serve --host 127.0.0.1 --port 0 --no-browser` | `/healthz` returns 200 |
| P-V4 | Tauri package includes sidecar | `cargo tauri build` from `desktop/` | Build succeeds; bundled sidecar present in output |
| P-V5 | Packaged desktop launches without `.venv\Scripts` on `PATH` | Sanitized PATH launch with `WEAVER_DESKTOP_SIDECAR` unset | Window opens and cockpit loads from bundled sidecar |
| P-V6 | No 401 loop | `sidecar.console.log` tail | `GET /healthz 200` then `GET /ui 200`, no repeated `401` |
| P-V7 | Logs exist and are safe | Inspect `%APPDATA%\Weaver\logs` | `runtime.log` + `sidecar.console.log`; no API keys/session token |
| P-V8 | Clean shutdown leaves no orphan | Close window, inspect process list | No attributable `weaver`/`python`/`uvicorn` process |
| P-V9 | Crash screen still works | Bad `WEAVER_DESKTOP_SIDECAR` launch | Crash screen with console path and mapped failure |
| P-V10 | Python static checks still pass | `uv run ruff check .`; `uv run pyright` | Both exit 0 |
| P-V11 | Scope fence held | `rtk git diff --stat` and file review | No provider, translation pipeline, QA/export, schema, or cockpit redesign edits |

## 8. Rollback plan

1. Revert the P3 commit that adds `bundle.externalBin` wiring.
2. Revert or disable the minimal bundled-sidecar resolver.
3. Revert or disable the P2 desktop-local PyInstaller build tooling.
4. Restore the Sprint O PATH-sidecar behavior: desktop resolves `WEAVER_DESKTOP_SIDECAR` or `weaver` on `PATH`.
5. Re-run `cargo tauri build` from `desktop/`.
6. Re-run the Sprint O packaged smoke with `.venv\Scripts` on `PATH`.
7. Document the Sprint P verdict as BLOCKED or PASS-WITH-CONDITIONS, preserving the failure evidence and next proposed packaging option.

Rollback must not touch `src/weaver/`, storage schema, provider code, translation
pipeline, QA/export, or cockpit UI.

## 9. Definition of Done

Sprint P is done only when:

- ADR 016 is accepted or Sprint P is explicitly blocked before implementation.
- P1 through P6 are completed in order.
- Packaged Windows desktop app launches without `.venv\Scripts` or external `weaver` on `PATH`.
- `/healthz` and `/ui` load from the bundled sidecar.
- `runtime.log` and `sidecar.console.log` are generated.
- Crash screen remains useful on sidecar startup failure.
- Window close leaves no attributable sidecar orphan.
- `uv run ruff check .` and `uv run pyright` pass.
- Final P6 gate report records verdict, risks, artifact sizes, rollback, and next step.

**Verdict definitions:**

- **PASS:** P-V1 through P-V11 green, self-contained Windows desktop alpha works.
- **PASS-WITH-CONDITIONS:** packaged app launches without external PATH sidecar but documented alpha limits remain, such as size or startup delay.
- **BLOCKED:** bundled artifact cannot satisfy launch, security, or lifecycle gates without a broader architecture change.

## Handoff

**Track:** T0/T9 planning
**Scope:** Define Sprint P execution plan and ADR proposal for a bundled Windows sidecar.
**Files/Areas Touched:** `docs/superpowers/plans/2026-06-14-sprint-p-bundled-sidecar.md`; `docs/decisions/016-bundled-python-sidecar.md`.
**What Changed:** Planning only. PyInstaller onedir is accepted for Sprint P, not implemented.
**What Was Intentionally Not Changed:** No production code, no Rust runtime code, no Python runtime code, no provider logic, no translation pipeline, no QA/export/schema/cockpit UI, no lockfiles, no dependency manifests, no Tauri config.
**Validation Performed:** Planning verification only: `uv run ruff check .`; `uv run pyright`.
**Known Risks:** PyInstaller hidden imports/package data, artifact size, bundled runtime path, and Tauri `externalBin` path conventions remain unproven until P2/P3.
**Recommended Next Role / Next Step:** Start P1 with `rtk read --level minimal --max-lines 220 desktop/src/launch_config.rs` and complete the launch-path audit before any PyInstaller implementation.
