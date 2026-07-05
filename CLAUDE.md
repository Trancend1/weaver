# Weaver

Offline-capable, glossary-aware **JP→EN light-novel translation workbench** with a **CLI** and local **web cockpit**. Development is **web-cockpit-first**, with the CLI serving as a supporting interface for automation and power-user workflows.

**Not a SaaS platform, consumer-facing product, hosted service, collaborative platform, or complex SPA.**

> **Operating Manual:** This repository follows the global agent workflow defined in `@WORKFLOW.md`. This document serves as the repository-level coordination layer and references supporting documentation rather than duplicating strategy, process, or implementation details.
>
> **Current Orchestrator:** Repository Owner (Trancend1) + Claude acting as Lead Technical Orchestrator.
>
> **Current Phase:** **v0.7.2 released** — tag `v0.7.2` on `main` ships Connection-First Routing (ADR 018) + Translation Enforcement Loop (ADR 019). Post-release audit blocker fixes landed on branch `fix/v072-audit-blockers` (2 commits, pending merge).
>
> **Status:** No active sprint. Full release audit (2026-07-05): all gates green (ruff / format / pyright clean; **1614 passed** after fixes). The audit's three High findings are fixed on `fix/v072-audit-blockers`: (H1) cockpit-saved API key invisible to translate until restart → provider factory now resolves keys shell-env→secret-store at build time; (H2) legacy gemini shim endpoint corrected `…/v1beta` → `…/v1beta/openai`; (H3) provider network calls moved **outside** the SQLite write transaction. Medium/Low findings carried into v0.7.3 planning (§2.3).

> **Current Objective:** Merge `fix/v072-audit-blockers`, then open the **v0.7.3 execution plan** (per §2.2: define §2.3/§2.4 first — no implementation before the plan). Candidate scope = audit carry-forward list in §2.3.
>
> **Current Sprint:** none active. After v0.7.3: **Cross-Platform Desktop (macOS/Linux)** with a fresh plan + ADR (§2.1.1).

---

## 1. Documentation Map

Docs are the spec. Code follows docs. If code contradicts docs, ask first.

| Topic                                                        | Source of truth                                                                                                                                                                                                              |
| ------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| User-facing: install, quickstart, commands                   | [README.md](README.md)                                                                                                                                                                                                       |
| Navigation supplement — module map, CLI/web flow, data, deps | [docs/CODEMAPS/architecture.md](docs/CODEMAPS/architecture.md) · [backend](docs/CODEMAPS/backend.md) · [frontend](docs/CODEMAPS/frontend.md) · [data](docs/CODEMAPS/data.md) · [dependencies](docs/CODEMAPS/dependencies.md) |
| Runtime contract for Tauri (or any) host shell               | [docs/SIDECAR_CONTRACT.md](docs/SIDECAR_CONTRACT.md)                                                                                                                                                                         |
| Testing, regression, release, migration discipline           | [docs/MAINTENANCE.md](docs/MAINTENANCE.md)                                                                                                                                                                                   |
| Architecture decisions (ADR `001`–`019`)                     | [docs/DECISIONS.md](docs/DECISIONS.md) · [docs/decisions/](docs/decisions/)                                                                                                                                                  |
| Active reference specs                                       | [docs/PROMPT_DESIGN.md](docs/PROMPT_DESIGN.md) · [docs/SECURITY_AND_PERFORMANCE.md](docs/SECURITY_AND_PERFORMANCE.md)                                                                                                        |
| RTK shell tooling rule                                       | `C:\Users\transcend\.claude\RTK.md`                                                                                                                                                                                          |
| Global workflow template (this file follows it)              | `C:\Users\transcend\.claude\WORKFLOW.md`                                                                                                                                                                                     |

**Hierarchy:** `docs/CODEMAPS/` is the primary navigation supplement (module map, CLI/web workflows, data flow, dependencies). ADRs and active sprint docs are source of truth for decisions. `SIDECAR_CONTRACT.md`, `MAINTENANCE.md`, `PROMPT_DESIGN.md`, and `SECURITY_AND_PERFORMANCE.md` remain as detailed reference docs for their respective domains. `.reports/` is an audit/report artifact area; do not treat it as product or architecture authority.

---

## 2. Progress — Phase Schedule

### 2.1 Roadmap Snapshot

Current status: **active phase defined in §2.3**.

| Sprint                                                    | Status           | Hasil utama                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| --------------------------------------------------------- | ---------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Audit Cleanup Sprint**                                  | ✅ Done          | Dead code kecil dihapus, bug audit utama dibereskan, full gate hijau                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| **Q2C — Runtime Edge-Case Hardening**                     | ✅ Done          | ParseJob cancellation consistency, EPUB import snapshot atomicity                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| **Q2D — Provider Config UX Consolidation**                | ✅ Done / merged | `/ui/providers` jadi canonical config surface, `/ui/config` jadi compatibility redirect                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| **Q2E — Workspace Review & Export Confidence**            | ✅ Done / merged | Review/export/QA readiness UX lebih jelas                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| **Q2F — Tauri Sidecar Readiness Gate**                    | ✅ PASS          | Python/FastAPI contract + Rust compile verified; runtime smoke N1–N6 owner-confirmed                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| **Sprint N — Desktop Runtime Validation**                 | ✅ Done          | `cargo tauri dev` smoke green — N1–N6 (window, transition, no-401, no-orphan, logs, crash screen)                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| **Sprint O — Desktop Packaging / Installer Alpha**        | ✅ PASS          | Packaged `weaver-desktop.exe` builds + runs (O-V1–O-V7). Both conditions now closed: external PATH-sidecar → resolved by **Sprint P** (bundled sidecar); signing/auto-update/installer-final → resolved by **Desktop Installer & Release Hardening** (NSIS installer + signing-ready + opt-in update + tagged release). Superseded by P + ADR 017.                                                                                                                                                                                                                           |
| **Sprint P — Bundled Sidecar / Standalone Desktop Alpha** | ✅ PASS          | P1–P6 done; packaged app launches PATH-free, `/healthz`+`/ui` 200 (no 401), logs, crash screen, no orphan (WM_CLOSE + owner-confirmed native X-close 2026-06-14); `HEALTH_BUDGET` 5→20 s for PyInstaller cold start; signing/auto-update/installer/cross-platform deferred (not blockers)                                                                                                                                                                                                                                                                                    |
| **Desktop Installer & Release Hardening**                 | ✅ PASS          | ADR 017 (2026-06-15). Shipped + owner-validated: exit-66 (`DataDirError`→66), single version source + drift guard, NSIS per-user installer (install/launch/uninstall smoke PASS, data preserved), signing-ready `bundle.windows`, opt-in notification-only update check (default OFF), tag-triggered `release.yml` — **v0.7.1 released end-to-end via CI** (installer + `latest.json` published; manifest URL serves `{"version":"0.7.1"}`), upgrade-compat test PASS (0.7.1 over 0.7.0 keeps data, single entry). Deferred non-blocker: code-signing cert. See gate report. |
| **v0.7.2 — Connection-First Routing + Enforcement Loop** | ✅ Done / tagged | ADR 018 + ADR 019, released as tag `v0.7.2` on `main`. **018:** one `openai_chat`(+`fake`), removed gemini/ollama natives + `google-generativeai`, connection registry + per-segment routing/fallback + discovery cache + CLI parity (S1–S5). **Post-S5 (done):** cockpit translate + glossary-suggest + candidate made routing-aware (`resolve_translation_engines`/`resolve_consumer_config`) — fixes live `provider.model missing`/`incomplete`; dup retranslate CTA dropped; copywriting pass. **019 (done):** glossary/character/TM enforcement loop + anti-slop (E1–E4). **Post-release audit (2026-07-05):** 3 High findings fixed on `fix/v072-audit-blockers` (key resolution, gemini shim URL, provider call inside write txn); Medium/Low carry-forward in §2.3.                                                                                                                                                                                                                                                             |
| **Cross-Platform Desktop (macOS/Linux)**                  | 📋 Planned       | WKWebView (macOS) + WebKitGTK (Linux) session-header injection and POSIX graceful shutdown (SIGTERM), plus per-OS bundled sidecar. See §2.1.1.                                                                                                                                                                                                                                                                                                                                                                                                                               |
| **Desktop Optimization**                                  | 📋 Backlog       | onedir→onefile or payload trim and cold-start budget tuning, only after the installer ships and with evidence. See §2.1.1.                                                                                                                                                                                                                                                                                                                                                                                                                                                   |

Legend: ✅ complete · 🟡 pass-with-conditions · 🔜 next · 📋 planned/backlog · ⏭️ blocked · 🚫 deferred

Completed work is historical. Keep detailed evidence in git history, ADRs, sprint plans, validation notes, and handoff docs. This operating file should only preserve information needed to guide current and future work.

When starting a new sprint or phase:

- Update §2.1 with the current status.
- Define the active scope in §2.3.
- Define exit criteria in §2.4.
- Add only durable carry-forward lessons to §2.5.
- Do not continue old sprint scaffolding by default.

### 2.1.1 Deferred / Backlog (not yet scheduled)

Evidence-linked carry-forward. These are proposals, not active scope: each needs its own plan (and an ADR where it changes packaging shape, the stack, or a contract) before implementation. Do not scaffold ahead of a plan.

> Naming: forward sprints use **descriptive names, not alphabet letters**. Completed sprints keep their historical labels (Sprint N/O/P, Q2x) only because handoff filenames, ADRs, and git history already reference them.

**Desktop track pipeline:**

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

**Desktop (carried out of Sprint N/O/P):**

| Item                                                                         | Source of truth                                                                     | Proposed sprint                       |
| ---------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- | ------------------------------------- |
| Windows installer (`nsis`/`msi`), code signing, auto-update, upgrade testing | ADR 016 (deferred); `desktop/tauri.conf.json` `targets:["app"]` only                | **Installer & Release Hardening**     |
| Exit code `66` data-dir error implementation                                 | `docs/SIDECAR_CONTRACT.md` §5 (reserved) → `services/app_paths.ensure_runtime_dirs` | Installer & Release Hardening (minor) |
| macOS WKWebView + Linux WebKitGTK session-header injection                   | `desktop/src/webview_session.rs` (`#[cfg(not(windows))]` no-op)                     | **Cross-Platform Desktop**            |
| POSIX graceful shutdown (SIGTERM before SIGKILL)                             | `desktop/src/sidecar.rs` (`kill()` SIGKILL-only on non-Windows)                     | Cross-Platform Desktop                |
| onedir→onefile / payload-size + cold-start tuning                            | ADR 016 ("onefile remains a future optimization")                                   | Desktop Optimization                  |

**Product / feature backlog (deferred by their ADRs, no owner schedule yet):**

| Item                                   | Source of truth                                      | Status                                            |
| -------------------------------------- | ---------------------------------------------------- | ------------------------------------------------- |
| OCR implementation beyond the contract | ADR 012 + `services/ocr_contract.py` (contract only) | Deferred feature; reopen with a plan              |
| Per-chapter QA tree badges             | ADR 008 (deferred to avoid full novel-scope scan)    | Deferred UX; gate on render-path budget (Gate B1) |
| QA `error` severity tier               | ADR 013 (**Rejected / Deferred**)                    | Do **not** plan unless explicitly reopened        |
| Provider-complete cost auditing        | ADR 014 (out of scope)                               | Reopen only with a migration + ADR                |

**Permanently out of scope unless an ADR reopens (CLAUDE.md §3.4/§3.5):** new provider families, route rewrites, SPA migration, Node build pipeline, external queue/worker daemon, cloud sync, telemetry/phone-home, multi-user SaaS architecture.

> Sequencing rule: ship **Installer & Release Hardening** (public, signed Windows installer) before Cross-Platform Desktop and Desktop Optimization. Those two are lower priority than a signed, installable Windows build, which is the nearest user-facing gap after the bundled sidecar.

### 2.2 Reusable Phase Gate

Before starting any new sprint, phase, or stage:

1. **Define scope** in §2.3, including acceptance criteria and explicit non-goals.
2. **List exit criteria** in §2.4 in plain language.
3. **Verify each criterion** with a concrete command, test, file check, or manual inspection.
4. **State user-facing status:** usable now, internal-only, not yet user-facing, or blocked.
5. **If all pass** — update §2.1 / §2.3 / §2.4 / §2.5 and write a handoff note.
6. **If any fails** — mark blocked, record missing proof, and stop.

> Required reminder: **Check exit criteria first. No next stage until evidence exists. Explain the detail for manual inspection.**

### 2.3 Active Phase — none (between sprints; v0.7.2 released)

**v0.7.2 shipped:** tag `v0.7.2` on `main` — Connection-First Routing (ADR 018, S1–S5 + post-S5 hardening) + Translation Enforcement Loop (ADR 019, E1–E4). Deep detail lives in ADR 018/019, the enforcement-loop plan (`docs/superpowers/specs/2026-06-16-enforcement-loop-execution-plan.md`), §2.4, and git history. The D9 lean-backing fence held: no circuit breaker, health-score, presets, cost dashboard, rotation window, or `routing_decisions` ledger.

**Post-release audit (2026-07-05)** — full-repo release audit; three High findings fixed on `fix/v072-audit-blockers` (2 commits, **pending merge**), gates green after fix (ruff/format/pyright clean, **1614 passed**):

- **H1 fixed** (`019834a`): a key saved from a running cockpit was invisible to translate until restart (Test ✓ but translate raised `WEAVER_CONN_<NAME> is not set`). The provider factory now resolves keys **shell env → secret store** at build time (`providers/registry._resolve_key_value`).
- **H2 fixed** (`019834a`): the legacy gemini D6 shim pointed at `…/v1beta` (no `/chat/completions` route there) → corrected to `…/v1beta/openai` (ADR 018 §5.3).
- **H3 fixed** (`dee710f`): `translate_one_segment` held the WAL write lock across the provider network call (minutes, × fallback chain × repair re-ask) — concurrent cockpit writes failed with "database is locked". Provider calls now run outside any transaction; one segment **result** = one atomic commit (§4.2 state rule updated to match).

**Carry-forward → v0.7.3 planning (audit findings, not yet scoped):**

- **Medium:** a dead primary aborts the run at healthcheck even when healthy fallbacks exist; a corrupt `connections.toml`/`secrets.toml` parses as empty and the next write silently rewrites it (data-loss edge); legacy `[provider]` brand projects now record `provider="custom"` in attempt history (0.7.1 recorded the brand); enforcement violations/repair outcomes are not persisted or surfaced (and detection is gated by `enforce_repair`, contradicting its docstring); per-segment token cost splits between the row (final attempt only) and the run summary (incl. repair).
- **Low:** `list_connections` re-parses the registry TOML N+1 times on render; `_escape` in the TOML writers misses control chars/newlines; `weaver inspect` (`services/project.py:244`) is the last direct `[provider]` reader (deferred routing seam, per owner).
- **Pending validations:** live Gemini/Ollama over their OpenAI-compatible endpoints (`requires_cloud`/`requires_ollama`, real machine); owner-visible E2 repair token-cost delta before locking default-on; the gemini shim's default model `gemini-1.5-flash` is retired upstream — revisit during the live check.
- **Speed candidate (needs an ADR):** bounded in-process translate concurrency (2–4 segments), unlocked by the H3 transaction split.

**Next:** merge `fix/v072-audit-blockers` → write the v0.7.3 execution plan and update §2.3/§2.4 (Gate A) before any implementation. Do not continue v0.7.2 scaffolding.

---

**Historical — Desktop Installer & Release Hardening (✅ PASS)**

The Desktop Installer & Release Hardening sprint closed **PASS** (2026-06-15). ADR 017 shipped: NSIS per-user installer, signing-ready pipeline (unsigned until cert), opt-in notification-only update check (default OFF), single version source + drift guard, exit-66, and a tag-triggered release workflow that published **v0.7.1** end-to-end (installer + `latest.json`). Owner-machine smoke (install/launch/uninstall + upgrade) PASS; data preserved across both. Code signing is the only deferred non-blocker. Decisions locked: auto-update = opt-in notification only (default OFF); signing = signing-ready; installer = NSIS only; release = GitHub Actions on tag push. Full rationale in ADR 017. Cross-Platform Desktop (macOS/Linux) remains planned (§2.1.1).

---

**Historical — Sprint P complete (✅ PASS)**

**Sprint P closed** under ADR 016, **PASS** (owner human-close confirmed 2026-06-14). Q2F + Sprint N + Sprint O also closed. Full backlog in §2.1.1.

**Status: ✅ Sprint P PASS** — the packaged Windows alpha is self-contained. Bundled PyInstaller onedir sidecar staged via Tauri `bundle.externalBin`; resolver order per ADR 016: `WEAVER_DESKTOP_SIDECAR` override → bundled sidecar → PATH `weaver` fallback. Packaged PATH-free launch returns `/healthz` 200 then `/ui` 200 (no 401 loop), generates logs in `%APPDATA%\Weaver\logs`, shows the crash screen on forced failure, and leaves no orphan after WM_CLOSE and the owner-confirmed native X-button close.

Done (Sprint P — P1–P6):

- P1 audit: `externalBin` alone is insufficient; a Rust resolver is required.
- ADR 016 accepted: PyInstaller onedir + Tauri externalBin staging + minimal bundled-sidecar resolver.
- P2 built `desktop/target/sidecar/weaver/weaver.exe`; direct sidecar serve passed `/healthz` 200 and `/ui` 200.
- P3 staged `desktop/sidecar/weaver-x86_64-pc-windows-msvc.exe`, configured Tauri `externalBin`, mapped PyInstaller `_internal`, added resolver order.
- P3b fixed the startup-readiness race: `HEALTH_BUDGET` 5→20 s (bounded) for PyInstaller cold start, plus `[host]` startup diagnostics (source/path/budget, elapsed) in `sidecar.console.log` and on the crash screen.
- P4/P5 packaged standalone smoke + regression audit: PATH-free `/healthz`+`/ui` 200, 0 new 401, 6 logs, `NO_SECRET_TOKEN_MATCHES`, WM_CLOSE → no orphan, bad-override crash screen, scope fence held.
- P6 gate report: PASS-WITH-CONDITIONS. Sizes: host 3.27 MB, sidecar 17.2 MB, onedir ~171 MB.

Carry-forward (deferred, not blockers):

- Human X-button close owner-confirmed 2026-06-14 (P-V8 PASS) → Sprint P promoted to PASS.
- Signing / auto-update / final installer / cross-platform deferred to a release-hardening sprint.

Done (Sprint O — packaged alpha, owner-confirmed):

- O1 packaging audit; O3 `cargo tauri build` → `weaver-desktop.exe` 3.1 MB (exit 0)
- O4 packaged smoke: launch → cockpit `/ui`, `/healthz`+`/ui` 200 (no 401), no orphan, logs, crash screen
- O5 logs/crash/uninstall behavior documented; O6 gate report (PASS-WITH-CONDITIONS)
- Carry-forward condition: packaged exe still needs `.venv\Scripts` on PATH → Sprint P removes this

Done (Q2F):

- Sidecar contract fully audited against current FastAPI app
- `/healthz`, `/health`, `/version`, `/runtime/status` verified over real HTTP
- Random port + session token startup contract validated
- Token boundary verified: public paths vs protected paths
- Startup diagnostics tested: exit 64 (non-loopback in desktop), exit 65 (port-in-use), exit 66 reserved
- `/ui` rendered HTML contains no hardcoded `127.0.0.1:8765` (static grep + runtime test)
- Templates contain zero `127.0.0.1` references
- CORS lockdown, docs-disabled, same-origin-only all verified
- Rust/Tauri `cargo check` passes, crate version pins confirmed via `cargo tree`
- Desktop smoke checklist created
- Q2F readiness report produced

Done (Sprint N — runtime smoke, owner-confirmed via `cargo tauri dev`):

- N1 native window + loading screen ✅; N2 loading→cockpit `/ui` transition ✅
- N3 no 401 loop; protected routes work via `X-Weaver-Session` ✅
- N4 close window → sidecar killed, no orphan `weaver`/`python`/`uvicorn` ✅
- N5 `runtime.log` + `sidecar.console.log` generated in `logs_dir` ✅
- N6 forced startup failure → crash screen with mapped exit code ✅

### 2.4 Exit Criteria

#### Connection-First Routing (v0.7.2) exit — ✅ MET (ADR 018, released in tag `v0.7.2`)

_Bagian A — engine de-brand (DONE 2026-06-15):_

- [x] `providers/deepseek.py` renamed to `openai_chat.py` (`OpenAIChatProvider`/`OpenAIChatConfig`); brand strings gone from engine/errors (`grep -i deepseek src/weaver` = shim-only). Ruff/pyright/pytest green (1491 passed).
- [x] Cockpit "Legacy aliases…" hint removed; `_config_form.html` + `test_ui_providers.py` updated.
- [x] `providers/gemini.py` + `providers/ollama.py` removed; `google-generativeai` dropped from `pyproject.toml`; `gemini_generate`/`ollama_generate` protocols gone (registry = `openai_chat` + `fake` only). Legacy `type=gemini|ollama` auto-maps to an `openai_chat` connection via the D6 shim (Gemini → `…/v1beta/openai` — endpoint corrected in the 2026-07-05 audit fix, Ollama → `:11434/v1` keyless). Keyless `openai_chat` (empty `api_key_env` → dummy key) added + tested. (S1, verified 2026-06-16: ruff/pyright clean, pytest 1519 passed.)

_Bagian B — connection-first UX + registry + routing (lean backing, D9):_

- [x] **Connection form = Name + Endpoint + Key + [Test]** only; **no** protocol/type/engine field shown. Advanced (collapsed) = env-name override + "use shell env" + keyless. Test renders `✓ Connected · N models · NNN ms`. (`_connection_form.html`, hybrid key per D7.)
- [x] "Providers" surface relabelled **Connections**; route `/ui/providers` kept (ADR 015 bookmarks alive).
- [x] `core/connection_registry.py` + `~/.weaver/connections.toml` (honors `WEAVER_CONNECTIONS_PATH`, owner-only 0600); register/test/delete via cockpit + `services/connections.py` facade (hybrid key → `WEAVER_CONN_<NAME>` secret).
- [x] **Model discovery** (`providers/discovery.py`): on-demand `GET /v1/models` POST (Test + project "Load models") yields the model list/count, **never on render, no background thread**. Persisted to a workspace cache (`core/connection_models.py` → `~/.weaver/connection_models.json`, S3) so the cockpit shows a connection's models without re-probing; `(stale)` hint after the TTL; changing the connection in Switch AI reads the cache (no probe).
- [x] **Model-centric project AI**: project page shows **Active AI** (`model via connection`) for `translate`; **Switch AI** picks a connection + model (with on-demand "Load models" suggestions) and writes `[routing.translate]`; the next run uses it. (`ui_routing.py`, `_active_ai.html`, `services/routing.py`.)
- [x] `model` accepts any free-form id end-to-end; discovery only _suggests_ (no enum anywhere).
- [x] `services/routing.py` precedence (`[routing.<task>]` → legacy `[provider]` → workspace `[defaults].default_connection`) wired into `translate_project`; **simple per-segment fallback** (`resolve_chain` + `[routing.<task>].fallback` array, try-next on `ProviderError` with a 30 s in-process cold-mark, no circuit breaker) wired into `translate_one_segment`. (S2, done 2026-06-16.)
- [x] Legacy `[provider]`-only projects resolve bit-for-bit to 0.7.1 behavior (resolver returns `[provider]` when no routing entry; covered by the existing translation suite).
- [x] `ruff`, `ruff format`, `pyright`, `pytest` green (1537 passed; +46 connection/routing tests).
- [x] **Lean-backing fence (D9) held:** no circuit breaker, health-score formula, presets, `routing_decisions` table, cost/observability dashboard, rotation window, or native non-OpenAI families. Health badge = config state on render; live ✓/models only on Test.

##### Slice log (S1–S5 — all shipped; historical evidence)

- **S1 — Collapse natives + drop dep (closes Bagian A). ✅ DONE (2026-06-16).** Deleted `providers/gemini.py`/`ollama.py` (+ their unit/live tests), dropped `google-generativeai`, removed `gemini_generate`/`ollama_generate` from `registry.py` (now `openai_chat` + `fake`). `_LEGACY_DEFAULTS` shim maps `type=gemini|ollama|deepseek` → `openai_chat` endpoints. **Keyless edge fixed:** `_build_openai_chat` accepts empty `api_key_env`; `OpenAIChatProvider` feeds a dummy key when keyless, but keeps the "named env but no value → `ProviderUnavailable`" guard. Verified: ruff/pyright clean, pytest 1519 passed; stale protocol strings cleaned in `config_writer` + `test_workspace_providers`. _Deferred (not blocking): live validation of Gemini/Ollama over their OpenAI-compatible endpoints (`requires_cloud`/`requires_ollama`) on a real machine._
- **S2 — Routing precedence tier + simple fallback. ✅ DONE (2026-06-16).** Added the workspace `[defaults].default_connection` tier to `resolve_provider_config` and `resolve_chain(task)` (primary + `[routing.<task>].fallback` array of `{connection, model}`; unknown fallback connections skipped, primary stays strict). `translate_one_segment` now tries the chain per segment, cold-marking a failed engine for 30 s (no circuit breaker, D9); `translate_project` builds the fallback engines once and shares a per-run cold dict. TM short-circuit stays ahead of routing. Tested incl. an end-to-end rescue (primary `fail_rate=1.0` cold-marked + skipped, backup carries all 6 segments). _Remaining for S3/S4: a cockpit editor to author the `fallback` array (today it is project.toml-only)._
- **S3 — Discovery cache. ✅ DONE (2026-06-16).** `core/connection_models.py` caches each connection's last `/v1/models` snapshot to a **workspace JSON file** `~/.weaver/connection_models.json` (honors `WEAVER_CONNECTION_MODELS_PATH`, 0600). **Deviation from ADR 018 §6.1** (which sketched a per-project `connection_models` SQLite table): a connection is workspace-level, so its cache is too — a per-project table would duplicate it per project and needs a migration; the JSON file is the lean fit (D9) and keeps derived data out of `connections.toml` (D2). `services/connections.refresh_models`/`cached_models` wired into the connection-card Test + project Load-models (probe → cache) and a cache-only render path (`/routing/cached-models`, Gate-B1 safe); `(stale)` hint after the 6 h TTL. _Remaining (S4): a single grouped-by-connection picker across all connections (today the Switch AI datalist shows the selected connection's cached models)._
- **S4 — Cockpit cleanup + fallback-author UI. ✅ DONE (2026-06-16).** Reframed the legacy editor heading to "Per-project provider (legacy)" with a pointer to Connections (route kept, ADR 015). Added a **Fallback chain** section to the Active AI panel: shows the configured chain and lets the user **Add / Clear** fallbacks from the cockpit — no more hand-editing `project.toml`. Backed by `config_writer.set_routing(..., fallbacks=...)`, which now rewrites the machine-owned `[routing.<task>]` section (preserving every other section + comments), preserves an existing `fallback` array when none is passed, and writes `{connection, model}` inline-table arrays. _Remaining (nice-to-have): a single grouped-by-connection model picker across all connections (today the Switch AI datalist shows the selected connection's cached models)._
- **S5 — CLI parity. ✅ DONE (2026-06-16).** `weaver connections list/add/test/rm` (hybrid key: `--key`/`--env`/`--shell`/`--keyless`, prompts hidden; `test` probes + caches) and `weaver routing show/set` (writes `[routing.<task>]`) mirror the cockpit via the existing services. Key values are never printed.

**Key files (already built, reuse — do not re-derive):** `core/connection_registry.py`, `core/task_types.py`, `providers/discovery.py`, `services/connections.py` (hybrid key: `probe_connection`, `add_connection`, `derive_env_name`), `services/routing.py` (`resolve_provider_config`, `resolve_active_ai`), `services/config_writer.set_routing`, `api/routers/ui_providers.py` (connection routes) + `ui_routing.py` (Active AI/Switch AI), partials `_connection_*`/`_connections`/`_active_ai`/`_routing_models`. Tests mirror under `tests/unit/{core,providers,services,api}/`.

##### Post-sprint owner-feedback refinements (2026-06-16)

- **Connection form gained a Default Model field** (Test loads the endpoint's models into a suggestions datalist via `hx-swap-oob`). A router serves many models; the connection captures an optional default. (commit `2835b85`)
- **Legacy per-project provider editor removed** from the cockpit — `#config-editor` + `_config_form.html` + `POST /ui/providers/config` gone; JSON `/config` API + `provider_config` service kept for automation/back-compat. `/ui/config` now redirects to `#connections`. (commit `52da0f3`)
- **Cross-project table is now an Active-AI switch station** — each row shows the resolved Active AI (model via connection / legacy / not set) and a per-row **Switch AI** that writes `[routing.translate]` for that project and re-renders the row (`_provider_row.html`, `POST /ui/providers/{name}/switch`, `workspace_providers` carries the resolved Active AI; `resolve_active_ai` now normalizes legacy `[provider]` so a brand alias still shows its shim model). Gate B1 preserved (no provider call on render).

##### Post-S5 hardening (2026-06-16) — ✅ DONE

- [x] **Cockpit translate path routing-aware.** `validate_provider_config` → `resolve_translation_engines` in `workspace_translate.py`; `prepare_chapter_translation` + `prepare_batch_translation` now resolve `resolve_chain(TaskType.translate)` (Active AI + fallback engines on the `TranslationPlan`), not raw `[provider]`. Fixes the live `provider.model missing` error for connection-first projects; brings the cockpit to CLI parity (fallback chain too). +4 regression tests.
- [x] **Glossary-suggest + candidate routing-aware.** New `services/routing.resolve_consumer_config` (resolve the secondary task; inherit the project's `translate` Active AI when the task isn't separately routed and `[provider]` is empty). Wired into `glossary_suggestion.py` (`TaskType.glossary_suggest`) and `candidate_generation.py` (`TaskType.candidate`). Fixes the live `Provider configuration is incomplete` error on the glossary page / "Suggest" actions. +4 tests.
- [x] **Duplicate CTA removed.** `skip_existing` dropped from the Retranslate dropdown (it equalled the primary "Translate" button) — `workspace.html` + `test_ui_jobs`.
- [x] **Plain-language copywriting pass** across the cockpit (onboarding, dashboard, project, Active AI, connections/secrets, providers table, QA, export preflight, queue, resources, workspace/segment) + `status_labels` ("Stale"→"Outdated", "Manual"→"Manual edit"). Behavior unchanged; ~10 UI test-string updates.
- [x] `ruff`/`ruff format`/`pyright` clean; full suite **1553 passed, 1 skipped**.

#### Translation Enforcement Loop (ADR 019) exit — ✅ MET (released in tag `v0.7.2`)

Makes glossary/character/TM **binding**, not decorative, + anti-slop. Plan: [`2026-06-16-enforcement-loop-execution-plan.md`](superpowers/specs/2026-06-16-enforcement-loop-execution-plan.md). Hard-rule fence: bounded **1** repair pass (no circuit breaker, D9), explicit translate-time only (Gate B1), failure visible, cost shown. Slices (each independent + shippable):

- [x] **E1+E2 — Detection gate + bounded repair. ✅ DONE (2026-06-16).** Shipped together (a detection-only gate would be a zero-caller module, §4.2/§4.3). `services/enforcement.py` (pure): `evaluate_translation` reuses `check_glossary_mismatch` + `check_character_name_missing` + `check_untranslated_japanese` + a **loose anti-truncation floor 0.15** (NOT `[qa] minimum_length_ratio` — forcing length causes padding-slop, Q4); `repair_translation(provider, …)` (provider param = `[routing.repair]` seam, deferred) builds the repair prompt (`prompts.render_enforcement_repair_prompt`, Python-string), calls `complete()`, re-parses. Wired into `translate_one_segment`: detect → **one** bounded re-ask → re-validate → commit the repaired attempt only if not strictly worse, else keep primary. `_try_repair` degrades gracefully (`ProviderError`/`ParserError`/`NotImplementedError` → keep primary; never block, never substitute). `[translation] enforce_repair` default true (`enforce_repair_enabled`); detection runs regardless. Plumbed through `translate_project` + `TranslationPlan` (chapter + batch). Repass tokens counted into segment usage. **+11 tests** (9 gate/repair unit, 2 e2e: repair-replaces / parse-fail-keeps-primary). Full suite **1564 passed**.
- [x] **E3 — `[translation_profile]` contract + banned-slop seed. ✅ DONE (2026-06-16).** New `TranslationProfile` value type (providers/types) on `TranslationContext`; `build_translation_profile(config)` parses `[translation_profile]` (`tone`/`dialog_style`/`name_rendering`/`tense`/`banned_phrases`), returns `None` when absent (no behavior change). Style fields emit a `<profile>` prompt block (`balanced_user.jinja2`, only when `has_style`). `banned_phrases` is a deterministic **soft** anti-slop check in `evaluate_translation` (feeds the same E2 repair). Seed `core/slop_seed.py` (5 phrases) applies only when the section is declared; `banned_phrases = []` disables, custom array replaces. Plumbed via `TranslationPlan.profile` (chapter + batch). Pure config, no schema change.
- [x] **E4 — Recover discarded `uncertain_terms` → `glossary_candidates`. ✅ DONE (2026-06-16).** `storage.record_uncertain_glossary_candidate` (idempotent: skip approved terms, bump existing **pending** candidate, never resurrect handled ones, `category="discovered"`); called per committed segment in `translate_one_segment` on `final.uncertain_terms`. Free entity discovery, no extra model call (replaces the proposal's "continuous extraction").
- [x] `ruff`/`ruff format`/`pyright`/`pytest` green each slice (E3+E4: +13 tests). _Owner-visible token-cost delta before locking E2 default-on still recommended on a live run._

#### Desktop Installer & Release Hardening exit — ✅ MET (ADR 017, PASS)

- [x] NSIS installer builds; installs per-user with a Start-menu entry + uninstaller (owner smoke 2026-06-15).
- [x] Uninstall preserves `%APPDATA%\Weaver` (projects/DB/logs) (install smoke + upgrade test).
- [x] Signing pipeline signs when a cert secret is present and builds unsigned (without failing) when absent — unsigned path proven via the v0.7.1 CI release; signed path enables on cert (deferred).
- [x] Update check is OFF by default; opted-in it notifies (no download/install) and is a silent no-op on failure (4 Rust tests; live `latest.json` manifest verified).
- [x] `pyproject` is the single version source; the drift guard fails on mismatch.
- [x] Tag-triggered release workflow publishes a GitHub Release with the installer + `latest.json` (v0.7.1, run 27529052365).
- [x] Exit 66 raised + tested; `SIDECAR_CONTRACT.md` §5 updated.
- [x] Upgrade test: installing vN+1 over vN preserves data and replaces the binary (0.7.1 over 0.7.0, owner machine).
- [x] `uv run ruff check .`, `ruff format --check .`, `pyright`, `pytest` all green.
- [x] Final gate report records sizes, signed/unsigned status, and upgrade evidence.

> **Standing condition (deferred non-blocker):** released installers stay **unsigned** until a code-signing certificate is procured (ADR 017 D2) — store `WINDOWS_CERTIFICATE_THUMBPRINT` to enable, no code change. macOS/Linux remain deferred (§2.1.1).

#### Q2F exit (already met)

- [x] Sidecar contract documented and mapped.
- [x] Health/readiness endpoints tested over real HTTP.
- [x] Random port + session token contract validated.
- [x] Token boundary verified.
- [x] Exit codes 64/65 tested; 66 documented reserved.
- [x] Startup diagnostics (no secret leakage, stdout summary) verified.
- [x] Rust/Tauri compile verified (`cargo check`).
- [x] Desktop smoke checklist documented.
- [x] Q2F readiness report completed.

#### Sprint N exit — ✅ MET (owner-confirmed runtime smoke); Q2F promoted to **PASS**

- [x] N1 — Native window opens and the loading screen appears.
- [x] N2 — Loading screen transitions to the Cockpit `/ui`.
- [x] N3 — No 401 loop; protected routes work via the `X-Weaver-Session` header.
- [x] N4 — Closing the window kills the sidecar; no orphan `weaver`/`python`/`uvicorn` process remains.
- [x] N5 — `runtime.log` and `sidecar.console.log` generated in `logs_dir`.
- [x] N6 — Forced startup failure shows the crash screen with a mapped exit code.
- [x] `cargo tauri dev` smoke run; N1–N6 owner-confirmed. **Sprint O — Desktop Packaging / Installer Alpha** is now unblocked.

#### Sprint P exit — ✅ MET (PASS)

- [x] P1 — Audit current sidecar launch path and Tauri `externalBin` expectations.
- [x] P2 — Build experimental PyInstaller onedir sidecar and direct-test via `WEAVER_DESKTOP_SIDECAR`.
- [x] P3 — Stage `externalBin` + add minimal bundled-sidecar resolver.
- [x] P3b — Fix startup-readiness race (`HEALTH_BUDGET` 5→20 s) + add `[host]` startup diagnostics.
- [x] P4 — Packaged app launches without `.venv\Scripts` on PATH; `/healthz` 200 + WebView `/ui` 200 proven (isolated + default `%APPDATA%`).
- [x] P5 — Logs, crash, shutdown, no orphan (WM_CLOSE), `NO_SECRET_TOKEN_MATCHES` validated against the bundled sidecar.
- [x] P-V8 — Human native X-button close owner-confirmed 2026-06-14: no orphan, no restart/hang.
- [x] P6 — Final gate report: PASS.

Deferred (not blockers): signing / auto-update / final installer / cross-platform → release-hardening sprint.

### 2.5 Phase Log

Deep detail lives in git history, ADRs, sprint plans, and handoff notes. This section preserves only operational lessons still useful for future work.

| Area                          | Source of truth                                                                                                                                                                                                         | Carry-forward rule                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| ----------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Architecture baseline         | Current architecture docs + ADRs                                                                                                                                                                                        | Prefer existing architecture over new layers. Do not introduce abstractions unless they remove real duplication or protect a proven boundary.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| CLI / API / UI workflow       | Current workflow docs + tests                                                                                                                                                                                           | Preserve existing entry points and user workflows. Any route, command, selector, or schema rename requires tests and migration notes.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| Desktop / sidecar boundary    | Current desktop docs + sidecar contract, if present                                                                                                                                                                     | Keep desktop integration isolated from core services. Do not let desktop code become a second source of business logic.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| Provider layer                | Current provider ADR/spec + provider tests                                                                                                                                                                              | Keep provider primitives domain-agnostic. Put workflow validation in services, not provider adapters.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| Workspace/read models         | Current workspace services + tests                                                                                                                                                                                      | Read paths should stay cheap, deterministic, and side-effect-free. Avoid expensive scanning, hashing, provider calls, or QA work on render paths.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| Cleanup/audit work            | Current audit plan + handoff notes                                                                                                                                                                                      | Treat audit findings as hypotheses until manually verified. Delete only when references, runtime paths, tests, and fallback behavior are understood.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| Sidecar contract testing      | `tests/integration/test_runtime_random_port.py` · `tests/unit/api/test_desktop_security.py`                                                                                                                             | Real HTTP/Uvicorn is preferred over TestClient for sidecar contract tests. Reuse the `sidecar_server` fixture pattern rather than reimplementing Uvicorn threading.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| CLI startup diagnostics       | `tests/unit/api/test_desktop_security.py`                                                                                                                                                                               | Mock `uvicorn.run` for exit-code tests (64/65). Use `_make_fake_uvicorn` helper. Assert no secret/token leakage in error output.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| Sprint N readiness            | `docs/SIDECAR_CONTRACT.md` · `desktop/README.md`                                                                                                                                                                        | Desktop shell must be compile-verified (`cargo check`) before runtime smoke (`cargo tauri dev`). Do not skip compile gate.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| Desktop packaging (Q2F/N/O/P) | `docs/INSTALL_DESKTOP.md` · Sprint P gate report (`docs/superpowers/handoffs/2026-06-14-sprint-p6-gate-report.md`) · ADR 016 (per-stage Q2F/N/O/P handoffs consolidated into the gate report; full logs in git history) | Sprint P (PASS) shipped the self-contained Windows alpha: PyInstaller onedir + Tauri `bundle.externalBin` + runtime resolver. Resolver order is mandatory: `WEAVER_DESKTOP_SIDECAR` override → bundled sidecar → PATH `weaver` fallback; `externalBin` config alone is insufficient and the PATH fallback must stay. Desktop startup `HEALTH_BUDGET` is **20 s** (bounded, P3b) because PyInstaller cold start exceeds the old 5 s — independent of the §7 5 s shutdown grace. Do not switch onedir→onefile, drop the PATH fallback/override, or add `tauri-plugin-shell` without evidence + an ADR. Bundling logic stays in `desktop/`/CI, never in `src/weaver/`. Sprint P = PASS (human X-close owner-confirmed 2026-06-14); signing/installer deferred to release-hardening. |

| Connection/routing security (v0.7.2) | `docs/superpowers/handoffs/2026-06-16-connection-routing-security-review.md` | Connection/routing/enforcement routes audited for webUI + desktop. All behind the `X-Weaver-Session` boundary (only `_PUBLIC_PATHS = /healthz,/health,/version,/static` are open) + same-origin CORS; Gate B1 held (provider calls are explicit-POST only); secrets validated (`^[A-Za-z_][A-Za-z0-9_]*$`) + `0o600` + never echoed; HTMX hooks are **relative** (no host hardcoding). **Two fixes:** `find_project` rejects `/`,`\\`,`.`,`..` names (Windows `\\`-traversal — desktop target); inline error fallbacks now `html.escape` the `name` param (reflected-XSS). Rule: untrusted route params reflected outside Jinja **must** be `html.escape`d; never join a route `name` into a filesystem path without the separator/`..` guard. |
| Provider keys & transaction shape (v0.7.2 audit) | `docs/superpowers/handoffs/2026-07-05-v072-audit-and-blocker-fixes.md` · commits `019834a`/`dee710f` | The provider factory resolves key values **shell env → secret store** at build time (`providers/registry._resolve_key_value`) — never assume `apply_secrets_to_env` re-runs mid-session; keep the Test-probe and build-time resolution paths consistent. Never hold a SQLite write transaction across a provider network call: one segment **result** = one atomic commit (row + memory + candidates + status); the `in_progress` marker is its own short txn and `reset_in_progress_segments` is the crash net. The gemini legacy shim endpoint is `…/v1beta/openai` (bare `…/v1beta` has no `/chat/completions`). |

| Installer & release (ADR 017) | `docs/decisions/017-*.md` · `docs/superpowers/handoffs/2026-06-15-installer-release-gate-report.md` · `.github/workflows/release.yml` | `pyproject` is the **single version source**; never hand-edit `tauri.conf.json` version — run `desktop/scripts/sync-version.ps1`, and a `v*` tag must equal it (`check-version.ps1 -Tag`). Releases are tag-triggered (`release.yml`, windows runner); signing is **off until** the `WINDOWS_CERTIFICATE_THUMBPRINT` secret exists (no code change to enable). Update check is **opt-in, notification-only, default OFF** (`WEAVER_DESKTOP_UPDATE_CHECK` env or `%APPDATA%\Weaver\desktop\settings.json`) — never add download/install or `tauri-plugin-updater`/`-shell` without a new ADR. Installer config validated against the compiled `tauri-utils` schema (`deny_unknown_fields`) — verify field casing there, not just docs. Exit-66 is now a real tested code (`DataDirError`). Desktop/packaging logic stays in `desktop/`+CI, never `src/weaver/`. |

> Historical test counts are evidence only at the time they were recorded. Re-run relevant verification for the current phase; do not assume old counts still apply.

---

## 3. Stack

This section describes the default project stack. Treat `pyproject.toml`, current ADRs, and lockfiles as the final source of truth.

### 3.1 Core

**Runtime and tooling:** Python 3.11+ · uv · `pyproject.toml` · ruff · pyright basic · pytest

**CLI and app foundation:** typer · rich · pydantic v2 · tomllib · pathlib · sqlite3

**Storage:** SQLite in WAL mode, no ORM by default

**Import/export and document handling:** ebook/document libraries currently declared in `pyproject.toml`

**Provider integration:** provider SDKs currently declared in `pyproject.toml`; do not add or replace provider dependencies without an ADR or explicit sprint scope

### 3.2 Web Cockpit

**Default web stack:** FastAPI · server-rendered Jinja2 · HTMX

Rules:

- Web cockpit is optional and isolated behind the web extra.
- Keep the UI server-rendered.
- No SPA by default.
- No Node/build pipeline by default.
- Vendor browser assets locally when practical; avoid CDN dependency for core UI behavior.
- `asyncio` is allowed only where the FastAPI/web boundary requires it.
- Routes/templates must stay thin. Business logic belongs in services.

### 3.3 Desktop Shell

**Default desktop boundary:** Tauri in `desktop/`, isolated from Python core.

Rules:

- Desktop code is not a Python dependency.
- Desktop shell launches or connects to the local FastAPI sidecar according to the current sidecar contract.
- Desktop must not duplicate business logic from CLI, API, services, or storage.
- Desktop-specific behavior stays inside `desktop/` unless an ADR explicitly expands the boundary.

### 3.4 Deferred / Out of Scope Unless Planned

The following are not part of the default stack and must not be scaffolded casually:

- OCR implementation
- New provider families
- Route rewrites
- SPA migration
- Node build pipeline
- External queue
- Cloud sync
- Telemetry
- Multi-user SaaS architecture

### 3.5 Banned Unless Explicitly Approved

The following require an ADR or explicit orchestrator approval before use:

- Flask
- Django
- SQLAlchemy or another ORM
- Celery, RQ, or external worker queues
- Docker as a required local runtime
- React/Vue/Svelte/SPA framework
- Required Node build pipeline
- OpenTelemetry
- Sentry or external error tracking
- External job queue, worker daemon, or multi-process worker pool
- Global mutable cross-project store
- `asyncio` outside the web layer without a documented reason

### 3.6 Stack Change Rule

A stack change is allowed only when it satisfies all of these:

1. Solves a current, documented project problem.
2. Has an ADR or explicit sprint scope.
3. Includes migration impact.
4. Includes rollback strategy.
5. Keeps CLI, API, desktop, storage, and tests coherent.

---

## 4. AI Instructions

### 4.1 Before Coding

1. Read this file first, then the relevant current doc/ADR from §1.
2. Check the active stage in §2.3 before starting any work. If no sprint/stage is active, do not continue old scaffolding by default; open a new execution plan first.
3. Respect the active execution plan, stage order, and gate rules defined for the current sprint.
4. Run `rtk git status --short --branch`. If WIP overlaps the relevant area, tell the orchestrator before editing.
5. Confirm scaffolding is actually requested. Docs/strategy request ≠ build code.
6. Check the file tree before creating new files or folders. Use exact names/values from the current docs for types, schemas, exit codes, selectors, and routes. Do not improvise.
7. Before committing: scan the diff for AI attribution trailers, bot author metadata, leaked credentials, and unrelated changes.

### 4.2 Code Rules

Follow the current engineering ADR/source-of-truth listed in §1.

- **Types:** Type hints on every public function. Pyright basic must pass.
- **Modularity:** One concept per file. Split if >400 lines or >5 public functions. Functions >50 lines or >4 params need justification.
- **Naming:** Forbidden filenames: `utils.py`, `helpers.py`, `manager.py`. Avoid class names ending `Manager`/`Helper`/`Handler` unless they truly are that pattern. Name modules for purpose.
- **Public APIs:** No `**kwargs` in public APIs. No bare `except:` or `except Exception:` outside CLI/web boundaries. Never use `except: pass`.
- **Errors:** All domain errors go through the `WeaverError` hierarchy. User-facing errors must state what failed, likely cause, and next action.
- **State discipline:** State writes go through services. CLI/web must not touch SQLite directly. One segment result = one atomic commit (translation row + memory + status together); provider network calls never run inside an open transaction. Status transitions live in the same transaction as the data they describe.
- **Layer boundaries:** Shared/core code is framework-agnostic. No web `Request`/`Response`, DI wiring, template output, or CLI formatting in core services. Pydantic belongs at the web/API boundary. UI templates/routes carry no business logic.
- **API keys:** Env vars or local secrets file only. Never store keys in config, logs, rendered HTML, SSE events, tests, or fixtures. Shell env wins.
- **Value types:** Use `@dataclass(frozen=True)` for value objects. Use `pathlib.Path` for paths. Use atomic writes for valuable state.
- **Cockpit UI hooks:** Do not rename/remove existing route, template, CSS, HTMX, or DOM hooks unless the active plan explicitly requires it and tests are updated.
- **Tests:** Mirror the source tree. Use `FakeProvider`; never live LLMs in CI. Fixtures must be public-domain or synthetic. Mock external boundaries only, not internal code.
- **Security for I/O changes:** Parse input through typed schemas/models, not raw dict chains. Never pass user strings to `os.system`, `subprocess(shell=True)`, `eval`, or `exec`. Malformed input must fail safely.
- **Performance:** Preserve documented runtime budgets. Any regression over 20% needs evidence and justification.
- **Tech-debt prevention:** No stub functions “for later”, no commented-out code, no single-caller abstractions, no config flag to defer a decision. Dead code is deleted on sight. TODO/FIXME must include an issue and cleanup plan.
- **Git/PR:** Conventional Commits with scope, for example `feat(translate): ...`. Branches use `feat|fix|docs|chore/<name>`. One PR = one concern. No force-push to `main`.
- **Githooks:** `.githooks/` are mandatory. Keep `git config core.hooksPath .githooks` enabled.

### 4.3 Anti-Slop

The LLM must be load-bearing infrastructure, never decoration.

- No “smart”, “AI-powered”, “magical”, or “intelligent” feature names.
- No chat UIs, avatars, sparkles, fortune-cookie loaders, marketing language, telemetry, or phone-home behavior.
- No prompt-wrapper features. A new “mode” that only changes the system prompt is not a feature.
- A feature ships only if all six gates pass:
  1. Real pain: evidenced, not “would be cool”.
  2. Falsifiable spec.
  3. Deterministic where possible.
  4. User can override every AI artifact.
  5. Failure is visible and never silently substituted.
  6. Cost is visible.

- No config flags for unbuilt features. No stub functions. No commented-out code. No abstractions with one caller.

### 4.4 Scope Discipline

Build vertically, not horizontally. One polished slice beats several half-finished ones. When in doubt between spectacle and correctness, prioritize correctness.

- Build only what the active stage lists.
- Deferred items get no scaffolding “for later”.
- One PR = one concern. Do not bundle refactor + feature.
- One implementation stage should map to one branch + one PR unless the active execution plan says otherwise.
- Add a **Non-Goals** line per stage to fence scope.
- No global mutable store without an ADR.
- No cross-project write behavior without an ADR.
- No expensive file hashing, scanning, or source inspection on render paths unless explicitly budgeted and tested.
- When no sprint is active, open a new scope by writing a sprint execution plan and updating §2.3 / §2.4 before implementation.

Default build order:

1. Validate prior carry-over.
2. Implement stages in execution-plan order.
3. Update docs and handoff notes.
4. Run final gate validation.

### 4.5 Communication

- Terse, technical. No filler, no apology, no marketing language.
- Reference files as `[name](path/file.md)` or `src/weaver/foo.py:42`.
- State decisions directly.
- Use concise Indonesian when the user writes in Indonesian.
- When uncertain, present 2–3 concrete options with trade-offs.
- Flag conflicts early: locked-stack changes, phase jumps, scope creep, direction regressions.
- During debugging: state what is happening, what was expected, and what evidence supports the conclusion.

### 4.6 Contribution Identity

> **Copy this section verbatim into every project CLAUDE.md. Do not modify.**

AI is a ghostwriter. Repository accountability remains with the human owner.

- Do not add `Co-Authored-By: Claude` or any AI/model co-author trailer to commits.
- Do not add “Generated with Claude Code” or equivalent tags to commit messages or PR bodies.
- Do not push commits with AI or bot author identity.
- Do not make AI appear in the GitHub contributor graph.
- Author and committer identity must be the repo owner’s human identity configured for the project.
- If AI assistance needs to be disclosed, mention it only in normal prose in a PR description or changelog, never in git metadata.

---

## 5. Implementation Agent Team

Weaver is built by the repo owner with Claude as Lead Technical Orchestrator, who splits work across specialist roles. Each role maps to a Weaver layer and is **realized** either by the orchestrator working inline or by a named Claude subagent/skill (spawn only when the owner asks, per the harness rule).

| #   | Role                                   | Weaver domain                                                           | Must not do                                                                             | Realized by                                                              |
| --- | -------------------------------------- | ----------------------------------------------------------------------- | --------------------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| 1   | **Lead Orchestrator**                  | Stage sequencing, scope control, merge readiness, final gate            | Skip final validation; assign ambiguous work; build a hub on the un-hardened foundation | Orchestrator (inline) · `Plan`                                           |
| 2   | **Product / Workflow Architect**       | User journey, page hierarchy, workflow coherence (cockpit)              | Add pages without a user-journey path; design features that bypass the core pipeline    | Orchestrator · `feature-dev:code-architect`                              |
| 3   | **Frontend Engineer**                  | Jinja2 + HTMX templates, partials, navigation, a11y, 390px+ states      | Add a frontend build step; rename HTMX hooks (§4.2); noisy UI outside the design system | Orchestrator · `frontend-design`                                         |
| 4   | **Backend Engineer**                   | API routers, `services/`, CLI commands, provider boundaries, validation | Put business logic in routers; touch SQLite from CLI/web; bypass services               | Orchestrator · `feature-dev:code-architect`/`code-explorer`              |
| 5   | **Data / Storage Engineer**            | `storage/migrations.py`, `schema.sql`, persistence, backward compat     | Schema churn without approval; break compat without ADR; mutate on a read path          | Orchestrator · `pr-review-toolkit:type-design-analyzer`                  |
| 6   | **QA / Validation Engineer**           | pytest suite, regression, edge cases, acceptance                        | Validate unit-only; skip user-facing workflow paths                                     | `pr-review-toolkit:pr-test-analyzer` · `verify`                          |
| 7   | **Security / Safety Engineer**         | I/O surfaces, secrets, path traversal, EPUB/image handling              | Unsafe file/subprocess patterns; secrets in config/logs/render; cross-project path leak | `security-review` · `pr-review-toolkit:silent-failure-hunter`            |
| 8   | **Performance / Reliability Engineer** | Render-path cost (Gate B1), job recovery, budgets                       | Ship blocking UX; hide errors with silent retries; hash source files on render          | Orchestrator (budget checks) · `pr-review-toolkit:silent-failure-hunter` |
| 9   | **Documentation / Handoff Writer**     | CLAUDE.md, sprint notes, ADR drafts, §8 handoff                         | Duplicate source-of-truth docs; write verbose non-operational prose                     | Orchestrator · `pr-review-toolkit:comment-analyzer`                      |
| 10  | **Critic / Devil's Advocate**          | Challenge assumptions, overengineering, hidden bugs, sequencing         | Block without an actionable alternative; complain without evidence                      | `pr-review-toolkit:code-reviewer` · `feature-dev:code-reviewer`          |
| 11  | **Release Captain**                    | Stage/sprint final gate, "done/not-done", known-gap doc                 | Mark done without evidence; merge incomplete work                                       | Orchestrator · `code-review`                                             |

**Rule:** No role overrides the orchestrator's scope without documenting reason, risk, and a proposed alternative. **The same agent should not be the sole reviewer of its own work** — builder (Backend/Frontend) → reviewer (Critic/QA/Security). Spawn subagents only when the owner asks (harness rule); otherwise the orchestrator fills the role inline.

---

## 6. Implementation Tracks

A track is owned by exactly one role. Supporting roles review or provide input but do not override the owner.

| Track | Name                           | Owner             | Weaver entry → exit                                                                                                      |
| ----- | ------------------------------ | ----------------- | ------------------------------------------------------------------------------------------------------------------------ |
| T0    | **Docs & Source of Truth**     | Doc Writer        | Stage scope defined → CLAUDE.md/§2 + handoff (§8) updated; ADRs current                                                  |
| T1    | **Product Workflow & UX**      | Product Architect | Stage defines/modifies a flow → journey documented; no orphan pages/states                                               |
| T2    | **Frontend (Jinja2 + HTMX)**   | Frontend Eng      | T1 defines UI; tokens exist → renders at 390px+; keyboard nav; loading/empty/error states; hooks intact                  |
| T3    | **Backend / API & Services**   | Backend Eng       | Contracts defined; storage exists → endpoints correct; input validated; services own writes; routers SQL-free            |
| T4    | **Data, Storage & Migration**  | Storage Eng       | Schema/migration required → forward + idempotency tested; existing data preserved; no silent loss                        |
| T5    | **Provider / Job Integration** | Backend Eng       | New provider/model config required → retry/fallback works; secrets confirmed; cost visible; ADR `010` intact             |
| T6    | **QA, Testing & Regression**   | QA Eng            | Implementation complete → full suite passes; regressions + edge cases documented; acceptance verified                    |
| T7    | **Security & Reliability**     | Security Eng      | Feature touches I/O/secrets/fs/subprocess/network → surfaces enumerated; risks + mitigations documented                  |
| T8    | **Performance & Runtime**      | Perf Eng          | Feature complete → budget met or regression justified; **zero render-path hashing**; no blocking UX; job recovery tested |
| T9    | **Release & Final Gate**       | Release Captain   | All tracks done; T6/T7/T8 passed → checklist signed; known gaps + next step clear                                        |

**Sprint Q track note:** every Q stage runs T0 (docs) + the build tracks it needs, always gated by T6/T7/T8. Q11 is validation-only (T6/T7/T8 → T0) — no new build tracks. v12 migration is conditional at Q12.

---

## 7. Orchestrator Operating Model

1. Read §1 docs governing the current stage; identify the stage from §2.3.
2. Confirm §3 locked-stack constraints — no new dependency or architecture shift without an ADR/owner approval.
3. Split the stage into tracks (§6); give each track an owner, scope, **acceptance criteria, and explicit non-goals** before implementation.
4. Require a handoff note (§8) at the end of each track.
5. Run Critic review (role #10) before the final gate; run QA + Security + Perf (T6+T7+T8) before merging.
6. Produce a per-track status: **Done** (implemented + validated + documented + handed off) · **Partial** (known gaps documented) · **Blocked** (external dependency) · **Deferred** (reason + trigger) · **Risk Accepted** (mitigation + rollback documented).

**Operating rule:** optimize for sequence, coherence, and risk reduction — not maximum parallel work. **Q1+Q2 hardened the foundation precisely so Q3+ hubs can be built one at a time without re-auditing the read paths.**

---

## 8. Agent Handoff Protocol

Every track ends with a handoff note. Without it, the work is incomplete by definition.

```
## Handoff: [Role]
**Track:** [T0-T9]
**Scope:** [what this track was asked to do]
**Files/Areas Touched:** [created/modified]
**What Changed:** [summary]
**What Was Intentionally Not Changed:** [scope boundaries respected]
**Validation Performed:** [tests run, manual checks, evidence — paste commands/output]
**Known Risks:** [incomplete, fragile, or uncertain]
**Recommended Next Role / Next Step:** [single next action]
```

**Rule:** a handoff must leave enough context to continue **without re-auditing the repo**. Update §2.3/§2.5 at each stage gate. The "next step" line is mandatory.

---

## 9. Review Gates

| Gate               | Stage                | Checks                                                                                                                         | Skippable?   |
| ------------------ | -------------------- | ------------------------------------------------------------------------------------------------------------------------------ | ------------ |
| **A — Scope**      | Before work          | Aligned with active stage (§2.3)? Owner clear? Non-goals stated? Acceptance defined?                                           | No           |
| **B — Readiness**  | Before coding        | Affected files known? §3 constraints respected? Matches existing patterns? **Gate B1: no QA/provider/hashing on render path.** | No for T2–T5 |
| **C — Validation** | After implementation | Tests/manual checks documented? Regressions + edge cases listed? Handoff written?                                              | No for T2–T8 |
| **D — Release**    | Before merge         | Work complete? Known gaps documented? Critic review done? §2.4 stage criteria green?                                           | No           |

**Gate-skip rule:** fewer gates for small changes (single file, <50 lines, no schema change), but **never skip Gate C**. Document any skip in the handoff.

---

## 10. Decision Rules

| #   | Rule                                                                                                                                         |
| --- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Prefer **existing architecture** over new patterns. The cross-project read layer is `workspace_index`; do not invent a parallel store.       |
| 2   | Prefer **small, sequenced changes** over broad rewrites. One stage, one branch, one PR.                                                      |
| 3   | Prefer **user workflow completion** over isolated polish. A working end-to-end cockpit path beats a perfectly refactored unused component.   |
| 4   | **Explicit ownership** — every track has a named owner role (§5).                                                                            |
| 5   | **No new runtime dependency** without an ADR. A new import is an architecture decision.                                                      |
| 6   | **No "complete" without validation evidence.** "It compiles" / "tests should pass" is not validation — run them.                             |
| 7   | **Do not modify roadmap/architecture/stack silently.** Propose changes in a handoff or ADR draft.                                            |
| 8   | **When in doubt, document the uncertainty** and propose the smallest safe next step. A documented question beats an undocumented assumption. |

---

_This file is the operating manual for Weaver. It follows the global template `@WORKFLOW.md`. Read it before any code change. The roadmap (§2.1) is the plan; the active phase (§2.3) is the status — do not conflate them._
