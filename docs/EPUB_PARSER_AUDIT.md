# EPUB Parser Audit — Phase F1

Phase F1 introduces an additive EPUB package contract beside the existing
`DocumentIR` import/export path. The goal is to make EPUB metadata and structure
observable before later phases integrate preview, validation, translation
preservation, and export fidelity.

## Current behavior

- `src/weaver/readers/epub.py` reads source EPUBs into `DocumentIR` for the active
  import and translation flow.
- `DocumentIR` currently contains normalized book metadata, non-document assets,
  spine-backed chapters, and translatable text blocks with markup context.
- `src/weaver/renderers/epub.py` reopens the original EPUB, replaces translated
  text blocks by `EpubMarkupContext.xpath`, and writes the translated EPUB.
- `src/weaver/services/import_source.py`, `src/weaver/services/preview.py`, and
  `src/weaver/services/export.py` continue to call `read_epub`; Phase F1 does not
  change their behavior.

## Phase F1 additions

- `ParsedEpub` is a parallel contract for package-level inspection.
- `parse_epub_structure()` extracts minimal OPF metadata: title, creator,
  language, publisher, identifier, and description.
- The structure skeleton exposes manifest resources, spine resources,
  navigation entries, resources, images, and validation issues.
- Navigation XHTML is excluded from the spine-backed chapter list so the richer
  contract and existing `DocumentIR` avoid treating NAV as chapter content.

## Phase F2 additions

- `EpubPackageMetadata` now includes repeated DC metadata lists for contributor,
  date, subject, rights, source, coverage, relation, type, and format.
- OPF `meta` extraction captures modified date, cover metadata, Calibre series
  name/index, and EPUB 3 collection fields.
- Unrecognized OPF metadata is retained in a raw fallback map for later audit and
  vendor-specific parsing without changing import/export behavior.

## Phase F3 additions

- Manifest resources now preserve OPF manifest order and expose id, href,
  resolved internal ZIP path, media type, properties, and category.
- Resource flags identify spine items, navigation items, stylesheets, images,
  fonts, scripts, and cover candidates.
- Resource categories cover chapter XHTML/HTML, NAV, NCX, image, CSS, font,
  audio, video, script, package, unknown, and supporting assets.
- `parse_epub_structure()` can inspect OPF/manifest data directly from the ZIP so
  missing manifest files can be reported instead of failing before validation.
- Missing manifest resources produce deterministic `missing-manifest-resource`
  validation errors with the original manifest href.

## Phase F4 additions

- Spine resources now preserve original OPF `itemref` order while keeping NAV
  items out of chapter-backed reading order.
- `SpineResource` exposes idref, index/order, manifest-linked href/resolved
  path, media type, linear/non-linear state, manifest/archive existence, page
  spread, itemref properties, and navigation state.
- Parsed EPUBs now expose spine-level `toc` and `page-progression-direction`
  attributes.
- Validation now reports missing manifest idrefs, missing archive resources for
  spine items, duplicate spine idrefs, empty spine, and non-linear spine items.

## Phase F5 additions

- Navigation entries now preserve source type (`nav` or `ncx`), nav type, label,
  href, resolved path, fragment, hierarchy depth, child entries, and order.
- EPUB 3 NAV parsing covers nested TOC, landmarks, page-list, `lot`, and `loa`
  structures with Japanese labels preserved as UTF-8.
- NCX parsing covers `navMap`, nested `navPoint` entries, labels, content `src`,
  and `playOrder` where present.
- Navigation hrefs are linked back to manifest ids and spine indexes by resolved
  internal path when possible.
- Validation now reports navigation hrefs missing from manifest, hrefs outside
  the spine, duplicate hrefs per navigation source type, and empty TOC.

## Phase F6 additions

- Image resources now carry light-novel preview metadata: role, kind, manifest
  id, optional width/height, byte size, preview availability, linked spine index,
  and XHTML `referenced_by` data.
- Image role classification is best-effort and non-fatal. It uses OPF cover
  metadata, manifest properties, ids, href filenames/paths, and simple XHTML
  references.
- XHTML reference scanning covers simple `<img src>` and SVG `<image href>` / XML
  namespaced href attributes, normalized to EPUB internal ZIP paths.
- Validation now reports missing image archive resources, image references that
  are not manifest-backed, and unsupported image media types.
- OCR, image text extraction, overlays, redraw, and image mutation remain out of
  scope and gated separately.

## Phase F7 additions

- EPUB structure validation now lives in `src/weaver/readers/epub_validation.py`
  as a deterministic engine used by `parse_epub_structure()`.
- `ValidationIssue` remains backward-compatible and now additively includes
  `path`, `resource_id`, and `scope` for stable grouping before preview/API/UI.
- Existing metadata, manifest, spine, navigation, and image checks were moved
  out of the reader and normalized into one validation pass.
- Validation remains non-fatal and deterministic; it does not change
  `read_epub()`, `DocumentIR`, import, translation, or export behavior.

## Phase F8 additions

- EPUB structure preview now has a framework-agnostic service in
  `src/weaver/services/epub_structure_preview.py` that serializes `ParsedEpub`
  into JSON/UI-friendly metadata, counts, resources, spine, navigation, images,
  validation issues, and readiness flags.
- JSON preview is exposed at `POST /projects/epub-preview` for either a temporary
  uploaded EPUB or a sandboxed browsed `source_path`.
- UI preview is exposed at `/ui/epub-preview?source_path=...` and renders a
  sectioned, reader-like inspection surface: readiness badge, structure-count
  tiles, metadata summary, nested NAV/NCX table of contents, reading order,
  short untranslated chapter excerpts, an image inventory, and validation issues
  grouped by scope.
- Preview is read-only: no SQLite writes, no import side effects, no image bytes
  exposed, no OCR, and no translation/export behavior changes. Chapter excerpts
  are trimmed source text read on demand; they are never translated or persisted.

## Phase F9 additions

- `ParsedEpub` now carries a derived `TranslationPreservationContext` that keeps
  future translation/export preservation metadata separate from `DocumentIR`.
- Chapter context links spine-backed XHTML resources to manifest ids, spine
  indexes, and available NAV/NCX labels while marking them as normal
  `DocumentIR` segment sources.
- Non-text resources now produce preservation records for images, CSS, fonts,
  NAV/NCX, and supporting assets without turning them into translation segments.
- Image records preserve role/kind, reference XHTMLs, linked spine index, and a
  data-only future OCR placeholder flag without implementing OCR.
- No database persistence, translation behavior, import flow, export renderer,
  image bytes, or OCR behavior changed.

## Phase F10 additions

- EPUB export fidelity checks now live in
  `src/weaver/services/epub_export_fidelity.py` as a framework-agnostic,
  read-only source-vs-export audit service.
- The fidelity report compares parsed source and exported EPUB structures for
  core metadata, manifest resource presence, category counts, spine order,
  NAV/NCX presence, image resources, and validation issue count changes.
- Missing exported manifest assets are reported as critical gaps when the href
  is absent from the exported manifest or still listed but missing from the ZIP.
- The report separates passed checks, warnings, critical gaps, missing resource
  hrefs, and source/export structure counts for deterministic test assertions.
- No renderer behavior, import flow, translation behavior, `DocumentIR`, image
  bytes, OCR, or EPUB asset mutation changed.

## Phase F11 additions

- Broader synthetic light-novel regression coverage now exercises a single EPUB
  fixture with cover, color illustration, insert illustration, character page,
  divider image, CSS, font, NAV, NCX, nested TOC, landmarks, page-list, and a
  non-linear spine item.
- Regression tests prove `read_epub()` still returns normal `DocumentIR` text
  segments, image assets do not become translation segments, import still adds a
  volume, export still writes an EPUB, preview remains deterministic/read-only,
  and the F10 fidelity report catches missing exported image assets.
- A missing optional font resource fixture confirms `parse_epub_structure()` can
  report archive gaps without failing the structure audit path. The existing
  `read_epub()` behavior for physically invalid EPUBs remains unchanged.
- No concrete renderer gap was found by the F11 synthetic fixture coverage, so no
  renderer, import, translation, persistence, OCR, or image mutation changes were
  made.

## Phase F12 closeout

- Phase F closes with additive EPUB structure parsing, preview, preservation
  context, validation, export fidelity reporting, and broader regression coverage
  in place.
- `read_epub()` remains the import/export/translation path and still returns
  `DocumentIR`; `parse_epub_structure()` remains the parallel package-inspection
  path for preview, validation, preservation context, and fidelity checks.
- The FastAPI preview surfaces remain read-only: `POST /projects/epub-preview`
  returns JSON from an uploaded or sandboxed source EPUB, and
  `/ui/epub-preview?source_path=...` renders a minimal structure preview.
- No renderer rewrite was made. F10/F11 coverage found no concrete export gap for
  the tested metadata, manifest resource, spine, NAV/NCX, image, CSS/font, and
  validation scenarios.

## OCR gating

- OCR/vision extraction is not implemented in Phase F.
- No OCR, computer-vision, image-processing, or provider dependency was added.
- Image-text placeholders in the preservation context are data-only markers for
  future review workflows; they do not extract Japanese text, translate image
  text, expose image bytes, or mutate/copy/recompress assets.
- Any future OCR work must be adapter-based and gated behind separate approval.
  If it adds a dependency, external provider, credential behavior, batch mode, or
  image output format, open a dedicated ADR before implementation.

## Known parser gaps

- OPF metadata coverage does not yet model all `refines` relationships,
  alternate-script metadata, file-as/sort metadata, role/scheme attributes, or
  multiple identifiers with primary-id semantics.
- Manifest entries do not yet include checksums, real referenced-by relationships,
  duplicate ID detection, media sniffing, or export preservation strategy.
- Spine parsing does not yet map spine items to NAV/NCX labels, infer light-novel
  section roles, or validate page progression against writing mode/CSS.
- NAV/NCX parsing does not yet classify Japanese labels into light-novel section
  roles, merge duplicate NAV/NCX views into a canonical tree, or parse all EPUB
  navigation extensions beyond the currently modeled types.
- Image classification remains heuristic only; it does not inspect visual
  contents, infer text presence, or perform OCR/vision analysis. The filename/id
  heuristic matches English/romaji and a small set of Japanese tokens
  (カラー/口絵, 人物/キャラ, 挿絵); it does not read image `alt` text.
- Validation covers metadata title/language, missing manifest/image resources,
  unsupported image media types, image references missing a manifest item, spine
  idref/archive/duplicate/empty/non-linear issues, and nav href resolution/spine
  linkage/duplicate/empty-TOC. It does not yet model duplicate manifest IDs,
  cover ambiguity, or image-text validation.
- OCR/vision extraction is not implemented and remains gated for a separate
  adapter-backed phase after explicit approval/ADR.

## Phase F pre-PR audit (fixes applied)

An end-to-end audit of F1–F12 before opening the PR applied small, focused fixes
without changing `read_epub()`, `DocumentIR`, persistence, translation, export, or
OCR behavior:

- **Parser bug:** the Japanese image-role tokens in `_image_role` were stored as
  double-encoded mojibake and could never match. They are corrected to
  `カラー`/`口絵` (color), `人物`/`キャラ` (character), and `挿絵`/`挿し絵` (insert).
  Regression test: `test_parse_epub_structure_classifies_japanese_image_roles`.
- **Reader-like preview:** the preview serializer now also exposes a readiness
  label, per-severity counts, page-progression direction, spine page-spread/nav
  flags, validation grouped by scope, and short untranslated chapter excerpts
  (`read_chapter_excerpt`, bounded by `_MAX_EXCERPTS`).
- **Preview UI:** `epub_preview.html` was rebuilt on the cockpit design system
  (panels, segmented section anchors, stat tiles, tables, badges, nested TOC
  tree, empty states, path clipping). The previous template referenced several
  non-existent CSS classes.
- **Discoverability:** the sandboxed source browser now offers a "preview" link
  for `.epub` entries, so translators can inspect structure before import.
- Full gate after fixes: `pytest` 843 passed / 4 skipped, `pyright` 0, `ruff
  check` + `ruff format --check` clean, `weaver --help` OK.

## Post-F recommendation

Use the stabilized parser/preview/fidelity surfaces for real EPUB fixture audits.
Open future work in small gates: export preservation integration first, then OCR
adapter design only after dependency/provider/security decisions are approved.
