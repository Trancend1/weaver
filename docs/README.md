# Weaver Documentation

Weaver is an offline-capable, glossary-aware **Japanese→English light-novel translation workbench**. It turns a Japanese source into a translated EPUB/TXT/HTML (plus Markdown review files) while keeping terminology and naming consistent across a long novel.

Two surfaces drive the **same** core:

- **CLI** (`weaver …`) — the original, complete surface. Scriptable, resumable.
- **Web cockpit** (`weaver serve`) — a local single-user browser UI on **FastAPI** (Jinja2 + HTMX UI + typed JSON API; see [ADR 004](decisions/004-fastapi-cockpit-technical-direction.md)). The legacy Flask cockpit was removed in Sprint 13B; FastAPI is now the only web surface.

**Status:** the **MVP Web Cockpit Foundation** is shipped (`v0.7.0-rc.1`) — consistency-first translator workflow (project/novel/volume/chapter, workspace, glossary, character DB, translation memory, batch, export), plus **UI/UX polish** (Phase A) and **read-only translation QA** (Phase B, ADR `008`). Next: release hardening. See [MVP_SCOPE.md](MVP_SCOPE.md) and [CLAUDE.md](../CLAUDE.md) §2.

> Active ADRs start at `001` ([DECISIONS.md](DECISIONS.md)). Pre-reset specs, old ADRs, and completed sprint/phase reports were removed from the tree on 2026-06-05 and live in **git history**.

## Where to start

| You want to… | Read |
|---|---|
| Install and run the full workflow | [QUICKSTART.md](QUICKSTART.md) |
| Understand the codebase layout & boundaries | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Use the CLI | [CLI_WORKFLOW.md](CLI_WORKFLOW.md) |
| Use / extend the web cockpit | [COCKPIT_WORKFLOW.md](COCKPIT_WORKFLOW.md) |
| Configure providers, models, API keys | [PROVIDER_AND_MODEL_CONFIG.md](PROVIDER_AND_MODEL_CONFIG.md) |
| Understand how a segment becomes a translation | [TRANSLATION_PIPELINE.md](TRANSLATION_PIPELINE.md) |
| Understand EPUB package parsing / preview / fidelity | [PHASE_F_PLAN.md](PHASE_F_PLAN.md), [EPUB_PARSER_AUDIT.md](EPUB_PARSER_AUDIT.md) |
| See MVP scope, gaps, and the sprint plan | [MVP_SCOPE.md](MVP_SCOPE.md) |
| Edit the cockpit UI (tokens, layout, components) | [DESIGN_NOTES.md](DESIGN_NOTES.md) |
| Maintain the repo (cleanup, tests, releases) | [MAINTENANCE.md](MAINTENANCE.md) |
| Read the active architecture decisions | [DECISIONS.md](DECISIONS.md) |

## Supplementary references (still active)

- [ENGINEERING_STANDARDS.md](ENGINEERING_STANDARDS.md) — coding rules, naming, testing.
- [PROMPT_DESIGN.md](PROMPT_DESIGN.md) — prompt templates.
- [SECURITY_AND_PERFORMANCE.md](SECURITY_AND_PERFORMANCE.md) — budgets, threat model.
- [AI_SLOP_PREVENTION.md](AI_SLOP_PREVENTION.md) — feature gates, anti-patterns.
