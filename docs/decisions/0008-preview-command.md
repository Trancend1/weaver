# 0008: Preview Command

Date: 2026-05-23
Status: accepted

## Context

After translating, users want to spot-check results without running a full Markdown export. `weaver inspect` shows counts but not content. A read-only inline preview that shows source + translation pairs for specific segments or chapters fills this gap.

## Decision

Add `weaver preview <project.toml> [--segment ID] [--chapter K] [--pager auto]`.

Behavior:

- Without filters: shows all segments in spine order (source + translation or status marker).
- `--segment ID`: shows one segment only.
- `--chapter K`: shows all segments in chapter K (1-indexed).
- `--pager auto`: pipes output through `$PAGER` when set; otherwise prints directly.
- Output uses Rich panels for terminal display: source text in a quote block, translation below.

Implementation lives in `src/weaver/services/preview.py` which returns a list of `PreviewBlock` dataclasses. The CLI renders them. The service never touches the terminal — rendering stays in the CLI boundary.

The command is read-only: no database writes, no side effects.

## Consequences

**Easier:** Fast spot-check without export. Segment-level filtering lets users verify specific problem areas flagged by `weaver validate`.

**Harder:** Preview output is not identical to Markdown export — different rendering logic. This is acceptable because preview is a debugging tool, not a publishing surface.
