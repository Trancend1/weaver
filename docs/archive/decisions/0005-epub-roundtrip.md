# 0005: EPUB Roundtrip Strategy

Date: 2026-05-19
Status: accepted

## Context

Users want a translated EPUB out, not a Markdown dump. The source is EPUB; the output is EPUB; the reader (Calibre, Apple Books, mobile readers) must reopen the file without complaint. Metadata, spine order, image assets, CSS references, and most internal hrefs must survive. Ruby/furigana, vertical text, and complex footnotes are explicitly out of scope at MVP-0 ([PRD_v2.md](../PRD_v2.md) §6 Output). Translation only writes text; the renderer must not "improve" structure it wasn't asked to.

## Decision

Implemented in [src/weaver/renderers/epub.py](https://github.com/Trancend1/weaver/blob/main/src/weaver/renderers/epub.py).

1. Load the source EPUB with `ebooklib.epub.read_epub`. Keep the resulting `EpubBook` as the carrier — metadata, spine, manifest, and asset items all flow through it untouched.
2. Group `BlockIR` by chapter `href`.
3. For each chapter, parse the XHTML via `xml.etree.ElementTree.fromstring(item.get_content())`. XHTML and EPUB namespaces are registered once at module load so output keeps `xmlns="http://www.w3.org/1999/xhtml"`.
4. For each block, walk `markup_context.xpath` step-by-step (no XPath engine). Each step matches by local tag name and 1-indexed positional predicate (`p[4]`). On a hit, replace `element.text` with the translation and `element.clear()`-equivalent drop of children to avoid stale mixed content.
5. Blocks that have no translation (status `failed` / `stale` / `pending` / missing) fall back to source text — the source XHTML is left untouched. Counters in `EpubRenderResult.translated_blocks` / `fallback_blocks` surface to the CLI summary.
6. If the source EPUB lacks an `EpubNcx` item, synthesize one before writing. Without this, `ebooklib.write_epub` emits `<spine toc="ncx">` referencing a nonexistent manifest entry and the output cannot be reopened.
7. Output path: `<output_dir>/epub/<source-stem>.translated.epub`.

`--mode epub` is mutually exclusive with `--translation-only` (CLI rejects with exit `1` + clear message).

## Consequences

**Easier:** Round-trip preserves metadata, spine order, image assets, and CSS without the renderer having to understand them. Untranslated blocks degrade gracefully to source text — no blank pages. The output reopens in `ebooklib` and EPUB 2 readers thanks to the synthesized NCX. The xpath resolver is small, deterministic, and entirely under our control.

**Harder:** Dropping element children to clear mixed content destroys ruby/furigana, inline links inside paragraphs, and footnote anchors. Documented limitation; users with ruby-heavy source EPUBs should expect plain text in those blocks. The hand-rolled xpath walker only understands the predicates that `readers/epub.py` emits — extending the reader to richer XPath requires changing the renderer too. Vertical-text CSS is preserved but content reflows horizontally; layout-critical books will look wrong.
