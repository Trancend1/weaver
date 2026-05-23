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

<glossary>
{glossary_block}
</glossary>

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

**Maximum context tokens:** Target ≤ 600 tokens for the context block. If the rolling window exceeds this due to long segments, truncate to fewer previous segments. Never truncate a segment mid-sentence.

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

`uncertain_terms` is for terms the model flagged as ambiguous. Stored; surfaced in `weaver validate` as informational warnings.

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
| Context block | ~300 tokens | 600 tokens |
| Source segment | ~150 tokens | 1,000 tokens |
| **Total input** | **~640 tokens** | **~2,020 tokens** |
| Output (translation) | ~200 tokens | 1,500 tokens |

If a source segment exceeds 1,000 tokens (rare for prose paragraphs; possible for dense passages), the segment is flagged during `weaver init` with a warning. It is still translated but the context window may be compressed to stay under provider limits.

Provider context limits:
- Ollama models (qwen3:14b): 32k context — no problem at these sizes.
- DeepSeek-chat: 64k context — no problem.

These budgets exist to control cost and latency, not to work around context limits.

---

## Model-Specific Notes

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
- Rate limit handling: on 429, backoff 60 seconds and retry. Mark segment failed only after `max_retries` exhausted.
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
