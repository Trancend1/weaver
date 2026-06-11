# ADR 013 — QA `error` Severity Tier (Rejected / Deferred)

## Status

Rejected — deferred (maintainer + Lead Orchestrator, 2026-06-12). Governance gate of **Sprint Q11 — Validation improvements** ([SPRINT_Q_EXECUTION_PLAN.md §Q11](../../.docs/audit/SPRINT_Q_EXECUTION_PLAN.md)). Doc-only; the decision is to **not** change the severity data layer.

## Context

WV-008 asked whether Weaver's QA severity vocabulary should grow a fourth, top
tier — `error` — above `critical`, so that a future class of "this will produce a
broken book" findings could outrank the existing `critical` translation findings.

The current contract is fixed by ADR [`008`](008-translation-qa-architecture-and-severity.md):

- `weaver.qa.checks.Severity = Literal["info", "warning", "critical"]`, single-sourced
  and imported by `qa/report.py` (`QASeverity = Severity`), `qa/consistency_checks.py`,
  and `qa/scope_checks.py`.
- `weaver validate --json` emits `summary.{info,warning,critical}` and exits `1` on any
  `critical` (schema `qa_report_schema()`); the `export_history`/export-gate path keys
  the Final-export block on `report.critical_count > 0`.
- The dead `qa_warnings` table (retired in Q11, WV-011) carried a 3-tier
  `CHECK (severity IN ('info','warning','critical'))` — a 4-tier severity would have
  contradicted it (QF-16).

Sprint Q11 adds three deterministic fidelity checks (`max_length_ratio`,
`punctuation_mismatch`, `broken_line_breaks`) and joins read-only EPUB **structure**
validation into the report (WV-007). The question is whether any of these justify a
new tier.

## Decision

**Do not introduce an `error` severity tier. Keep the 3-tier
`info | warning | critical` contract from ADR 008.**

Rationale:

1. **No new check needs it.** The three Q11 fidelity checks are advisory signals
   (length/punctuation/line-break heuristics) and map cleanly to `warning`/`info`.
   None asserts a guaranteed-broken artifact.
2. **Structure findings stay advisory, not escalated.** WV-007 joins persisted EPUB
   `ValidationIssue`s (their own `error|warning|info`) into the report under a new
   `structure` category with `source = "structure"`. EPUB `error` is mapped **down** to
   QA `warning` (never `critical`) so a structural finding never raises the badge to
   "errors" and never blocks a Final export. The export gate is Q7-owned and explicitly
   out of Q11 scope; routing structure criticals into the gate would require changing it.
3. **A 4-tier enum is a wide, mostly-cosmetic blast radius.** It would touch the wire
   schema, exit-code semantics, two badge maps, the export-gate predicate, and every
   severity test — for no behavioral gain that `critical` does not already provide.
4. **ADR 008 stands.** The "label `critical` as Error in the UI, keep `critical` on the
   wire" convention already gives users an "Error" affordance without a data-layer change.

If a genuine "guaranteed-broken-output" check class ever arrives (e.g. a structure
finding that must hard-block Final export), this ADR is the re-open point: it would need
(a) a concrete failing check, (b) an export-gate change scoped by `source`, and (c) a
wire/exit-code migration plan. None exist today.

## Consequences

Improves: zero churn to the `weaver validate` JSON/exit-code contract, the export gate,
and existing severity tests; structure findings are surfaced without surprising
export-blocking behavior; the severity vocabulary stays single-sourced.

Tradeoffs: a structural `error` is shown as a QA `warning`, so its original EPUB severity
is presentation-flattened in the QA view (the raw severity remains visible on the
Content Explorer → Warnings tab, which reads the snapshot directly). Accepted: the QA
report is advisory by ADR 008, and the Explorer remains the fidelity-detail surface.

## Related Files

- `src/weaver/qa/checks.py` (`Severity`, the three Q11 checks); `src/weaver/qa/report.py`
  (`QACategory` + `structure`, `QASource`, `QAIssue.source`).
- `src/weaver/services/translation_qa.py` (`_structure_issues`, `_STRUCTURE_SEVERITY_MAP`).
- `src/weaver/services/export_gate.py` (unchanged; keys on `critical_count`).
- ADR [`008`](008-translation-qa-architecture-and-severity.md) (severity contract this
  decision preserves).
- [SPRINT_Q_EXECUTION_PLAN.md §Q11](../../.docs/audit/SPRINT_Q_EXECUTION_PLAN.md) (WV-008 step 1).
