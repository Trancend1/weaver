# Sprint P2 - PyInstaller Sidecar Artifact Experiment

**Verdict:** PARTIAL PASS

P2 built the experimental PyInstaller onedir sidecar artifact and proved the
existing `serve` contract can start from that artifact. Tauri wiring was not
changed.

## Scope

P2 scope was limited to:

- Add desktop-local PyInstaller build surface.
- Build `desktop/target/sidecar/weaver/weaver.exe`.
- Direct-test the artifact.
- Smoke-test the existing desktop app through `WEAVER_DESKTOP_SIDECAR`.
- Do not edit `desktop/tauri.conf.json`.
- Do not add `bundle.externalBin`.
- Do not add the Rust bundled-sidecar resolver yet.

## Files changed

- `desktop/sidecar/weaver_sidecar_entry.py`
- `desktop/sidecar/weaver-sidecar.spec`
- `desktop/scripts/build-sidecar.ps1`
- `docs/superpowers/handoffs/2026-06-14-sprint-p2-pyinstaller-experiment.md`

No `pyproject.toml`, `uv.lock`, `Cargo.toml`, `Cargo.lock`, `tauri.conf.json`,
Rust runtime code, Python runtime code, provider logic, translation pipeline, QA,
export, schema, or cockpit UI was changed.

## Build approach

PyInstaller was not added to project dependencies. The repeatable build wrapper
uses:

```powershell
uv run --python <system-python> --no-managed-python --no-python-downloads --all-extras --with "pyinstaller>=6,<7" pyinstaller ...
```

The script sets `UV_CACHE_DIR` to `desktop/target/uv-cache` when not already set
so the packaging cache stays local to the desktop build output. The build needed
local toolchain/cache access outside the workspace and was run with command
approval.

The PyInstaller spec includes:

- `weaver/api/templates`
- `weaver/api/static`
- `weaver/providers/templates`
- `weaver/storage/schema.sql`
- `weaver.api` hidden imports for Uvicorn's `weaver.api.app:create_api_app`
  factory string
- Uvicorn loop/protocol/lifespan hidden imports

## Artifact

```text
desktop/target/sidecar/weaver/weaver.exe
```

Artifact executable size:

```text
17,214,723 bytes
```

Onedir total file payload:

```text
785 files
171,175,979 bytes
```

## Validation evidence

### CLI help

Command:

```powershell
.\desktop\target\sidecar\weaver\weaver.exe --help
```

Result: PASS. The artifact renders the normal Weaver Typer command surface,
including `serve` and `serve-api`.

### Package data

Command:

```powershell
Get-ChildItem .\desktop\target\sidecar\weaver\_internal\weaver\api\templates,
  .\desktop\target\sidecar\weaver\_internal\weaver\api\static,
  .\desktop\target\sidecar\weaver\_internal\weaver\providers\templates,
  .\desktop\target\sidecar\weaver\_internal\weaver\storage
```

Result: PASS. Templates, static assets, provider prompt templates, and
`schema.sql` are present in the onedir payload.

### Direct sidecar serve smoke

Command shape:

```powershell
$env:WEAVER_ENV = "desktop"
$env:WEAVER_DOCS = "false"
$env:WEAVER_SESSION_TOKEN = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
$env:WEAVER_DATA_DIR = ".\desktop\target\p2-direct-runtime-<timestamp>"
.\desktop\target\sidecar\weaver\weaver.exe serve --host 127.0.0.1 --port 18765 --no-browser
```

Result: PASS.

Evidence:

```text
GET /healthz -> 200
GET /ui with X-Weaver-Session -> 200
runtime.log generated
backend.log/export.log/job.log/provider.log generated
no sidecar process left after cleanup
```

### Desktop override smoke

Command shape:

```powershell
$env:WEAVER_DESKTOP_SIDECAR = "D:\DevSpace\Projects\weaver\desktop\target\sidecar\weaver\weaver.exe"
$env:WEAVER_DATA_DIR = ".\desktop\target\p2-desktop-runtime-<timestamp>"
Start-Process .\desktop\target\release\weaver-desktop.exe
```

Result: PARTIAL PASS.

Evidence from `sidecar.console.log`:

```text
GET /healthz HTTP/1.1" 200 OK
GET /ui HTTP/1.1" 200 OK
GET /static/app.css HTTP/1.1" 200 OK
GET /static/htmx.min.js HTTP/1.1" 200 OK
GET /static/weaver-mark-mono.svg HTTP/1.1" 200 OK
```

Logs generated:

```text
runtime.log
sidecar.console.log
backend.log
export.log
job.log
provider.log
```

Lifecycle issue:

```text
CloseMainWindow() returned True and the desktop process exited, but the
PyInstaller sidecar process remained alive.
```

Cleanup was performed manually:

```text
NO_ORPHANS_AFTER_CLEANUP
```

This may be specific to the programmatic close path used in the smoke or to the
older Sprint O packaged executable, but it is not counted as a clean lifecycle
pass. P5 must repeat a true window-close/no-orphan validation after P3.

### Secret/session leakage scan

Command shape:

```powershell
Select-String -Pattern '0123456789abcdef','WEAVER_SESSION_TOKEN',
  'DEEPSEEK_API_KEY','GEMINI_API_KEY','OPENAI_API_KEY','api_key','apikey'
```

Result:

```text
NO_SECRET_TOKEN_MATCHES
```

## Hidden import / package data fixes

First direct serve failed:

```text
ERROR: Error loading ASGI app. Could not import module "weaver.api.app".
```

Fix:

```python
hiddenimports += collect_submodules("weaver.api")
```

After rebuild, direct `/healthz` and `/ui` passed.

PyInstaller warning file still lists many optional/platform-specific missing
modules. Notable expected entries include POSIX-only modules, optional lxml/html
parsers, optional trio/http2/brotli extras, optional `fugashi`, and optional
Google/gRPC helpers. None blocked the validated direct cockpit smoke.

## Commands run

```powershell
rtk git add docs/decisions/016-bundled-python-sidecar.md docs/superpowers/plans/2026-06-14-sprint-p-bundled-sidecar.md docs/superpowers/handoffs/2026-06-14-sprint-p1-sidecar-launch-audit.md
rtk git commit -m "docs(desktop): accept bundled sidecar strategy"
rtk git push --set-upstream origin feat/bundled-sidecar-desktop
rtk read --level minimal --max-lines 260 pyproject.toml
rg -n "[project.scripts]|weaver\\s*=|def main|Typer|templates|static|Jinja2Templates" pyproject.toml src\weaver
rg --files src\weaver\api src\weaver\cli src\weaver
rtk read --level minimal --max-lines 260 src\weaver\cli\main.py
rtk read --level minimal --max-lines 120 src\weaver\api\templating.py
rtk read --level minimal --max-lines 100 src\weaver\providers\prompts.py
rtk read --level minimal --max-lines 180 src\weaver\api\app.py
rtk read --level minimal --max-lines 220 src\weaver\core\templates.py
rtk read --level minimal --max-lines 220 src\weaver\storage\db.py
.\desktop\scripts\build-sidecar.ps1
.\desktop\target\sidecar\weaver\weaver.exe --help
curl.exe -s -o NUL -w "%{http_code}" http://127.0.0.1:18765/healthz
curl.exe -s -o NUL -w "%{http_code}" -H "X-Weaver-Session: <token>" http://127.0.0.1:18765/ui
Start-Process .\desktop\target\release\weaver-desktop.exe
Get-Content .\desktop\target\p2-desktop-runtime-<timestamp>\logs\sidecar.console.log -Tail 30
Select-String -Pattern ...
```

## Handoff

**Track:** T3/T6/T7/T8 packaging experiment
**Scope:** Build and direct-test a PyInstaller onedir sidecar artifact for Sprint P.
**Files/Areas Touched:** `desktop/sidecar/`, `desktop/scripts/`, this handoff.
**What Changed:** Added desktop-local PyInstaller entrypoint/spec/build wrapper. Built generated artifact under `desktop/target/sidecar/weaver/`.
**What Was Intentionally Not Changed:** No Tauri config, no externalBin, no Rust resolver, no Python runtime logic, no provider/translation/QA/export/schema/cockpit UI, no dependency manifests or lockfiles.
**Validation Performed:** Artifact existence/size, `--help`, package-data inspection, direct `serve` smoke (`/healthz 200`, `/ui 200`), desktop override smoke (`/healthz 200`, `/ui 200`, static assets 200), logs generated, secret/token scan.
**Known Risks:** Programmatic desktop close left the PyInstaller sidecar orphaned; P5 must revalidate true window-close lifecycle after P3. Optional PyInstaller missing-import warnings remain to monitor if deeper UI/provider routes fail.
**Recommended Next Role / Next Step:** P3 can start for `externalBin` staging and minimal bundled-sidecar resolver, but it must preserve `WEAVER_DESKTOP_SIDECAR` priority and include no-orphan lifecycle regression validation before claiming Sprint P PASS.
