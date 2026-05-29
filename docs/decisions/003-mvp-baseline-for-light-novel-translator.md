# ADR 003 — MVP Baseline for the Light-Novel Translator

## Status

Accepted

## Context

The product target is sharpened: **Weaver = a Japanese→English light-novel translation workbench**, web-cockpit-first. For long-form light novels, raw sentence translation is not the hard problem — **consistency across chapters** is (character names, terminology, world-building terms, honorifics, tone). The MVP must therefore treat consistency machinery as first-class, not optional.

The audit found the existing v0.6.0 codebase covers some of this and is missing the rest:

- **Exists:** provider registry (deepseek/gemini/ollama/custom/fake), resumable translate orchestrator, glossary workflow (extract/review/edit/conflicts/diff), EPUB import, EPUB + Markdown export, deterministic QA.
- **Missing:** character database, translation memory, TXT/HTML import, TXT/HTML/DOCX export, an explicit Volume tier, a two-column workspace with auto-save/revisions, and batch at volume/novel scope.

This ADR records the **MVP baseline** as a direction. It does not implement features — the gap analysis and sprint mapping live in `docs/MVP_SCOPE.md` and the active phase in `CLAUDE.md` (Task 5 of the reset).

## Decision

The **MVP Web Cockpit Foundation** must deliver, or explicitly sprint-map, these eight areas:

1. **Project management** — create project; import TXT/EPUB/HTML; organize Novel → Volume → Chapter.
2. **Translation workspace** — JP/EN two-column view; editable result; auto-save; revision history.
3. **AI translation** — configurable provider/model (OpenAI, Gemini, DeepSeek, Groq, OpenRouter, OpenAI-compatible `custom`); translate chapter, translate selection, safe retranslate.
4. **Glossary** — project-scoped add/edit/delete; injected into prompt context; model instructed to follow it.
5. **Character database** — JP name, EN name, gender, role, notes; project-scoped; injected into prompt context.
6. **Translation memory** — source→target store; lookup before the AI call; reuse on match; fall back to AI on miss; project-scoped.
7. **Batch translation** — chapter / volume / novel scope; progress + per-unit status; errors never silently kill a job.
8. **Export** — EPUB (priority), TXT, HTML, DOCX.

**Highest-impact, build-first:** glossary, character database, translation memory, context-aware translation, consistency checking — these protect long-novel consistency.

**Scope guard:** retranslate must not destroy prior output without confirmation/versioning. API keys remain env-var or secret-store only (ADR `004` / archived `0020`), never in project config.

## Consequences

Improves: a concrete, consistency-first definition of "done enough to polish"; every gap is owned by a sprint before any UI polish begins.

Tradeoffs: character DB + translation memory are net-new shared-core subsystems (data model, storage, prompt injection) — real work, deferred to sprints, not the baseline task. Advanced features (style presets, cost estimator, AI quality review) are explicitly out of the MVP gate.

## Related Files

- `docs/MVP_SCOPE.md` (gap table + acceptance checklist)
- `CLAUDE.md` (active phase + sprint plan)
- `src/weaver/services/{project,translation,glossary,export}.py`, `storage/`, `readers/`, `renderers/`
