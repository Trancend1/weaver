# 0010: QA JSON Schema Versioning

Date: 2026-05-23
Status: accepted

## Context

`weaver validate --json` emits a stable JSON payload consumed by scripts and CI pipelines. As the QA engine evolves (new checks, new fields), consumers need a machine-readable signal when the shape changes so they can update their parsers.

## Decision

Add a `schema_version` integer to the top level of the `--json` payload:

```json
{
  "schema_version": 1,
  "project": "...",
  "total_segments": 42,
  "summary": { ... },
  "findings": [ ... ]
}
```

Version `1` is the current shape shipped in Phase 9 and documented in Phase 11a's `--schema` output. The version number increments when:

- A required field is added or removed.
- A field's type changes.
- The `findings` array item shape changes.

Additive optional fields (new keys with default-absent semantics) do not bump the version.

`weaver validate --schema` output also gains `"schema_version": "integer"` in its fields dict and a top-level `"current_version": 1` key.

The full schema contract is documented at `docs/api/qa_json_schema.md`.

## Consequences

**Easier:** Downstream consumers can `if payload["schema_version"] != 1: warn(...)` and degrade gracefully. Schema documentation lives next to the code.

**Harder:** Maintainer must remember to bump the version on breaking changes. Mitigated by a test that asserts the version matches the documented constant.
