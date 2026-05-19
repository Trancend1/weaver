# Weaver

Offline-capable, glossary-aware JP-to-EN novel translation workbench.

Weaver is a local CLI for turning a Japanese EPUB into two reviewable outputs:
a Markdown review set and a translated EPUB. It is intentionally small: no GUI,
no hosted service, no accounts, and no telemetry by default.

## Start Here

- [Quickstart](quickstart.md): install and first run.
- [Product Requirements](PRD_v2.md): MVP-0 scope and acceptance criteria.
- [Security And Performance](SECURITY_AND_PERFORMANCE.md): threat model and budgets.
- [Benchmarks](benchmarks.md): release-candidate performance evidence.
- [Architecture](SYSTEM_ARCHITECTURE.md): modules, schema, and provider interface.
- [Engineering Standards](ENGINEERING_STANDARDS.md): coding and review rules.

## Release Gate

The v0.1.0 gate is defined by `PRD_v2.md` AC-1 through AC-9, plus the Phase 10
hardening checklist in `BLUEPRINT_EXECUTION_PLAN.md`.
