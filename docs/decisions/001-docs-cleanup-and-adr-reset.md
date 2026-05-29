# ADR 001 — Docs Cleanup and ADR Reset

## Status

Accepted

## Context

Weaver shipped through Phases 0–13 (v0.6.0: CLI complete, Flask web cockpit end-to-end). The accumulated documentation no longer matched the next direction:

- `CLAUDE.md` had grown to ~48 KB — a phase-history museum (full per-phase exit-criteria ledgers for Phases 0–13), not an operational file.
- `docs/` held nine pre-build strategy documents (go-to-market, startup verdict, priority matrix, brand, design-system, future roadmap, execution blueprint, benchmarks, release acceptance) that are historical, not development-actionable.
- Twenty ADRs (`0001`–`0020`) accumulated across phases. Several (notably `0016`, which selected Flask and *rejected* FastAPI) conflict with the new FastAPI-first cockpit direction. Leaving them in the active set would keep steering agents/developers by superseded decisions.
- An accidental nested git clone (`weaver/`, ~10.5k files, same remote at v0.4.0) and a working-tree deletion of `uv.lock` were repo-hygiene hazards.

The maintainer chose a **controlled reset** — audit, archive, re-baseline — not a destructive rewrite. Working behavior (CLI + Flask cockpit) must be preserved.

## Decision

1. **Archive, don't delete.** Move all twenty old ADRs to `docs/archive/decisions/` and the nine strategy docs to `docs/archive/strategy/`. They stay version-controlled and browsable, out of the active set.
2. **Reset the active ADR set to `001`–`005`.** Active numbering restarts at `001`. Important insights from archived ADRs are migrated into the new ones (e.g. `0016`/`0017`/`0019`/`0020` insight → `002`/`004`).
3. **Compress `CLAUDE.md`** into a short operational file (overview, status, focus, boundaries, commands, coding rules, active phase/sprint, MVP priorities, quality gates). Phase 0–13 history is preserved in git history and the archive, not in the active doc.
4. **Repo hygiene:** gitignore + remove the accidental `weaver/` nested clone; restore the committed `uv.lock`.

## Consequences

Improves: active docs become small and match the codebase + new direction; agents stop following superseded decisions; nothing historical is lost (archived, not deleted).

Tradeoffs: ADR renumbering means in-code/in-doc references to old numbers (`ADR 0016`, `0020`, …) now point at archived files — callers must reference the new active ADRs or the archive path. Old phase evidence is one `git log` away rather than inline.

## Related Files

- `docs/archive/decisions/0001-0020*.md` (archived)
- `docs/archive/strategy/*.md` (archived)
- `docs/decisions/001-005*.md` (new active set)
- `CLAUDE.md`, `.gitignore`
