# 0002: Intermediate Representation Shape

Date: 2026-05-19
Status: accepted

## Context

Source readers (EPUB today, plausibly HTML/PDF later) and the translation orchestrator must agree on a neutral document representation. The renderer needs enough information to write translated text back into the original EPUB structure without the translator having to think about XHTML. Sidecar data (image assets, CSS) must survive the round-trip. The shape must also be immutable enough that orchestrator and renderer cannot accidentally desync.

## Decision

Three immutable dataclasses in [src/weaver/core/ir.py](https://github.com/Trancend1/weaver/blob/main/src/weaver/core/ir.py), all `@dataclass(frozen=True)`:

- `DocumentIR(metadata: DocumentMetadata, assets: list[AssetIR], chapters: list[ChapterIR])` — top-level format-neutral handoff.
- `ChapterIR(id, title, href, order, blocks: list[BlockIR])` — spine-ordered grouping.
- `BlockIR(id, chapter_id, order, kind, source_text, normalized_source_text, markup_context: EpubMarkupContext)` — single translatable block. `kind` is `Literal["paragraph", "heading", "quote", "other"]`.

`EpubMarkupContext` lives in the same module and carries the reader-specific payload: `file_href`, `xpath`, `tag`, `attrs`, `text_node_index`. The translation layer never reads `markup_context`; only the EPUB renderer does. `AssetIR` carries raw bytes through so binary resources are not re-derived.

Source text appears twice on each block: `source_text` (verbatim, used for rendering fallbacks and example sentences) and `normalized_source_text` (NFKC + whitespace-collapsed, used for hashing and translation prompts).

## Consequences

**Easier:** Translator code is format-agnostic — no XML in `services/translation.py`. Frozen dataclasses preclude accidental mutation across the long orchestrator loop. Asset bytes survive untouched into the renderer. The reader/renderer contract is the dataclass itself; tests pin the contract by constructing IR objects directly.

**Harder:** A non-EPUB reader (HTML, PDF) needs a markup-context variant, which today means widening `BlockIR.markup_context` to a union. Whole-document-in-memory: a 200k-character novel is fine, but a 100k-segment archive would need streaming. Frozen lists inside `ChapterIR`/`DocumentIR` are technically still mutable Python lists — the immutability is by convention; the tests rely on it.
