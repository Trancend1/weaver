# ADR 006 — Novel / Volume / Chapter Data Model

## Status

Accepted

## Context

The MVP baseline (ADR `003`) requires a **Novel → Volume → Chapter** structure
and multi-format import. The v0.6.0 schema modelled `project = one EPUB` with
chapters attached directly to a project (`storage/schema.sql`, schema v2) — no
Volume tier, and a single `projects.source_path`. Light novels ship per-volume,
so a series (Novel) naturally has several source files (Volumes), each with its
own chapters.

This ADR records how the tier was introduced without breaking the shipped CLI or
existing project databases. It covers Sprint 1, stage 1a (model + migration +
EPUB-as-volume); the TXT/HTML readers (1b) and cockpit tree UI (1c) build on it.

## Decision

1. **Project = Novel; each imported source file = Volume.** New `volumes` table
   (`id, project_id, title, source_path, source_format, volume_order, created_at`);
   `chapters` gains `volume_id`. `source_format` is constrained to
   `epub | txt | html`. `chapters.project_id` is kept (denormalized) so existing
   spine-order translate/segment queries are unchanged.
2. **Schema bumped v2 → v3** (`storage/db.py SCHEMA_VERSION = 3`). Fresh databases
   apply the full `schema.sql`; existing v2 databases run `_migrate_to_v3`, which
   creates `volumes`, adds `chapters.volume_id`, and wraps each project's existing
   chapters in **one synthesized default volume** (`source_format='epub'`,
   `volume_order=0`). No data is lost; the old database is untouched until the
   migration transaction commits.
3. **`weaver init <epub>` is preserved.** It now creates the Novel and its first
   Volume in one step; CLI output and `InitResult` are unchanged. A new
   `weaver import <project.toml> <source>` command and `services/import_source.py`
   add further volumes, reusing the existing reader → segment-sync → glossary
   pipeline. One import = one transaction.
4. **`projects.source_path` may be an empty string** for a Novel created before
   its first import (avoids a SQLite table rebuild to drop `NOT NULL`); the first
   import backfills it. `inspect` now reports a `Volumes` count.

## Consequences

Improves: the data model matches light-novel reality (a Novel with multiple
Volumes); import is reusable across formats; legacy projects upgrade transparently.

Tradeoffs: a schema migration is the highest-risk change (covered by a v2→v3
migration test); chapter/segment IDs must stay unique across volumes in one
database — EPUB IDs already fold in the book identifier, but TXT/HTML readers
(1b) must fold in the source filename to avoid collisions. EPUB write-back
(`renderers/epub.py`, Sprint 7) still depends on `EpubMarkupContext`; volumes
sourced from TXT/HTML carry no such context and are out of scope here.

## Related Files

- `src/weaver/storage/schema.sql`, `storage/migrations.py` (`_migrate_to_v3`), `storage/db.py`
- `src/weaver/storage/volumes.py` (new), `storage/segments.py` (`sync_document_segments` gains `volume_id`)
- `src/weaver/services/import_source.py` (new), `services/project.py`, `services/translation.py`
- `src/weaver/cli/main.py` (`import` command, `inspect` volume count)
- `docs/MVP_SCOPE.md` (Sprint 1), `docs/ARCHITECTURE.md` (data model)
