# Weaver Prompt Design

Specification for all LLM prompts used in Weaver MVP-0. This document is the source of truth for what gets sent to the model. Engineers implementing `providers/` and `services/translation.py` must follow this spec.

## Design Principles

1. **Structure over prose.** Use explicit XML-like delimiters, not narrative instructions.
2. **JSON output contract.** All responses parsed as JSON. No free-form prose output from the model.
3. **Fail loudly.** If the model cannot comply with JSON contract, segment is marked `failed` — not silently accepted.
4. **Minimal system prompt.** Instruction token count should be small relative to context. Do not write a 2,000-token system prompt.
5. **Glossary as data, not instruction.** Glossary terms are injected as a structured list, not woven into prose instructions.

---

## Balanced Mode — Full Prompt Spec

### System Prompt (constant across segments)

```
You are a professional literary translator working from Japanese to English.

Rules:
- Translate the text inside <source> tags from Japanese to English.
- Produce natural, readable English that preserves the author's tone and register.
- Do not summarize, paraphrase, or add content not present in the source.
- If a term appears in <glossary>, use the specified English translation exactly.
- Apply the honorific policy specified in <policy>.
- Respond ONLY with a valid JSON object. No explanation. No markdown. No prose outside the JSON.

Response format:
{
  "translation": "<translated text here>",
  "notes": ["<optional translator note>"],
  "uncertain_terms": ["<JP term you were unsure about>"]
}
```

### User Message Template

The user message is assembled per-segment from the following template. All `{variable}` fields are populated by `build_context()` in `services/translation.py`.

```
<policy>
honorifics: {honorific_policy}
</policy>

<profile>
{profile_block}
</profile>

<glossary>
{glossary_block}
</glossary>

<characters>
{characters_block}
</characters>

<context>
{context_block}
</context>

<source>
{source_text}
</source>
```

### Field Definitions

#### `{honorific_policy}`

One of the three literal values:

```
preserve   — keep all honorifics as-is (さん → -san, 様 → -sama, etc.)
localize   — convert honorifics to natural English equivalents where possible
hybrid     — preserve relationship-defining honorifics (様, 殿), localize casual ones (ちゃん, くん)
```

All three values are user-configurable via `[translation] honorifics` in `project.toml`. The template outputs the value verbatim; the LLM interprets the policy string from the definitions above.

#### `{profile_block}` (ADR 019 E3)

Optional project-level **style contract** from the `[translation_profile]` table in `project.toml`. Only the fields the user set are emitted, one `key: value` line each:

```
tone: literary
dialogue: natural
names: first_full_then_short
tense: past
```

Source fields (all optional, free-form — no enum): `tone`, `dialog_style` (emitted as `dialogue`), `name_rendering` (emitted as `names`), `tense`. Parsed by `build_translation_profile()` into a `TranslationProfile` carried on `TranslationContext.profile`.

**Emission rule:** the `<profile>` block is emitted only when at least one *style* field is set (`TranslationProfile.has_style`). If the section is absent, or carries only `banned_phrases` (a gate-only concern, see Enforcement Loop), the block is omitted entirely — prompt output is byte-for-byte unchanged from a project with no profile.

#### `{glossary_block}`

TSV-formatted list of approved glossary terms relevant to the current segment, one per line:

```
{source_term}\t{target_term}\t{category}\t{notes}
```

Example:

```
護衛	bodyguard	role	Use "bodyguard" throughout, not "escort" or "guard"
魔王	Demon King	title	Capitalize as proper title
カイ	Kai	name	Protagonist's name
```

**Filtering rule:** Only inject terms where the source appears as a substring of `normalized_source_text`. Do not inject the entire glossary for every segment — this wastes tokens and degrades model attention.

If no terms match: omit the `<glossary>` block entirely (do not send an empty block).

**Maximum glossary terms per segment:** 20. If more than 20 terms match, prioritize by frequency descending. This is a hard cap to prevent prompt bloat.

#### `{characters_block}` (Sprint 5C)

TSV-formatted list of project characters whose Japanese name appears in the current segment, one per line:

```
{jp_name}\t{en_name}\t{gender}\t{role}\t{notes}
```

Example:

```
エリナ	Elina	Female	Main Heroine	protagonist
魔王	Demon King	Male	Antagonist
```

**Filtering rule:** Only inject characters whose `jp_name` appears as a substring of `normalized_source_text` (same approach as glossary). If none match, omit the `<characters>` block entirely.

**Maximum characters per segment:** 20 (hard cap). Characters are project-scoped (`characters` table, schema v4) and injected so the model renders names consistently across chapters. Optional fields render as empty TSV columns.

#### `{context_block}`

Formatted rolling window of previous segments in the current chapter. Format:

```
[PREV-{N}] {source_text}
→ {translated_text}

[PREV-{N-1}] {source_text}
→ {translated_text}
```

`N` = number of previous segments included (up to 5 at MVP-0). Segments are listed oldest-first so the immediately preceding segment is last.

Example (2-segment window):

```
[PREV-2] 彼は剣を鞘に収めた。
→ He sheathed his sword.

[PREV-1] 「まだ終わりじゃない」とカイは言った。
→ "It's not over yet," Kai said.
```

If the segment is the first in a chapter: omit the `<context>` block.

**Maximum context tokens:** Target ≤ 1,000 tokens for the context block, measured with the CJK-aware estimator (CJK characters ≈ 1 token each, other characters ≈ ¼ token — audit N7; the pre-v0.7.3 flat `chars // 4` estimate undercounted Japanese ~3×). If the rolling window exceeds this due to long segments, truncate to fewer previous segments. Never truncate a segment mid-sentence.

#### `{source_text}`

The `normalized_source_text` field from `BlockIR`. Normalized with `unicodedata.normalize("NFKC", ...)` and half/full-width correction. Not escaped further; the `<source>` delimiter provides structural separation.

---

## JSON Output Contract

Expected response schema:

```json
{
  "translation": "string, required, non-empty",
  "notes": ["string", "..."],
  "uncertain_terms": ["string", "..."]
}
```

Field rules:

| Field | Required | Empty OK | Max length |
|-------|----------|----------|------------|
| `translation` | Yes | No | 8,000 chars |
| `notes` | No | Yes (omit or `[]`) | 3 items, 200 chars each |
| `uncertain_terms` | No | Yes (omit or `[]`) | 10 items |

`notes` is for translator observations (e.g., "Japanese pun does not translate directly"). Stored in `translations.raw_response` for review. Not surfaced in EPUB output.

`uncertain_terms` is for terms the model flagged as ambiguous. Since ADR 019 (E4) each entry is also recorded as a **discovered** glossary candidate for review (`storage.record_uncertain_glossary_candidate`) — see Enforcement Loop §4.

---

## Parse And Repair Flow

```python
def parse_response(raw: str) -> TranslationResponse:
    # Attempt 1: direct JSON parse
    try:
        data = json.loads(raw)
        return validate_schema(data)
    except (json.JSONDecodeError, ValidationError):
        pass

    # Attempt 2: extract JSON from response (model sometimes wraps in markdown)
    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group())
            return validate_schema(data)
        except (json.JSONDecodeError, ValidationError):
            pass

    # Attempt 3: repair prompt
    return send_repair_prompt(raw)
```

### Repair Prompt

Sent as a follow-up message in the same conversation if provider supports it, or as a new single-turn call otherwise:

```
The previous response was not valid JSON. Respond ONLY with a valid JSON object matching this schema:
{
  "translation": "<your translation here>",
  "notes": [],
  "uncertain_terms": []
}

No markdown. No explanation. JSON only.
```

If the repair also fails: segment is marked `failed`. Raw response is stored in `translations.raw_response` for debug. No further retries. The orchestrator moves to the next segment.

> **Two distinct repair paths.** The flow above is the **JSON-validity** repair, internal to the provider transport (`providers/openai_chat.py`) — it fixes malformed output. It is *not* the enforcement repair below, which is a domain-level service concern (ADR 014 boundary). A successful translation can still violate glossary/character/anti-slop constraints; that is what the Enforcement Loop handles.

---

## Enforcement Loop (ADR 019)

Makes the glossary/character database **binding** instead of advisory. Runs in `services/translation.py::translate_one_segment` after a successful (JSON-valid) translation and **before commit**. Pure service logic (`services/enforcement.py`); the provider stays domain-agnostic.

### 1. Detection (E1 — free, always-on)

`evaluate_translation()` deterministically checks the fresh translation, reusing the QA primitives so the translate-time gate and the advisory QA report agree:

- **glossary target present** (`check_glossary_mismatch`) — a matched term's target must appear,
- **character EN-name present** (`check_character_name_missing`),
- **no untranslated-Japanese residue** (`check_untranslated_japanese`, 4+ contiguous JP chars),
- **not catastrophically truncated** — a *loose* floor (target empty or < 0.15× source length). This is **not** `[qa] minimum_length_ratio`: forcing length makes the model pad with filler, which is itself slop.
- **no banned-slop phrase** (E3) — optional, soft.

Detection costs **zero tokens** and runs on every segment regardless of the repair switch, so a violation is always recorded/visible even when repair is off.

### 2. Targeted repair (E2 — bounded 1-pass, switchable)

On violation, and when `[translation] enforce_repair` is true (default), one repair re-ask is issued via the provider's `complete()` primitive, enumerating the specific violations:

```
Revise this ja to en translation.
The previous translation broke the constraints listed below. Produce a
corrected translation that fixes every listed problem and changes nothing
else ...
Constraints that were violated:
- Glossary term '李晨' -> 'Li Chen' matched source but target is absent ...
Source (ja): ...
Previous translation (fix only what the constraints require): ...
```

The reply is re-parsed and re-validated **once**. The repaired attempt is committed **only if it is not strictly worse** than the original (a fix that regressed is discarded). Bounded to one pass — no loop, no circuit breaker (ADR 018 D9). Repair tokens are counted into the segment's usage.

**Never blocks, never substitutes.** Any repair failure (provider error, unparseable output, or a provider that does not implement `complete()`) keeps the good primary translation; residual violations remain visible in the QA report. Translate-time only (Gate B1).

### 3. Style contract + anti-slop (E3)

`[translation_profile]` drives both the `<profile>` prompt block (above) *and* a deterministic `banned_phrases` check. A banned-phrase hit is a **soft** trigger (asks the model to reconsider the phrasing) that feeds the same E2 repair — never a hard block, since a flagged phrase can be legitimate. The shipped seed (`core/slop_seed.py`) applies only when `[translation_profile]` is declared; `banned_phrases = []` disables it, a custom array replaces it.

### 4. Free entity discovery (E4)

After commit, each `uncertain_terms` entry the model self-reported is recorded as a **discovered** glossary candidate (`storage.record_uncertain_glossary_candidate`): idempotent (skips already-approved terms, bumps an existing *pending* candidate's frequency, never resurrects a handled one). No extra model call — it recovers a signal the response already carries. The user reviews discoveries in the existing candidates page.

---

## Glossary Suggestion Prompt (Used During `weaver init`)

During glossary candidate extraction, each candidate gets one LLM call to suggest an initial English target. This is a separate, cheaper prompt.

### System Prompt

```
You are a Japanese-to-English literary translator. Given a Japanese term from a novel, suggest the most appropriate English translation.
Respond ONLY with a valid JSON object. No explanation.

Response format:
{
  "target": "<suggested English translation>",
  "category": "<one of: name, title, place, skill, item, honorific, role, other>",
  "notes": "<brief translator note, or empty string>"
}
```

### User Message

```
Term: {source_term}
Context examples:
{example_sentences}
```

`example_sentences` = up to 3 sentences from the corpus where the term appears, selected at random. Maximum 300 chars total.

### Response Handling

- If valid JSON: populate `glossary_candidates` table with suggested `target`, `category`, `notes`.
- If invalid JSON after one repair attempt: store candidate with `target = null`, `category = "other"`, `notes = "LLM suggestion failed"`.
- Candidate status remains `pending` in all cases. User must approve.

**Batch strategy:** Send suggestions in batch if the provider supports it (e.g., use multiple simultaneous calls or provider batch API). At MVP-0, send serially — one call per candidate. Add concurrency in MVP-1 when rate limits are understood.

---

## Prompt Versioning

Prompt templates are code. They live in `src/weaver/providers/templates/`:

```
src/weaver/providers/templates/
├── balanced_system.txt
├── balanced_user.jinja2
├── repair.txt
├── glossary_suggestion_system.txt
└── glossary_suggestion_user.jinja2
```

Use Jinja2 for templates with variables. The `{variable}` notation in this document is for readability; actual implementation uses `{{ variable }}` Jinja2 syntax.

**Version tracking:** When a prompt template changes, the old version is moved to `templates/archive/v{N}/`. The `schema_version` in `project.toml` and DB must be bumped when a prompt change affects output semantics, because previously-translated segments may become inconsistent.

This is not automated. The maintainer makes this call when a breaking prompt change ships.

---

## Token Budget

Target token counts per segment translation call:

| Component | Target tokens | Hard cap |
|-----------|---------------|----------|
| System prompt | ~120 tokens | 200 tokens |
| Policy block | ~10 tokens | 20 tokens |
| Glossary block | ~60 tokens | 200 tokens (20 terms × ~10 tokens each) |
| Context block | ~700 tokens | 1,000 tokens |
| Source segment | ~150 tokens | 1,000 tokens |
| **Total input** | **~1,040 tokens** | **~2,420 tokens** |
| Output (translation) | ~200 tokens | 1,500 tokens |

If a source segment exceeds 1,000 tokens (rare for prose paragraphs; possible for dense passages), the segment is flagged during `weaver init` with a warning. It is still translated but the context window may be compressed to stay under provider limits.

Provider context limits:
- Ollama models (qwen3:14b): 32k context — no problem at these sizes.
- DeepSeek-chat: 64k context — no problem.

These budgets exist to control cost and latency, not to work around context limits.

---

## Model-Specific Notes

> **Historical (pre-ADR 018).** Since v0.7.2 there is **one** transport — `openai_chat` (+ `fake`) — and a project routes to a registered **connection** + free-form model id (`[routing.<task>]`, ADR 018). The native Gemini/Ollama clients and `google-generativeai` were removed; Gemini/Ollama are reached as OpenAI-compatible connections. The per-model tuning notes below are kept for reference; they no longer map to distinct provider classes.

### Ollama / qwen3:14b

- Use `/api/generate` endpoint with `stream: false`.
- Set `temperature: 0.3` for translation (low but not zero — zero can produce repetitive output on JP text).
- Set `top_p: 0.9`.
- Do not set `format: "json"` in the Ollama API call — some models ignore JSON formatting when this flag is set; rely on prompt-level JSON instruction instead.

### DeepSeek-chat

- Use OpenAI-compatible `/v1/chat/completions` endpoint.
- Set `temperature: 0.3`.
- DeepSeek supports `response_format: {"type": "json_object"}` — use it as a second layer of enforcement.
- Model: `deepseek-chat` (not `deepseek-coder`).

### Gemini Flash (`gemini-1.5-flash`)

- Use `google-generativeai` SDK, `GenerativeModel("gemini-1.5-flash")`.
- Set `generation_config={"temperature": 0.3, "response_mime_type": "application/json"}` — Gemini natively supports JSON-only response mode.
- Free tier: 15 requests/minute, 1 million tokens/day — sufficient for serial translation of a full novel.
- Rate limit handling: 429s are retried with backoff by the OpenAI SDK transport within the explicit `[provider] max_retries` budget (default 2 — v0.7.3 M3, audit N2); once exhausted the segment is marked failed.
- **Recommended first-choice for hardware-limited developers and users who want zero-cost translation.**

### FakeProvider

- Returns `{"translation": "[FAKE] {source_text}", "notes": [], "uncertain_terms": []}` by default.
- Configurable pattern: `FakeProvider(pattern="TRANSLATED: {source}")`.
- Configurable failure rate: `FakeProvider(fail_rate=0.1)` — fails 10% of segments to test retry/failed logic.
- Never makes network calls.
- **Primary tool for all development and CI.** Use this before touching any real provider.

---

## Prompt Quality Evaluation

How to assess whether the prompt is working:

1. **Glossary consistency test.** Translate a 5-chapter fixture where a term appears 20+ times. Count how many times the approved glossary target appears vs. the term's frequency in source. Target: ≥ 90% adherence.

2. **Honorific retention test.** Translate a scene with 5 different honorifics. Verify in output (`preserve` mode): all honorifics appear in romanized form.

3. **JSON compliance rate.** Run 100 segments through the provider. Count segments requiring repair, segments failing even after repair. Target: ≥ 95% direct parse, ≤ 2% total failure rate.

4. **Length ratio check.** JP to EN typically expands by 1.2–2.0x in character count. Segments below 0.3x are caught by QA. Spot-check 10 segments manually for quality beyond that.

These tests are manual at MVP-0. `weaver bench` command is deferred to MVP-1 once a fixture corpus is established.
