# QA JSON Schema

Version: `1`

## Overview

`weaver validate --json` emits a JSON payload with a stable shape. The `schema_version` integer at the top level signals breaking changes to downstream consumers.

## Current Shape (v1)

```json
{
  "schema_version": 1,
  "project": "string",
  "total_segments": 42,
  "summary": {
    "info": 0,
    "warning": 2,
    "critical": 0
  },
  "findings": [
    {
      "segment_id": "8a3df9c64e0a7ce0",
      "check": "untranslated_japanese",
      "severity": "warning",
      "message": "Translation contains untranslated Japanese characters."
    }
  ]
}
```

## Fields

| Field | Type | Description |
|-------|------|-------------|
| `schema_version` | integer | Schema version; bumps on breaking changes |
| `project` | string | Project name from `project.toml` |
| `total_segments` | integer | Total segment count in the project |
| `summary.info` | integer | Count of info-severity findings |
| `summary.warning` | integer | Count of warning-severity findings |
| `summary.critical` | integer | Count of critical-severity findings |
| `findings[].segment_id` | string | Segment identifier |
| `findings[].check` | string | Check name (see below) |
| `findings[].severity` | string | `info`, `warning`, or `critical` |
| `findings[].message` | string | Human-readable finding description |

## Check Names

| Check | Severity | Description |
|-------|----------|-------------|
| `empty_translation` | critical | Translated segment has no text |
| `untranslated_japanese` | warning | Translation contains Japanese characters |
| `length_ratio` | warning | Translation length ratio below threshold |
| `glossary_mismatch` | warning | Approved glossary term missing from translation |
| `failed_segment` | critical | Segment status is `failed` |
| `stale_segment` | info | Segment source changed since last translation |

## Versioning Contract

- Version increments when required fields are added/removed or types change.
- Additive optional fields do not bump the version.
- Inspect the current version: `weaver validate --schema`.

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | No critical findings |
| 1 | At least one critical finding |
