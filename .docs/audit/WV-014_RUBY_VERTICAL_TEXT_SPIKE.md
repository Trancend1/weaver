# WV-014 — Ruby (furigana) & Vertical-Text Fidelity Spike

**Sprint:** Q11 (Validation improvements) · **Type:** investigation-only (no renderer rewrite) · **Date:** 2026-06-12

**Scope.** Trace how `<ruby>`/`<rt>` furigana and vertical-text presentation
(`writing-mode`, OPF `page-progression-direction`) survive the
import → preview → export path. Outcome = this finding + a scoped follow-up issue
where fidelity is lost. No preservation implementation lands in Q (per the Q11
plan; ADR 008 / Gate B1 fences unchanged).

**Method.** Code trace of the reader, the structure parser, and the EPUB renderer,
plus a characterization test (`tests/unit/readers/test_epub_ruby_spike.py`) that
pins the current text-extraction behavior.

---

## Findings

### 1. Ruby is FLATTENED on import — the reading leaks into the source segment ⚠️ (defect)

`weaver/readers/epub.py:1429` extracts block text with:

```python
def _element_text(element):
    return collapse_whitespace("".join(element.itertext()))
```

`itertext()` walks **all** descendants, so for
`<p>吾輩は<ruby>猫<rt>ねこ</rt></ruby>である</p>` the extracted source segment is
`吾輩は猫ねこである` — the furigana reading (`ねこ`) is concatenated onto the base
(`猫`). With `<rp>` fallback parens present, those leak too (`漢字(かんじ)`).

**Impact.** The model receives a corrupted source (`猫ねこ`), which can degrade
translation quality and pollutes glossary/QA matching against `segments.source_text`.
This is the one genuine fidelity defect found. Pinned by
`test_ruby_reading_leaks_into_source_text` so a future fix is a deliberate change.

### 2. Ruby on export — acceptable, no action

`weaver/renderers/epub.py:189` `_replace_text` removes child elements and sets
`element.text = translation`, but it runs **only** for blocks that have a
publishable translation (`renderers/epub.py:94-104`):

- **Translated block:** ruby children removed → English text, no furigana.
  Correct — English has no furigana.
- **Untranslated / fallback block:** `_replace_text` is never called, so the
  original markup (including `<ruby>`) is preserved verbatim in the output.

No change needed: ruby loss on translated blocks is the intended outcome.

### 3. Vertical text is PRESERVED on export — no action ✅

`render_translated_epub` re-reads the **source** EPUB (`renderers/epub.py:65`,
`epub.read_epub(source_epub_path)`) and edits only `<p>`-level text nodes inside
content documents by xpath. It never touches stylesheets or the OPF spine. So:

- CSS `writing-mode: vertical-rl` / `-epub-writing-mode` in stylesheets is copied
  unchanged (stylesheets are non-content items, never rewritten).
- OPF `page-progression-direction` ("rtl") is carried on the `book` object and
  preserved; the structure parser also captures it
  (`ParsedEpub.page_progression_direction`, persisted in the snapshot header —
  `epub_snapshots.page_progression_direction`).

Vertical-text **layout** therefore survives import → export. (Weaver never claims
to *re-flow* vertical text in the HTML reading preview, which is horizontal by
design — that is a preview-only presentation choice, not a stored-data loss.)

---

## Severity & decision

| Aspect | State | Action |
|---|---|---|
| Ruby reading leaks into `source_text` (import) | **Defect** | Scoped follow-up (below). No fix in Q11. |
| Ruby lost on translated blocks (export) | Intended | None |
| Ruby kept on untranslated/fallback blocks (export) | Correct | None |
| Vertical text (`writing-mode` + OPF ppd) | Preserved | None |

Only one item is a real defect, and it is import-side, deterministic, and
narrowly fixable — it does **not** justify a renderer rewrite (the Q11 fence).

## Recommended scoped follow-up (post-Q candidate)

**Issue: strip ruby annotations from imported source text.** In `_element_text`
(or a small pre-pass), drop the text content of `<rt>` and `<rp>` elements while
keeping the ruby **base**, so `<ruby>猫<rt>ねこ</rt></ruby>` extracts as `猫`.

- Surface: `weaver/readers/epub.py` text extraction only.
- Risk: low — base text is what the translator needs; readings are pronunciation
  aids, not content. Re-import / re-parse required to take effect (changes
  `source_text`, hence `source_hash` → existing translations go stale by design).
- Test: extend `tests/unit/readers/test_epub_ruby_spike.py` to assert the stripped
  form once implemented; add a round-trip on a real ruby fixture.
- Blocker / why deferred: changing extraction shifts `source_hash` for any
  ruby-bearing segment, which is a migration-of-meaning best done as its own
  reviewed change with a re-import note — out of Q11's validation-only scope.

## Evidence index

- `src/weaver/readers/epub.py:1429-1430` — `_element_text` uses `itertext()` (flatten).
- `src/weaver/renderers/epub.py:65` — renderer re-reads source EPUB (assets/OPF preserved).
- `src/weaver/renderers/epub.py:94-104,189-192` — translation applied per-block; `_replace_text` only on translated blocks.
- `src/weaver/core/epub_structure.py` — `ParsedEpub.page_progression_direction` captured.
- `tests/unit/readers/test_epub_ruby_spike.py` — characterization tests (current flatten behavior).
