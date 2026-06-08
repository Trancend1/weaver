# ADR 011 — Project Terminology Consolidation (retires "Novel" from ADR 006)

## Status

Accepted (maintainer, 2026-06-08). Locked **before** Sprint H begins. **Supersedes in part** ADR [`006`](006-novel-volume-chapter-data-model.md): the data model (`Project → Volume → Chapter → Segment`) is unchanged; the user-facing label "Novel" is retired.

## Context

ADR `006` introduced the three-tier hierarchy as **Novel → Volume → Chapter**, but the SQLite schema landed with `projects` and `volumes` tables (not `novels`):

```sql
CREATE TABLE projects (id INTEGER PRIMARY KEY, name TEXT NOT NULL, ...);
CREATE TABLE volumes  (id INTEGER PRIMARY KEY, project_id INTEGER REFERENCES projects(id), ...);
```

Subsequent phases (B, D, E, F) used "Project" in routes, services, templates, and CLI output. The result is a documentation/UI/CLI vocabulary split: the schema, code symbols, and most UI say "Project"; ADR `006` and a small number of remaining strings say "Novel".

Sprint H needs a single, consistent term because:

1. The Volume lifecycle status added in H surfaces in copy ("This Project has 3 Volumes ready for export"); two terms in one sentence is incoherent.
2. The JSON endpoints expand in H (`GET /projects/{project}/volumes/{volume_id}`); the URL term cannot drift from the in-page term.
3. The Tauri shell (Sprint N) opens a WebView onto this UI; locking the term before packaging avoids relabeling under a signed release.

## Decision

**The user-facing tier is "Project". "Novel" is retired from copy, CLI help text, routes, and docs.**

1. **Schema is unchanged.** `projects` and `volumes` stay. No migration. (This is the cheap part — the schema was already correct.)
2. **Code symbols already say `project`.** No symbol rename. Where a stray `novel` survives (audit logged in Sprint H1), it is renamed to `project`.
3. **Copy and CLI.** All user-visible strings use "Project". `weaver init` / `weaver inspect` command names stay (no breaking CLI rename); only their output strings change.
4. **Docs.** ADR `006` is left intact as a historical record of why the tier was introduced; this ADR is the active label authority. New docs use "Project" only.
5. **Hierarchy is unchanged: `Project → Volume → Chapter → Segment`.** This ADR does **not** add a tier (there is no project-of-projects).

### Out of scope

- Renaming `projects` or `volumes` SQLite tables.
- Adding a fourth tier above Project.
- Changing the CLI command names (`init`, `import`, `inspect`, `delete`).

## Consequences

**Improves.**

- One vocabulary across schema, code, routes, UI, and docs.
- Sprint H gets a clean baseline for Volume lifecycle copy.
- Tauri shell ships under a stable label.

**Tradeoffs.**

- ADR `006`'s headline ("Novel / Volume / Chapter") becomes a historical title. The body stays accurate (it describes a schema that already used `projects`).
- Any external scripts that grepped Weaver output for "Novel" will need to update. The user is the only consumer of CLI output today, so this is contained.

## Related Files

- `src/weaver/storage/schema.sql` — already `projects` + `volumes` (no change).
- `src/weaver/services/project.py`, `src/weaver/services/import_source.py` — already use `project`.
- `src/weaver/cli/main.py` — copy audit + fixes in Sprint H1.
- `src/weaver/api/templates/**` — copy audit + fixes in Sprint H1.
- ADR [`006`](006-novel-volume-chapter-data-model.md) — superseded in part (label only; data model stands).
- [docs/weaver_next_plan.md](../weaver_next_plan.md) Sprint H — implementation scope and acceptance.
