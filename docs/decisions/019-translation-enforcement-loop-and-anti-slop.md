# ADR 019 — Translation Enforcement Loop + Anti-Slop Post-Check

## Status

**Accepted (owner "lanjutkan progres", 2026-06-16).** Folded into the **v0.7.2** scope on
`feat/connection-first-routing` (no separate branch/PR — owner direction: complete everything in
0.7.2). The four open questions are resolved (see "Resolved decisions"). Makes the **existing**
glossary/character/TM machinery *load-bearing* instead of advisory. Companion to ADR 014 (the
`complete()` transport primitive) and ADR 018 (per-task routing). Origin: owner concern that
glossary, persistent character/term, and MTL-slop handling must be **real, not gimmick**
(`.proposal/weaver-novel-translation-proposal.md` review, 2026-06-16). Execution plan:
[`2026-06-16-enforcement-loop-execution-plan.md`](../superpowers/specs/2026-06-16-enforcement-loop-execution-plan.md).

## Context

### The verified gap: inject + advisory verify + JSON-only repair, never connected

Weaver already owns the three pieces of an enforcement loop, but they are **wired apart**:

1. **Inject (the "ask").** Approved glossary terms and characters are substring-filtered
   (cap 20) and pasted into the prompt as TSV `<glossary>`/`<characters>` blocks. The system
   prompt only *persuades*: *"If a term appears in `<glossary>`, use the specified English
   translation exactly."*
   — `providers/templates/balanced_system.txt:7-8`, `balanced_user.jinja2:4-17`,
   `services/translation.py:120-159`.
2. **Verify (the "check") — deterministic, but disconnected.** `check_glossary_mismatch`
   (`qa/checks.py:185-219`) and `check_character_name_missing`
   (`qa/consistency_checks.py:46-78`) deterministically detect when a matched term/name's
   target is **absent** from the translation. Both emit severity **`warning`**, and only run
   inside **on-demand advisory QA** — never at translate time.
3. **Repair (the "fix") — exists, but JSON-only.** A bounded single repair re-ask already
   exists (`providers/openai_chat.py:109-121`, `templates/repair.txt`) but fires **only** when
   the model returns malformed JSON. It knows nothing about glossary/character violations.

**Consequence (the gimmick).** When the model ignores a glossary term or drops a character
name, the bad translation is **committed as-is**; the violation becomes a `warning` the user
may never open. The glossary/character database is therefore **decorative**: present in the
prompt, not binding on the output. This is exactly the "gimmick" the owner flagged — and the
code confirms it.

Two more signals are already produced and then **discarded**:

- The model returns `uncertain_terms` on every segment (`balanced_system.txt:16`), parsed into
  `TranslationResponse.uncertain_terms` (`providers/parser.py:63`, `types.py:70`) — but **no
  code consumes it**. Free entity-discovery thrown away.
- `[qa] minimum_length_ratio` and `detect_untranslated_japanese` thresholds exist per project,
  but only as post-hoc advisory checks, not as translate-time guards.

### Why "more context" does not fix this

The reviewed proposal leads with breadth (cross-chapter context, richer character schema,
genre packs, fuzzy TM, TMX). None of those make a single term *bind*. Feeding a larger,
un-enforced prompt enlarges the gimmick surface. The smallest change with the largest effect
on "no-gimmick translation" is to **close the verify→repair loop**, reusing primitives that
already exist.

## Decision

> All clauses below stay inside the locked hard rules (ADR 018 D9, CLAUDE.md §3.4/§3.5):
> bounded single re-ask (not a circuit breaker / retry storm), explicit translate-time only
> (Gate B1), deterministic checks, **visible failure never silently substituted**, cost
> visible, single-user, no telemetry.

### 1. A deterministic post-translation enforcement gate, in the service layer

Add a validation gate to the translation pipeline (`services/translation.py`,
`translate_one_segment`, after a successful provider response and **before** `record_translation`).
The gate runs the **already-existing deterministic checks** against the fresh translation:

- glossary target presence (`check_glossary_mismatch`) — **strong, safe** trigger (binary),
- character EN-name presence (`check_character_name_missing`) — **strong, safe** trigger (binary),
- untranslated-JP residue (reuse the `detect_untranslated_japanese` logic) — strong trigger,
- a **loose anti-truncation floor** (target empty or < ~15% of expected) — *weak* guard for
  broken/truncated output only, **not** the QA `minimum_length_ratio` (Q4 — see §6),
- optional **banned-slop** phrase list (new, deterministic, **soft** trigger — see §3).

The gate lives in a **service**, not in the provider, preserving the ADR 014 boundary: the
provider's JSON-repair is a *transport* concern; enforcement is a *domain* concern. The
provider stays domain-agnostic.

**Detection is free and always on (Q1).** The gate is pure deterministic substring/ratio work
— **zero tokens, zero model call**. It therefore runs on *every* translated segment
unconditionally and **records which checks fired on the row**, so a glossary/character
violation is *always* visible even when the (token-costing) repair pass in §2 is switched off.
This alone removes the gimmick: a term can no longer be silently ignored. Only the §2 repair
re-ask spends tokens and is switchable.

### 2. One bounded, targeted repair re-ask on violation

If the gate finds violations **and the repair pass is enabled** (`[translation] enforce_repair`,
default true — see §6), issue **exactly one** repair re-ask that **enumerates the specific
violations** ("Glossary requires 李晨 → 'Li Chen'; it is missing. Re-emit the same translation,
changing only what is needed to satisfy these constraints; do not alter anything else."). Reuse
the existing repair scaffold (`load_repair_prompt` pattern) with a new enforcement-repair prompt
template.

- **Bounded to 1 pass.** Mirrors the JSON-repair contract exactly. No loop, no escalation, no
  cold-mark, no circuit breaker.
- **Switchable, but detection is not.** When `enforce_repair = false`, the §1 detection still
  runs and marks violations (free); only this token-costing re-ask is skipped. So turning it off
  trades cost for fixes — never for the gimmick.
- **Re-validate once after repair.** If the repair satisfies the checks → commit the repaired
  text. If it still violates → **commit the best attempt and mark the segment** (the violations
  are recorded as findings on the row, surfaced in the workspace, never silently dropped and
  never blocking). Failure stays visible (CLAUDE.md §4.3 gate 5).
- **Never block, never substitute.** The loop improves the output or surfaces the problem; it
  never refuses to translate and never swaps in source text on its own.

### 3. Anti-slop as a style contract + deterministic post-check

Add `[translation_profile]` to `project.toml` (pure config, no schema change), emitted as a
`<profile>` block in the prompt:

```toml
[translation_profile]
tone = "literary"            # casual | formal | literary | archaic
dialog_style = "natural"     # natural | stiff | verbose
name_rendering = "first_full_then_short"
tense = "past"
banned_phrases = ["it can't be helped", "as expected of", "to think that"]
```

`banned_phrases` is a **deterministic** check that feeds the **same §2 repair trigger** — slop
is corrected by the same single-pass loop, not by a separate mechanism. The profile is a
*contract* (drives both the prompt and the post-check), not decoration.

**Seed list + soft trigger (Q2).** Weaver ships a **small (~5–8), high-confidence** MTL-calque
seed list (e.g. "it can't be helped", "as expected of", "to think that…") in `core/`. It
applies **only when the project declares `[translation_profile]`**, and is **fully overridable**
(`banned_phrases = []` disables it; a custom array replaces the seed). Unlike the glossary/
character checks (binary, safe), a banned-phrase hit is a **soft trigger**: the repair re-ask
asks the model to *reconsider* the phrasing, never a hard failure — because a flagged phrase can
be legitimate in context. The seed stays deliberately tiny to avoid false positives.

### 4. Recover the discarded signals (free, no extra call)

- **`uncertain_terms`** from every response → insert into `glossary_candidates`
  (`frequency++`), so entity discovery is continuous **without a second model call**. This
  replaces the proposal's "continuous extraction" (#4), which added a call per segment.
- Persist the enforcement outcome (which checks fired, whether repair succeeded) into the
  existing append-only provenance so debugging stays possible.

### 5. Routing seam (declare, do not build yet)

The repair/enforcement re-ask uses the **same engine as `translate`** by default — the segment's
provider is already in hand in `translate_one_segment`, so no new resolver call is needed now. A
future `[routing.repair]` (or `[routing.critic]`) override — routing the repair pass to a
stronger model than bulk translation — is a natural extension of ADR 018 + the new
`resolve_consumer_config` seam, but is **explicitly out of scope here** (Q3: deferred — no
single-caller abstraction ahead of need; adding it later is a config-only, non-breaking change).

**One discipline to keep the seam cheap (Q3):** the enforcement-repair function **takes the
`provider` as a parameter** (it does *not* hardcode the translate provider). That way, switching
the repair pass to a `[routing.repair]` engine later is a one-line feed change, not a refactor.

### 6. Default behavior (resolved)

- **Detection: always on, free** (§1). Violations are always recorded on the segment, so the
  gimmick is gone regardless of the repair switch.
- **Repair re-ask: on by default, switchable** via `[translation] enforce_repair` (default
  `true`). Capped at 1 pass, fires only on violating segments; the repass token cost is counted
  into the segment's usage and shown. Set `false` to keep detection-only (cost-free) behavior.
- **Length is a weak guard, never a primary trigger (Q4).** Forcing length *causes* slop — the
  model pads with filler to hit a ratio, and JP→EN legitimately compresses. So the translate-time
  guard uses a **separate, very loose anti-truncation floor** (empty / catastrophically short
  output only). The existing `[qa] minimum_length_ratio` stays **advisory-only** and is *not*
  reused as a repair trigger. The strong, slop-safe triggers are glossary/character presence
  (binary); length only catches broken output.

## Consequences

**Positive**
- Glossary/character/TM become **binding**, not decorative — directly answers the owner's
  "no-gimmick" requirement, with code-level proof (the checks already exist).
- Anti-slop gets a real lever (deterministic detect → bounded repair), not just prompt wishes.
- Reuses existing primitives (checks, repair scaffold, `complete()`/`translate()`,
  per-task routing) — minimal new surface; honors "prefer existing architecture".
- Cross-chapter *name/term consistency* is largely solved as a side effect (the glossary is
  project-scoped and now enforced), reducing the urgency of the expensive LLM-summary path.

**Negative / costs**
- Extra token + latency cost on violating segments (bounded to one repass each). Visible, but
  real — must be measured against a baseline before default-on is locked.
- Determinism limits: substring presence ≠ semantic correctness (a term can be present but
  misused). Accepted: this ADR raises the floor, it does not claim semantic perfection.
- `banned_phrases` is a blunt instrument; kept optional and per-project.

## Alternatives rejected

1. **Keep advisory-only (status quo).** This *is* the gimmick the owner rejected. No.
2. **Hard-block / refuse to commit on violation.** Breaks the translate flow and the
   "never block, Draft always works" stance (ADR 017 / export philosophy). No.
3. **Unbounded retry until clean.** Violates ADR 018 D9 (no circuit breaker / retry storm)
   and risks token blowups. No — bounded 1-pass only.
4. **LLM-judge every segment (paired comparison / critic model on all).** Expensive, slop-prone
   (the judge hallucinates), and over-engineered for the floor we need. Deferred as a possible
   Phase-D differentiator, not the enforcement mechanism.
5. **Put the loop in the provider.** Violates ADR 014's transport/domain boundary. Enforcement
   stays in the service.

## Resolved decisions (2026-06-16)

1. **Default on/off → split.** Detection always on (free, kills the gimmick); repair re-ask on
   by default but switchable via `[translation] enforce_repair`. (§1, §2, §6)
2. **`banned_phrases` → small shipped seed, soft trigger, override-able**, active only when
   `[translation_profile]` is declared. (§3)
3. **`TaskType.repair` → deferred.** Reuse the segment's provider; the repair function takes
   `provider` as a parameter so a `[routing.repair]` override is a 1-line change later. (§5)
4. **Length-ratio → not a primary trigger.** Reusing `[qa] minimum_length_ratio` is rejected
   (forcing length causes padding-slop); a separate loose anti-truncation floor is used instead.
   Glossary/character presence are the strong triggers. (§1, §6)

These resolutions are the Lead-Orchestrator/Critic recommendation folded into the design; the
owner accepts or amends them at ADR sign-off.

## Next step

On acceptance: open a sprint with an execution plan (§2.3/§2.4), starting with the
enforcement gate + targeted-repair template (the P0 core), then the `[translation_profile]`
contract, then the `uncertain_terms → candidates` recovery. Each slice ships behind the gate
checklist; no cross-chapter summarizer until P0 is proven insufficient with evidence.
