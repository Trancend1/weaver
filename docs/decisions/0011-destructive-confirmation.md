# 0011: Destructive-Action Confirmation Prompts

Date: 2026-05-23
Status: accepted

## Context

Two Weaver commands can silently destroy user work:

1. `weaver init` on an already-initialized project overwrites `project.toml`, the database, and glossary candidates without warning.
2. `weaver glossary edit` syncs a TSV back into SQLite. If the user accidentally deleted rows or changed statuses, approved glossary terms are lost.

Fan-translators invest hours in glossary curation. Silent overwrites violate the principle of least surprise.

## Decision

Add interactive confirmation prompts before destructive actions:

**`weaver init` overwrite:**
- Before calling `initialize_project()`, check if the target `project.toml` already exists.
- If it exists, print the path and prompt: `"Project already exists at <path>. Overwrite? [y/N]"`.
- Default is abort (N). `--yes` / `-y` flag skips the prompt.

**`weaver glossary edit` sync:**
- Before syncing TSV rows, show a summary: `"Will sync N rows from TSV (M status changes). Continue? [y/N]"`.
- Default is abort. `--yes` / `-y` flag skips the prompt.

Both prompts use `typer.confirm()` for consistent behavior. In non-interactive terminals (piped stdin), `typer.confirm()` raises `typer.Abort` unless `--yes` is passed, which is the safe default.

## Consequences

**Easier:** Users get a safety net before destructive operations. Scripts use `--yes` for automation.

**Harder:** Interactive prompts break non-interactive pipelines that do not pass `--yes`. This is intentional — destructive actions should require explicit opt-in in automation contexts.
