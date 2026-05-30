# MVP Scope

The MVP target is a **consistency-first JP→EN light-novel translator**, web-cockpit-first (ADR 003). For long novels the hard problem is consistency (names, terms, honorifics, tone) across chapters — so glossary, character DB, and translation memory are first-class, not optional.

> **Task 5 finalized (2026-05-29).** The gap table below is verified against `src/weaver/` (module listing + grep for character DB, translation memory, Volume tier, readers/renderers). The active phase/sprint table lives in [CLAUDE.md §2](../CLAUDE.md).

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
| Character database | **missing** | only char-string ops (`core/segment.py`, `providers/parser.py`) | full feature absent — net-new model + storage + injection | P0 | 4 |
| Translation memory | **missing** | none (grep `translation_memory`/`Memory` = 0) | absent — net-new store + lookup-before-AI | P0 | 5 |
| Batch translation | partial | resumable orchestrator in `services/translation.py`; web single-job (`web/job_manager.py`) | no volume/novel scope; no job hierarchy | P1 | 6 |
| Export | partial | `services/export.py` (Markdown), `renderers/epub.py` | no TXT/HTML/DOCX renderer | P1 | 7 |

Status: `exists` = usable · `partial` = some structure, not complete · `missing` = no meaningful support. Priority: `P0` = MVP blocker · `P1` = MVP-required, lower risk.

## Sprint mapping (MVP Web Cockpit Foundation)

| Sprint | Delivers |
|---|---|
| 1 | Novel/Volume/Chapter model; TXT/EPUB/HTML import; project detail |
| 2 | JP/EN two-column workspace; edit; auto-save; basic revisions |
| 3 | Provider/model config (FastAPI-safe boundary, Pydantic schemas); translate chapter/selection; safe retranslate |
| 4 | Project glossary + character database; prompt injection; consistency baseline |
| 5 | Translation memory; lookup-before-AI; reuse |
| 6 | Batch chapter/volume/novel; job status; progress |
| 7 | Export TXT/HTML/EPUB/DOCX |
| 8 | MVP stabilization: smoke CLI+web, regression, acceptance checklist, UI/UX plan |

## What must exist before UI polish
Create/import a project · manage chapters · edit source+translation side by side · run AI translation · glossary influences translation · character DB influences translation · TM reduces repeat calls · batch is monitorable · output exportable · every gap mapped to a sprint. UI polish (ADR 005) starts only after this bar is met.

## Acceptance checklist (gate before polish)
- [ ] Create a novel project
- [ ] Import TXT / EPUB / HTML
- [ ] Novel/Volume/Chapter structure exists
- [ ] JP/EN two-column workspace; edits persist; revision record
- [ ] Provider/model configurable; translate chapter + selection; safe retranslate
- [ ] Glossary project-scoped, injected, model instructed to follow
- [ ] Character DB project-scoped, injected
- [ ] TM: lookup before AI, reuse on match, AI fallback on miss
- [ ] Batch chapter/volume/novel; visible progress + per-unit status; errors not silent
- [ ] Export EPUB (priority) + TXT/HTML/DOCX present or sprint-mapped
- [ ] CLI not broken · web not broken · docs match code · active ADRs `001`+ · gaps sprint-mapped · no premature UI polish
