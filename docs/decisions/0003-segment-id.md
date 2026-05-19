# 0003: Segment Identity And Source Hashing

Date: 2026-05-19
Status: accepted

## Context

Translations persist across crashes, days-long pauses, and source-text edits. The state store needs a primary key that (a) round-trips identically when the same EPUB is read twice, (b) flips to a stale state on real text edits without losing the structural row, and (c) does not collide at the realistic scale of a 200k-character / ~10k-segment novel. The CLI surfaces this id to the user via `weaver edit <segment-id>`, so it must be short enough to type.

## Decision

Two separate values per segment, computed in [src/weaver/core/segment.py](../../src/weaver/core/segment.py):

```
segment_id  = blake2b(chapter_href || 0x1f || dom_path || 0x1f || paragraph_index, digest_size=8).hex
source_hash = sha256(normalize_japanese_text(source_text)).hex
```

`segment_id` is 16 lowercase hex chars (64 bits). `source_hash` is full SHA-256 (256 bits). `normalize_japanese_text` is NFKC + whitespace collapse.

Stale rule: when a segment is re-read from the source EPUB, compare the new `source_hash` against the stored value. Mismatch → flip status to `stale`, invalidate the prior translation. Same hash → keep the row.

Chapter id is derived analogously: `blake2b(book_identifier || spine_href, digest_size=8).hex`.

## Consequences

**Easier:** Re-reading the same EPUB always produces the same segment ids, so resume after a crash needs no intermediate map. A targeted source edit only marks its own segment stale; everything else stays translated. 16-char ids are short enough for `weaver edit ch1-seg-009913ddcb720798` and 64-bit space is comfortably collision-free at a few thousand segments per project. The hash algorithm split keeps purposes distinct: structural identity (BLAKE2b, fast) versus content fingerprint (SHA-256, ubiquitous).

**Harder:** `dom_path` is part of the id, so the XPath shape produced by the EPUB reader is frozen — changing how the reader walks the DOM would invalidate every prior project. The id is opaque (not human-readable) so error messages must include the chapter to give the user grounding. Two hash algorithms instead of one is a slight cognitive load but each serves a different role and substituting either would either lose speed (using SHA for ids) or unnecessarily inflate id length (using BLAKE2b at 256 bits).
