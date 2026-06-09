# Page Layout Blueprint

> **Purpose.** Target layout for every page in the audited IA, reconciled with the actual cockpit. Source: [`docs/sourceofarchitecture.md`](../../docs/sourceofarchitecture.md) §5–19, §23. Build state from [THE_COUNCIL_WEAVER_AUDIT](THE_COUNCIL_WEAVER_AUDIT.md).
> **Constraint.** Stack is locked: server-rendered **Jinja2 + HTMX, no SPA, no build** (ADR 004/007). Every layout below is achievable with partial swaps; none requires a client framework.
> **Legend.** ✅ exists · ◑ partial · ⬜ new.

---

## 0. Global shell (applies to every page)

```text
┌───────────────────────────────────────────────────────────────────────┐
│ TOPBAR:  [Weaver]  ……………………………………………  [Active jobs ◍]  [Config] │
├───────────┬───────────────────────────────────────────────────────────┤
│ WORKSPACE │  CONTEXT BAR:  Project › Volume › Chapter   |  Stage  | Next │
│ SIDEBAR   ├───────────────────────────────────────────────────────────┤
│ (global)  │                                                             │
│           │  MAIN CONTENT (page-specific)                               │
│  Projects │                                                             │
│  Queue    │                                                             │
│  Resources│                                                             │
│  Providers│                                                             │
│  Exports  │                                                             │
│  Settings │                                                             │
└───────────┴───────────────────────────────────────────────────────────┘
│ FOOTER: runs locally on your machine                                    │
```

- **Workspace Sidebar (⬜ new, `sourceofarchitecture.md §8`).** Global, persistent, project-independent. Answers *"which area of the workspace?"*. Today there is no global sidebar — only a per-project one and a topbar (`base.html:21`, `_sidebar.html`). **Rule (§8):** the sidebar structure never changes on navigation; only main content + the contextual panel + selection change.
- **Context Bar (◑).** Always shows active Project / Volume / Chapter + current stage + primary next action (`§23`). Today this is partly carried by per-page breadcrumbs (`_page_header.html`); promote it to a persistent bar.
- **Topbar (◑→fix).** Replace today's `Dashboard / New project / Config` with `Weaver` (→ Dashboard) · global search (Q) · **Active jobs** · **Config**. Fix the "Dashboard"-labels-"Projects" mismatch (P-04).
- **Contextual Project Side Panel (◑).** Only inside a project; answers *"where am I in this novel?"* (`§10`). Today this is the chapter tree in `_sidebar.html:42`; extend it with volume nodes + per-node status + issue markers.

---

## 1. Dashboard `/` (◑ flat today)

**Today:** a project-grid titled "Projects" (`dashboard.html`). **Target (`§6`):** a global command center.

```text
CONTEXT: (global)
┌─ Current Project ───────────────┐ ┌─ Provider Health ───────────┐
│ Title · active volume · chapter │ │ active · fallback · avg ms  │
│ progress %  · last activity     │ │ recent failures · est. cost │
│ [Continue Translation] [Open]   │ └─────────────────────────────┘
│ [Run Validation] [Preview]      │ ┌─ Translation Queue ─────────┐
└─────────────────────────────────┘ │ waiting/processing/review/  │
┌─ In Progress ──┐ ┌─ Recently ───┐ │ failed/completed (counts)   │
│ project cards  │ │ Completed    │ └─────────────────────────────┘
│ progress/status│ │ [Open Export]│ ┌─ Recent Activity ───────────┐
└────────────────┘ └──────────────┘ │ timeline (imports, jobs…)   │
                                     └─────────────────────────────┘
```

- **Blocks:** Current Project · In Progress · Recently Completed · Translation Queue · Provider Health · Recent Activity (`§6.1–6.6`).
- **Dependency:** Queue / Provider-Health / Activity are **cross-project** → require the cross-project read layer (P-09). **Sprint Q.** The "Current Project + In Progress" cards are achievable from existing per-project discovery → **Sprint P** can ship a lighter Dashboard first.

---

## 2. Project Overview `/ui/projects/{id}` (⬜ today = tree)

**Today:** tree + import + export panels (`project.html`). **Target (`§11`):** an overview; move tree/import/export to their own tabs.

```text
CONTEXT: Project
┌─ Project Summary ───────────────────────────┐ ┌─ Quick Actions ───────────┐
│ Title · Author · JP→EN · N vols · chapters  │ │ [Continue Translation]    │
│ · segments · imported · last edited · status│ │ [Open Last Chapter]       │
└─────────────────────────────────────────────┘ │ [Run Validation]          │
┌─ Translation Progress ──────┐ ┌─ Health ─────┐ │ [Preview EPUB]            │
│ translated/reviewed/        │ │ glossary cov.│ │ [Export EPUB]             │
│ validated/failed/manual     │ │ char consist.│ │ [Open Glossary/Chars]     │
│ pending export              │ │ untranslated │ └───────────────────────────┘
└─────────────────────────────┘ │ missing img  │ ┌─ Current Activity ────────┐
                                 │ warnings     │ │ last chapter/segment/job  │
                                 └──────────────┘ └───────────────────────────┘
```

- **Tabs within Project:** Overview · Content Explorer · Editor · Review & Validation · Preview · Export · Analytics (`§9`). Today these are scattered sidebar links + subnav with duplication (P-04).
- **Sprint:** P (Overview + tab reframe), Q (Analytics, Health depth).

---

## 3. Content Explorer `/ui/projects/{id}/volumes/{vid}` (◑ = structure preview)

**Target (`§12`):** file-tree + reading-order inspector + asset browser in one.

```text
CONTEXT: Project › Volume
┌─ Volume Tree (spine order) ─┐ ┌─ Detail (selected node) ─────────────────┐
│ Cover                        │ │ Chapter: title · N segments              │
│ Color Illustrations          │ │ translated% · reviewed% · validation     │
│ Character Introduction       │ │ [Open in Editor] [Run Validation]        │
│ Chapter 1 …                  │ ├──────────────────────────────────────────┤
│ Interlude / Afterword / Bonus│ │ Asset browser · Metadata · Warnings tabs │
└──────────────────────────────┘ └──────────────────────────────────────────┘
```

- Reading order **follows the EPUB spine, not raw file order** (`§12.1`) — already true in the snapshot.
- Structure Warnings reuse the persisted snapshot validation (`epub_preview.html:205`).
- **Sprint:** P (reframe preview → Explorer entry + node status), Q (segment list + full asset browser).

---

## 4. Translation Editor `/ui/projects/{id}/volumes/{vid}/chapters/{cid}` (◑ = 2-col)

**Today:** 2-column JP/EN + job panel (`workspace.html`). **Target (`§13.1`):** 3 columns.

```text
CONTEXT: Project › Volume › Chapter   | progress bar | [Translate][Retranslate ▾]
┌ Content tree ┐┌ Editor ───────────────────────┐┌ Context panel ──────────┐
│ Volume       ││ ▸ Segment (source JP)         ││ Detected glossary terms │
│ Chapter      ││   Translation (editable)      ││ Characters in segment   │
│ Segment list ││   status badge · notes        ││ AI Candidates [Generate]│
│ (jump/filter)││   [Save][Generate][Compare]   ││ History (on demand)     │
│              ││   [Approve][Approve as manual] ││ Consistency warnings    │
└──────────────┘└───────────────────────────────┘└─────────────────────────┘
│ Job panel (SSE/poll, cancel) — refresh-safe                               │
```

- **New vs today:** the right **Context panel** (glossary/characters/**candidates with a Generate button**/history) — P-01 + the editor 3-column gap.
- **Keep:** filters, jump, shortcuts, manual-protect, append-only history (`workspace.html`).
- **Sprint:** P.

---

## 5. Review (human) `/ui/projects/{id}/volumes/{vid}/review` (◑ split across pages)

**Today:** separate Candidates + Drafts pages, list-only, no generation. **Target (`§14.1`, `§14.5`):** a Review Queue + resolution workflow.

```text
CONTEXT: Project › Volume — Review
┌─ Filters: chapter · severity · type · status · last edited ─────────────┐
├─ Review Queue ──────────────────────────────────────────────────────────┤
│ ☐ Needs Review   ☐ Needs Revision  ☐ Suspicious  ☐ Glossary conflict    │
│ ☐ Character conflict  ☐ Untranslated                                     │
│  ── per item: source snippet · current translation · issue · actions ──  │
│     [Open in Editor][Accept][Edit][Retranslate][Ignore once][Resolved]   │
│     [Add to Glossary][Add Character Mapping][Generate candidate]         │
└──────────────────────────────────────────────────────────────────────────┘
```

- **Persistent review status** per segment (P-03) drives the queue.
- Candidate + character-draft cards live here (with **Generate** — P-01); apply remains non-destructive.
- **Sprint:** P (queue MVP + generation + review status), Q (full resolution actions).

---

## 6. Validation (automatic) `/ui/projects/{id}/.../validation` (◑ = QA pages)

**Today:** QA report pages (`qa.html`, `ui_qa.py`) — translation checks only. **Target (`§14.2–14.4`):** one report, translation + structure.

```text
CONTEXT: Project/Volume/Chapter — Validation
┌ Badge: clean/warnings/errors · counts by severity (info/warning/error/critical) ┐
├ Filters: severity · category (completeness/staleness/consistency/quality/        │
│          export_readiness/structure) ───────────────────────────────────────────┤
│ Issue list: rule · severity · message · [Open affected chapter/segment]          │
│ Roll-ups: per chapter · per volume                                               │
└──────────────────────────────────────────────────────────────────────────────────┘
```

- Add a **structure** category sourced from the persisted snapshot (P-06); add `error` tier.
- **Review & Validation** may share one module page with two tabs (route `/quality` per `§21`) — but the two concerns stay distinct.
- **Sprint:** P.

---

## 7. Reading Preview `/ui/projects/{id}/volumes/{vid}/preview` (⬜ new)

**Target (`§15`):** translated reading simulation + before/after. **Today:** none (the "preview" route is structure/source — P-02).

```text
CONTEXT: Project › Volume — Preview
┌ Mode: [Reading] [Before/After] [Structure] ─────────────────────────────┐
│ READING:  cover → color illustrations → chapter title → translated flow  │
│           → inserts → afterword → bonus   (renders translated output)     │
│ BEFORE/AFTER:  source JP  |  translated EN   (per segment / per chapter)  │
│ STRUCTURE:  final order (cover · TOC · chapters · interlude · afterword)  │
└──────────────────────────────────────────────────────────────────────────┘
```

- Render via the export renderer (`renderers/rendered_document`) **without writing files**.
- **Sprint:** P.

---

## 8. Export `/ui/projects/{id}/.../export` (◑ = preflight + trigger)

**Today:** preflight panel + format select + trigger on the project page (`project.html:65`). **Target (`§16`):** a dedicated Export surface.

```text
CONTEXT: Project — Export
┌ Export Readiness: chapters translated · criticals resolved · images ·    ┐
│                   metadata · TOC · glossary conflicts · structure valid    │
├ Format: [EPUB][TXT][HTML][DOCX]   Settings: ☐preserve struct ☐images ……   │
├ Validation Gate:  Draft (always)  |  Final (☐ require clean — opt-in)      │
├ [Export Draft]  [Export Final]                                            │
├ Export History: date · format · status · validation · path · size · ver   │
└───────────────────────────────────────────────────────────────────────────┘
```

- Keep advisory default; add **opt-in** Final gate + Draft/Final distinction (P-07); add **Export History** ledger.
- **Sprint:** P (gate toggle + Draft/Final), Q (history + settings panel).

---

## 9. Knowledge: Glossary & Characters `/ui/projects/{id}/{glossary,characters}` (✅)

**Today:** glossary CRUD + candidate review (approve/edit/reject, conflicts, coverage diff); character DB CRUD (`ui_admin.py`). These are the **most complete** review loops in the app. **Target:** keep; relocate under a **Resources** grouping (project-level) per `§17`; surface them in the editor context panel (cross-link).

```text
GLOSSARY: term table (source→target, category, notes) · candidate queue · conflicts · coverage diff
CHARACTERS: jp_name → en_name · gender/role/notes · (drafts feed from Review)
```

- **Sprint:** P (cross-link into editor), Q (Workspace-level shared Resources).

---

## 10. Workspace hubs: Queue · Resources · Providers · Exports · Settings (⬜)

**Target (`§5`, §17–19):** global operational areas in the Workspace sidebar.

| Hub | Content | Today | Sprint |
|---|---|---|---|
| Translation Queue | cross-project jobs by state | per-project jobs only (`routers/ui.py:235`) | Q (needs P-09) |
| Resources | shared glossaries / character DB / TM / prompt templates / style guides | per-project only | Q |
| Providers | active/fallback, routing, cost, history, health | config form only (`/ui/config`) | Q |
| Exports | generated exports, queue, templates | per-project export only | Q |
| Settings | workspace settings · preferences · diagnostics | `/ui/config` + `weaver doctor` | P (consolidate) |
| Analytics | progress/quality/review/AI-usage/glossary/export metrics (`§19`) | none | Q |

All cross-project hubs depend on the **cross-project read layer** (P-09). They are **Sprint Q (Workspace v2)**.

---

## 11. Empty / Warning / Error states (`§23.2–23.3`)

Every page must implement the three-question contract:
- **Empty:** what's missing · why it matters · first action (`_empty_state.html` exists ✅ — extend everywhere).
- **Warning:** what · which part · blocking? · recommended action.
- **Error (404/422):** `not_found.html` / `error.html` exist ✅; ensure each carries a next-command (the `WeaverError` "what failed / likely cause / next command" contract already does this in services).
