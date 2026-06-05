# Phase B — Translation QA & Consistency Checks · Stage B1 Plan

> **Status:** Stage B1 (audit & design only — **no code**). Gate B1 deliverable.
> **Baseline:** `v0.7.0-rc.1` + Phase A UI polish (FastAPI is the sole web cockpit).
> **Core principle — _report first, fix later._** Phase B only **reads** data and produces a QA
> report. It must not mutate any translation, call a provider/LLM, or do semantic/vector analysis.
> **Non-goals (Phase B rules):** no auto-fix · no provider calls · no DB mutation · no semantic/vector
> search · no parallel QA system · no React/Vue/Node (UI stays Jinja2 + HTMX) · no visual polish
> beyond a usable layout.

---

## 1. Headline decision

**Reuse and extend the existing QA layer; do not build a parallel one.** Weaver already ships a
deterministic, framework-agnostic per-segment QA engine (`weaver.qa.checks`) consumed by
`weaver validate` (via `services/qa.py`). Phase B keeps that single source of truth for per-segment
rule logic, and adds (a) **Novel/Volume/Chapter scoping**, (b) a small set of **new deterministic
rules** (character-name consistency, repeated translation, fallback-heavy / mixed-status / untranslated
at scope level), and (c) **web report API + UI + a pre-export warning**.

**Severity stays `info | warning | critical`** — the existing vocabulary is preserved; the draft
plan's `error` is **rejected** in the data layer and mapped to the presentation word "error" only
(see §4).

---

## 2. Existing QA inventory (audit)

| Asset | Location | What it is | Phase B disposition |
|-------|----------|-----------|---------------------|
| `Severity` | `qa/checks.py:12` | `Literal["info","warning","critical"]` | **Reuse verbatim** as `QASeverity`. |
| `SegmentInput` | `qa/checks.py:19` | Frozen per-segment record (`segment_id`, `source_text`, `normalized_source_text`, `status`, `translation_text`) | **Reuse.** |
| `QAWarning` | `qa/checks.py:35` | Frozen per-segment finding (`segment_id`, `check_name`, `severity`, `message`) | **Reuse** as the per-segment finding; lifted into the richer `QAIssue` at the service boundary. |
| `check_empty_translation` | `qa/checks.py:45` | published segment with empty text → `critical` | **Reuse.** |
| `check_untranslated_japanese` | `qa/checks.py:60` | ≥4 contiguous JP chars in translation (JP leak) → `critical` | **Reuse.** |
| `check_length_ratio` | `qa/checks.py:76` | translation/source length ratio < min → `warning` | **Reuse** ("suspiciously short"). |
| `check_glossary_mismatch` | `qa/checks.py:95` | approved glossary source matched but target absent → `warning` | **Reuse** (template for the new character check). |
| `check_failed_segment` | `qa/checks.py:133` | status `failed` → `critical` | **Reuse.** |
| `check_stale_segment` | `qa/checks.py:146` | status `stale` → `warning` | **Reuse.** |
| `run_all_checks(...)` | `qa/checks.py:159` | aggregates the 6 per-segment checks; `[qa]` config flags + `minimum_length_ratio` | **Reuse** inside the new service's per-segment loop. |
| `validate_project` / `ValidationReport` | `services/qa.py:35` | `weaver validate` engine: read-only DB, **single flat project, project-wide**, no Volume/Chapter scope | **Keep unchanged** (CLI wire-compat). Shares `qa/checks` with Phase B → no duplication. |
| `format_report_json` / `qa_report_schema` | `services/qa.py:92` `:117` | `--json` payload (`schema_version`, summary `{info,warning,critical}`, findings) + schema description; references **ADR 0010** for versioning | Phase B report schema must stay **consistent** with this and bump `schema_version`. |
| `weaver validate` CLI | `cli/main.py` | runs `validate_project`, prints findings, exit `1` on any `critical` | **Unchanged.** Remains the CLI surface; cockpit QA is the additive scope-aware surface. |

**Key gaps the existing engine does not cover** (and Phase B must add):
1. **Scoping** — `services/qa.py._load_segments` (`services/qa.py:160`) loads *all* segments for the
   single flat project; no chapter/volume/novel report. `_load_single_project` (`:200`) predates the
   Novel/Volume/Chapter model.
2. **Character-name consistency** — no check over the character DB.
3. **Cross-segment / scope rules** — no repeated-translation, fallback-heavy, mixed-status, or
   "segment not yet translated" (status-level) rule.

**Read functions already available** (the new service composes these; all read-only):

| Need | Function | Location |
|------|----------|----------|
| Read-only connection | `connect_readonly_database` | `storage/db.py` |
| Scope → chapter ids | `list_chapter_ids_for_volume`, `list_chapter_ids_for_project` | `storage/segments.py:301` `:319` |
| Chapter existence / record | `chapter_exists`, `get_chapter` → `ChapterRecord` | `storage/segments.py:255` `:270` |
| Segments in a chapter | `list_chapter_segments` → `SegmentRecord` | `storage/segments.py:226` |
| Publishable / fallback state | `list_export_segment_states` → `ExportSegmentState(id,status,publishable_text)` | `storage/translations.py:211` `:196` |
| Glossary terms | `list_glossary_terms` → `GlossaryTerm` | `storage/glossary.py` |
| Characters | `list_characters` → `CharacterRecord(jp_name,en_name,gender,role,notes)` | `storage/characters.py:25` |
| Volumes / tree counts | `list_volumes`, `project_tree` (`ChapterView`/`VolumeView`/`NovelTree`, incl. `done_count`) | `storage/volumes.py`, `services/project_tree.py:57` |
| Segment status vocabulary | `pending · in_progress · translated · failed · stale · skipped · manual` | `storage/schema.sql:42` |
| Published statuses | `{translated, manual}` | `qa/checks.py:16` |

---

## 3. Architecture recommendation

Preserve the existing **pure-checks / service** split and extend it:

```
weaver/qa/checks.py            (EXISTING)  pure per-segment primitives — REUSE, unchanged
weaver/qa/consistency_checks.py (NEW)      pure: character-name consistency, untranslated-status (per-segment)
weaver/qa/scope_checks.py       (NEW)      pure: repeated-translation, fallback-heavy, mixed-status (collection/scope)
services/translation_qa.py      (NEW, B2)  framework-agnostic orchestration: read DB → run rules → QAReport
api/routers/qa.py               (NEW, B3)  thin JSON adapter (Pydantic at boundary only)
api/routers/ui_qa.py            (NEW, B4)  presentation-only Jinja2+HTMX report pages/fragments
services/qa.py                  (EXISTING) weaver validate — KEEP; both share weaver.qa.checks
```

**Why new modules (not bloat `checks.py`):** `qa/checks.py` already exposes 7 public functions
(over the §4.2 "≤5 public functions / one concept per file" guideline). New rule functions go in
new, focused modules that **import** `QAWarning`/`QASeverity`/`SegmentInput` from `checks.py` — one
finding type, one severity enum, zero duplication. No refactor of the existing file is in scope.

**Data flow (read-only, deterministic):**

```
analyze_chapter/volume/novel(project_toml, scope_id)
  └─ connect_readonly_database(db_path)                # ADR 0017 read-only handle
       ├─ resolve scope → [chapter_id...]              # list_chapter_ids_for_volume/project
       ├─ load SegmentInput[] for scope                # NEW scoped loader (see §6 B2)
       ├─ load glossary terms + characters             # list_glossary_terms / list_characters
       ├─ load export states (publishable/fallback)    # list_export_segment_states (DRY w/ export)
       ├─ per segment: run_all_checks(...) + new per-segment rules
       └─ per chapter/scope: scope rules (repeated, fallback-heavy, mixed-status)
  └─ aggregate → QAReport (frozen dataclass)           # Pydantic only later, at the API boundary
```

**No parallel system, restated:** per-segment rule *logic* lives only in `weaver/qa/*`. Both
`services/qa.py` (CLI) and `services/translation_qa.py` (cockpit) call those same pure functions.
The "fallback-heavy" rule reuses `list_export_segment_states` — the **same** publishable rule the
exporter uses (`export_book.py`), so QA and export never disagree about what counts as published.

---

## 4. Severity decision

**Keep `info | warning | critical`. Reject introducing `error` into the data/wire layer.**

Rationale:
- The existing `Severity` type, `weaver validate --json` payload, `qa_report_schema()`, the
  exit-code contract (**any `critical` → exit 1**), ADR 0010, and the QA tests all use `critical`.
  Renaming to `error` breaks that contract for zero functional gain.
- One enum, imported from `qa/checks.py`, keeps CLI and cockpit reports identical in vocabulary.

**Mapping (presentation only):** the cockpit may *label* `critical` as **"Error"** in the UI, and the
project/chapter/tree **badge** uses states `clean` / `warnings` / `errors`. The wire value stays
`critical`. For count fields the API uses **`critical_count`** (consistent with the enum), not the
draft's `error_count` — this is a deliberate deviation from the draft B3 shape for internal
consistency; the UI prints "Errors: N" from `critical_count`.

| Draft plan term | Phase B decision |
|-----------------|------------------|
| severity `error` | **`critical`** (reused) |
| `error_count` (API field) | **`critical_count`** |
| badge state `errors` | kept as a **UI label**, computed from `critical_count > 0` |

Badge rule: `errors` if `critical_count > 0`; else `warnings` if `warning_count > 0`; else `clean`
(info-only does not raise a badge).

---

## 5. Deterministic rule list

Per-segment rules reuse `weaver.qa.checks`; new rules are pure functions in the new modules. All
are deterministic and read-only.

| # | Rule (`check_name`) | Scope | Severity | Source | Data needed |
|---|---------------------|-------|----------|--------|-------------|
| 1 | `failed_segment` | segment | `critical` | reuse `check_failed_segment` | status |
| 2 | `empty_translation` | segment | `critical` | reuse `check_empty_translation` | status + text |
| 3 | `untranslated_japanese` (JP leak) | segment | `critical` | reuse `check_untranslated_japanese` | translation text |
| 4 | `stale_segment` | segment | `warning` | reuse `check_stale_segment` | status |
| 5 | `length_ratio` (suspiciously short) | segment | `warning` | reuse `check_length_ratio` | source + translation len |
| 6 | `glossary_mismatch` | segment | `warning` | reuse `check_glossary_mismatch` | glossary terms + texts |
| 7 | `untranslated_segment` | segment | `warning` | **new** (`consistency_checks`) | status ∈ {pending, in_progress, skipped} |
| 8 | `character_name_missing` | segment | `warning` | **new** (`consistency_checks`) | characters: jp_name in source, en_name absent in translation (mirrors rule 6) |
| 9 | `repeated_identical_translation` | chapter | `warning` | **new** (`scope_checks`) | same published translation text for ≥2 segments whose sources differ; min-length guard to skip short interjections |
| 10 | `fallback_heavy_chapter` | chapter | `warning` | **new** (`scope_checks`) | fraction of segments with `publishable_text is None` ≥ threshold (+ min segment count) |
| 11 | `mixed_status_chapter` | chapter | `info` | **new** (`scope_checks`) | chapter mixes published and unpublished/failed/stale statuses (partial progress) |

Thresholds — **module-level constants first; not `[qa]`-configurable yet** (Gate B1 decision; QA
config can be added later if users need it). `minimum_length_ratio = 0.3` (existing `[qa]` flag,
unchanged) · `fallback_heavy_ratio = 0.5` · `fallback_heavy_min_segments = 5` · `repeated_min_chars = 8`
(the last three are new constants in `scope_checks.py`, no config surface in Phase B).

**Issue categories** (`QACategory`): `completeness` (1,2,7) · `staleness` (4) · `consistency` (6,8) ·
`quality` (3,5,9) · `export_readiness` (10,11).

---

## 6. Report schema proposal

Service returns **frozen dataclasses** (framework-agnostic); Pydantic mirrors them only at the API
boundary (B3). Consistent with `qa_report_schema()` / ADR 0010; `schema_version` bumped.

```python
QASeverity = Literal["info", "warning", "critical"]          # imported from qa.checks.Severity
QACategory = Literal["completeness","staleness","consistency","quality","export_readiness"]
QAScope    = Literal["chapter","volume","novel"]

@dataclass(frozen=True)
class QAIssue:
    rule: str                 # check_name
    category: QACategory
    severity: QASeverity      # info|warning|critical
    message: str
    segment_id: str | None    # set for segment-scope rules
    chapter_id: str | None    # set for chapter/segment rules

@dataclass(frozen=True)
class QAScopeSummary:         # per-chapter (in volume/novel) or per-volume (in novel)
    scope: Literal["chapter","volume"]
    id: str
    title: str | None
    total_issues: int
    info_count: int
    warning_count: int
    critical_count: int
    badge: Literal["clean","warnings","errors"]

@dataclass(frozen=True)
class QAReport:
    schema_version: int
    project: str
    scope: QAScope
    scope_id: str             # chapter_id | str(volume_id) | project name (novel)
    total_segments: int
    total_issues: int
    info_count: int
    warning_count: int
    critical_count: int
    badge: Literal["clean","warnings","errors"]
    issues: tuple[QAIssue, ...]
    summary_by_category: dict[QACategory, int]
    summary_by_chapter: tuple[QAScopeSummary, ...]   # chapter scope: empty
    summary_by_volume: tuple[QAScopeSummary, ...]    # only at novel scope
```

JSON shape (B3 response; `…/chapters/{id}/qa` example):

```json
{
  "schema_version": 2,
  "project": "my-novel",
  "scope": "chapter",
  "scope_id": "ch_…",
  "total_segments": 120,
  "total_issues": 7,
  "info_count": 2, "warning_count": 4, "critical_count": 1,
  "badge": "errors",
  "issues": [
    {"rule":"failed_segment","category":"completeness","severity":"critical",
     "message":"Segment is marked failed.","segment_id":"seg_…","chapter_id":"ch_…"}
  ],
  "summary_by_category": {"completeness":3,"consistency":2,"quality":1,"export_readiness":1},
  "summary_by_chapter": [],
  "summary_by_volume": []
}
```

- **chapter** report: `summary_by_chapter`/`summary_by_volume` empty; issues are segment+chapter scope.
- **volume** report: `summary_by_chapter` = one `QAScopeSummary` per chapter; issues aggregated.
- **novel** report: `summary_by_volume` = per-volume; `summary_by_chapter` = per-chapter (for badges).

---

## 7. Staged implementation plan (B2–B6)

Each stage stops at its gate (§2.2 of CLAUDE.md) for inspection. One PR = one concern.

### B2 — QA engine foundation (no API/UI)
- **New pure rules:** `weaver/qa/consistency_checks.py` (`check_untranslated_segment`,
  `check_character_name_missing(seg, characters)`), `weaver/qa/scope_checks.py`
  (`check_repeated_identical_translation(segments)`, `check_fallback_heavy(chapter_states, *, ratio, min_segments)`,
  `check_mixed_status(segments)`). Reuse `QAWarning`/`QASeverity`/`SegmentInput`.
- **New service:** `services/translation_qa.py` — `analyze_chapter(project_toml, chapter_id, *, cwd=None)`,
  `analyze_volume(project_toml, volume_id, *, cwd=None)`, `analyze_novel(project_toml, *, cwd=None)` →
  `QAReport`; data model (`QAReport`, `QAIssue`, `QASeverity`, `QACategory`, `QAScopeSummary`).
  Scoped segment loader (new SQL filtered by `chapter_id` / `volume_id` / `project_id`, mirroring
  `services/qa.py:160` but scoped); compose `run_all_checks` + new rules; reuse
  `list_export_segment_states`, `list_glossary_terms`, `list_characters`, `list_chapter_ids_for_*`,
  `get_chapter`.
- **Errors:** typed `WeaverError`s — reuse existing `ChapterNotFoundError` / `VolumeNotFoundError`
  (`errors.py:80` `:84`); validate existence via `chapter_exists` (`storage/segments.py:255`) /
  `list_chapter_ids_for_volume`.
- **Tests:** `tests/unit/qa/test_scope_checks.py`, `tests/unit/qa/test_consistency_checks.py`,
  `tests/unit/services/test_translation_qa.py` — a fixture DB proving every rule (1–11) fires and
  that clean data yields an empty report. One test asserts **no provider import / no write** on the
  QA path.
- **Gate B2:** engine + tests clean; pyright/ruff green. No API/UI.

### B3 — FastAPI QA API (no UI)
- `api/routers/qa.py` — `GET /projects/{name}/qa` (novel), `GET …/volumes/{id}/qa`,
  `GET …/chapters/{id}/qa`. Pydantic response models mirror the dataclasses. Thin adapter over B2.
- Unknown project/volume/chapter → 404 via existing handlers; reuse error mapping.
- **Tests:** `tests/integration/test_qa_api.py` — valid report per scope, 404s, JSON schema shape.
- **Gate B3:** API + tests clean. No UI.

### B4 — FastAPI UI QA report (no export integration)
- `api/routers/ui_qa.py` (presentation-only) — `GET /ui/projects/{name}/qa`,
  `GET /ui/projects/{name}/chapters/{id}/qa`. Templates `qa.html` + partials
  `_qa_summary.html`, `_qa_issues.html`; severity badge + category filter (HTMX query params).
- **Badges (Gate B1 decision):** **explicit QA pages first.** Project-page header badge + chapter-page
  badge come from the QA report rendered *on that page*. **Per-chapter tree badges are deferred** — do
  **not** run a full novel-scope QA scan automatically on every project-tree render. A lightweight
  summary badge may be added in a later slice only if it is proven performance-safe.
- **Tests:** `tests/integration/test_ui_qa.py` — pages render, filter narrows, badges reflect counts.
- **Gate B4:** usable UI; Jinja2 + HTMX only; no auto-fix. No export change yet.

### B5 — Export QA warning (advisory, non-blocking)
- Pre-export preflight in the export UI panel: before starting the export job, call
  `analyze_<scope>` and render a summary fragment (untranslated / failed / stale / fallback /
  glossary / character counts + total warning/critical) with **"Export anyway"** vs
  **"Review QA first"**. New route e.g. `GET /ui/projects/{name}/export/preflight?scope=…`.
- **Export behavior unchanged:** `services/export_book.py`, `run_export`, and the export endpoints
  are untouched; source fallback stays valid; the warning is advisory only.
- **Tests:** `tests/integration/test_ui_export_preflight.py` — warning shown when issues exist;
  export still reachable; clean project shows no blocker.
- **Gate B5:** warning works; no hard block.

### B6 — Docs & stabilization
- Docs: `TRANSLATION_PIPELINE.md` (QA stage), `COCKPIT_WORKFLOW.md` (QA API + UI + preflight),
  `ARCHITECTURE.md` (new modules), `QUICKSTART.md` (QA walk), `CLAUDE.md` (§2.5 phase log).
- Extend `qa_report_schema()` (or add a sibling describing the scoped report) and reconcile with
  ADR 0010; bump `schema_version`.
- Full regression: `pytest`, `pyright`, `ruff`; FastAPI UI + QA API smoke; export flow still works;
  assert **no translation mutation, no provider call** during QA.
- **Gate B6:** Phase B complete when B1–B5 stable and validation green.

---

## 8. Resolved decisions (Gate B1, maintainer)

1. **ADR 008 — yes.** Write `docs/decisions/008-translation-qa-architecture-and-severity.md`
   (doc-only) capturing §3–§4. Reason: the QA architecture + severity contract affects API/UI/CLI
   behavior, so it warrants an ADR.
2. **Severity — keep `info | warning | critical`.** Do not introduce `error` in the data/wire layer;
   UI may label `critical` as "Error" visually. **`repeated_identical_translation` → `warning`**
   (raised from the draft `info`); **`mixed_status_chapter` → `info`**.
3. **Thresholds — constants/defaults first, not `[qa]` config yet.** `fallback_heavy_ratio = 0.5`,
   `min_segments = 5`, `repeated_min_chars = 8` as module-level constants. Configurable QA thresholds
   may be added later if users need them.
4. **Tree badges — deferred.** B4 starts with explicit QA pages/reports; do not auto-run full novel
   QA on every tree render. An optional lightweight summary badge may come later only if perf-safe.
5. **`weaver validate` rebase — optional / not required** (B6 nicety only; must not change CLI
   output or exit codes). Left open, low priority.

---

## 9. Gate B1 — deliverables checklist

- [x] **QA architecture recommendation** — reuse/extend `weaver.qa.checks`; new pure-rule modules +
      `services/translation_qa.py`; no parallel system (§3).
- [x] **Existing QA inventory** — `weaver.qa.checks`, `services/qa.py`, `weaver validate`, reusable
      read functions, and the gaps (§2).
- [x] **Severity decision** — keep `info | warning | critical`; reject `error` in data, map to UI
      label only; `critical_count` field (§4).
- [x] **Report schema proposal** — `QAReport`/`QAIssue`/`QAScopeSummary`/`QACategory` + chapter/
      volume/novel JSON shape (§6).
- [x] **Rule list** — 11 deterministic rules (6 reused, 5 new) with scope/severity/source/data (§5).
- [x] **Staged implementation plan** — B2 engine → B3 API → B4 UI → B5 export warning → B6 docs (§7).
- [x] **Maintainer gate** — §8 decisions locked; **ADR 008** to be written, then B2 approved.

**Gate B1 PASSED.** Decisions recorded in §8 and ADR `008`. B2 may begin (engine + tests only).
