# Execution Plan — Translation Enforcement Loop (ADR 019, P0)

**Status:** Active — **ADR 019 accepted (2026-06-16).** Folded into **v0.7.2**.
**E1+E2 shipped** (commit `992d533`, full suite 1564 passed) — together (a detection-only gate
would be a zero-caller module, §4.2/§4.3). **E3+E4 shipped** (`[translation_profile]` `<profile>`
block + banned-slop soft check; `uncertain_terms` → discovered glossary candidates). **P0 done —
next: tag v0.7.2.**
**Governs:** the P0 core of ADR 019 (make glossary/character binding + anti-slop real).
**Branch target:** `feat/connection-first-routing` (owner direction: complete everything in
v0.7.2, no PR).

---

## Scope & non-goals (whole sprint)

**In scope (P0):** the verify→repair loop that turns the *existing* glossary/character/TM
machinery from decorative into load-bearing, plus the anti-slop style contract.

**Out of scope (explicit non-goals):**
- Cross-chapter narrative summarizer / story-context layers (ADR 019 defers; needs its own ADR).
- Fuzzy TM, TMX I/O, genre packs, in-reader highlight, reverse-lookup, AI paired-judging.
- `[routing.repair]` / `TaskType.repair` (ADR 019 §5 — seam declared, not built).
- Any unbounded retry, circuit breaker, health-score, cost dashboard, telemetry (ADR 018 D9).
- Any AI work on a render path (Gate B1) — enforcement runs only inside an explicit translate job.

**Hard-rule fences (must hold every slice):** bounded **1** repair pass; detection is free +
deterministic; failure visible never silently substituted; cost (repass tokens) shown;
single-user; no new runtime dependency.

---

## Slice E1 — Detection gate (free, always-on) — *kills the gimmick by itself*

**Goal:** run the existing deterministic checks against a fresh translation inside
`translate_one_segment`, **before commit**, and record which checks fired on the attempt — with
**no model call** and **no repair yet**. After E1, a glossary/character violation is always
visible even with zero added token cost.

**Files (anchors):**
- `services/enforcement.py` (new) — pure function `evaluate(translation, source, glossary,
  characters, profile) -> EnforcementResult` reusing `qa/checks.check_glossary_mismatch`,
  `qa/consistency_checks.check_character_name_missing`, JP-residue, anti-truncation floor.
- `services/translation.py:translate_one_segment` (~533–560) — call the gate post-response,
  pre-`record_translation`.
- Persistence of findings — **decide at readiness (Gate B):** reuse the append-only
  `translations` provenance vs a tiny column. Prefer reuse; a migration needs justification.

**Acceptance:**
- A segment whose translation omits a matched glossary target / character EN-name is **flagged**
  (finding recorded + surfaced in the workspace/run summary), and the translation still commits.
- Anti-truncation floor flags only empty/catastrophically short output (**not** terse-but-valid).
- Zero added model calls; `pytest` proves the gate is pure (no provider/DB in the evaluator).
- `[qa] minimum_length_ratio` is **not** consulted by the gate (Q4).

**Non-goals:** no repair re-ask, no prompt change, no config flag yet.

---

## Slice E2 — Targeted repair re-ask (bounded 1-pass, switchable)

**Goal:** when E1 finds violations and `[translation] enforce_repair` (default `true`) is on,
issue **one** repair re-ask enumerating the specific violations, re-validate once, commit the
better result; if still violating, commit best attempt + keep the finding (visible, non-blocking).

**Files (anchors):**
- `providers/templates/enforcement_repair.jinja2` (new) — enumerates violations; "change only
  what is needed".
- `services/enforcement.py` — `repair_once(provider, segment, violations, ...)` that **takes the
  `provider` as a parameter** (ADR 019 §5 seam discipline), reusing the `complete()`/`translate()`
  primitive + parser.
- `services/translation.py:translate_one_segment` — call `repair_once` on violation; count repass
  tokens into the segment usage.
- `core/config.py` — parse `[translation] enforce_repair` (default true).

**Acceptance:**
- Violating segment → exactly **one** repair call (assert call count == 1), never a loop.
- Repaired text satisfying the checks is committed; persistent violation → best attempt committed
  + finding retained.
- `enforce_repair = false` → E1 detection still runs/marks; **zero** repair calls.
- Repass token cost appears in the segment's usage and the run summary.
- `FakeProvider` drives the test deterministically (no live model).

**Non-goals:** no second pass, no routing override, no banned-phrase handling yet.

---

## Slice E3 — Translation Profile contract + banned-slop seed (soft trigger)

**Goal:** `[translation_profile]` becomes a real contract — drives a `<profile>` prompt block
**and** the post-check. Ship a tiny override-able banned-phrase seed as a **soft** repair trigger.

**Files (anchors):**
- `core/config.py` — parse `[translation_profile]` (`tone`, `dialog_style`, `name_rendering`,
  `tense`, `banned_phrases`); pure config, no schema change.
- `core/slop_seed.py` (new) — ~5–8 high-confidence calques; applied only when
  `[translation_profile]` is present; replaced/disabled by `banned_phrases`.
- `providers/templates/balanced_system.txt` + `balanced_user.jinja2` — emit `<profile>` block.
- `services/enforcement.py` — banned-phrase hit = **soft** trigger ("reconsider", never hard-fail).

**Acceptance:**
- A project with `[translation_profile]` emits a `<profile>` block; a project without it is
  byte-for-byte unchanged in prompt output (backward compat).
- A banned-phrase hit triggers at most the same single E2 repair (soft), never a block.
- `banned_phrases = []` disables; a custom array replaces the seed.

**Non-goals:** no scoped "term conventions", no per-thread inheritance (Phase D).

---

## Slice E4 — Recover discarded `uncertain_terms` → glossary candidates (free discovery)

**Goal:** consume the `uncertain_terms` already returned by every response
(`providers/parser.py:63`, today dropped) → upsert into `glossary_candidates` (`frequency++`),
giving continuous entity discovery **with no extra model call**.

**Files (anchors):**
- `services/translation.py:translate_one_segment` — after a successful (or repaired) commit, feed
  `response.uncertain_terms` to a candidate upsert.
- `services/glossary.py` / `storage/glossary.py` — reuse the existing candidate upsert
  (`frequency` increment) path; no new table.

**Acceptance:**
- A response with `uncertain_terms` produces/updates `glossary_candidates` rows (`frequency++`),
  reviewable in the existing cockpit candidates page.
- No extra provider call is made; duplicates increment frequency, not duplicate rows.
- Opt-out respected if a project disables discovery (reuse existing cadence/config if present).

**Non-goals:** no separate "continuous extraction" model call (E4 replaces it for free).

---

## Sequencing & gates

```
E1 (detection, free) ──► E2 (repair, switchable) ──► E3 (profile + slop) ──► E4 (uncertain_terms)
        │ gimmick already dead after E1                                          │ free discovery
```

- **E1 is independently shippable** and the highest-value slice: it removes the gimmick at zero
  token cost. Ship it first; E2–E4 are improvements on top.
- Each slice: ruff + ruff format + pyright + `pytest -q -m "not requires_cloud and not requires_ollama"`
  green before the next. One slice = one commit.
- Gate B1 check per slice: confirm no enforcement runs on any render path (only inside the
  translate job).
- Owner-visible evidence required for E2 (token-cost delta on a violating fixture) before
  defaulting `enforce_repair = true` is locked.

## Open implementation decisions (settle at Gate B, not now)

1. **Findings persistence** — reuse `translations` provenance vs a small column/table. Prefer
   reuse; a migration must be justified (CLAUDE.md §4.2 / no schema churn).
2. **Anti-truncation floor value** — propose target empty or < ~15% of a char-based expectation;
   tune against a fixture so terse-but-valid JP→EN never triggers.
3. **Where the `<profile>` block sits** relative to `<glossary>`/`<policy>` for best adherence —
   decide with a small prompt A/B on the fake + one live smoke (owner machine).
