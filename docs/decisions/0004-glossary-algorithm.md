# 0004: Glossary Candidate Extraction And Review

Date: 2026-05-19
Status: accepted

## Context

A long novel uses character, place, skill, and world-term names hundreds of times each. Per-segment LLM calls drift on these surface forms (護衛 becomes "escort" in chapter 3 and "bodyguard" in chapter 7) — that is the single loudest pain point in MTL forums. Manual extraction does not scale past a few chapters. Pure LLM-suggested glossaries hallucinate. Some users (notably on Windows) cannot install MeCab/fugashi without a separate binary step and would be blocked if tokenization were mandatory. A bad approved glossary entry must not silently corrupt thousands of segments.

## Decision

Implemented in [src/weaver/services/glossary.py](../../src/weaver/services/glossary.py). Per project, at `weaver init` time:

1. **Tokenize.** Optional `fugashi` proper-noun pass when MeCab is available; deterministic regex fallback otherwise. Regex covers katakana runs (≥ 2 chars, optional `たち`), honorific patterns (`Xさん` / `Xちゃん` / `X様`), and CJK runs (2–8 chars). If no candidates surface, a single-term fallback drawn from the document title prevents an empty TSV.
2. **Filter.** Keep terms with frequency ≥ 2 across the document **or** present in any chapter title.
3. **Cluster.** Collapse `たち` suffix to root form so `護衛` and `護衛たち` share one candidate.
4. **Examples.** Capture up to two source-text sentences per candidate during the same pass for the review UX.
5. **Persist.** Write rows to `glossary_candidates` (SQLite) and mirror to `glossary_candidates.tsv` with `status='pending'`.

Review surface (`weaver glossary review`) actions: `[a]pprove`, `[e]dit`, `[r]eject`, `[s]kip`, `[u]ndo`, `[q]uit`. Approved/edited candidates flow into `glossary_terms`. Translation pre-filters approved terms by substring match against `normalized_source_text`, capped at 20 per segment.

**Conflict guard:** two approved candidates with different `target` values for the same `source` halt `weaver translate` with exit code 6 before any provider call.

LLM-suggested initial targets (PRD §6 step 6) are deferred — the review screen offers the source itself as the default target.

## Consequences

**Easier:** Deterministic baseline runs anywhere Python runs; Windows users not blocked. The TSV mirror lets power users batch-edit in `$EDITOR` and re-sync. Conflicts get caught once at the start of `translate`, not per-segment. Approved terms reach prompts via a clearly bounded surface-match filter — no fuzzy matching, no model-side glossary injection.

**Harder:** Regex fallback produces noisy candidates the user must reject. Variant clustering is suffix-only — prefix and honorific stripping are out of scope. No LLM-suggested initial targets at MVP-0, so the translator types every English target by hand. The 20-term-per-segment cap is fixed; very name-dense segments may silently lose the 21st term until the user re-orders the glossary.
