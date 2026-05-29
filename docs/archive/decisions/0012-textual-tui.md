# 0012: Textual TUI for weaver dashboard

Date: 2026-05-23
Status: accepted

## Context

`weaver inspect` prints a one-shot status table. Power users running long translation jobs want to check progress without re-invoking the command. A persistent TUI that they can leave open and refresh on demand fits that workflow. The TUI must degrade gracefully when textual is not installed — the base tool must not require a 4 MB framework for users who only use `weaver translate`.

## Decision

Add `weaver dashboard <project.toml>` backed by the `textual` library, shipped as an optional extra `[tui]`. The dashboard is read-only: it calls `inspect_project()` to load state and renders it in a Textual `App`. Key bindings: `r` to refresh, `q` to quit. No background polling — manual refresh only avoids leaving SQLite connections open across event-loop ticks.

`textual` is declared under `[project.optional-dependencies] tui = ["textual>=0.60"]`. The CLI defers `from weaver.tui.dashboard_app import run_dashboard` to inside the command function body so that `import weaver.cli.main` never fails in CI (where only the `dev` extra is installed). A `_require_textual()` guard at the top of `run_dashboard` raises `ConfigError` with an install hint when the package is absent.

The TUI aesthetic is documented in ADR 0015.

## Consequences

Easier: users can watch translation progress without re-running `weaver inspect`. Dashboard reuses `inspect_project()` — no duplicate SQL.

Harder: Textual's async event loop cannot be driven by `typer.testing.CliRunner`. CLI tests mock `run_dashboard` at the function boundary; service-layer tests call `inspect_project()` directly. A new `src/weaver/tui/` package is added, making the source tree slightly larger.
