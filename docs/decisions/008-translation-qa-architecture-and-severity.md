# ADR 008 — Translation QA Architecture & Severity Contract

## Status

Accepted (maintainer, 2026-06-05). Gate B1 of **Phase B — Translation QA & Consistency Checks**. Doc-only; no code lands with this ADR.

## Context

Phase B adds a **read-only, report-first** QA capability: surface translation-quality and
consistency problems before export, without auto-fix, provider/LLM calls, mutation, or
semantic/vector analysis ([CLAUDE.md §2.3](../../CLAUDE.md), [PHASE_B_QA_PLAN.md](../PHASE_B_QA_PLAN.md)).

A deterministic QA layer already exists and ships today:

- `weaver.qa.checks` — pure, framework-agnostic per-segment checks (`SegmentInput`, `QAWarning`,
  `Severity = Literal["info","warning","critical"]`, six checks + `run_all_checks`).
- `services/qa.py` (`validate_project`) — the `weaver validate` engine: read-only DB, **single flat
  project, project-wide**, no Novel/Volume/Chapter scoping; emits a `--json` payload whose severity
  enum is `info|warning|critical`, with exit code `1` on any `critical` (schema described by
  `qa_report_schema()`, versioned per ADR `0010`, archived).

The risk in Phase B is **building a second, parallel QA system** with divergent rules and a divergent
severity vocabulary (the draft plan proposed `info|warning|error`). That would fork per-segment logic,
break the existing `--json`/exit-code contract, and let QA and export disagree about what counts as
"published".

## Decision

**1. Reuse and extend the existing QA layer; do not build a parallel one.**

- Per-segment rule *logic* stays single-sourced in `weaver.qa.checks` and is **reused unchanged**.
- New deterministic rules live in **new pure modules** (`weaver/qa/consistency_checks.py`,
  `weaver/qa/scope_checks.py`) that import `QAWarning`/`Severity`/`SegmentInput` from `checks.py` — one
  finding type, one severity enum, no duplication. The existing `qa/checks.py` is not refactored.
- A new framework-agnostic service `services/translation_qa.py` orchestrates **scope-aware** analysis
  (`analyze_chapter` / `analyze_volume` / `analyze_novel`): open a read-only connection, resolve scope
  → chapter ids, load segments + glossary + characters + export states, run the shared checks + new
  rules, and aggregate a frozen `QAReport`. It reuses existing readers (`list_chapter_ids_for_*`,
  `get_chapter`, `list_export_segment_states`, `list_glossary_terms`, `list_characters`).
- `services/qa.py` / `weaver validate` stay **unchanged**; both CLI and cockpit share
  `weaver.qa.checks`. The cockpit QA API/UI is **additive** (scope-aware), not a replacement.
- The `fallback_heavy_chapter` rule reuses `list_export_segment_states` — the **same** publishable
  rule the exporter uses — so QA and export never disagree.

**2. Severity contract: keep `info | warning | critical`. Do not introduce `error` in the
data/wire layer.**

- The QA severity enum is `Literal["info","warning","critical"]`, imported from `weaver.qa.checks`.
  This preserves the `weaver validate --json` payload, the exit-code semantics (any `critical` → exit
  `1`), ADR `0010`, and the existing tests.
- The UI **may label** `critical` as "Error" and uses badge states `clean` / `warnings` / `errors`,
  but the wire value stays `critical`. API count fields use `critical_count` (not `error_count`).
- Rule severities are fixed at: `failed_segment`, `empty_translation`, `untranslated_japanese` →
  `critical`; `stale_segment`, `length_ratio`, `glossary_mismatch`, `untranslated_segment`,
  `character_name_missing`, `repeated_identical_translation`, `fallback_heavy_chapter` → `warning`;
  `mixed_status_chapter` → `info`.

**3. Thresholds are module-level constants first, not `[qa]` config (yet).**
`fallback_heavy_ratio = 0.5`, `fallback_heavy_min_segments = 5`, `repeated_min_chars = 8` live as
constants in `scope_checks.py`. (`minimum_length_ratio = 0.3` remains the existing `[qa]` flag.)
A QA config surface may be added later via a follow-up decision if users need it.

**4. Layering.** Service returns frozen dataclasses; **Pydantic only at the API boundary**; UI is
presentation-only Jinja2 + HTMX (ADR `007`). No business logic in routes/templates.

## Consequences

Improves: one source of truth for per-segment QA logic across CLI and cockpit; no severity/translation
layer to maintain; QA agrees with export on "published"; the existing `weaver validate` contract is
untouched; clean read-only/deterministic boundary (testable without providers).

Tradeoffs: the API count field name (`critical_count`) and the UI label ("Error") differ in wording —
documented and intentional. The scope-aware loader adds a new SQL path beside `services/qa.py`'s
project-wide loader; an optional B6 rebase could unify them, but only if it leaves CLI output/exit
codes identical (not required). Per-chapter tree badges are deferred to avoid a full novel-scope scan
on every tree render; explicit QA pages come first.

## Related Files

- [PHASE_B_QA_PLAN.md](../PHASE_B_QA_PLAN.md) (Stage B1 plan: inventory, rule list, schema, B2–B6).
- `src/weaver/qa/checks.py` (reused); new `weaver/qa/{consistency_checks,scope_checks}.py`,
  `services/translation_qa.py` (Stage B2).
- `src/weaver/services/qa.py` (`weaver validate`, unchanged); ADR `0010` (archived, QA JSON schema).
- ADR [`002`](002-cli-web-boundary-and-maintenance-structure.md) (framework-agnostic core),
  [`003`](003-mvp-baseline-for-light-novel-translator.md) (deterministic-by-default),
  [`007`](007-fastapi-ui-stack.md) (Jinja2 + HTMX UI).
- [CLAUDE.md §2.3](../../CLAUDE.md) (Phase B active scope).
