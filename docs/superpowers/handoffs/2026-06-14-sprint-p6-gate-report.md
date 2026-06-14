# Sprint P6 — Bundled Sidecar Gate Report

**Verdict: ✅ PASS** (promoted from PASS-WITH-CONDITIONS on 2026-06-14 after owner
human-close confirmation).

The Windows desktop alpha is now **self-contained**: the packaged app launches,
serves the cockpit, and shuts down cleanly with **no external `weaver` on `PATH`**
— closing the primary Sprint O condition. The last open condition (human
window-close) was owner-confirmed on 2026-06-14 (see Owner Confirmation below).
Release-grade work (signing, auto-update, final installer, cross-platform) remains
**deferred future work — not a Sprint P blocker**.

## Owner Confirmation — Human Close (P-V8), 2026-06-14

The owner manually launched the packaged app in PATH-free mode (bundled sidecar),
saw the loading screen → cockpit, then closed it with the **native window X
button** (real user interaction, not WM_CLOSE automation). After closure no
attributable `weaver` / `python` / `uvicorn` / bundled-sidecar process remained;
no restart, hang, or orphan. **P-V8 = PASS.** This closes the final
owner-confirmation condition carried from Sprint P.

## What Sprint P Actually Closed

This is the **biggest desktop milestone so far**: Sprint P removed the desktop
shell's hard dependency on an externally-installed `weaver` command. Before, the
packaged app could only find its backend by walking `PATH` into the repo virtual
environment — so it was not actually distributable. Now the backend ships inside
the package and `PATH` is only a last-resort dev/diagnostics fallback.

```text
Before (Sprint O):
  weaver-desktop.exe ──► PATH lookup ──► .venv\Scripts\weaver.exe   (external, required)

After (Sprint P):
  weaver-desktop.exe ──► resolver:
                           1. WEAVER_DESKTOP_SIDECAR override (optional)
                           2. bundled sidecar via Tauri externalBin   ◄── normal path
                           3. PATH `weaver`                            (dev/diagnostics fallback only)
```

Concretely: a tester can now run the packaged `weaver-desktop.exe` on a clean
Windows machine with **no Python, no virtualenv, and nothing named `weaver` on
`PATH`**, and the cockpit still launches. That was impossible before Sprint P and
was the single largest condition carried out of Sprint O.

## What Sprint P delivered

- PyInstaller **onedir** sidecar artifact (existing FastAPI app, no runtime
  rewrite).
- Tauri `bundle.externalBin` staging + `_internal` resource mapping.
- Minimal Rust bundled-sidecar resolver, order: `WEAVER_DESKTOP_SIDECAR` override
  → bundled sidecar → bare `weaver` on `PATH` (dev/diagnostics fallback).
- Startup-readiness fix (P3b): `HEALTH_BUDGET` 5 s → bounded 20 s for slow
  PyInstaller cold start; `[host]` startup diagnostics in `sidecar.console.log`
  and on the crash screen (resolved source/path, elapsed wait).

Architecture unchanged: FastAPI stays the sidecar, Tauri stays the host, sidecar
contract is intact, local-first/offline, no telemetry, Windows-only.

## Validation matrix (final)

| ID | Check | Result |
| --- | --- | --- |
| P-V1 | ADR 016 accepted before impl | PASS |
| P-V2 | Sidecar artifact builds | PASS |
| P-V3 | Direct sidecar `/healthz 200` | PASS |
| P-V4 | Tauri package includes sidecar | PASS |
| P-V5 | PATH-free packaged launch | PASS |
| P-V6 | No 401 loop | PASS |
| P-V7 | Logs exist + safe (default `%APPDATA%`) | PASS |
| P-V8 | No orphan on close (WM_CLOSE + human X-close) | PASS — human X-close owner-confirmed 2026-06-14 |
| P-V9 | Crash screen on failure | PASS |
| P-V10 | ruff + pyright | PASS |
| P-V11 | Scope fence held | PASS |

Evidence detail: `docs/superpowers/handoffs/2026-06-14-sprint-p4-p5-packaged-standalone-smoke.md`.

## Commands run (Sprint P closeout)

```
cargo check                 # PASS (3 pre-existing sidecar.rs dead-code warnings)
cargo tauri build           # PASS (1m52s)
uv run ruff check .         # All checks passed
uv run pyright              # 0 errors, 0 warnings
# packaged PATH-free smokes (isolated + default %APPDATA%): /healthz 200, /ui 200,
# static 200, 0 new 401, 6 logs, NO_SECRET_TOKEN_MATCHES, WM_CLOSE -> no orphan,
# bad override -> crash screen; git status -- src/weaver = none
```

## Artifact sizes

| Artifact | Size |
| --- | --- |
| `weaver-desktop.exe` (host) | 3.27 MB |
| `weaver.exe` (bundled sidecar) | 17.2 MB |
| `_internal` payload | 784 files (~171 MB onedir total) |

## Remaining risks

| Risk | Severity | Mitigation / status |
| --- | --- | --- |
| Human X-button close (was a condition) | Closed | Owner-confirmed 2026-06-14: native X-close leaves no orphan |
| Cold first-launch may approach the 20 s budget | Low | Budget bounded at 20 s; `[host]` elapsed diagnostic quantifies real cold start; warm runs were 2.1–2.7 s |
| ~171 MB onedir payload (size) | Medium (accepted) | Alpha tradeoff per ADR 016; onefile/compression is future optimization, **not** in scope |
| PyInstaller hidden-import gaps on rarely-hit routes | Medium | P2 added `collect_submodules("weaver.api")`; full cockpit nav + static assets verified 200; monitor on new routes |
| SmartScreen/AV may flag unsigned packed exe | Medium | Expected for an unsigned alpha; signing deferred |

## Deferred work (explicitly out of Sprint P scope)

- Code signing.
- Auto-update.
- Final production installer (NSIS/MSI).
- Cross-platform packaging (macOS WKWebView / Linux WebKitGTK header injection).
- onedir → onefile / payload-size optimization.
- macOS/Linux session-header interceptor (`webview_session.rs` is Windows-only).

## Rollback path

Per ADR 016 §Rollback: remove `bundle.externalBin` + resolver, disable the
PyInstaller build tooling, restore the Sprint O PATH-sidecar behavior, rebuild,
re-run the Sprint O packaged smoke with `.venv\Scripts` on `PATH`. Rollback
touches only `desktop/` + docs — never `src/weaver/`.

## Next-sprint recommendation

1. ✅ Done — owner confirmed human X-button close leaves no orphan (2026-06-14);
   Sprint P promoted to PASS.
2. Open a release-hardening sprint: signing + final installer (and optionally
   payload-size reduction) — separate scope, separate ADR if it changes packaging
   shape.

## Handoff

**Track:** T9 release gate
**Scope:** Final Sprint P verdict, risks, deferred work, rollback, sizes.
**Files/Areas Touched:** this report; `CLAUDE.md` phase ledger; `desktop/README.md`
status refresh (docs only).
**What Changed:** Sprint P closed at PASS (owner human-close confirmed 2026-06-14);
no code changed in P6.
**What Was Intentionally Not Changed:** no `src/weaver/`, provider, translation,
QA/export, schema, cockpit UI, resolver strategy, or PyInstaller shape.
**Validation Performed:** see matrix + P4/P5 handoff + Owner Confirmation section.
**Known Risks:** size/signing/installer/cross-platform deferred (not blockers).
**Recommended Next Role / Next Step:** open a release-hardening sprint plan for
signing + installer.
