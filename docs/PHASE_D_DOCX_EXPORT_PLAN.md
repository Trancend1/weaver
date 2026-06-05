# Phase D — DOCX Export Plan (D1: Audit & Architecture)

> **Status:** **D1–D4 complete.** Plan approved (custom OOXML writer, no `python-docx`,
> no new dependency); DOCX export implemented end-to-end (`renderers/docx.py` +
> `export_book.py` target + cockpit dropdown) with renderer/service/API/UI tests and
> full Gate-D regression. See §8 for the as-built outcome.
> **Scope guard:** DOCX is the *only* new export target. No combined EPUB/ZIP, no
> QA threshold config, no provider change, no EPUB/TXT/HTML behavior change.

This document is the source of truth for Phase D. It audits the current
volume-aware export system, decides the DOCX renderer strategy and dependency,
defines DOCX output behavior and formatting baseline, and lays out the staged
implementation (D2–D4) with a validation matrix.

---

## 1. Current export architecture (audit)

### 1.1 The pipeline, end to end

```
UI dropdown / API POST / CLI
        │  target = "epub" | "txt" | "html"
        ▼
services/export_book.py
  prepare_export()  → validates scope + target → ExportPlan (per-volume plans)
  run_export()      → loops volumes → _render_volume() per volume → ExportResult
        │
        ▼
  _render_volume(target):                       _resolved_chapters()
    epub + source=epub → renderers/epub.py        reads DB, builds
    epub + source≠epub → renderers/epub_synthesis  list[RenderChapter]
    txt               → renderers/txt.py          (title + (kind,text) blocks,
    html              → renderers/html.py          translation-or-source-fallback)
```

Key files audited:

| File | Role |
|------|------|
| [services/export_book.py](../src/weaver/services/export_book.py) | Volume-aware orchestrator: scope/target validation, per-volume planning, fallback resolution, render dispatch. **Framework-agnostic.** |
| [renderers/rendered_document.py](../src/weaver/renderers/rendered_document.py) | Shared value type `RenderChapter(title, blocks)` + `block_to_html(kind, text)`. The renderer contract. |
| [renderers/txt.py](../src/weaver/renderers/txt.py) | Pure TXT renderer (string builder). |
| [renderers/html.py](../src/weaver/renderers/html.py) | Pure HTML5 renderer (string builder, reuses `block_to_html`). |
| [renderers/epub_synthesis.py](../src/weaver/renderers/epub_synthesis.py) | Pure EPUB synthesis from `RenderChapter` (uses `ebooklib`). |
| [renderers/epub.py](../src/weaver/renderers/epub.py) | EPUB write-back into the original source EPUB (markup-preserving). |
| [api/routers/export.py](../src/weaver/api/routers/export.py) | FastAPI start/status/cancel/SSE job endpoints. Thin adapter. |
| [api/routers/ui.py](../src/weaver/api/routers/ui.py) | HTMX export trigger + job progress panel. |
| [api/routers/ui_qa.py](../src/weaver/api/routers/ui_qa.py) | Advisory `export/preflight` panel (passes `target` through). |
| [api/schemas.py](../src/weaver/api/schemas.py) | `ExportRequest.target: str = "epub"`. |
| [templates/project.html](../src/weaver/api/templates/project.html) | `<select name="target">` dropdown (EPUB/TXT/HTML). |

### 1.2 The renderer contract (the seam DOCX plugs into)

Every renderer consumes the same already-resolved shape — there is **no DB access
and no fallback logic in any renderer**:

```python
@dataclass(frozen=True)
class RenderChapter:
    title: str | None
    blocks: tuple[tuple[str, str], ...]   # ordered (kind, text)
```

`kind ∈ {"heading", "quote", "paragraph", <other>}`. The shared `block_to_html`
collapses unknown kinds to `<p>`. The export service has *already* picked the
publishable translation or its source fallback before the renderer sees the text.

**This is the only contract DOCX must honor.** A DOCX renderer is a fourth pure
renderer consuming `Sequence[RenderChapter]`, exactly parallel to `render_txt` /
`render_html`.

### 1.3 The dispatch + validation seam

DOCX wiring touches exactly these existing points (no structural change):

1. `export_book.py:59-61` — `ExportTarget` Literal + `EXPORT_TARGETS` frozenset.
   Add `"docx"`.
2. `export_book.py:450-482` — `_render_volume` `if/elif` dispatch chain. Add a
   `docx` branch calling the new renderer with `_resolved_chapters(...)`.
3. File naming (`export_book.py:418,421`) — `volume-{index:02d}-id{id}.{target}`
   already derives the extension from `target`; `.docx` works with **no change**.
4. `api/schemas.py` — `ExportRequest.target` is a free `str`; invalid targets are
   rejected by `prepare_export` → `ValueError` → HTTP 422. No schema change
   strictly required, but the docstring should list `docx`.
5. `templates/project.html:50-54` — add `<option value="docx">DOCX</option>`.
6. UI/preflight (`ui.py`, `ui_qa.py`) — pass `target` through verbatim; **no
   change needed** beyond the dropdown option.

### 1.4 Critical audit finding: DOCX always synthesizes (never re-reads source)

EPUB has two paths: write-back (source=epub, markup-preserving) vs synthesis
(source≠epub). **DOCX has no write-back path** — there is no "DOCX source format"
to preserve, and re-reading a source EPUB to reconstruct Word markup is out of
scope. DOCX therefore behaves like TXT/HTML: it **always** builds from
`_resolved_chapters(...)` (the DB-resolved `RenderChapter` list), regardless of
`source_format`. This is simpler than EPUB and requires no new resolution logic.

This satisfies the behavioral requirements automatically:

| Requirement | How it's already guaranteed by the contract |
|---|---|
| Per-volume artifact | `run_export` loops volumes; one artifact each. |
| Latest translation only | `list_export_segment_states` → `publishable_text` (latest attempt, hash-matched). |
| Manual edits preserved | `manual` is a publishable status; its text flows through unchanged. |
| Source fallback for untranslated | `publishable.get(segment.id, segment.source_text)` in `_resolved_chapters`. |
| No history export | Renderers only ever see resolved text, never attempt history. |

DOCX inherits all five for free. No new service logic — only a new renderer + a
dispatch branch + a target-set entry.

---

## 2. Dependency decision

**Recommendation: custom minimal OOXML writer — no new dependency.**

A `.docx` is a ZIP of a handful of flat XML parts (OpenXML WordprocessingML). For
Weaver's block model (title, headings, paragraphs, blockquotes, page breaks) the
required document is small and fully deterministic. Python ships `zipfile` and
the codebase already hand-writes TXT and HTML renderers with `xml.sax.saxutils`.

### 2.1 Options compared

| | **A. Custom minimal writer (recommended)** | **B. `python-docx`** |
|---|---|---|
| New dependency | **None** | `python-docx` **+ transitive `lxml`** (C-extension) |
| Offline install | Trivial (stdlib `zipfile` + string XML) | `lxml` needs a compiled wheel; heavier, can fail on locked-down offline boxes |
| Fits stack ethos | Yes — matches hand-rolled txt/html, "deterministic, minimal" | Adds a non-trivial dep tree for a small output |
| OOXML correctness burden | We own ~4 static XML parts + paragraph builder | Library guarantees valid output |
| `weaver[web]` sufficiency (exit criterion) | Met with zero deps | Requires adding `python-docx` to the `web` extra |
| Code volume | ~1 renderer file (~120–160 lines) incl. static templates | Smaller renderer, larger dep surface |
| ADR required | No (no dependency added) | **Yes** — stack §3 lists no DOCX lib; new dep = ADR per CLAUDE.md §4.2 |

### 2.2 Why custom writer wins here

- **Exit criterion alignment.** Phase D exit (§2.4 CLAUDE.md) demands "`weaver[web]`
  extra is sufficient (no new top-level dep without ADR)." A zero-dependency
  writer satisfies this with no ADR and no extra-list edit.
- **Offline-capability.** Weaver's headline trait is offline operation. `lxml` is a
  compiled dependency whose offline wheel availability is exactly the friction
  Weaver avoids. `zipfile` is stdlib.
- **Scope match.** EPUB justifiably uses `ebooklib` because EPUB packaging (NCX,
  nav, spine, manifest, rels) is genuinely complex. The DOCX we need is closer to
  the HTML renderer in complexity than to EPUB. The minimal OOXML surface is:
  - `[Content_Types].xml` (static)
  - `_rels/.rels` (static)
  - `word/_rels/document.xml.rels` (static / near-static)
  - `word/styles.xml` (static — defines Title, Heading1, Quote styles)
  - `word/document.xml` (generated from `RenderChapter` blocks)
- **Determinism.** Hand-written XML gives byte-stable output (important for the
  "deterministic by default" rule and for stable tests).

### 2.3 Fallback position

If, during D2, OOXML correctness proves a maintenance burden (e.g. Word
rejects the file, or styling needs grow), escalate to `python-docx` **via a short
ADR** added to `docs/decisions/` and place the dep under the `web` extra (so
`weaver[web]` stays sufficient). The renderer's public signature stays identical,
so the swap is internal. Default plan proceeds with the custom writer.

---

## 3. DOCX renderer design

New file: `src/weaver/renderers/docx.py` — pure renderer, parallel to `txt.py`.

### 3.1 Public signature (mirrors the existing renderers)

```python
@dataclass(frozen=True)
class DocxRenderResult:
    output_path: Path
    chapters: int
    blocks: int

def render_docx(
    *,
    output_path: Path,
    title: str,
    language: str,
    chapters: Sequence[RenderChapter],
) -> DocxRenderResult:
    ...
```

- No DB access, no fallback logic, no web/CLI types (ADR 002).
- Raises `ExportError` on write failure (same class TXT/HTML use — **no new error
  type**; `errors.py` unchanged).
- `output_path.parent.mkdir(parents=True, exist_ok=True)` then atomic-ish write of
  the ZIP (write to a temp path + `os.replace`, matching the codebase's
  valuable-state write discipline).

### 3.2 Block → OOXML mapping (parallel to `block_to_html`)

A new helper `block_to_docx_paragraph(kind, text) -> str` keeps the mapping in one
place, mirroring `block_to_html`:

| `kind` | HTML (today) | DOCX paragraph |
|---|---|---|
| `heading` | `<h2>` | `<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>…</w:t></w:r></w:p>` |
| `quote` | `<blockquote>` | `<w:p><w:pPr><w:pStyle w:val="Quote"/></w:pPr>…</w:p>` |
| `paragraph` / other | `<p>` | `<w:p><w:r><w:t xml:space="preserve">…</w:t></w:r></w:p>` |

Text is XML-escaped with `xml.sax.saxutils.escape` (same as the other renderers).
`xml:space="preserve"` guards leading/trailing whitespace.

### 3.3 Document structure

- **Title**: first paragraph, `Title` style, from `title`.
- **Per chapter**:
  - Chapter heading paragraph (`Heading1` style) from `chapter.title or
    "Chapter N"` (same fallback EPUB synthesis uses).
  - One paragraph per block via `block_to_docx_paragraph`.
  - **Page break between chapters**: apply `<w:pageBreakBefore/>` to each chapter
    heading *except the first*. (Cleaner than an empty break paragraph; no trailing
    blank page.)
- `language` flows into the document default `<w:lang>` in `styles.xml` for
  metadata parity with the EPUB/HTML `lang` attribute.

### 3.4 Static parts

`[Content_Types].xml`, `_rels/.rels`, `word/_rels/document.xml.rels`, and
`word/styles.xml` are module-level string constants (the styles part defines
`Title`, `Heading1`, and `Quote`). Only `word/document.xml` is generated. This
keeps the renderer auditable and the output minimal & valid.

### 3.5 Wiring in `export_book.py`

```python
ExportTarget = Literal["epub", "txt", "html", "docx"]
EXPORT_TARGETS = frozenset({"epub", "txt", "html", "docx"})
```

`_render_volume` gains a branch (after `html`):

```python
elif target == "docx":
    render_docx(
        output_path=plan.output_path,
        title=plan.volume_title,
        language=project.target_lang,
        chapters=_resolved_chapters(connection, plan, publishable=publishable),
    )
```

No other service change. The `ExportArtifact` accounting (translated/fallback
counts) is target-agnostic and already correct.

---

## 4. API / UI / CLI impact

| Surface | Change | Notes |
|---|---|---|
| `EXPORT_TARGETS` / `ExportTarget` | add `"docx"` | Single source of truth for validation. |
| `_render_volume` dispatch | add `docx` branch | The only logic change. |
| `api/schemas.py` `ExportRequest` | docstring lists `docx` | No validation change (service validates). |
| `api/routers/export.py` | **none** | Generic over `target`. |
| `api/routers/ui.py` | **none** | Generic; reads `target` from the form. |
| `api/routers/ui_qa.py` preflight | **none** | Passes `target` through. |
| `templates/project.html` | add `<option value="docx">DOCX</option>` | One line. |
| `templates/partials/_export_preflight.html` | **none** | Already forwards hidden `target`. |
| **Legacy CLI** (`weaver export`, `services/export.py`) | **none** | Out of scope — single-volume, markdown/epub only. DOCX is a cockpit feature (matches CLAUDE.md "multi-volume is the cockpit's job"). |

No FastAPI route, job-flow, SSE, schema-validation, or progress change. DOCX is a
new value flowing through an already-generic pipeline.

---

## 5. Validation matrix

Tests mirror the source tree (`tests/unit/renderers/test_docx.py` new;
`tests/unit/services/test_export_book.py` extended; one API/UI test). All use
`FakeProvider`/fixtures — no live LLM, public-domain fixtures only.

| # | Layer | Test | Asserts |
|---|---|---|---|
| V1 | renderer | `render_docx` writes a file | output exists, `.docx`, non-empty |
| V2 | renderer | output is a valid ZIP with required parts | `zipfile.is_zipfile` true; contains `[Content_Types].xml`, `word/document.xml`, `word/styles.xml`, `_rels/.rels` |
| V3 | renderer | block kinds map to styles | `document.xml` has `Title`, `Heading1` per chapter, `Quote` for quote blocks, plain `<w:p>` for paragraphs |
| V4 | renderer | page break between chapters | `pageBreakBefore` present on chapters 2..N, **absent** on chapter 1 |
| V5 | renderer | XML-escaping | text with `&`/`<`/`>`/`"` is escaped; no malformed XML |
| V6 | renderer | empty chapter list | valid minimal docx, `chapters=0` |
| V7 | service | `export_novel(target="docx")` | one artifact per volume, `target="docx"`, `.docx` paths |
| V8 | service | volume + chapter scope `docx` | correct filenames (`volume-..`, `chapter-..`), counts |
| V9 | service | fallback for untranslated | untranslated segment renders source text; `fallback_segments` counted |
| V10 | service | manual edit preserved | `manual`-status segment's text appears verbatim |
| V11 | service | DOCX never re-reads EPUB source | monkeypatch `read_epub` asserts not called (mirror existing `test_export_txt_does_not_reread_epub_source`) |
| V12 | service | read-only | no translation rows written (mirror `test_export_writes_no_translation_rows`) |
| V13 | api | `POST …/export/novel {"target":"docx"}` → 202 | job starts, terminal status has `target="docx"` |
| V14 | api | unsupported target still 422 | regression: `prepare_export` rejects e.g. `"pdf"` |
| V15 | ui | dropdown renders DOCX option | `project.html` GET contains `value="docx"` |
| V16 | regression | full suite green | `pytest`, `pyright` 0, `ruff` + format clean; existing 703 tests unaffected |

**Acceptance (Phase D DOCX slice, from CLAUDE.md §2.4):**

- [ ] `target="docx"` produces a valid `.docx` (opens in Word/LibreOffice; V2/V3 cover structure).
- [ ] `weaver[web]` install is sufficient — no new top-level dep (custom writer ⇒ no dep at all).
- [ ] Per-volume artifact; latest translation only; manual preserved; source fallback; no history. (V7–V12)
- [ ] EPUB/TXT/HTML behavior unchanged (V16 regression; no edits to those renderers).
- [ ] Docs updated (D4).
- [ ] One PR per concern; no auto-fix, no provider call in the new path.

---

## 6. Staged implementation plan

> Each stage stops at its gate (CLAUDE.md §2.2) for inspection. No stage starts
> until the prior gate passes.

| Stage | Deliverable | Gate criteria |
|---|---|---|
| **D1 — Audit & plan** *(this doc)* ✅ | `docs/PHASE_D_DOCX_EXPORT_PLAN.md`: architecture audit, dependency recommendation, renderer design, API/UI impact, validation matrix, staged plan. **No code.** | Plan approved; dependency decision accepted. ✅ |
| **D2 — Renderer + service target** ✅ | `renderers/docx.py` (`render_docx`, `_block_paragraph`, `DocxRenderResult`); add `"docx"` to `ExportTarget`/`EXPORT_TARGETS`; `_render_volume` branch. Tests V1–V12. | V1–V12 green; pyright/ruff clean; EPUB/TXT/HTML tests untouched & passing. ✅ |
| **D3 — API/UI integration** ✅ | `ExportRequest` docstring; `project.html` DOCX option. Tests V13–V15. | V13–V15 green; soak/job flow unaffected; UI dropdown → export → artifact. ✅ |
| **D4 — Docs + regression + release note** ✅ | Update TRANSLATION_PIPELINE, COCKPIT_WORKFLOW, ARCHITECTURE, QUICKSTART, MAINTENANCE, CHANGELOG `[Unreleased]`, CLAUDE.md; doc map entry for this plan. Full regression (V16). | All docs updated; full suite green; CHANGELOG entry added; CLAUDE.md phase log row. ✅ |

> The shared block→paragraph mapping ships as a private `_block_paragraph` inside
> `renderers/docx.py` (single consumer) rather than a shared
> `block_to_docx_paragraph` in `rendered_document.py` — `block_to_html` lives in the
> shared module because it has two consumers (EPUB synthesis + HTML); the DOCX
> mapping has one, and folds in the docx-only page-break concern.

**Out of scope for all of Phase D's DOCX slice** (explicit non-goals, no
scaffolding): combined EPUB/ZIP bundle, QA threshold config (`[qa]` table),
QA tree badges, provider hardening, legacy-CLI DOCX, DOCX images/cover/TOC field,
styling beyond the §3.2 baseline.

---

## 7. Gate D1 sign-off (resolved)

1. **Dependency** → **custom minimal OOXML writer** approved (no dependency, no ADR).
2. **Formatting baseline** → title + `Heading1` headings + paragraphs + `Quote`
   blockquote + page break before chapters 2..N, confirmed. No cover page.
3. **Blockquote styling** → built-in `Quote` paragraph style, confirmed.

---

## 8. As-built outcome (D2–D4)

Implemented exactly as designed; no deviation from §1–§6.

**Files changed**

| File | Change |
|---|---|
| `src/weaver/renderers/docx.py` | **new** — `render_docx`, `DocxRenderResult`, static OOXML parts, `_block_paragraph` mapping, atomic ZIP write. |
| `src/weaver/services/export_book.py` | `"docx"` added to `ExportTarget`/`EXPORT_TARGETS`; `render_docx` import; `_render_volume` DOCX branch. |
| `src/weaver/api/schemas.py` | `ExportRequest` docstring now lists `epub/txt/html/docx`. |
| `src/weaver/api/templates/project.html` | `<option value="docx">DOCX</option>`. |
| `tests/unit/renderers/test_docx.py` | **new** — 6 renderer tests (V1–V6). |
| `tests/unit/services/test_export_book.py` | +5 DOCX service tests (V7–V12); the unsupported-target test now uses `pdf` (V14). |
| `tests/unit/api/test_export.py` | +1 DOCX endpoint test (V13); 422 test now uses `pdf`. |
| `tests/unit/api/test_ui_jobs.py` | DOCX added to dropdown + export parametrize (V15). |

No change to `api/routers/export.py`, `api/routers/ui.py`, `api/routers/ui_qa.py`,
`api/jobs.py`, or any EPUB/TXT/HTML renderer — confirming the pipeline was already
generic over `target`.

**DOCX package structure (as written by `_build_package`)**

```
my.docx (ZIP, deflated)
├── [Content_Types].xml              # declares document + styles content types
├── _rels/.rels                      # root rel → word/document.xml
├── word/_rels/document.xml.rels     # document rel → styles.xml
├── word/styles.xml                  # Normal, Title, Heading1, Quote + docDefaults lang
└── word/document.xml                # <w:body> of styled <w:p> paragraphs + <w:sectPr/>
```

**Validation result** — see §5 matrix; all V1–V16 green. Gate-D commands:
`pytest` (full suite green), `pyright` 0 errors, `ruff check` + `ruff format --check`
clean, `weaver --help` OK, cockpit + DOCX export smoke OK.

**Known DOCX limitations (intentional, baseline scope)**

- No images, footnotes, endnotes, or embedded fonts.
- No table of contents field, cover page, headers/footers, or page numbers.
- No styling beyond Title / Heading1 / Normal / Quote; no per-run formatting
  (bold/italic spans inside a block are not preserved — blocks are plain text).
- Per-volume artifacts only; **no merged-omnibus DOCX** (a combined EPUB/ZIP bundle
  is a separate, deferred Phase D item).
- DOCX is cockpit-only; the legacy `weaver export` CLI is unchanged (markdown/epub).
