# Sprint History — Archived Evidence (pre-v0.7.3)

> **Archive only — not an authority.** Current scope lives in `CLAUDE.md` §2.3; decisions live in ADRs; full logs live in git history and `docs/superpowers/handoffs/`. Moved out of `CLAUDE.md` on 2026-07-13 to keep the operating file lean.
>
> Naming: forward sprints use **descriptive names, not alphabet letters**. Historical labels (Sprint N/O/P, Q2x) survive only in handoff filenames, ADRs, and git history.

## Completed roadmap (through v0.7.1)

| Sprint                                                    | Status           | Hasil utama |
| --------------------------------------------------------- | ---------------- | ----------- |
| **Audit Cleanup Sprint**                                  | ✅ Done          | Dead code kecil dihapus, bug audit utama dibereskan, full gate hijau |
| **Q2C — Runtime Edge-Case Hardening**                     | ✅ Done          | ParseJob cancellation consistency, EPUB import snapshot atomicity |
| **Q2D — Provider Config UX Consolidation**                | ✅ Done / merged | `/ui/providers` jadi canonical config surface, `/ui/config` jadi compatibility redirect |
| **Q2E — Workspace Review & Export Confidence**            | ✅ Done / merged | Review/export/QA readiness UX lebih jelas |
| **Q2F — Tauri Sidecar Readiness Gate**                    | ✅ PASS          | Python/FastAPI contract + Rust compile verified; runtime smoke N1–N6 owner-confirmed |
| **Sprint N — Desktop Runtime Validation**                 | ✅ Done          | `cargo tauri dev` smoke green — N1–N6 (window, transition, no-401, no-orphan, logs, crash screen) |
| **Sprint O — Desktop Packaging / Installer Alpha**        | ✅ PASS          | Packaged `weaver-desktop.exe` builds + runs (O-V1–O-V7). Both conditions now closed: external PATH-sidecar → resolved by **Sprint P** (bundled sidecar); signing/auto-update/installer-final → resolved by **Desktop Installer & Release Hardening** (NSIS installer + signing-ready + opt-in update + tagged release). Superseded by P + ADR 017. |
| **Sprint P — Bundled Sidecar / Standalone Desktop Alpha** | ✅ PASS          | P1–P6 done; packaged app launches PATH-free, `/healthz`+`/ui` 200 (no 401), logs, crash screen, no orphan (WM_CLOSE + owner-confirmed native X-close 2026-06-14); `HEALTH_BUDGET` 5→20 s for PyInstaller cold start; signing/auto-update/installer/cross-platform deferred (not blockers) |
| **Desktop Installer & Release Hardening**                 | ✅ PASS          | ADR 017 (2026-06-15). Shipped + owner-validated: exit-66 (`DataDirError`→66), single version source + drift guard, NSIS per-user installer (install/launch/uninstall smoke PASS, data preserved), signing-ready `bundle.windows`, opt-in notification-only update check (default OFF), tag-triggered `release.yml` — **v0.7.1 released end-to-end via CI** (installer + `latest.json` published; manifest URL serves `{"version":"0.7.1"}`), upgrade-compat test PASS (0.7.1 over 0.7.0 keeps data, single entry). Deferred non-blocker: code-signing cert. See gate report. |

v0.7.2 (Connection-First Routing + Enforcement Loop) is summarized in `CLAUDE.md` §2.1; its full exit-criteria record (Bagian A/B, slice log S1–S5, post-S5 hardening, E1–E4) lives in git history of `CLAUDE.md` and in ADR 018/019 + handoffs.

## Desktop track pipeline (completed through Installer & Release Hardening)

```text
Packaging Alpha                ✅ done   (was Sprint O)
   ↓
Bundled Sidecar                ✅ done   (was Sprint P)
   ↓
Installer & Release Hardening  ✅ done   (ADR 017; v0.7.1 released)
   • Windows NSIS installer        ✅
   • Signing-ready pipeline        ✅ (signs on cert; deferred)
   • Opt-in update notification    ✅ (default OFF)
   • Upgrade testing               ✅
   ↓
Cross-Platform Desktop         🔜 next      (macOS / Linux)
   ↓
Desktop Optimization           📋 backlog
```

**Desktop items carried out of Sprint N/O/P (resolved / still open):**

| Item                                                                         | Source of truth                                                                     | Disposition                           |
| ---------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- | ------------------------------------- |
| Windows installer (`nsis`/`msi`), code signing, auto-update, upgrade testing | ADR 016 (deferred); `desktop/tauri.conf.json`                                       | ✅ Shipped by Installer & Release Hardening (cert still deferred) |
| Exit code `66` data-dir error implementation                                 | `docs/SIDECAR_CONTRACT.md` §5 → `services/app_paths.ensure_runtime_dirs`            | ✅ Shipped (tested `DataDirError`→66)  |
| macOS WKWebView + Linux WebKitGTK session-header injection                   | `desktop/src/webview_session.rs` (`#[cfg(not(windows))]` no-op)                     | Open → **Cross-Platform Desktop**     |
| POSIX graceful shutdown (SIGTERM before SIGKILL)                             | `desktop/src/sidecar.rs` (`kill()` SIGKILL-only on non-Windows)                     | Open → Cross-Platform Desktop         |
| onedir→onefile / payload-size + cold-start tuning                            | ADR 016 ("onefile remains a future optimization")                                   | Open → Desktop Optimization           |

Historical sequencing rule (now satisfied): ship Installer & Release Hardening before Cross-Platform Desktop and Desktop Optimization — the signed/installable Windows build was the nearest user-facing gap after the bundled sidecar.

## Durable desktop lessons (moved from CLAUDE.md §2.5)

Consult these when the desktop track reopens (Cross-Platform Desktop sprint):

| Area                          | Source of truth                                                                                                                                                                                                         | Carry-forward rule |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------- |
| Sidecar contract testing      | `tests/integration/test_runtime_random_port.py` · `tests/unit/api/test_desktop_security.py`                                                                                                                             | Real HTTP/Uvicorn is preferred over TestClient for sidecar contract tests. Reuse the `sidecar_server` fixture pattern rather than reimplementing Uvicorn threading. |
| CLI startup diagnostics       | `tests/unit/api/test_desktop_security.py`                                                                                                                                                                               | Mock `uvicorn.run` for exit-code tests (64/65). Use `_make_fake_uvicorn` helper. Assert no secret/token leakage in error output. |
| Sprint N readiness            | `docs/SIDECAR_CONTRACT.md` · `desktop/README.md`                                                                                                                                                                        | Desktop shell must be compile-verified (`cargo check`) before runtime smoke (`cargo tauri dev`). Do not skip compile gate. |
| Desktop packaging (Q2F/N/O/P) | `docs/INSTALL_DESKTOP.md` · Sprint P gate report (`docs/superpowers/handoffs/2026-06-14-sprint-p6-gate-report.md`) · ADR 016 | Sprint P (PASS) shipped the self-contained Windows alpha: PyInstaller onedir + Tauri `bundle.externalBin` + runtime resolver. Resolver order is mandatory: `WEAVER_DESKTOP_SIDECAR` override → bundled sidecar → PATH `weaver` fallback; `externalBin` config alone is insufficient and the PATH fallback must stay. Desktop startup `HEALTH_BUDGET` is **20 s** (bounded, P3b) because PyInstaller cold start exceeds the old 5 s — independent of the 5 s shutdown grace. Do not switch onedir→onefile, drop the PATH fallback/override, or add `tauri-plugin-shell` without evidence + an ADR. Bundling logic stays in `desktop/`/CI, never in `src/weaver/`. |
| Installer & release (ADR 017) | `docs/decisions/017-*.md` · `docs/superpowers/handoffs/2026-06-15-installer-release-gate-report.md` · `.github/workflows/release.yml` | `pyproject` is the **single version source**; never hand-edit `tauri.conf.json` version — run `desktop/scripts/sync-version.ps1`, and a `v*` tag must equal it (`check-version.ps1 -Tag`). Releases are tag-triggered (`release.yml`, windows runner); signing is **off until** the `WINDOWS_CERTIFICATE_THUMBPRINT` secret exists (no code change to enable). Update check is **opt-in, notification-only, default OFF** (`WEAVER_DESKTOP_UPDATE_CHECK` env or `%APPDATA%\Weaver\desktop\settings.json`) — never add download/install or `tauri-plugin-updater`/`-shell` without a new ADR. Installer config validated against the compiled `tauri-utils` schema (`deny_unknown_fields`) — verify field casing there, not just docs. Exit-66 is a real tested code (`DataDirError`). Desktop/packaging logic stays in `desktop/`+CI, never `src/weaver/`. |
