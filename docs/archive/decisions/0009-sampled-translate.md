# 0009: Sampled Translate

Date: 2026-05-23
Status: accepted

## Context

Translating a full novel (thousands of segments) through a cloud provider is expensive and slow. Users want a fast-fail sanity check: translate a small sample, verify the provider responds, glossary terms apply correctly, and output quality is acceptable before committing to a full run.

## Decision

Add `weaver translate --first-N <int>` to `weaver translate`. When set, the orchestrator selects up to N segments from the pending (or failed, with `--retry-failed`) queue and stops after translating them. State is consistent: translated segments are committed; remaining segments stay pending.

`--first-N` composes with existing flags:

- `--first-N 10 --dry-run`: estimate tokens for only 10 segments.
- `--first-N 5 --retry-failed`: retry only the first 5 failed segments.
- `--first-N 0`: no-op, translates nothing (useful for scripting guards).

The truncation happens after segment selection but before the translation loop. No new database queries are needed — just `selected = selected[:first_n]`.

## Consequences

**Easier:** Fast-fail workflow: `weaver translate --first-N 3` → review output → `weaver translate` for the rest. Cost control for cloud providers.

**Harder:** Users may forget they used `--first-N` and think translation is complete. Mitigated by the summary output always showing `Selected: N` and `Pending: M` counts.
