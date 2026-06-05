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

## ADR rules

- One decision per file. Format: Status / Context / Decision / Consequences / Related Files.
- A new architectural choice that changes a locked decision must **supersede** the prior ADR explicitly (do not silently contradict it).
- Reopening anything on the rejected stack list ([CLAUDE.md §3](../CLAUDE.md)) requires a new ADR.
- Archived ADRs are read-only history; cite the active ADR (or the archive path) instead of an old number.

## Notable carried-forward decisions (from archive)

These archived ADRs still describe behavior in the current code; their intent is carried forward by the active set:

- `0017` localhost security model → folded into [004](decisions/004-fastapi-cockpit-technical-direction.md).
- `0019` job-manager / SSE progress → folded into [004](decisions/004-fastapi-cockpit-technical-direction.md).
- `0020` local secret store → folded into [004](decisions/004-fastapi-cockpit-technical-direction.md) + [PROVIDER_AND_MODEL_CONFIG.md](PROVIDER_AND_MODEL_CONFIG.md).
