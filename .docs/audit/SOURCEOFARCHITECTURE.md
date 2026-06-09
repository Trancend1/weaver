# Weaver — Source of Architecture (Reconciled)

> **What this is.** The canonical product-architecture spec for Weaver, **rebuilt from the Council audit**. It reconciles the target IA/UX in [`docs/sourceofarchitecture.md`](../../docs/sourceofarchitecture.md) (the draft) with the **actual repository state**, and annotates every concept with its build status. This is the spec Sprints **P** and **Q** build against — use this, not the draft.
> **Build-state legend.** ✅ built · ◑ partial · ⬜ planned. Annotations reflect the repo as of 2026-06-09 (Sprints A–M complete).
> **Companions.** [Audit](THE_COUNCIL_WEAVER_AUDIT.md) · [Workflow](WORKFLOW_BLUEPRINT.md) · [Layouts](PAGE_LAYOUT_BLUEPRINT.md) · [Backlog](ISSUE_BACKLOG.md) · [Roadmap](ROADMAP_REPLAN.md).

---

## 1. Product purpose

**Weaver** is an offline-capable, glossary-aware **JP→EN light-novel translation workbench**. It imports a source (EPUB / TXT / HTML), helps a single user translate it under AI assistance with full manual control, checks quality, and exports a faithful result. It is a **local, single-user tool** — **not** a SaaS, hosted service, consumer product, or SPA.

The user keeps control through segment-level editing, glossary + character consistency, deterministic validation, and (target) review state, preview, and export history.

**Core loop:**
```text
Import → Inspect structure → Translate (chapter/segment) → Review (human) → Validate (auto) → Preview output → Export (versioned) → Iterate
```

---

## 2. Core product model ✅

Weaver manages a series scalably through a five-level hierarchy. This model is **built and consistent end-to-end** (ADR 011 finished the Novel→Project rename).

```text
Workspace                  ← all projects on the machine (filesystem discovery)
└── Project                ← one light-novel title / series (= one project.toml + one SQLite DB)
    └── Volume             ← one publication unit (typically one EPUB file)
        └── Chapter        ← one reading-order unit (EPUB spine, not raw file order)
            └── Segment     ← smallest unit of translation / review / validation / history
```

| Level | Meaning | Storage |
|---|---|---|
| Workspace | All projects under the books dir | Filesystem (`discover_projects`) — **not** a DB row |
| Project | One series | `projects` table (one row per DB) |
| Volume | One EPUB/TXT/HTML | `volumes` table |
| Chapter | One spine doc | `chapters` table (`spine_order`) |
| Segment | One text block | `segments` table |
| Export | Versioned output | per-volume artifact under `output/<target>/` (history ⬜) |

> **Architectural note (audit P-09).** "Workspace" exists only at the filesystem layer; each Project is an isolated DB. Cross-project features (Translation Queue, Provider Health, shared Resources, Analytics) need a **cross-project read layer** (Sprint Q) — they are not free under one-DB-per-project.

---

## 3. Information architecture

```text
Dashboard            global command center                    ◑ (flat project list today)
Workspace (global)   Projects · Queue · Resources ·            ⬜ (no global sidebar today)
                     Providers · Exports · Settings
Project Workspace    Overview · Content Explorer · Editor ·    ◑ (scattered; no Overview)
                     Review & Validation · Preview · Export · Analytics
```

| Area | Function | Scope | Build |
|---|---|---|---|
| Dashboard | Global summary + resume work | Global | ◑ project grid only |
| Workspace sidebar | Operational hubs across projects | Global | ⬜ |
| Project Overview | One project's status at a glance | Project | ⬜ |
| Content Explorer | Volume/chapter/segment/asset structure | Volume | ◑ (structure preview) |
| Translation Editor | Translate/edit segments | Chapter/Segment | ◑ (2-col, no context panel) |
| Review (human) | Editorial checkpoint + queue | Segment/Chapter | ◑ (candidates list; no gen UI; no review state) |
| Validation (auto) | Deterministic QA report | Chapter/Volume/Novel | ✅ (translation only; structure unjoined) |
| Preview (output) | Reading simulation + before/after | Volume | ⬜ |
| Export | Versioned output + gate + history | Volume/Project | ◑ (advisory only; no history) |
| Analytics | Progress/quality/cost metrics | Project | ⬜ |

---

## 4. Navigation model

Two navigation systems, kept strictly separate (`sourceofarchitecture.md §7`). Today they are **triplicated and inconsistent** (audit P-04); the target is below.

### 4.1 Persistent Workspace Sidebar ⬜ (global)
Answers *"which area of the workspace?"*. Structure never changes on navigation.
```text
Projects (active/recent/favorite/new) · Translation Queue · Resources
(glossaries/characters/TM/prompts/style guides) · Providers · Exports · Settings
```

### 4.2 Contextual Project Side Panel ◑ (per project)
Answers *"where am I in this novel?"*. Today: a chapter tree grouped by volume title (`_sidebar.html:42`). Target: volume nodes + chapters + front-matter/illustrations/afterword/bonus + per-node status + issue markers.

### 4.3 Three-question contract
Every primary page must answer (`§23`): **What am I working on · Where is progress · What is next.** Carry this in a persistent context bar (Project › Volume › Chapter · stage · next action).

---

## 5. Status model (canonical) — *the single taxonomy*

> This section is the **authoritative status taxonomy** (audit WV-006). All five axes are independent; DB, API, and UI must map to these names. The right column records today's reality and the gap.

### 5.1 Translation status (per segment)
| Canonical | DB today (`segments.status`) | Gap |
|---|---|---|
| Untranslated | `pending` | rename at presentation |
| Translating | `in_progress` | — |
| Translated | `translated` | — |
| Manually Edited | `manual` | — |
| Failed | `failed` | — |
| Stale | `stale` | (extra; keep) |
| Skipped | `skipped` | (extra; keep) |
| **Locked** | — | ⬜ not modeled |

> Dead UI branches `reused`/`tm`/`memory` are **not** valid segment statuses (TM reuse stores a `memory`-tagged *attempt*; the segment becomes `translated`). Remove them (WV-006).

### 5.2 Review status (per segment) ⬜ — **new axis (WV-003)**
`Not Reviewed · Needs Review · Needs Revision · Approved · Rejected`. Not modeled today; candidate/draft `approved/rejected` is a *different* concept (the suggestion, not the final translation's review state).

### 5.3 Validation status (per scope) ◑
`Not Checked · Passed · Warning · Failed · Critical`. Today QA emits `info/warning/critical` (badge `clean/warnings/errors`), computed on demand, not persisted, **no `error` tier** (WV-008), **structure checks separate** (WV-007).

### 5.4 Export status (per volume) ⬜ — **not persisted (WV-009)**
`Not Ready · Draft Ready · Ready · Exporting · Exported · Failed`. Volume lifecycle explicitly defers `exported` (`volume_lifecycle.py:18-23`).

### 5.5 Job status (per job) ✅
| Canonical | DB today (`jobs.status`) |
|---|---|
| Waiting | `queued` |
| Processing | `running` |
| Cancelling | *(cooperative; not persisted)* |
| Cancelled | `cancelled` |
| Completed | `done` |
| Failed | `failed` |
Reserved: `processed`, `finalizing`. Align labels at presentation.

### 5.6 Derived volume lifecycle ✅ (UI convenience)
`empty · imported · in_progress · translated · translating` — recomputed from counts + JobRegistry (`volume_lifecycle.py`). Keep as a *derived* convenience, not a sixth persisted axis.

---

## 6. Routes (reconciled)

Target routes are short, lowercase, slug-friendly (`sourceofarchitecture.md §21`). The repo uses `/ui/...` with project **name** (not id). The target adds a stable id (WV-010) but **does not require a `/workspace` prefix rewrite** — `/ui` is the established root (`app.py:159`).

| Concept | Today (built) | Target |
|---|---|---|
| Dashboard | `/ui` ✅ | `/ui` |
| New project | `/ui/new` ✅ | `/ui/new` |
| Project Overview | `/ui/projects/{name}` ◑ (tree) | `/ui/projects/{id}` (overview) |
| Content Explorer | `/ui/projects/{name}/volumes/{vid}/structure` ◑ | `/ui/projects/{id}/volumes/{vid}` |
| Translation Editor | `/ui/projects/{name}/chapters/{cid}` ◑ | `/ui/projects/{id}/volumes/{vid}/chapters/{cid}` |
| Review (human) | (candidates/drafts pages) ◑ | `/ui/projects/{id}/volumes/{vid}/review` |
| Validation (auto) | `/ui/projects/{name}/qa` ✅ | `/ui/projects/{id}/.../validation` (or `/quality` combined) |
| Reading Preview | — ⬜ | `/ui/projects/{id}/volumes/{vid}/preview` |
| Export | `/ui/projects/{name}/export` ◑ | `/ui/projects/{id}/.../export` |
| Config / Settings | `/ui/config` ✅ | `/ui/settings` (grouped) |

> Route changes are **non-breaking-first**: add id resolution alongside name (WV-010) before deprecating name-based URLs. Combined Review+Validation may live at `/quality` (`§21`) with two tabs.

---

## 7. Module reference (where each concept lives) ✅

| Concept | Code |
|---|---|
| Import / read | `readers/{epub,txt,html}.py` → `core/ir.DocumentIR` → `core/ir.scope_document_to_volume` |
| Structure parse | `readers/epub.parse_epub_structure` → `core/epub_structure.ParsedEpub`; `readers/epub_validation.py` |
| Snapshot | `services/epub_snapshot.py`, `services/epub_reparse.py`; tables `epub_snapshot*` |
| Translate | `services/{translation,workspace_translate,batch_translate}.py`; jobs `api/jobs.py` |
| TM / glossary / characters | `services/{translation_memory,glossary*,characters}.py`; `storage/*` |
| Candidates / drafts | `services/{candidate_generation,candidate_apply,character_draft}.py`; `storage/{candidates,character_drafts}.py` |
| Validation (auto) | `services/translation_qa.py`; `qa/{checks,consistency_checks,scope_checks}.py` |
| Preview (output) | ⬜ (target: reuse `renderers/rendered_document`) |
| Export | `services/export_book.py`; `renderers/{epub,epub_synthesis,txt,html,docx}.py`; `services/epub_export_fidelity.py` |
| Jobs | `api/jobs.py`, `services/job_store.py`; tables `jobs`/`job_events`/`job_progress_snapshots` |
| UI | `api/routers/{ui,ui_admin,ui_qa}.py`; `api/templates/**`; `api/ui_context.py` |
| Runtime / desktop | `api/app.py`, `services/{app_paths,runtime_env,logging_setup}.py`; `docs/SIDECAR_CONTRACT.md` |

Layer rule (ADR 002/004): shared/core (`services/storage/core/providers/readers/renderers/qa`) is framework-agnostic; only `api/` is framework-coupled; CLI/web are thin callers; **state writes go through services**.

---

## 8. Main modules (target spec, build-annotated)

### 8.1 Dashboard ◑ → target `§6`
Command center: **Current Project · In Progress · Recently Completed · Translation Queue · Provider Health · Recent Activity.** Today: flat project grid. Queue/Health/Activity need the cross-project layer (Sprint Q); Current/In-Progress can ship in Sprint P from per-project discovery.

### 8.2 Project Overview ⬜ → target `§11`
Summary · Translation Progress · Current Activity · Project Health · Recent Changes · Quick Actions. **Sprint P.**

### 8.3 Content Explorer ◑ → target `§12`
Volume tree (spine order) · Chapter list · Segment list · Asset browser · Metadata inspector · Structure warnings. Today: structure preview surface (snapshot-backed). **Sprint P** reframes the entry; **Sprint Q** adds segment list + full asset browser.

### 8.4 Translation Editor ◑ → target `§13`
3-column: Content tree | Editor | **Context panel** (glossary/characters/AI candidates/history/consistency). Today: 2-column + job panel, no context panel, no candidate generation. **Sprint P** (WV-001, WV-013).

### 8.5 Review (human) ◑ → target `§14.1, §14.5`
Review Queue + resolution workflow + persistent per-segment review status. Candidate/draft cards with **Generate** (non-destructive apply). Today: list-only, generation JSON-only, no review state. **Sprint P** (WV-001, WV-003).

### 8.6 Validation (auto) ✅/◑ → target `§14.2–14.4`
One deterministic report covering translation **and** structure; severities `info/warning/error/critical`; categories incl. `structure`. Today: translation checks only, 3 severities, structure unjoined. **Sprint P** (WV-007, WV-008).

### 8.7 Preview (output) ⬜ → target `§15`
Reading Preview (translated flow) · Before/After · Image-in-context · Structure Preview. Render via export renderer, no file write. **Sprint P** (WV-002).

### 8.8 Export ◑ → target `§16`
Readiness · Format · Settings · **Validation Gate** (Draft always / Final opt-in clean) · **Export History** · Output files. Today: advisory only, no Final gate, no history, atomic + fidelity-checked + per-volume. **Sprint P** (gate toggle) + **Sprint Q** (history).

### 8.9 Resources / Providers / Analytics ⬜ → target `§17–19`
Workspace + project-level shared resources; provider routing/cost/health; progress/quality/AI-usage analytics. All cross-project → **Sprint Q** (needs WV-010).

---

## 9. Ideal workflow (target) → see [WORKFLOW_BLUEPRINT](WORKFLOW_BLUEPRINT.md)

```text
Dashboard → Open Project → Project Overview → Select Volume → Content Explorer
→ Translate (3-col editor, generate candidates non-destructively)
→ Review (queue + persistent review status) ⇄ Validate (auto, translation+structure)
→ Reading Preview (translated output + before/after)
→ Export (Draft always / Final opt-in clean, versioned + history)
→ Iterate (refresh-safe jobs, recoverable)
```

---

## 10. UX principles ✅ (keep) / ◑ (extend)

- Every page answers **context / progress / next action** (`§23`). ◑ extend via the persistent context bar.
- **Deterministic by default**; LLM only where determinism is impossible, output is verifiable, and the user can override (ADR 008 + CLAUDE.md §4.3). ✅
- **No anti-slop UI** (no "smart/AI-powered/magical", no chat/avatars/sparkles). ✅
- Empty/Warning/Error states answer *what's missing / why / first action* and *what / where / blocking? / recommended action* (`§23.2–23.3`). ◑ extend everywhere.
- Microcopy: specific, action-oriented, names the impact and the next step (`§23.1`). ◑.
- **Secrets** via env / `~/.weaver/secrets.toml` only — never in config, logs, render, or SSE. ✅

---

## 11. What is locked (do not change without an ADR)

- Stack: Python 3.11+ · FastAPI · Jinja2 + HTMX (no SPA/build) · SQLite (WAL, no ORM) · typer + rich.
- Job model: in-process, single-process, SQLite-durable; **no** Celery/Redis/RQ/external worker (ADR 010).
- `read_epub()`/`DocumentIR` is the translation path; `ParsedEpub` is the structural layer — **do not merge**.
- Tauri is a packaging shell in `desktop/`, not a Python dependency (ADR 009).
- Provider keys via env/secret store; never rendered/logged.

---

## 12. Provenance

This document supersedes the draft `docs/sourceofarchitecture.md` for planning purposes. The draft remains the historical input; this reconciled version is build-state-accurate and is the spec of record for Sprints P and Q. When the draft and this document disagree, **this document wins**; when this document and code disagree, **code is the evidence and an issue is filed** (per the build-state annotations above).
