# ADR 012 — Image Preview / OCR Security Gate

## Status

Accepted (maintainer, 2026-06-09). Locked at the start of Sprint M. Governs all
image-byte preview behavior and blocks any real OCR implementation until the
explicit approval gates below are satisfied.

## Context

Phase F and Sprint J already parse and persist EPUB image metadata:

- image role/kind classification
- dimensions and byte-size metadata
- manifest/back-reference context
- future OCR placeholders in preservation records

That metadata is useful, but exposing image bytes introduces a new security and
cost boundary that earlier phases intentionally deferred. Sprint M needs a safe,
read-only preview path before any OCR adapter or job can exist.

The risks are straightforward:

1. **Path traversal / archive escape.** Manifest metadata may contain hostile or
   malformed paths.
2. **Unsafe MIME exposure.** EPUB packages may contain SVG, scripts, or unknown
   binaries masquerading as images.
3. **Oversized bytes.** A very large asset can make preview expensive or unsafe.
4. **Mutation drift.** Preview must not rewrite, recompress, or overwrite EPUB
   resources.
5. **OCR creep.** Once bytes are exposed, it becomes easy to silently add OCR or
   provider calls unless the boundary is explicit.
6. **Credential/cost leakage.** OCR must not upload bytes or spend provider
   budget without an explicit, reviewable configuration and approval gate.

## Decision

### 1. Image byte access policy

Image preview is allowed **only** for a persisted, manifest-backed snapshot image
selected by `volume_id + manifest_id`.

- Raw filesystem paths are never accepted.
- Raw archive paths are never accepted from the client.
- The source of truth is the persisted EPUB snapshot plus the imported volume's
  original EPUB path.

### 2. MIME allowlist

The preview endpoint allows only these media types:

- `image/jpeg`
- `image/png`
- `image/gif`
- `image/webp`

Rejected by default:

- SVG
- PDF
- unknown / custom binaries
- anything not explicitly in the allowlist

### 3. Max byte size

Preview is capped at **8 MiB** per image.

- Oversized images are rejected before or during archive read.
- Metadata may still be shown even when byte preview is rejected.

### 4. Path traversal protections

- Preview uses the snapshot's normalized archive path only.
- Archive paths that normalize to an absolute path or contain `..` escape are
  rejected.
- Preview reads from the EPUB ZIP archive only; it does not map archive members
  onto arbitrary filesystem paths.

### 5. No-mutation / no-overwrite rule

Preview is **strictly read-only**.

- No image rewrite
- No recompression
- No EXIF stripping
- No thumbnail persistence
- No overwrite of archive contents
- No write-back to project files or snapshot rows

### 6. UI scope

Sprint M adds a preview affordance only on existing EPUB structure/image
inventory surfaces.

- No gallery app
- No reader mode
- No image editor
- No drag/drop asset workflow

### 7. OCR adapter contract (gated only)

Sprint M may define a **contract** for future OCR, but may not implement a real
OCR provider.

The contract must carry:

- image reference (`volume_id + manifest_id` or equivalent safe identifier)
- extracted text output
- provenance
- provider/model metadata
- cost metadata
- failure state

But Sprint M must not:

- call a cloud OCR provider
- upload image bytes by default
- auto-apply OCR output to translation state
- mutate segment/workspace text automatically

### 8. Provider / credential / cost controls

Real OCR is blocked until all of the following are explicitly approved in a
future ADR or sprint gate:

1. provider config is explicit and local to the project/runtime
2. credentials are sourced only from existing approved secret mechanisms
3. cost metadata is recorded and user-visible
4. byte upload scope is documented
5. OCR output lands as a draft artifact only
6. no automatic translation or export mutation occurs

### 9. OCR approval gates

**Gate A — Security boundary accepted.** This ADR is merged and enforced.

**Gate B — Read-only preview proven.**

- traversal rejected
- unsupported MIME rejected
- oversized image rejected
- missing manifest image rejected
- no writes/mutation performed

**Gate C — OCR implementation approval (future only).**

Requires a separate explicit approval. Without Gate C, OCR remains contract-only.

## Consequences

**Improves**

- Image preview becomes safe and reviewable.
- OCR remains blocked behind explicit policy instead of sneaking in through a
  preview endpoint.
- Sprint N can rely on a stable local-image boundary.

**Tradeoffs**

- Some EPUB images (for example SVG or oversized assets) remain metadata-only.
- No thumbnail cache means previews are simple but not aggressively optimized.
- OCR progress is intentionally slower because approval gates are explicit.

## Related Files

- `src/weaver/services/image_preview.py`
- `src/weaver/services/epub_snapshot.py`
- `src/weaver/services/epub_structure_preview.py`
- `src/weaver/api/routers/projects.py`
- `src/weaver/api/routers/ui.py`
- `src/weaver/api/templates/epub_preview.html`
- `docs/weaver_next_plan.md` Sprint M
