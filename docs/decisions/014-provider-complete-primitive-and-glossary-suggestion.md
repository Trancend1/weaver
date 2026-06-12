# ADR 014 — Provider `complete()` Primitive + On-Demand Glossary Target Suggestion

## Status

Accepted (maintainer + Lead Orchestrator, 2026-06-12). Governance gate of **Sprint R —
AI glossary-target suggestion** (feature #4). Design spec:
[`2026-06-12-glossary-ai-target-suggestion-design.md`](../superpowers/specs/2026-06-12-glossary-ai-target-suggestion-design.md).

## Context

The glossary candidate-review flow requires a human to type an English `target` for each
pending Japanese source term. Sprint Q added terms search/pagination (#2) and lazy example
sentences (#3). Feature #4 adds an explicit, on-demand **"Suggest with AI"** button that
proposes an editable target — re-introducing, done properly, the deliberately-removed dead
`Translate target with AI` stub (`test_ui_glossary.py::test_glossary_page_has_no_dead_ai_stub`).

Two architectural questions had to be settled before building:

1. **How does a provider produce a suggestion for a short term?** The only provider entry
   point today is `LLMProvider.translate(TranslationRequest) -> TranslationResponse`
   (`providers/base.py:35`), whose contract is a **prose segment** — JSON-schema parse,
   `notes`/`uncertain_terms`, repair pass, `balanced-1.0` prompt. A glossary term is not a
   segment. Reusing `translate()` would corrupt that contract, pollute provenance, and tend
   to return a full sentence rather than a term.
2. **Where does AI-feature plumbing live without leaking domain into the transport layer or
   assuming a vendor?** Weaver's locked stack forbids hidden architecture and the §4.2 layer
   rule keeps shared/core framework- and domain-agnostic.

## Decision

### 1. Add a domain-agnostic `complete()` primitive to the provider protocol

Extend `LLMProvider` with one abstract method:

```python
def complete(self, prompt: str, *, system: str | None = None,
             max_output_tokens: int) -> Completion
```

returning `Completion(text, input_tokens, output_tokens, raw_response)`. It is implemented
by every registered provider (`deepseek` — also serving `custom`, `gemini`, `ollama`,
`fake`). `fake.complete()` is deterministic so CI never calls a live model.

`complete()` is a **transport primitive**: it returns the model's text completion plus token
usage and carries **no** glossary, translation, or any other domain knowledge.

- **It is not an escape hatch.** Every AI feature's prompt and output validation stay in a
  **service**. A provider must never gain a domain-specific method (e.g.
  `suggest_glossary_target`) — that would leak domain into the transport layer and violate
  §4.2. `complete()` receives an opaque string and returns an opaque string.
- We reject reusing `translate()` for terms: the segment contract (schema/repair/provenance)
  must stay intact and term≠segment.
- We reject a glossary-specific provider method: single-caller + layer-boundary violation.

### 2. No hidden default provider — vendor-agnostic, fully config-driven

The suggestion feature selects **no** provider of its own. It instantiates the provider via
the existing `build_provider(data["provider"])` factory (`providers/registry.py:38`), which
**requires** `provider.type` from the user's `[provider]` block and raises `ConfigError`
when absent (registry.py:53). `provider`, `model`, `base_url`, and `api_key_env` all come
from user configuration or the existing cockpit/CLI provider flow — never hardcoded, never
defaulted to DeepSeek/Gemini/Ollama. OpenAI-compatible / custom endpoints work through the
existing `type = "custom"` path (user-supplied `base_url` + `api_key_env`; the key value is
never read from config). This mirrors `services/candidate_generation.py` exactly. Weaver
must never assume a vendor.

### 3. Ephemeral suggestion, strict minimal output

The service `services/glossary_suggestion.py` builds the domain prompt (term + category +
≤N example sentences from #3's `_segment_examples`), calls `complete()`, and parses a
**strict minimal JSON object `{"target": "..."}`**. The suggestion is **ephemeral**: it only
pre-fills the existing editable target field. There is **no** persistence and **no** schema
migration — the human's `Save & approve` (the existing flow) is what persists. The service
**rejects** empty, multiline, over-length, or sentence/paragraph-shaped output (a glossary
target is a term, not prose). **No confidence score** is added — the UI shows target,
provider, model, and token usage only.

### 4. On-demand only — Gate B1 and cost control

A provider is called **only** inside the `POST .../candidates/{id}/suggest` handler on an
explicit user click — **never** on any page/fragment render (Gate B1; asserted by a spy
test). One suggestion per click; there is **no "Suggest all" batch** (caps runaway cost).
Cost is visible before (`(LLM call)` hint) and after (`provider · model · ~tokens`).

The feature satisfies all six anti-slop gates (§4.3): see the design spec §7. Gate 3 (LLM
only when determinism is impossible AND output is verifiable) holds: a novel term's target
cannot be derived deterministically, and the human reviews/edits every suggestion before it
is ever approved.

## Consequences

Improves: a grounded, editable target suggestion that respects the user's chosen provider;
a clean, reusable transport primitive with correct layer boundaries; zero schema churn; the
segment `translate()` contract stays untouched.

Tradeoffs:

- The provider protocol grows a second method; four implementations must stay in sync (an
  abstract method makes a missing implementation a load-time failure, not a silent gap).
- `complete()`'s genericity invites future misuse. Mitigation: this ADR fixes the rule —
  **domain prompts live in services; providers stay domain-agnostic** — and review enforces
  it. Adding a domain method to a provider is an ADR-level change.
- Suggestion is not persisted, so there is no per-suggestion cost ledger. Accepted: the
  decision that persists (approve/edit) already records the term; a suggestion ledger would
  need its own migration and is explicitly out of scope (re-open here if cost auditing of
  rejected suggestions ever becomes a requirement).

## Related Files

- `src/weaver/providers/base.py` (`LLMProvider` + new `complete()`), `providers/types.py`
  (`Completion`), `providers/{deepseek,gemini,ollama,fake}.py` (implementations),
  `providers/registry.py` (`build_provider` — vendor-agnostic factory),
  `providers/prompts.py` (term-suggestion prompt + `GLOSSARY_SUGGEST_PROMPT_VERSION`).
- `src/weaver/services/glossary_suggestion.py` (new — `suggest_glossary_target`,
  `GlossarySuggestion`, output validation), `services/glossary_review.py`
  (`_segment_examples` grounding, from Sprint Q #3).
- `src/weaver/api/routers/ui_admin.py` (`POST .../suggest`),
  `templates/partials/_glossary_candidate_edit.html` + `_glossary_candidates.html`.
- ADR [`009`](009-htmx-first-fastapi-stable-tauri-sidecar-ready.md) (HTMX-first, no SPA),
  ADR [`010`](010-persistent-job-core-sqlite-in-process.md) (no external queue — the
  suggestion is a synchronous on-demand call, not a job), `CLAUDE.md` §3 (locked stack /
  provider table), §4.3 (anti-slop gates).
