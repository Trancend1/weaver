# ADR 017 — Desktop installer, signing-ready pipeline, and opt-in update notification

**Status:** Accepted (2026-06-15)

## Context

ADR 016 (Sprint P, PASS) made the Windows desktop alpha self-contained: a
PyInstaller onedir sidecar staged through Tauri `bundle.externalBin`, resolved by
a minimal Rust resolver. What it shipped is a **portable `.exe`** only
(`desktop/tauri.conf.json` → `bundle.targets: ["app"]`). The remaining
release-grade gaps, all carried forward in CLAUDE.md §2.1.1, are:

- **No installer.** No NSIS/MSI config; a tester gets a bare portable exe with no
  Start-menu entry, no uninstaller, no version metadata surface.
- **No code signing.** The build is unsigned, so Windows SmartScreen warns on
  first run (`docs/INSTALL_DESKTOP.md` Known limitations #2).
- **No update path.** Updates are manual "find the new exe yourself." There is no
  signal to the user that a newer version exists.
- **No release automation.** `.github/workflows/ci.yml` is ubuntu-only Python
  lint/type/test. The desktop is never built, packaged, or released in CI. The
  desktop release is an undocumented manual maintainer step.
- **Two version sources.** `pyproject.toml` `0.7.0` and `tauri.conf.json` `0.7.0`
  are hand-synced with no guard — a release will drift them.
- **Exit code 66 is unimplemented.** `docs/SIDECAR_CONTRACT.md` §5 reserves `66`
  for data-dir errors and `cli/main.py` comments it, but no code path raises it;
  `services/app_paths.ensure_runtime_dirs` does a bare `mkdir(...)` whose
  `OSError`/`PermissionError` escapes as an unmapped crash.

This ADR governs the **Desktop Installer & Release Hardening** sprint. It changes
the packaging *shape* (portable → installer) and adds a network capability
(opt-in update check), so it requires its own ADR per CLAUDE.md §3.6 and the
ADR-rules in `docs/DECISIONS.md`.

## Relationship to ADR 016

This ADR **builds on** ADR 016 and does not change the bundled-sidecar
architecture: PyInstaller onedir + `bundle.externalBin` + the Rust resolver order
(`WEAVER_DESKTOP_SIDECAR` override → bundled sidecar → PATH fallback) all stay.

It **narrowly supersedes one clause** of ADR 016's Security section — the
statement *"No telemetry, update ping, analytics, remote logging, or hosted
dependency is introduced."* — and only for the **opt-in, notification-only
update check** decided below. Every other security guarantee of ADR 016 (no
telemetry, no analytics, no remote logging, no hosted runtime dependency, no
provider-secret bundling, loopback-only sidecar) remains in force. The
supersession is intentionally minimal and is recorded here so the contradiction
is explicit, not silent.

## Decisions

### D1 — Installer: NSIS only

Produce a Windows **NSIS** installer (`bundle.targets: ["nsis"]`, or `["app",
"nsis"]` to keep the portable exe). MSI/WiX is **not** built this sprint: Weaver
is explicitly *not* an enterprise/SaaS product (CLAUDE.md §intro, §3.4), NSIS is
Tauri's first-class Windows installer, and NSIS is the format the update flow and
most single-user installs expect. MSI can be reopened with a later ADR if a real
group-policy/enterprise deployment need appears.

The installer must:

- Install per-user (no admin elevation required) into the standard per-user
  location, consistent with the per-user `%APPDATA%\Weaver` data dir.
- Register a Start-menu shortcut and a standard Windows uninstaller.
- **Preserve `%APPDATA%\Weaver`** (projects, DB, logs) on uninstall — same data
  retention promise as `docs/INSTALL_DESKTOP.md` (the data holds the user's
  novels/translations).
- Carry correct version metadata derived from the single version source (D5).

### D2 — Signing: signing-ready pipeline, no-op until a cert exists

The maintainer has **no code-signing certificate yet**. Rather than block the
sprint, the release pipeline is built **signing-ready**:

- `desktop/tauri.conf.json` `bundle.windows` carries the stable, secret-free
  signing config (`timestampUrl`, `digestAlgorithm`).
- The signing identity (`certificateThumbprint` or a `signCommand`) is injected
  **only by CI from a repository secret**. When the secret is absent the build
  proceeds **unsigned** — the pipeline must not fail for a missing cert.
- When a cert is later procured, flipping signing on is a secrets-only change
  (store `WINDOWS_CERTIFICATE` + `WINDOWS_CERTIFICATE_PASSWORD`, or a thumbprint),
  with **no code rework**.

Self-signed certs are explicitly out of scope: they do not clear SmartScreen and
add trust-store complexity for no user benefit.

### D3 — Updates: opt-in update *notification* only (default OFF)

Auto-download/auto-install is **rejected**. The accepted feature is an **opt-in,
notification-only** update check:

- **Default OFF.** No network call happens unless the user opts in. This keeps the
  offline-first / no-phone-home identity intact for every default install.
- **Opt-in mechanism (desktop-only, per ADR 016 boundary — never in
  `src/weaver/`):** a host settings file `%APPDATA%\Weaver\desktop\settings.json`
  (`{"update_check": true}`), with an env override `WEAVER_DESKTOP_UPDATE_CHECK`
  (`1`/`true` enables, `0`/`false` disables) that wins for testing/CI.
- **When enabled:** on launch, a background thread performs **one** HTTPS GET to a
  static release manifest published by the release pipeline
  (`https://github.com/Trancend1/weaver/releases/latest/download/latest.json`),
  reads the latest version, and compares it to the running
  `CARGO_PKG_VERSION`. No request is made on any other event.
- **Notification only.** If a newer version exists, the host shows a
  **non-blocking** notification with the release page URL. It **never** downloads,
  executes, or installs anything. The user updates manually by downloading the new
  installer. If the check fails (offline, rate-limited, malformed), it is silent
  and the app continues normally — a failed update check must never block launch.
- **No `tauri-plugin-updater`.** Because we never download or execute an artifact,
  manifest-signature verification is unnecessary. The check is a plain HTTPS GET
  via the existing `ureq` client (HTTPS requires enabling its TLS feature — see
  Consequences). Avoiding the updater plugin keeps the dependency and capability
  surface minimal, consistent with ADR 016's caution against expanding the
  capability surface.

This satisfies the six anti-slop gates (CLAUDE.md §4.3): real pain (testers had no
update signal), falsifiable (version compare), deterministic (string compare),
user override (opt-in + the user performs the update), failure visible (silent
no-op on error, never a fake "up to date"), cost visible (no background polling;
one GET only when opted in).

### D4 — Release pipeline: GitHub Actions on tag push

A `windows-latest` GitHub Actions workflow triggered on `v*` tag push:

1. Builds the PyInstaller sidecar (`desktop/scripts/build-sidecar.ps1`).
2. Builds the Tauri NSIS installer.
3. Signs the installer **iff** the signing secret is present (D2).
4. Generates `latest.json` (the D3 manifest) from the tag version.
5. Publishes a GitHub Release with the installer + `latest.json` attached.

The existing ubuntu Python CI (`ci.yml`) is unchanged; release is a **separate**
workflow. A pre-release guard asserts tag == `pyproject` version == tauri version
(D5) and fails the release on mismatch.

### D5 — Single version source

`pyproject.toml` `version` is the **single source of truth**. The desktop version
is **derived**, not hand-edited:

- `desktop/scripts/sync-version.ps1` reads `pyproject.toml` and writes the same
  value into `desktop/tauri.conf.json`.
- A guard (run in CI and available locally) asserts the two match and, in the
  release workflow, that both equal the pushed tag (`vX.Y.Z` → `X.Y.Z`).

### D6 — Exit code 66 implementation

Implement the reserved data-dir exit code so the host's existing
`exit_meaning(66)` mapping (`desktop/src/lib.rs:391`) becomes reachable:

- Add `DataDirError(WeaverError)` to the error hierarchy.
- `services/app_paths.ensure_runtime_dirs` raises `DataDirError` on
  `OSError`/`PermissionError` instead of letting it escape.
- The `serve` path (`cli/main.py:_run_fastapi_cockpit`) calls
  `ensure_runtime_dirs()` before `uvicorn.run` and maps `DataDirError` to
  `typer.Exit(code=66)` with a what/why/next message.
- A regression test asserts exit 66 (mock the directory to be unwritable), joining
  the existing 64/65 tests; `SIDECAR_CONTRACT.md` §5 moves 66 from *reserved* to
  *implemented*.

## Options considered

### Updates

| Option | Verdict | Reason |
|---|---|---|
| Full background auto-update (default ON) | Rejected | Most strongly contradicts offline-first / no-phone-home; silently executes downloaded code. |
| Opt-in background updater (download+install) | Rejected | Still executes downloaded artifacts; needs updater keypair + signature infra for a feature the user can do manually. |
| **Opt-in notification only (default OFF)** | **Accepted (D3)** | Lightest possible network surface; user keeps full control; no artifact execution. |
| Manual "open releases page" only (no check) | Not chosen | Simpler, but gives no signal that an update *exists*; owner chose the notification middle-ground. |

### Installer

| Option | Verdict | Reason |
|---|---|---|
| **NSIS only** | **Accepted (D1)** | Tauri-first-class, updater-friendly, right fit for a single-user workbench. |
| NSIS + MSI | Rejected (this sprint) | MSI/WiX surface only pays off for enterprise/group-policy, which the project explicitly is not. |
| MSI only | Rejected | Weaker updater fit; enterprise-oriented. |

### Signing

| Option | Verdict | Reason |
|---|---|---|
| **Signing-ready, no-op until secret present** | **Accepted (D2)** | Unblocks the whole sprint with zero rework when a cert arrives. |
| Require OV/EV cert now | Blocked | No cert available. |
| Azure Trusted Signing | Deferred | Requires Azure setup not currently in place. |
| Self-signed | Rejected | Does not clear SmartScreen. |

## Consequences

- The desktop ships as an installable, uninstallable Windows app with proper
  identity metadata.
- A new GitHub Actions **release** workflow exists; tag push produces a published
  Release. CI cost rises (a Windows runner per release tag).
- `ureq` gains a TLS feature (rustls) for the opt-in HTTPS update check —
  a dependency/feature addition justified and bounded by this ADR (D3). It is the
  only new network egress and only fires on explicit opt-in.
- A new desktop capability surface: reading `settings.json`, one outbound HTTPS
  GET, and a notification window — all gated behind the opt-in flag.
- `pyproject.toml` becomes the authoritative version; editing
  `tauri.conf.json` version by hand is now a guarded error.
- Exit 66 becomes a real, tested contract code; `SIDECAR_CONTRACT.md` §5 updates.
- Until a cert is procured, released installers remain unsigned (SmartScreen may
  warn) — a documented, accepted known gap, not a blocker.

## Security considerations

- The update check is **opt-in and notification-only**: no artifact is downloaded
  or executed, so there is no remote-code-execution surface and no need for
  manifest signature verification.
- The manifest GET sends no identifying data beyond a standard User-Agent; it is a
  plain version lookup against a public GitHub release asset. No analytics, no
  telemetry payload, no cookies.
- Signing secrets live only in CI repository secrets, never in the repo, logs, or
  artifacts. A missing secret yields an unsigned build, never a leak.
- Provider secrets and `WEAVER_SESSION_TOKEN` handling are unchanged from ADR 016
  — none are bundled, logged, or shipped.
- The installer must not write provider keys or tokens anywhere.

## Rollback plan

Each decision rolls back independently:

1. **Update notification:** delete the update-check module, revert `ureq` TLS
   feature, drop the capability. Default-OFF means nothing else changes.
2. **Installer:** revert `bundle.targets` to `["app"]`; the portable exe (ADR 016
   state) is restored.
3. **Signing:** remove the `bundle.windows` signing block + CI signing step.
4. **Release workflow:** delete the workflow file; releases revert to manual.
5. **Version guard / sync:** delete the script + guard; revert to hand-synced.
6. **Exit 66:** revert `ensure_runtime_dirs` to bare `mkdir`, drop `DataDirError`
   and its test; `SIDECAR_CONTRACT.md` §5 returns 66 to *reserved*.

No rollback touches provider code, the translation pipeline, schema, QA/export, or
the cockpit UI.

## Acceptance criteria

- [ ] NSIS installer builds; installs per-user with Start-menu entry + uninstaller.
- [ ] Uninstall preserves `%APPDATA%\Weaver`.
- [ ] Signing pipeline runs signed when a cert secret is present and unsigned
      (without failing) when absent.
- [ ] Update check is OFF by default; when opted in it notifies (no download) and
      is a silent no-op on failure.
- [ ] `pyproject` version is the single source; the guard fails on drift.
- [ ] Release workflow on a `v*` tag produces a GitHub Release with installer +
      `latest.json`.
- [ ] Exit 66 raised + tested; `SIDECAR_CONTRACT.md` §5 updated.
- [ ] Upgrade test: installing vN+1 over vN preserves data and replaces the binary.
- [ ] `uv run ruff check .`, `uv run ruff format --check .`, `uv run pyright`,
      `uv run pytest` all pass.
- [ ] Final gate report records artifact sizes, signed/unsigned status, and the
      upgrade-test evidence.

## Related files

- `docs/superpowers/plans/2026-06-15-desktop-installer-release-hardening.md` (execution plan)
- `docs/decisions/016-bundled-python-sidecar.md` (built upon; one clause superseded)
- `docs/SIDECAR_CONTRACT.md` (§5 exit codes)
- `docs/INSTALL_DESKTOP.md`
- `desktop/tauri.conf.json`
- `desktop/Cargo.toml`
- `desktop/src/launch_config.rs`, `desktop/src/lib.rs`
- `desktop/scripts/build-sidecar.ps1`
- `src/weaver/services/app_paths.py`
- `src/weaver/cli/main.py`
- `.github/workflows/ci.yml` (sibling to the new release workflow)
