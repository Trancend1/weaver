# Architecture Decision Records

Active ADRs only. Active numbering was reset to `001` during the controlled reset (see [001](decisions/001-docs-cleanup-and-adr-reset.md)). Pre-reset ADRs `0001`–`0020` were archived during the reset and removed from the tree on 2026-06-05 — they live in **git history** and are **not** active decisions.

## Active

| ADR | Title | Summary |
|-----|-------|---------|
| [001](decisions/001-docs-cleanup-and-adr-reset.md) | Docs Cleanup and ADR Reset | Archive old ADRs + strategy docs, reset active set to 001–005, compress `CLAUDE.md`. |
| [002](decisions/002-cli-web-boundary-and-maintenance-structure.md) | CLI / Web / Shared-Core Boundary | Three binding layers; shared-core stays framework-agnostic. |
| [003](decisions/003-mvp-baseline-for-light-novel-translator.md) | MVP Baseline | Eight MVP areas; consistency machinery (glossary, character DB, TM) is first-class. |
| [004](decisions/004-fastapi-cockpit-technical-direction.md) | FastAPI Cockpit Direction | FastAPI is the web cockpit. Migration complete — Flask removed in Sprint 13B. Supersedes archived `0016`. |
| [005](decisions/005-cockpit-ui-ux-direction.md) | Cockpit UI/UX Direction | Calm, semantic-color, two-column workspace; HTMX-light, not SPA. |
| [006](decisions/006-novel-volume-chapter-data-model.md) | Novel/Volume/Chapter Data Model | Project=Novel, import=Volume; schema v3 + v2→v3 migration; `init` preserved. |
| [007](decisions/007-fastapi-ui-stack.md) | FastAPI Cockpit UI Stack | Server-rendered Jinja2 + HTMX, no Node/build, no SPA; no business logic in UI. Pins ADR `005`'s direction for Sprint 11. |
| [008](decisions/008-translation-qa-architecture-and-severity.md) | Translation QA Architecture & Severity | Phase B QA reuses `weaver.qa.checks` (no parallel system); keeps severity `info\|warning\|critical` (no `error`); scope-aware read-only `services/translation_qa.py`. |
| [009](decisions/009-htmx-first-fastapi-stable-tauri-sidecar-ready.md) | HTMX-first, FastAPI-stable, Tauri-sidecar-ready | Post-Phase-F roadmap; **supersedes** the npm `@weaver/cli` wrapper plan. Governed Sprints G–O (now superseded by the [audit roadmap replan](../.docs/audit/ROADMAP_REPLAN.md): N ∥ P → O → Q). |
| [010](decisions/010-persistent-job-core-sqlite-in-process.md) | Persistent Job Core | SQLite-backed JobRegistry, in-process only. No Celery/Redis/RQ/external worker (`api/jobs.py:8-10` boundary preserved). Locks before Sprint I. |
| [011](decisions/011-project-terminology-consolidation.md) | Project Terminology Consolidation | Retire user-facing "Novel" label; schema (`projects`/`volumes`) unchanged. Supersedes ADR `006` label only. Locks before Sprint H. |
| [012](decisions/012-image-preview-ocr-security-gate.md) | Image Preview / OCR Security Gate | Allows read-only manifest-backed image preview with MIME/size/path controls; keeps OCR contract-only until explicit future approval. |
| [013](decisions/013-qa-error-severity-tier.md) | QA `error` Severity Tier (Rejected/Deferred) | Sprint Q11 keeps the 3-tier `info\|warning\|critical` contract; no `error` tier. Structure findings (WV-007) map EPUB `error`→`warning` (advisory, never block Final export). Re-open point documented. |
| [014](decisions/014-provider-complete-primitive-and-glossary-suggestion.md) | Provider `complete()` Primitive + Glossary Target Suggestion | Sprint R adds a domain-agnostic `complete()` transport primitive (4 providers); on-demand AI glossary-target suggestion lives in a service (prompt+validation), ephemeral (no migration), provider fully config-driven (**no hidden vendor default**). Gate B1: provider called only on explicit POST. |
| [015](decisions/015-single-provider-config-surface.md) | Single provider-config surface at `/ui/providers` | Providers hub (`ui_providers.py`) is the canonical provider/model + secret config + health UI. `/ui/config` is a compatibility-only GET redirect to the hub editor. `ui_admin.py` is glossary/characters/TM only. Hub GET remains Gate-B1-safe (TOML-only read, no provider build). |
| [016](decisions/016-bundled-python-sidecar.md) | Bundled Python Sidecar (Windows Desktop Alpha) | PyInstaller onedir sidecar + Tauri `bundle.externalBin` staging + minimal Rust resolver (override → bundled → PATH fallback). Removes the Sprint O PATH dependency; FastAPI stays the sidecar. Shipped in Sprint P (PASS). |
| [017](decisions/017-desktop-installer-and-release-hardening.md) | Desktop Installer & Release Hardening | NSIS installer (no MSI); signing-ready CI (unsigned until a cert secret exists); opt-in notification-only update check (default OFF — narrowly supersedes ADR `016`'s "no update ping" clause); single version source (`pyproject`); exit-66 implemented; tag-triggered GitHub Actions release workflow. |
| [018](decisions/018-connection-first-routing.md) | Connection-First Routing | Collapse providers to one real transport: rename `deepseek.py`→`openai_chat.py` (de-brand), remove `gemini.py`/`ollama.py`, drop `google-generativeai` dep; Gemini/Ollama become `openai_chat` connections (gemini shim endpoint = `…/v1beta/openai`). Workspace connection registry (`~/.weaver/connections.toml`) + check + per-segment routing/fallback (no circuit breaker). `model` stays a free-form string; discovery is suggestion-only. Back-compat shim keeps legacy `[provider]` projects working; **narrowly supersedes** ADR `015`'s legacy-alias clause. Shipped in v0.7.2. |
| [019](decisions/019-translation-enforcement-loop-and-anti-slop.md) | Translation Enforcement Loop + Anti-Slop | Translate-time detection gate reusing the deterministic QA primitives + **one** bounded repair re-ask (`[translation] enforce_repair`, default on; never blocks, never silently substitutes); `[translation_profile]` style contract → `<profile>` prompt block + `banned_phrases` soft check; `uncertain_terms` recovered as discovered glossary candidates. Shipped in v0.7.2. |
| [020](decisions/020-bounded-translate-concurrency.md) | Bounded Translate Concurrency (**Accepted** 2026-07-21) | Opt-in `[translation] max_concurrent = 1..4` (default 1 = today's behavior bit-for-bit): bounded in-process worker window inside the existing per-job thread, per-worker SQLite connections, locked cold-mark map, committed-only rolling window. Unlocked by the H3 transaction split. No asyncio/process pool/external queue. Gate-B points settled 2026-07-21; implemented in v0.7.3 milestone M4. |

## ADR rules

- One decision per file. Format: Status / Context / Decision / Consequences / Related Files.
- A new architectural choice that changes a locked decision must **supersede** the prior ADR explicitly (do not silently contradict it).
- Reopening anything on the rejected stack list ([CLAUDE.md §3](../CLAUDE.md)) requires a new ADR.
- Archived ADRs are read-only history; cite the active ADR (or the archive path) instead of an old number.

## Notable carried-forward decisions (from archive)

These archived ADRs still describe behavior in the current code; their intent is carried forward by the active set:

- `0017` localhost security model → folded into [004](decisions/004-fastapi-cockpit-technical-direction.md).
- `0019` job-manager / SSE progress → folded into [004](decisions/004-fastapi-cockpit-technical-direction.md).
- `0020` local secret store → folded into [004](decisions/004-fastapi-cockpit-technical-direction.md) + [docs/CODEMAPS/dependencies.md](CODEMAPS/dependencies.md).
