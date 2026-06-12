# Sprint R — AI Glossary-Target Suggestion (Design Spec)

> **Status:** Approved design (maintainer, 2026-06-12). Feeds ADR `014` + the Sprint R
> implementation plan. Supersedes nothing; it re-introduces — done properly — the
> deliberately-removed dead `Translate target with AI` stub (`test_ui_glossary.py::test_glossary_page_has_no_dead_ai_stub`).
> **Companion ADR:** [`docs/decisions/014-provider-complete-primitive-and-glossary-suggestion.md`](../../decisions/014-provider-complete-primitive-and-glossary-suggestion.md)

## 1. Problem & Pain (anti-slop gate 1)

Reviewing glossary candidates means typing an English `target` for each pending
Japanese source term — potentially hundreds per novel. For obscure or katakana terms
the translator wants a grounded starting point. The CLI already shows example sentences
per candidate (`_print_candidate(examples=...)`, `cli/main.py:1155`); Sprint Q (#3)
brought that to the web (`examples_for_source`). The next friction is the target itself.

**Feature:** an explicit, on-demand **"Suggest with AI"** button per pending candidate
that proposes an editable EN target, grounded in the term + its example sentences, using
**the provider the user has already configured**. The suggestion only pre-fills the
existing editable field — the human still approves.

This is the natural #4 follow-on to Sprint Q's #2 (terms search/pagination) and #3 (lazy
examples). It is **not** a segment-editor suggestion (that overlaps `generate_candidate`)
and **not** a chat/agent surface.

## 2. Provider flexibility (hard requirement)

**Weaver must never assume or hardcode a provider vendor.** There is no hidden default
DeepSeek/Gemini/Ollama. The suggestion feature uses **exactly** the `[provider]` block the
user configured (`provider.type`, `model`, `base_url`, `api_key_env`) via the existing
`build_provider()` factory — identical to how `services/candidate_generation.py` already
works. `build_provider()` raises `ConfigError` when `provider.type` is absent
(`providers/registry.py:53`); the feature inherits that. OpenAI-compatible/custom
endpoints work through the existing `type = "custom"` path (user-supplied `base_url` +
`api_key_env`). The feature adds **no** provider-selection logic of its own.

## 3. Architecture — three layers, clean boundaries

```
UI (HTMX)         POST /ui/projects/{name}/glossary/candidates/{id}/suggest
   │                  → returns the edit-form fragment, target pre-filled + cost line
   ▼
Router            ui_admin.py: thin adapter; maps WeaverError → in-fragment error
   │
   ▼
Service (domain)  services/glossary_suggestion.py
   │  - loads candidate (source, category) + ≤N example sentences (read-only, reuses
   │    glossary_review._segment_examples from #3)
   │  - builds the term-suggestion PROMPT (domain knowledge lives HERE, never in providers)
   │  - build_provider(config) → healthcheck → provider.complete(prompt) → parse+validate
   │  - returns GlossarySuggestion(target, provider, model, input_tokens, output_tokens)
   │  - NO DB writes (ephemeral)
   ▼
Provider (transport, domain-agnostic)
      base.LLMProvider.complete(prompt, *, system=None, max_output_tokens) -> Completion
      implemented by deepseek / gemini / ollama / fake  (custom reuses the deepseek engine)
```

### 3.1 Provider layer — the `complete()` primitive

- New value type `providers/types.py::Completion`:
  `@dataclass(frozen=True) text: str; input_tokens: int | None; output_tokens: int | None; raw_response: str`.
- New abstract method on `base.LLMProvider`:
  `complete(self, prompt: str, *, system: str | None = None, max_output_tokens: int) -> Completion`.
- **`complete()` is a domain-agnostic transport primitive.** It returns the model's text
  completion + token usage. It carries **no** glossary/translation knowledge and is **not**
  an escape hatch for arbitrary AI features — any future caller must keep its domain prompt
  in a service (enforced by review + the ADR). It is justified now by exactly one caller;
  it is the honest generic primitive (not a `suggest_glossary_target` method, which would
  leak glossary domain into the provider layer and violate §4.2 layer boundaries).
- Implementations:
  - `deepseek.py` (also serves `custom`): reuse the existing `_chat_completion` engine
    (which already requests `response_format=json_object`); parse `prompt_tokens` /
    `completion_tokens`. Because the engine is json-mode, the **prompt must contain the
    word "json"** (json-mode-strict endpoints reject otherwise — see the healthcheck note
    at `deepseek.py:114`). The §4 suggestion prompt satisfies this.
  - `gemini.py`, `ollama.py`: plain-text completion with their usage fields
    (`prompt_token_count`/`candidates_token_count`, `prompt_eval_count`/`eval_count`).
  - `fake.py`: **deterministic** — returns a canned, parseable JSON target derived from the
    prompt/seed so CI never calls a live model.

### 3.2 Service layer — `services/glossary_suggestion.py`

```python
@dataclass(frozen=True)
class GlossarySuggestion:
    target: str
    provider: str
    model: str
    input_tokens: int | None
    output_tokens: int | None

def suggest_glossary_target(
    project_toml: Path, candidate_id: int, *, cwd: Path | None = None,
    provider: LLMProvider | None = None,  # injectable for tests
) -> GlossarySuggestion: ...
```

Flow: load `[provider]` config → `build_provider` (or injected) → `healthcheck()`
(`ProviderUnavailable` if down) → read-only load the candidate's `source` + `category` and
≤`EXAMPLE_LIMIT` example sentences → build the prompt → `provider.complete(prompt,
system=..., max_output_tokens=SMALL)` → parse strict JSON `{"target": "..."}` → **validate**
(§5) → return `GlossarySuggestion`. No writes. No auto-approve.

### 3.3 Prompt (domain, in the service or `providers/prompts.py`)

- A dedicated term-suggestion prompt + `GLOSSARY_SUGGEST_PROMPT_VERSION` constant.
- Instructs: given the JP `source`, optional `category`, and example sentences, return a
  **strict minimal JSON object `{"target": "..."}`** and nothing else — a concise glossary
  target (a term/short noun phrase), not a sentence, not prose, not multiline. Contains the
  literal word "json" (json-mode requirement).
- The system message states it is a translation-glossary assistant for `source_lang →
  target_lang` (pulled from the project record, never hardcoded EN).

### 3.4 UI / data flow

- `_glossary_candidates.html` pending rows: the target `<td>` (the existing
  `Save & approve` edit form) is wrapped in a swappable slot `#cand-edit-{{ c.id }}`,
  rendered from a new partial `partials/_glossary_candidate_edit.html`.
- Add a **"Suggest with AI"** button labelled with a `(LLM call)` hint → cost is visible
  **before** the click (gate 6a). `hx-post .../candidates/{id}/suggest`,
  `hx-target="#cand-edit-{id}"`, `hx-swap="innerHTML"`.
- Success: the router re-renders `_glossary_candidate_edit.html` with the `target` input
  pre-filled (`value="{{ suggestion.target }}"`) + a provenance line
  `via {{ provider }} · {{ model }} · ~{{ in+out }} tokens` (gate 6b). The translator edits
  if needed and clicks the existing **Save & approve** (gate 4 — nothing auto-persists).
- The button is rendered **only for pending rows**; actioned rows (the JS rewrites them to
  a confirmation) carry no Suggest button.

## 4. Error handling (anti-slop gate 5)

- `ProviderUnavailable` (key missing / network) → fragment shows
  `AI suggestion unavailable: <reason>` with the next-step; the input is **unchanged**.
- `ProviderError`/`ProviderResponseError`/`ProviderTimeout` mid-call → fragment shows the
  error; input unchanged; **no** retry-forever, **no** silent substitution.
- Empty / non-JSON / multiline / over-length / sentence-shaped completion → rejected by §5
  validation → fragment shows `AI returned no usable suggestion` (never fills blank/garbage).
- Failures never auto-approve, never persist, never get logged with secrets.

## 5. Output validation (anti-slop gate 3 verifiability; user notes 3 & 4)

The service **rejects** a completion that is not a clean glossary target:

1. Parse strict JSON; require a single `"target"` string key. Reject on parse failure or
   missing key.
2. `target = raw["target"].strip()`. Reject if **empty**.
3. Reject if **multiline** (contains `\n`).
4. Reject if **too long** — over `MAX_TARGET_CHARS` (e.g. 80) — or **sentence/paragraph
   shaped** (heuristic: ends with sentence punctuation `.!?。！？` and/or exceeds a word/char
   cap). A glossary target is a term, not prose.

A rejected completion raises a `WeaverError` (e.g. `GlossarySuggestionError`) surfaced per
§4 — it is never shown to the user as a usable suggestion. (The human still reviews the
accepted suggestion before approving — output is verifiable, which is what licenses the LLM
under gate 3.)

## 6. Gate B1 — no provider call on render (user note 6)

The glossary page render and the terms/candidates fragments **never** call a provider.
`complete()` runs **only** inside the `POST .../suggest` handler, on explicit user click.
This is asserted by test (spy `build_provider`/`complete` during a `GET /ui/.../glossary`
render → zero calls; called exactly once on POST).

## 7. Anti-slop six-gate mapping (§4.3)

| Gate | Satisfied by |
| --- | --- |
| 1 real pain | typing targets for hundreds of candidates; CLI/web examples evidence the workflow |
| 2 falsifiable spec | button → editable suggestion; tokens shown; failure shown; §5 validation |
| 3 deterministic-where-possible | term target is non-deterministic by nature; **LLM only**, and output is human-verified before approve |
| 4 user override | suggestion only fills the editable field; human must Save & approve |
| 5 failure visible | §4 — all errors shown inline, never silent/substituted/retry-forever |
| 6 cost visible | `(LLM call)` hint before; `provider · model · ~tokens` after |

## 8. Testing

- **Provider:** `fake.complete()` deterministic + parseable; deepseek/gemini/ollama
  `complete()` unit-tested with a **mocked client** (mirror existing `translate` tests) —
  assert the prompt is sent and usage parsed. Mock the external boundary only.
- **Service:** FakeProvider → grounded target (spy captures the prompt → contains the term
  + an example sentence); healthcheck-fail → `ProviderUnavailable`; provider raises →
  `ProviderError` surfaced; §5 validation rejects empty / multiline / over-long /
  sentence-shaped / non-JSON completions (one test each).
- **Router (UI):** POST suggest → 200 fragment with pre-filled value + cost line;
  provider-fail → error shown, no silent success; **Gate B1** spy test; secret-grep
  regression (rendered HTML carries env-var **name** only, never a key value);
  no-suggest-button on actioned rows.
- Full suite + ruff + pyright green at the stage gate.

## 9. Non-goals (user note 7 — scope fence)

No persistence / schema migration (ephemeral). No "Suggest all" batch (one at a time,
on-demand — caps runaway cost). No confidence score (just target + provider + model +
tokens). No new config flag. No provider expansion / hardcoded vendor. No auto-approve. No
segment-editor suggestion. `desktop/` untouched. No change to the export gate, QA, or any
read path's Gate-B1 posture.

## 10. New / changed surfaces

| Layer | File | Change |
| --- | --- | --- |
| Provider | `providers/types.py` | + `Completion` |
| Provider | `providers/base.py` | + abstract `complete()` |
| Provider | `providers/deepseek.py` (+`custom`), `gemini.py`, `ollama.py`, `fake.py` | implement `complete()` |
| Prompt | `providers/prompts.py` | + term-suggestion prompt + `GLOSSARY_SUGGEST_PROMPT_VERSION` |
| Service | `services/glossary_suggestion.py` | new — `suggest_glossary_target` + `GlossarySuggestion` + validation |
| Router | `api/routers/ui_admin.py` | + `POST .../candidates/{id}/suggest` |
| Template | `partials/_glossary_candidate_edit.html` | new — swappable edit-form slot |
| Template | `partials/_glossary_candidates.html` | wrap edit form in `#cand-edit-{id}`, add Suggest button |
| Docs | `docs/decisions/014-*.md`, `CLAUDE.md` §2, `AGENTS.md` | ADR + sprint status |

## 11. Open implementation questions (resolved at plan time)

- Exact placement of the term-suggestion prompt (in `providers/prompts.py` next to the
  translation prompts, vs service-local) — prefer `providers/prompts.py` for consistency,
  but the **prompt content is domain** and must not imply the provider knows glossary
  semantics; the provider only receives an opaque string.
- `complete()` json-mode handling per provider (deepseek forces json_object; gemini/ollama
  plain text + service-side parse) — covered in §3.1; nailed down in the plan.
