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
Two QA surfaces share the same deterministic per-segment checks in `qa/checks.py` — there is **no parallel QA system** (ADR 008). Both are **read-only, deterministic, report-first**: they never mutate translations, never call a provider, and never auto-fix.

- **CLI `weaver validate`** (`services/qa.py`) — the legacy project-wide check. Six checks; `--json` emits a stable shape (`schema_version: 1`). A `critical` finding exits 1. `--epub` optionally runs EPUBCheck. **Unchanged by Phase B.**
- **Cockpit QA (Phase B)** — scope-aware reports for **novel / volume / chapter** (`services/translation_qa.py`, `analyze_novel`/`analyze_volume`/`analyze_chapter` → `QAReport`). Reuses the `qa/checks.py` primitives and adds rules for character-name consistency, repeated translations, and chapter-level *untranslated / fallback-heavy / mixed-status* (new pure modules `qa/consistency_checks.py`, `qa/scope_checks.py`). Surfaced as JSON (`GET …/qa`), UI report pages, and an **advisory** pre-export warning. See [COCKPIT_WORKFLOW.md](COCKPIT_WORKFLOW.md).

**Severity is `info | warning | critical`** in both surfaces (ADR 008); the cockpit UI may *label* `critical` as "Error" for presentation only — the wire value stays `critical`. The cockpit "fallback-heavy" rule reuses the exporter's own publishable rule, so QA and export never disagree about what counts as published.

## 10b. Batch (chapter / volume / novel)
A batch runs the per-segment pipeline above across many chapters under **one trackable job**. `services/batch_translate.py` plans once — provider built + healthchecked a **single time**, glossary + characters loaded once — then runs chapter by chapter via the existing `run_translation` (no translation logic is duplicated). Scope resolves to chapters in **deterministic reading order**: `chapter` → one chapter; `volume` → that volume's chapters (`spine_order`); `novel` → all chapters (`volume_order`, then `spine_order`). An empty scope is **valid** (a `done(0)` result), not an error.

Per-chapter `mode` is inherited from the chapter pipeline (`skip_existing` default; `retranslate_non_manual`; `force_selected`) — **TM semantics and manual protection are unchanged**. Aggregate counters: `chapters_total`/`chapters_done`, `segments_total`, `translated`, `reused_from_memory`, `skipped`, `failed`, plus per-chapter outcomes and timing. **Invariant:** `translated` *includes* `reused_from_memory` (a TM hit is a success), so on full completion `translated + failed == segments_total` and `reused_from_memory <= translated`; `skipped` (mode-excluded segments) is reported separately and is **not** part of `segments_total`. **Cancellation is cooperative at two levels** — checked before each chapter and (via `run_translation`) before each segment; committed segments stay. FastAPI surface + lifecycle: [COCKPIT_WORKFLOW.md](COCKPIT_WORKFLOW.md). Single-process thread worker — **no external queue**.

## 11. Export
Two export paths exist. The **legacy** single-source path (`services/export.py`) writes per-chapter **Markdown** review files and a translated **EPUB** (`renderers/epub.py`, xpath block rewrite + nav fallback) for a project's one configured `source_file`; it stays for the CLI `weaver export`.

The **volume-aware** path (`services/export_book.py`, Sprint 8A) is the Novel/Volume/Chapter exporter: read-only `prepare_export`→`ExportPlan`, then `run_export`→`ExportResult`, plus `export_novel` / `export_volume` / `export_chapter`. Each volume becomes its **own EPUB** (per-volume artifact; no cross-EPUB merge). EPUB-sourced volumes reuse the write-back renderer; **TXT/HTML-sourced volumes are synthesized** from the persisted chapter/segment content (`renderers/epub_synthesis.py`) — their source files are never re-read. A segment contributes its **latest** translation only when status is `translated`/`manual` **and** the attempt's `source_hash` matches the segment (manual edits preserved; translation history is never exported); every other segment **falls back to source text** and is counted in `FallbackByStatus`. Export never blocks on incomplete translation, never blanks, never silently drops content, and is **read-only** (writes no translations, calls no provider). **FastAPI export endpoints** (start novel/volume/chapter + status/cancel/SSE, `api/routers/export.py` + `ExportJob`) shipped in Sprint 8B. **TXT and HTML output targets** shipped in Sprint 8C (`renderers/txt.py`, `renderers/html.py`; same publishable + source-fallback rule, built from the DB; one file per volume under `output/<target>/`). **DOCX output, the export UI, batch export, and a combined single-EPUB are (planned)** — EPUB is the priority format.

## Determinism note (anti-slop)
Everything except the model call is deterministic. The LLM is used only where determinism is impossible, its output is verifiable (QA), and the user can override (manual edit, glossary). See [AI_SLOP_PREVENTION.md](AI_SLOP_PREVENTION.md).
