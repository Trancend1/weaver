# 0015: TUI Aesthetic Policy for weaver dashboard

Date: 2026-05-23
Status: accepted

## Context

Without an explicit aesthetic policy the dashboard will drift toward whatever the implementer finds convenient — emoji, rainbow colors, or dense ASCII art. Weaver's brand direction calls for terse, technical, and distraction-free output. The TUI must apply the same discipline.

## Decision

The `weaver dashboard` Textual app follows these rules:

**Colors:** neutral dark background (Textual default theme). Progress-complete fill: green (`#00875f`). Status indicators: yellow for `pending`, red for `failed`, default for `translated`/`manual`. Column headers: bold white. No other decorative colors.

**Layout:** single full-width table with two columns (Field / Value), matching the `weaver inspect` Rich table layout. A footer bar shows key bindings: `[R] Refresh  [Q] Quit`. No sidebars, no panels, no nested widgets beyond the table and footer.

**Text:** no emojis in data cells. Labels match `weaver inspect` field names exactly (`Pending`, `Translated`, `Failed`, `Stale`, `Glossary Terms`, etc.). Percentages rendered as `N (P%)` — same helper as `_count_with_percent` in the CLI.

**`--no-color`:** honored by passing `no_color=True` to Textual's `App.__init__`, which disables all ANSI color output. The table remains visible in plain text.

**Auto-refresh:** not implemented. Manual `r` refresh only. No timers, no background threads.

## Consequences

Easier: dashboard looks and feels like `weaver inspect` — no learning curve. `--no-color` makes it usable in editors and log capture.

Harder: the aesthetic is locked; future contributors must update this ADR before adding colors or widgets beyond the table.
