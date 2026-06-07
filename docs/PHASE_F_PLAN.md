# Phase F — EPUB Light Novel Metadata, Structure & Image Text Completeness

> Phase F is no longer a UI polishing phase. It is a publication-parsing phase focused on treating a Japanese light novel EPUB as a complete book package, not only as extracted chapter text.
>
> This revision also includes image-based text handling for Japanese light novel assets such as character introduction pages, captioned illustrations, and other image-only pages. Metadata parsing finds and classifies the asset; OCR/vision extraction reads text inside the image; the translation pipeline translates the extracted text without mutating the original image by default.

## 1. Purpose

Phase F ensures Weaver can parse, validate, preview, translate, and re-export Japanese light novel EPUBs with their full publication structure intact.

The goal is to build a complete internal representation of an EPUB package, including OPF metadata, series/volume metadata, manifest assets, spine reading order, NAV/NCX hierarchy, images, styling resources, image text extraction records, and translation-ready text units.

By the end of this phase, Weaver must understand a light novel EPUB as:

```text
EPUB Package
├── Book metadata
├── Series / volume metadata
├── Manifest assets
├── Spine reading order
├── Navigation hierarchy
├── Visual assets
│   ├── Cover
│   ├── Color illustrations
│   ├── Insert illustrations
│   ├── Character introduction pages
│   ├── Decorative dividers
│   └── Other images
├── Image text extraction
│   ├── OCR blocks
│   ├── Bounding boxes
│   ├── Confidence
│   ├── Reading order
│   └── Translated sidecar text
├── Styling resources
├── Translation segments
└── Export-preservation map
```

## 2. Scope

### In scope

- OPF metadata extraction and normalization.
- EPUB 2 and EPUB 3 compatibility where practical.
- Manifest scanning for XHTML, CSS, images, fonts, navigation files, and supporting resources.
- Spine parsing that preserves the original reading order.
- NAV/NCX parsing for table of contents, chapter names, volume hierarchy, landmarks, and nested structure.
- Image detection, classification, validation, and preview.
- Japanese light novel structure heuristics, including cover, color pages, prologue, chapters, interlude, epilogue, afterword, bonus stories, character pages, and illustration sections.
- Review-gated Japanese OCR / vision text extraction for selected image assets.
- OCR block storage with source image path, bounding box, confidence, reading order, and extracted Japanese text.
- Translation of OCR-extracted text using the same glossary/character-aware translation pipeline where possible.
- Image translation preview through side-by-side image, OCR text, and translated text.
- Sidecar export for image text translations, such as appendix notes, JSON metadata, HTML notes, or optional reader-facing translated captions.
- Import preview that exposes metadata, structure, navigation, visual assets, OCR readiness, and validation results before translation.
- Translation integration so images, dividers, styling, reading order, and image-text sidecars are not destroyed during translation/export.
- EPUB export fidelity checks so translated EPUB output preserves the original book package as much as possible.
- Regression fixtures for real-world and synthetic Japanese light novel EPUB structures.
- Documentation updates for EPUB parsing contracts, metadata contracts, OCR/image-text contracts, and import/export workflow.

### Out of scope

- Distribution and installer work.
- Marketplace/public release packaging.
- Decorative UI polish unrelated to EPUB parsing, import preview, OCR preview, or import/export correctness.
- New web animation, design-system changes, or frontend polish unless required for EPUB/image/OCR preview.
- DRM removal or protected EPUB handling.
- Automatic semantic understanding of illustration contents beyond metadata, filename, dimension, placement heuristics, and explicit OCR/vision text extraction.
- Automatic replacement/redrawing of Japanese text inside illustrations.
- Image inpainting, image regeneration, or destructive editing of original artwork.
- Treating low-confidence OCR as final translation without user review.
- Running OCR on every image by default without user action or a clear batch setting.

## 3. Core data model target

Create or refine a stable internal representation for parsed EPUBs.

Suggested model shape:

```text
ParsedEpub
├── package_path
├── opf_path
├── metadata: EpubMetadata
├── manifest: list[ManifestAsset]
├── spine: list[SpineItem]
├── navigation: list[NavItem]
├── images: list[ImageAsset]
├── image_text: list[ImageTextExtraction]
├── styles: list[StyleAsset]
├── fonts: list[FontAsset]
├── validation_report: EpubValidationReport
└── preservation_map: ExportPreservationMap
```

Minimum fields to preserve for package assets:

- Original `href`.
- Resolved internal path.
- Manifest ID.
- Media type.
- Spine order.
- NAV/NCX label.
- Asset role/classification.
- Source checksum.
- Referencing XHTML files.
- Export strategy.

Suggested image text model:

```text
ImageTextExtraction
├── image_asset_id
├── source_href
├── extraction_status: not_run | extracted | low_confidence | failed | skipped
├── extraction_backend
├── detected_language
├── page_role: character_page | color_illustration | insert_art | cover | other
├── blocks: list[ImageTextBlock]
└── translation_status: not_translated | translated | needs_review | failed

ImageTextBlock
├── block_id
├── text_source
├── text_translated
├── bbox: x, y, width, height
├── confidence
├── reading_order
├── script_direction: horizontal | vertical | mixed | unknown
├── glossary_hits
├── character_hits
└── review_status: pending | accepted | edited | rejected
```

## 4. Stages

| Stage | Status | Focus | Output |
| --- | --- | --- | --- |
| **F1** | Done | EPUB parser audit and model contract | Current parser audit, missing metadata list, final `ParsedEpub` contract |
| **F2** | Done | OPF metadata extraction | Title, author, contributor, language, publisher, identifier, date, description, subject, rights, series/volume metadata |
| **F3** | Done | Manifest + resource mapping | Complete manifest map for XHTML, CSS, images, fonts, NAV/NCX, and supporting assets |
| **F4** | Done | Spine + reading order preservation | Canonical reading order, non-linear item handling, page progression direction, original order preserved |
| **F5** | Done | NAV/NCX hierarchy extraction | TOC tree, chapter labels, nested volume/chapter structure, landmarks, page-list where available |
| **F6** | Done | Image detection, classification, and preview | Cover, color illustrations, insert art, character pages, dividers, unknown images, preview data |
| **F7** | Done | Validation engine | Broken hrefs, missing assets, duplicate IDs, invalid media types, nav/spine mismatch, missing cover, metadata warnings |
| **F8** | Done | Import preview + UI/API integration | Preview endpoint/page showing metadata, structure, reading order, assets, image thumbnails, validation report |
| **F9** | Done | Translation pipeline integration | Segment mapping tied to spine/nav items; non-text assets preserved; no image/divider loss during translation |
| **F10** | Done | EPUB export fidelity | Deterministic source-vs-export fidelity report for metadata, manifest resources, spine, nav, images, CSS/fonts, validation, and missing assets |
| **F11** | Done | Fixtures, tests, docs, regression | Broader synthetic light-novel fixture coverage for images, CSS/fonts, NAV/NCX, nested TOC, page-list/landmarks, non-linear spine, import/export/preview/fidelity regressions |
| **F12** | Done | Final closeout, docs reconciliation, and OCR gating | Phase F docs reconciled, final validation run, import/export/translation behavior confirmed unchanged, OCR explicitly deferred behind separate adapter/provider approval |

### Phase F closeout status

Phase F is complete as an additive EPUB light-novel package parsing and preview
foundation. The shipped surface is intentionally read-only/parallel where it
touches package structure: `read_epub()`, `DocumentIR`, import, translation, and
export behavior remain the active production path.

OCR/vision work did not ship in Phase F. Image-text placeholders are data-only
preservation hints for future stages and do not extract text, call a provider,
write image files, mutate EPUB assets, or add dependencies.

## 5. Required EPUB metadata coverage

### OPF metadata

Must extract and normalize:

- `dc:title`
- `dc:creator`
- `dc:contributor`
- `dc:language`
- `dc:identifier`
- `dc:publisher`
- `dc:date`
- `dc:description`
- `dc:subject`
- `dc:rights`
- `meta name="cover"`
- EPUB 3 collection metadata where available:
  - `belongs-to-collection`
  - `collection-type`
  - `group-position`
- Calibre-style series metadata where available:
  - `calibre:series`
  - `calibre:series_index`

### Manifest

Must map:

- Chapter XHTML/HTML files.
- Cover page XHTML.
- NAV file.
- NCX file.
- CSS files.
- Image files: JPEG, PNG, WebP, SVG where supported.
- Font files.
- Other supporting resources.

Each manifest item should include:

- ID.
- Href.
- Resolved path.
- Media type.
- Exists/missing status.
- Resource category.
- Referenced-by list.
- Export preservation strategy.

### Spine

Must preserve:

- Original reading order.
- Manifest ID references.
- Linear/non-linear status.
- Page progression direction where present.
- Cover/color-page/prologue/chapter/epilogue/afterword/bonus positioning.
- Spine item to navigation item mapping when possible.

### NAV/NCX

Must extract:

- TOC hierarchy.
- Chapter names.
- Volume/part structure.
- Landmarks.
- Page-list when available.
- Japanese labels such as:
  - `表紙` — cover
  - `カラーイラスト` — color illustrations
  - `目次` — table of contents
  - `登場人物` / `人物紹介` — character introduction page
  - `プロローグ` — prologue
  - `第一章` / `第1章` — chapter
  - `間章` — interlude
  - `エピローグ` — epilogue
  - `あとがき` — afterword
  - `特典` — bonus / extra

### Images

Must identify and classify:

- Cover image.
- Color illustrations.
- Insert illustrations.
- Character introduction pages.
- Decorative dividers.
- Chapter ornaments.
- Publisher/logo images.
- Unknown images requiring manual review.
- Image assets likely to contain translatable text.

Classification signals:

- OPF cover metadata.
- Manifest ID/name.
- File path and filename.
- XHTML placement.
- Spine position.
- NAV/NCX label.
- Image dimensions.
- Repeated usage.
- Alt text/caption where available.
- CSS class/id references.
- OCR/vision text density when extraction is run.

Classification should include confidence:

```text
high    = strong metadata or structural signal
medium  = filename/path/placement heuristic
low     = weak heuristic; show as needs review
```

## 6. Preview requirements

Weaver should provide an EPUB preview before translation/import finalization.

Preview must show:

- Book title, author, language, publisher, identifier.
- Series title and volume number if detected.
- Cover preview.
- Reading order from spine.
- TOC hierarchy from NAV/NCX.
- Manifest summary by type.
- Image gallery grouped by classification.
- OCR readiness for image-based text pages.
- Extracted image text and translated sidecar text when OCR has been run.
- Missing/broken asset warnings.
- Unknown image list for review.
- Whether the EPUB is safe to translate/export.

Minimum preview shape:

```text
EPUB Preview
├── Metadata summary
├── Series / volume summary
├── Reading order
├── TOC tree
├── Assets summary
├── Image classification gallery
├── Image text OCR / translation preview
├── Validation warnings/errors
└── Import readiness status
```

## 7. Image text OCR & translation preview

Metadata parsing cannot translate text embedded inside images. It can only discover, classify, and order those images. For pages such as character introduction spreads, the translation feature must be a separate OCR/vision-assisted workflow.

### Goal

Detect image-based text pages in Japanese light novel EPUBs and provide a safe translation preview for text embedded inside those images.

Target image types:

- Character introduction pages, especially `登場人物` / `人物紹介` spreads.
- Color illustration pages with captions.
- Insert illustrations with text labels or notes.
- Image-only bonus pages with short Japanese text.
- Publisher pages with relevant reader-facing text, when useful.

### Required behavior

- OCR must be explicit, review-gated, or batch-configured; do not silently OCR every image by default.
- OCR results must be stored separately from original image assets.
- Original images must remain unchanged.
- Each OCR text block must retain bounding box, confidence, reading order, and source image reference.
- Low-confidence OCR blocks must be marked as `needs_review`.
- OCR output must be editable before or after translation.
- Translation must use glossary and character database context when available.
- Translated image text must be stored as sidecar data unless a later phase explicitly implements image redraw/overlay.
- Export should preserve original images and optionally include translated sidecar notes, appendix, or structured metadata.

### Suggested workflow

```text
Image asset detected
→ classify as character_page / captioned_illustration / insert_art / other
→ user opens image preview
→ user runs OCR for selected image or selected image group
→ Weaver stores OCR blocks with confidence and bounding boxes
→ user reviews or edits extracted Japanese text
→ Weaver translates reviewed OCR text
→ user reviews translated sidecar text
→ export keeps original image and includes translation notes/sidecar when enabled
```

### Output modes

| Mode | Status | Purpose |
| --- | --- | --- |
| Image preview + OCR text | Required | Show extracted Japanese text beside the image |
| Image preview + translated text | Required | Show translated sidecar text beside OCR text |
| Sidecar export | Required | Preserve translation without altering artwork |
| Appendix export | Optional | Add translated image-text notes at the end of EPUB/HTML/DOCX |
| Overlay preview | Optional / experimental | Visually align translated text over the image for review only |
| Image redraw/replacement | Out of scope | Do not edit artwork automatically |

### Validation for OCR results

Add deterministic checks:

- OCR text block has empty text.
- OCR text has very low confidence.
- OCR block has no bounding box.
- OCR block order is missing or duplicated.
- OCR output still contains obvious noise or isolated symbols.
- OCR translation is missing.
- OCR translation still contains Japanese text.
- OCR block references a missing image asset.

## 8. Validation rules

Add deterministic validation checks for EPUB completeness.

### Error

- OPF file missing or unreadable.
- Manifest item referenced by spine is missing.
- XHTML file in spine is missing.
- Image referenced by XHTML is missing.
- NAV/NCX file declared but missing.
- EPUB cannot produce a safe reading order.
- OCR block references a missing image asset.

### Warning

- Missing title.
- Missing language.
- Missing author/creator.
- Missing publisher.
- Missing identifier.
- Missing cover metadata.
- Cover image cannot be confidently identified.
- NAV/NCX hierarchy differs significantly from spine.
- Unknown images found.
- Image likely contains text but OCR has not been run.
- OCR result confidence is below the review threshold.
- OCR translation is missing for accepted OCR text.
- CSS/font resource missing but non-critical.
- Unsupported media type preserved but not previewable.

### Info

- Extra unreferenced assets.
- Non-linear spine items.
- Multiple possible cover candidates.
- Multiple navigation files.
- Series metadata detected from Calibre/vendor-specific metadata.
- OCR skipped by user.

## 9. Translation integration targets

Phase F should also close gaps that affect translation quality and export correctness.

Required targets:

- Segment IDs must be traceable back to EPUB spine item and original XHTML path.
- Translation must avoid modifying image-only pages unless explicitly supported.
- Decorative dividers must not become translation segments.
- Character introduction pages should be detected as either image-only, text-based, or mixed.
- OCR-extracted image text should become reviewable image-text units, not normal chapter segments.
- OCR image-text units should support glossary and character DB context.
- OCR image-text translations should not overwrite manual chapter translations or normal text segments.
- Color illustration sections should be preserved in reading order.
- Insert art inside chapters should remain near the original text location.
- Glossary and character database should receive chapter/volume/image-page context where possible.
- Translation memory entries should preserve source chapter/spine/image context.
- Retranslate modes must not accidentally overwrite manually preserved structural pages or reviewed OCR translations.
- QA should distinguish translatable text from metadata, image captions, image OCR text, navigation labels, and decorative content.

## 10. EPUB export fidelity targets

Translated export must preserve:

- OPF metadata, with translated title/description optional and original metadata retained.
- Manifest completeness.
- Spine order.
- NAV/NCX structure.
- Cover image and cover metadata.
- Color illustrations.
- Insert illustrations.
- Character pages.
- Decorative dividers.
- CSS.
- Fonts where legally embedded and already present.
- Original image paths when possible.
- OCR/image-text sidecar metadata when enabled.
- Optional translated image-text appendix or notes when enabled.
- XHTML structure as much as possible, replacing text content without flattening the book.

Add post-export validation:

- Exported EPUB can be reopened by Weaver.
- Exported OPF is valid enough for common EPUB readers.
- Exported spine count matches expected structure.
- Exported image count matches preservation expectations.
- Exported OCR/image-text sidecar count matches accepted OCR records when sidecar export is enabled.
- Exported NAV/NCX is not broken.
- Cover displays correctly.

## 11. Completion tasks beyond Phase F but before Distribution/Installer

These tasks help complete Weaver as a translation product without touching Distribution/Installer.

### Translation workflow completion

- Finalize chapter, volume, and full-novel translation flows.
- Make provider translation resumable and failure-safe.
- Ensure retry/retranslate modes are clearly separated:
  - skip existing
  - retranslate non-manual
  - force selected
- Preserve full attempt history.
- Add provider output normalization before saving translations.
- Add deterministic language/script checks for untranslated Japanese remnants.

### Glossary, character, and terminology completion

- Complete project-scoped glossary CRUD and import/export.
- Complete character database with aliases, honorific preference, role, and speech notes.
- Inject glossary and character context into translation prompts deterministically.
- Add consistency checks for names, honorifics, titles, and recurring terms.
- Support per-volume terminology overrides when needed.
- Allow OCR-derived character names and aliases to be proposed for review before entering the character DB.

### Translation memory completion

- Store reusable source → target pairs.
- Match exact and near-exact source segments.
- Prefer manual translations over AI translations.
- Track origin chapter/volume/provider.
- Track image OCR origin when TM entries come from image text.
- Expose TM suggestions in workspace.
- Prevent stale TM entries from silently overriding manual edits.

### Image-based text translation completion

- Add an OCR/vision adapter interface instead of hard-binding the whole app to one OCR backend.
- Support selected-image OCR first, then optional batch OCR for classified character pages/captioned illustrations.
- Store OCR blocks separately from normal chapter segments.
- Add review states for OCR text and OCR translations.
- Add side-by-side image/OCR/translation preview.
- Add export modes for image text sidecars and optional appendix notes.
- Add QA rules for low-confidence OCR, missing OCR translation, Japanese remnants, and broken image references.
- Keep image redraw/replacement out of scope until explicitly planned.

### QA completion

- Add report-first QA for:
  - untranslated Japanese text
  - empty translation
  - too-short/too-long translation
  - repeated source with inconsistent target
  - glossary target missing
  - character name inconsistency
  - honorific inconsistency
  - punctuation/quote mismatch
  - broken inline markup
  - suspicious duplicated translation
  - low-confidence OCR text
  - OCR text accepted but not translated
  - OCR translation still containing Japanese text
- Support chapter, volume, novel-level, and image-text QA reports.
- Keep QA deterministic first; no automatic fix unless introduced in a later explicit phase.

### Import/export completion

- Support TXT, HTML, and EPUB import consistently.
- Keep EPUB as the highest-fidelity path.
- Export TXT, HTML, DOCX, and EPUB from the same canonical translation state.
- Add export preflight before creating output.
- Add export bundle ZIP for multi-format output if already planned.
- Validate exported files after generation.
- Include OCR/image-text sidecar exports where enabled.

### Workspace completion

- Stable two-column source/translation workspace.
- Manual save and history view.
- Segment status clarity: pending, translated, manual, failed, stale.
- Chapter navigation, progress, and issue badges.
- Safe editing for long segments.
- Clear distinction between AI output and manual edits.
- Separate image-text review surface for OCR blocks so they do not pollute chapter segments.

### Documentation completion

- `EPUB_STRUCTURE.md` — EPUB parsing and preservation model.
- `METADATA_CONTRACT.md` — OPF/NAV/manifest/spine/image contract.
- `IMAGE_TEXT_OCR_CONTRACT.md` — OCR block model, confidence, review, translation, and sidecar export behavior.
- `IMPORT_EXPORT_WORKFLOW.md` — import, preview, translation, QA, export lifecycle.
- `TRANSLATION_PIPELINE.md` — prompt, provider, retry, save, history, TM behavior.
- `QA_RULES.md` — deterministic QA rule list and severity.
- `COCKPIT_WORKFLOW.md` — updated only where preview/workspace/export behavior changed.

## 12. Exit criteria

Phase F closeout status:

- [x] OPF metadata extraction covers the implemented required metadata families.
- [x] Manifest parser maps XHTML, CSS, image, font, NAV/NCX, and supporting resources.
- [x] Spine parser preserves original reading order, linear flags, and page progression metadata.
- [x] NAV/NCX parser extracts TOC hierarchy, landmarks, page-list, chapter labels, and Japanese labels.
- [x] Cover image detection works from OPF metadata and fallback heuristics.
- [x] Color illustrations, insert art, character pages, decorative dividers, publisher logos, and unknown images are classified best-effort.
- [x] Preview shows metadata, reading order, TOC/navigation, resources, image roles, validation issues, and readiness flags.
- [x] Validation engine reports EPUB structure issues deterministically.
- [x] Translation preservation context distinguishes normal text from non-text assets without changing translation behavior.
- [x] Export fidelity report compares metadata, manifest categories, spine, navigation, images, CSS/fonts/supporting assets, and validation issue deltas.
- [x] Exported EPUB can be reopened and inspected by Weaver in targeted regression coverage.
- [x] Tests cover OPF, manifest, spine, NAV, NCX, image classification, validation, preview, translation preservation, export fidelity, and broader synthetic light-novel fixtures.
- [x] Docs match the implemented behavior.
- [x] Full regression gate is the F12 closeout validation command bundle.

Deferred behind separate approval/ADR:

- [ ] OCR/vision extraction from images.
- [ ] OCR block model persistence, bounding boxes, confidence, and review workflow.
- [ ] OCR-extracted text translation and sidecar export.
- [ ] Any new OCR/provider/vision/image-processing dependency or credential behavior.

## 13. Validation gate

```bash
uv run pytest -q
uv run pyright
uv run ruff check .
uv run ruff format --check .
uv run weaver --help
```

Additional Phase F validation should include fixture-based EPUB checks once the commands/tests exist:

```bash
uv run pytest tests/unit/epub tests/integration/epub -q
uv run pytest tests/e2e/test_epub_import_preview_export.py -q
uv run pytest tests/unit/image_text tests/integration/image_text -q
```

Manual walkthrough:

```text
Import EPUB
→ inspect preview
→ verify metadata
→ verify spine order
→ verify TOC
→ verify images
→ flag character page for OCR
→ run selected-image OCR
→ review OCR blocks
→ translate OCR text
→ verify image text sidecar preview
→ translate sample chapter
→ QA
→ export EPUB
→ re-import exported EPUB
→ compare structure preservation report and image-text sidecar report.
```

## 14. Suggested agent command

```text
Refactor Phase F from UI polishing into EPUB Light Novel Metadata, Structure & Image Text Completeness.

Use the existing Phase F plan as the source to replace. Remove non-urgent UI polishing scope such as broad state audit, responsive polish, visual/copy consistency, and decorative cockpit polish unless directly required for EPUB preview, image preview, OCR preview, import/export correctness, or review workflow clarity.

Goal:
Weaver must parse Japanese light novel EPUBs as complete publication packages, not only as chapter text. Implement a complete EPUB representation covering OPF metadata, manifest, spine, NAV/NCX, images, styling resources, image-text extraction, validation, preview, translation preservation, and EPUB export fidelity.

Required work:
1. Audit the current EPUB parser/import/export pipeline.
2. Define a stable ParsedEpub contract with metadata, manifest assets, spine items, nav items, image assets, image-text extraction records, validation report, and preservation map.
3. Extract OPF metadata: title, creator, contributors, language, publisher, identifier, date, description, subject, rights, cover meta, EPUB 3 collection metadata, and Calibre series metadata when available.
4. Map manifest resources: XHTML/HTML, CSS, images, fonts, NAV/NCX, and supporting assets.
5. Preserve spine reading order, linear/non-linear status, page progression direction, and spine-to-nav mapping.
6. Parse NAV/NCX hierarchy, landmarks, page-list, chapter names, volume structure, and Japanese light novel labels.
7. Detect and classify images: cover, color illustrations, insert art, character introduction pages, decorative dividers, publisher/logo images, unknown images requiring review, and image assets likely to contain translatable text.
8. Add deterministic validation for missing/broken resources, bad spine references, missing metadata, cover ambiguity, nav/spine mismatch, unsupported resources, unknown images, OCR low confidence, OCR missing translations, and broken image-text references.
9. Add import preview/API/UI support showing metadata, reading order, TOC, asset summary, image gallery, classification confidence, OCR readiness/results, and validation readiness.
10. Add image text OCR/vision extraction as a review-gated workflow for selected image assets, especially character introduction pages and captioned illustrations.
11. Store OCR output as image-text blocks with source image path, bounding box, confidence, reading order, extracted Japanese text, translated text, and review status.
12. Translate OCR-extracted text using the existing translation pipeline with glossary and character DB context where available.
13. Keep original images immutable by default. Export image-text translations as sidecar data, appendix notes, or optional translated captions. Do not redraw or replace artwork.
14. Integrate with translation so segment IDs map back to original XHTML/spine items and non-text assets are preserved.
15. Ensure export preserves OPF metadata, manifest, spine, nav/ncx, cover, illustrations, character pages, decorative dividers, CSS, fonts, original reading order, and image-text sidecars where enabled.
16. Add fixtures and tests for OPF, manifest, spine, NAV, NCX, image classification, OCR block model, validation, preview, translation preservation, and export fidelity.
17. Update docs: EPUB_STRUCTURE.md, METADATA_CONTRACT.md, IMAGE_TEXT_OCR_CONTRACT.md, IMPORT_EXPORT_WORKFLOW.md, TRANSLATION_PIPELINE.md, QA_RULES.md, and COCKPIT_WORKFLOW.md where behavior changed.

Constraints:
- Do not work on Distribution/Installer.
- Do not add DRM removal.
- Do not mutate original images by default.
- Do not implement automatic image redraw/replacement in this phase.
- Do not treat decorative images/dividers as translation segments.
- Do not treat OCR output as final when confidence is low; require review status.
- Keep behavior deterministic and test-backed where possible.
- Prefer small service modules and typed models; templates/UI must not contain parsing, OCR, or translation logic.
- If an OCR backend requires a new dependency or external provider, isolate it behind an adapter and document the dependency/credential behavior before enabling it by default.

Final gate:
Run pytest, pyright, ruff check, ruff format --check, and weaver --help. Add EPUB-specific and image-text-specific unit/integration/e2e tests and include a final report showing parser coverage, validation coverage, OCR/image-text behavior, preview behavior, translation preservation, and export fidelity.
```

