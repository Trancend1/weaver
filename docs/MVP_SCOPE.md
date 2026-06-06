# MVP Scope

The MVP target is a **consistency-first JP→EN light-novel translator**, web-cockpit-first (ADR 003). For long novels the hard problem is consistency (names, terms, honorifics, tone) across chapters — so glossary, character DB, and translation memory are first-class, not optional.

> **Task 5 finalized (2026-05-29).** The gap table below is verified against `src/weaver/` (module listing + grep for character DB, translation memory, Volume tier, readers/renderers). The active phase/sprint table lives in [CLAUDE.md §2](../CLAUDE.md).
>
> **Progress (2026-06-02):** Sprints 1–8 shipped — Volume tier, FastAPI workspace + per-segment save + revision history, AI translate/retranslate, glossary, character database, translation memory (lookup-before-AI + reuse), **batch translation at chapter/volume/novel scope** (`services/batch_translate.py` + `api/routers/batch.py`, aggregate progress + cooperative cancel + SSE), and **volume-aware export** — EPUB (8A) + FastAPI export endpoints (8B) + TXT/HTML output (8C) via `services/export_book.py` + `renderers/{epub,epub_synthesis,txt,html}.py` + `api/routers/export.py`. Remaining export gap: **DOCX output (deferred, out of MVP) + export UI (deferred, post-MVP polish per ADR 005)**. **Sprint 9 (MVP stabilization) complete** — baseline evidence in git history. Live per-sprint detail: [CLAUDE.md §2.5](../CLAUDE.md). The snapshot table below is annotated with what has since shipped.

## Required MVP features

1. **Project management** — create project; import TXT/EPUB/HTML; organize Novel → Volume → Chapter.
2. **Translation workspace** — JP/EN two-column; editable; auto-save; revision history.
3. **AI translation** — configurable provider/model (OpenAI, Gemini, DeepSeek, Groq, OpenRouter, OpenAI-compatible `custom`); translate chapter / selection; safe retranslate.
4. **Glossary** — project-scoped CRUD; injected into prompt; model instructed to follow.
5. **Character database** — JP/EN name, gender, role, notes; project-scoped; injected into prompt.
6. **Translation memory** — source→target store; lookup before AI call; reuse on match; AI fallback.
7. **Batch translation** — chapter / volume / novel; progress + per-unit status; no silent failure.
8. **Export** — EPUB (priority), TXT, HTML, DOCX.

## Highest-impact (build-first)
Glossary · Character database · Translation memory · Context-aware translation · Consistency checking. These protect long-novel consistency and are the reason the product exists.

## Advanced (not MVP blockers)
Translation style presets · honorific rules (partial: `preserve`/`localize`/`hybrid` exists) · consistency checker · terminology checker · cost estimator · AI quality review.

## Gap analysis (finalized Task 5, verified against `src/weaver/`)

| MVP Area | Status | Evidence | Gap | Priority | Sprint |
|---|---|---|---|---|---|
| Project management | partial | `services/project.py`, `storage/projects.py`, `readers/epub.py` (only reader) | EPUB-only import; no Volume tier (grep `Volume` = 0); no TXT/HTML reader | P0 | 1 |
| Translation workspace | partial | `services/translation.py`, `services/manual_edit.py` | no 2-col UI; no auto-save; no revision store | P0 | 2 |
| AI translation | exists | `providers/registry.py` → `fake/deepseek/gemini/ollama/custom`; FastAPI chapter/selection translate via `services/workspace_translate.py` + `api/routers/translate.py` + `api/jobs.py` (Sprint 4A) | native OpenAI/Groq/OpenRouter absent but OpenAI-compatible `custom` covers them; 4A skips already-translated (safe-retranslate = 4C) | P0 | 4 |
| Glossary | exists | `services/glossary.py`, `glossary_review.py`, `glossary_diff.py`, web review | strong; prompt-injection wiring to confirm in sprint | P0 | 4 (polish) |
| Character database | exists ✅ (Sprint 5) | `storage/characters.py`, `services/characters.py`, `api/routers/characters.py`; `<characters>` prompt block | shipped — schema v4, project-scoped CRUD + prompt injection | P0 | 5 |
| Translation memory | exists ✅ (Sprint 6) | `storage/translation_memory.py`, `services/translation_memory.py`, `api/routers/translation_memory.py`; lookup/save in `translate_one_segment` | shipped — schema v5, lookup-before-AI, reuse, manual source-of-truth, `GET/DELETE …/memory` | P0 | 6 |
| Batch translation | exists ✅ (Sprint 7) | `services/batch_translate.py`, `api/routers/batch.py`, `BatchJob` in `api/jobs.py`; chapter/volume/novel scope + aggregate progress + cancel + SSE | shipped — reuses chapter pipeline; no external queue | P1 | 7 |
| Export | partial (Sprint 8A+8B+8C) | `services/export_book.py` (novel/volume/chapter → per-volume EPUB/TXT/HTML), `renderers/{epub,epub_synthesis,txt,html}.py`; `api/routers/export.py` + `ExportJob` (FastAPI export jobs); legacy `services/export.py` (Markdown) | DOCX output + export UI (deferred) | P1 | 8 |

Status: `exists` = usable · `partial` = some structure, not complete · `missing` = no meaningful support. Priority: `P0` = MVP blocker · `P1` = MVP-required, lower risk.

## Sprint mapping (MVP Web Cockpit Foundation)

| Sprint | Delivers |
|---|---|
| 1 | Novel/Volume/Chapter model; TXT/EPUB/HTML import; project detail |
| 2 | JP/EN two-column workspace; edit; auto-save; basic revisions |
| 3 | Translation workspace (FastAPI): two-column read, edit, save, revision history |
| 4 | Provider/model config; translate chapter/selection; safe retranslate |
| 5 | Project glossary + character database; prompt injection; consistency baseline |
| 6 | Translation memory; lookup-before-AI; reuse |
| 7 | Batch chapter/volume/novel; job status; aggregate progress; cancel |
| 8 | Export EPUB (priority) + TXT/HTML/DOCX |
| 9 | MVP stabilization: smoke CLI+web, regression, acceptance checklist, UI/UX plan |

> Numbering follows [CLAUDE.md §2.1](../CLAUDE.md) (FastAPI foundation inserted as Sprint 2; remaining sprints shifted +1; Flask decommission appended as Sprint 10).

## What must exist before UI polish
Create/import a project · manage chapters · edit source+translation side by side · run AI translation · glossary influences translation · character DB influences translation · TM reduces repeat calls · batch is monitorable · output exportable · every gap mapped to a sprint. UI polish (ADR 005) starts only after this bar is met.

## Acceptance checklist (gate before polish)
- [x] Create a novel project
- [x] Import TXT / EPUB / HTML
- [x] Novel/Volume/Chapter structure exists
- [x] JP/EN two-column workspace; edits persist; revision record
- [x] Provider/model configurable; translate chapter + selection; safe retranslate
- [x] Glossary project-scoped, injected, model instructed to follow
- [x] Character DB project-scoped, injected
- [x] TM: lookup before AI, reuse on match, AI fallback on miss
- [x] Batch chapter/volume/novel; visible progress + per-unit status; errors not silent — Sprint 7 (API; monitor UI deferred)
- [x] Export EPUB (priority) + TXT/HTML present; DOCX deferred (out of MVP) — Sprint 8A–8C: EPUB/TXT/HTML output + FastAPI export endpoints (`api/routers/export.py`); `target="docx"` returns 422 (handled deferral). DOCX output + export UI are deferred, not blockers
- [x] CLI not broken · web not broken · docs match code · active ADRs `001`+ · gaps sprint-mapped · no premature UI polish — **final gate Sprint 9 PASSED** (9A audit + validation ✅; 9B doc alignment ✅; 9C E2E proof ✅ on the real light-novel EPUB → **MVP baseline LOCKED**). Baseline evidence in git history.
