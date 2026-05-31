# Translation Pipeline

How a source document becomes a translated, consistency-checked output. Steps marked **(planned)** are MVP gaps (ADR 003 / [MVP_SCOPE.md](MVP_SCOPE.md)); the rest exist today. Prompt specifics: [PROMPT_DESIGN.md](PROMPT_DESIGN.md).

```
import → segment → [per pending segment:] build context → inject glossary
       → inject character context → TM lookup (reuse exact match, else AI)
       → AI call → parse/repair → save (1 segment = 1 txn) + save to TM
       → edit/revision → QA validate → export
```

## 1. Import
`readers/epub.py` parses an EPUB into a `DocumentIR` (chapters → blocks). **EPUB only today**; TXT/HTML readers are **(planned)**. Novel→Chapter exists; the **Volume tier is (planned)**.

## 2. Segmentation
`core/segment.py` splits blocks into translation segments with **deterministic IDs** (stable across re-init via source hashing) so runs are resumable and stale segments are detectable. Segments + glossary candidates are written to `weaver.db` (`storage/segments.py`, `storage/glossary.py`).

## 3. Context building
`services/translation.py` builds a rolling context window (prior segments / chapter context) for each pending segment so translations stay coherent across a chapter.

## 4. Glossary injection
Approved glossary terms (`glossary.tsv`, curated via `glossary_review`) are injected into the prompt, and the model is instructed to honor them. This is the primary consistency lever today. Unresolved approved-term conflicts halt translate with exit code 6.

## 5. Character context
A project-scoped character database (JP name, EN name, gender, role, notes) injected into the prompt to keep character names/voice consistent across chapters. `storage/characters.py` + `services/characters.py`; `build_context` filters by `jp_name` substring and renders a `<characters>` block (PROMPT_DESIGN.md). FastAPI CRUD: `GET/POST/PATCH/DELETE /projects/{name}/characters[/{jp_name}]`.

## 6. Translation memory lookup
Before the AI call, `translate_one_segment` looks up the segment's `source_hash` in a **project-scoped** `translation_memory` store (`storage/translation_memory.py`). On an **exact** match it reuses the stored target, records an audit-able attempt tagged provider/model `memory`, and **skips the provider** (0 token cost); on a miss it calls the model and saves the result back. **Exact match only** — no fuzzy/semantic. **Manual edits are the source of truth**: a manual save writes to TM and provider saves never overwrite a `manual` entry. Explicit retranslate (`retranslate_non_manual` / `force_selected`) bypasses the lookup (so it is not a silent no-op) but still refreshes provider entries. Reuse count surfaces as `reused_from_memory` in CLI/web/API run summaries. Read/manage: `GET /projects/{name}/memory` (entries + `total_entries`/`exact_hits`/`reused_from_memory`), `DELETE /projects/{name}/memory/{source_hash}` (removes only the TM row — history, manual edits, glossary, and characters are untouched).

## 7. AI call
The configured provider (`providers/registry.py` → adapter) translates the segment. `providers/parser.py` parses and repairs the JSON response. Honorific handling (`preserve` / `localize` / `hybrid`) comes from `[translation] honorifics`.

## 8. Save
Each segment translation is committed in **its own transaction** (`storage/translations.py`) — interrupt-safe and resumable. Statuses: pending / done / failed / stale / manual.

## 9. Edit / revision
`services/manual_edit.py` overrides a segment via `$EDITOR` (CLI) or per-segment (web). Manual status survives `--retry-failed`. A two-column workspace with **auto-save + revision history is (planned)**.

## 10. QA validate
`qa/checks.py` runs six deterministic checks (`services/qa.py`); `--json` emits a stable shape (`schema_version: 1`, [api/qa_json_schema.md](api/qa_json_schema.md) if present). A critical finding exits 1. `--epub` optionally runs EPUBCheck.

## 11. Export
`services/export.py` writes per-chapter **Markdown** review files; `renderers/epub.py` writes the translated **EPUB** (xpath block rewrite, nav fallback). **TXT / HTML / DOCX export is (planned)** (EPUB is the priority format).

## Determinism note (anti-slop)
Everything except the model call is deterministic. The LLM is used only where determinism is impossible, its output is verifiable (QA), and the user can override (manual edit, glossary). See [AI_SLOP_PREVENTION.md](AI_SLOP_PREVENTION.md).
