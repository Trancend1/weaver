# Sprint P — Workflow Coherence · Staged Execution Plan

> **Purpose of this document.** A *handoff-ready, gated* execution plan for Sprint P, sliced into small stages (P0–P7) that another agent (or human) can pick up one at a time. Each stage has its own gate so the sprint never advances on unverified work.
>
> **This is a plan, not an implementation.** Producing this document changed **no code**. Sprint P itself is executed later, stage by stage, on the branch named below.
>
> **Relationship to the audit docs.** This plan is the *operational staging layer*. The *issue-level detail* (evidence, exact reuse points, line numbers, gotchas) already lives in [.docs/audit/SPRINT_P_EXECUTION.md](../.docs/audit/SPRINT_P_EXECUTION.md). Each stage below cites the matching WV-item there — read that section before writing code. Spec of record: [.docs/audit/SOURCEOFARCHITECTURE.md](../.docs/audit/SOURCEOFARCHITECTURE.md); acceptance: [.docs/audit/ISSUE_BACKLOG.md](../.docs/audit/ISSUE_BACKLOG.md).

---

## 0. Branch, scope, and ground rules

### Branch

- **Do NOT continue on `feat/tauri-shell-alpha`** (that branch is Sprint N scaffold only; close its PR separately).
- **Recommended branch: `feat/workflow-coherence-p`**, cut from `main`.
- One PR per WV-item is preferred. Stages P1–P6 each map to ~one WV-item → ~one PR. P7 is the integration/PR-summary pass.
- If the Sprint N PR merges to `main` mid-sprint, rebase this branch on `main` (the two are independent; N is `desktop/` only, P is `src/weaver/` only).

### Hard scope fences (apply to every stage)

| Do NOT | Why |
|---|---|
| Touch `desktop/` | Sprint N's subtree; P is backend/cockpit only. |
| Start Sprint O (packaging/installer/signing) | Blocked until the O-gate (P1+P2) is green. |
| Start Sprint Q (cross-project Workspace hubs, Queue/Resources/Providers/Analytics, project-id layer) | Needs WV-010 + a cross-project read layer that does not exist. |
| Add React/Vue/Node/any build step or web font | Stack is locked: server-rendered Jinja2 + HTMX, HTMX vendored. |
| Implement OCR | Sprint M shipped the security gate only; OCR is out. |
| Add a provider / expand provider surface | Out of scope. |
| Add a schema migration | **Unless** a stage proves it necessary (only **P3** does — see there). Migrations must be additive, forward-only, idempotent, tested. |
| Add a runtime dependency | `pyproject.toml` runtime deps stay frozen (a new dep needs an ADR, not written inside P). |

### Layer & invariant rules (from the audit §0, summarized)

- `api/routers/ui*.py` are **thin adapters**: call a `services/*` function, render a template. No business logic, no SQLite in the UI layer.
- All state writes go through services, **one transaction**; a status transition lives in the same transaction as its data.
- **Do not rename/remove HTMX hooks:** `#tree`, `#ws-grid`, `#job-panel`, `#export-panel`, `#browser`, `#selected_source`, `#source_path`, `#qa-badge-status`, `#qa-issues`, `id="seg-{id}"`, `qa-badge-vol-*`, `qa-badge-ch-*`.
- Design tokens single-source: `api/static/app.css` `:root`. No magic numbers in templates.
- **Gate B1:** never run QA on a list/tree/overview render. QA is opt-in (button), computed on demand.
- When you intentionally change a user-facing string or layout marker, update the pinning test in the **same** PR: `tests/unit/api/test_ui_shell.py`, `test_ui_layout.py`, `test_ui_qa.py`, `test_ui_delete.py`.
- API keys never in config/logs/render/SSE. Contribution identity per CLAUDE.md §4.6 (no AI author metadata).

---

## ⚠️ Sequencing note (read before scheduling stages)

The stage **numbers** below follow the requested P0–P7 structure. The **dependency-correct execution order** differs in one place, and the executing agent should respect the dependency, not the number:

- The audit sequences **WV-006 (status taxonomy) _first_**, because Review (P3/WV-003), Navigation badges (P4/WV-004), and the editor consume the canonical status vocabulary. If WV-006 lands last (P6), P3 and P4 will hand-roll labels and then get retrofitted.
- **The O-gate items (P1/WV-001, P2/WV-002) have only weak taxonomy coupling** — they can ship before WV-006 with negligible rework, which is why they stay first (they must be provably done before Sprint O).

**Recommended real execution order:**

```
P0  →  P1 (WV-001 ★)  →  P2 (WV-002 ★)  →  P6 (WV-006)  →  P3 (WV-003)  →  P5 (WV-005)  →  P4 (WV-004)  →  P7
                         └── O-GATE done ──┘   └─ taxonomy lands before its consumers ─┘
```

If the team prefers to keep strict numeric order, P3 and P4 must introduce the `api/status_labels.py` helper incrementally and P6 then only *consumes* it everywhere — but pulling WV-006 to run right after P2 is cleaner and is the recommended path. **P4 (navigation) is the highest template-diff / highest UI-test-churn item; keep it after the O-gate and after WV-006 so a slip there cannot delay WV-001/002.**

★ = hard O-gate. Sprint O may not begin until **P1 and P2** are complete and gate-green.

---

## P0 — Audit & branch prep  *(no feature code)*

**Goal.** Establish the working branch and a verified map from each WV-item to the real files/tests, so every later stage starts from evidence, not assumption.

**In-scope.**
- Create `feat/workflow-coherence-p` from `main`.
- Confirm the working tree has **zero `desktop/` changes** and zero `src/weaver` drift vs the audit (the audit's line references were valid as of 2026-06-09).
- Re-verify the anchor points each stage depends on (spot-checked list below) and note any drift.
- Read [.docs/audit/SPRINT_P_EXECUTION.md](../.docs/audit/SPRINT_P_EXECUTION.md) §0–§2 and [SOURCEOFARCHITECTURE §5](../.docs/audit/SOURCEOFARCHITECTURE.md) (the five status axes).

**Out-of-scope.** Any edit under `src/weaver/`. Any migration. Any template change.

**Files likely touched.** None (this is orientation). Optional: a scratch note, not committed.

**Verified anchor map (confirmed valid at plan time):**

| WV | Anchor (confirmed) |
|---|---|
| WV-001 | `api/routers/candidates.py:146` (`/candidates/generate`), `:269` (`/drafts/generate`); UI review routes in `api/routers/ui.py` (~935–1133); `templates/partials/_segment.html:32` (review link, no generate); `candidates.html`, `_candidates_list.html`, `_drafts_list.html`. |
| WV-002 | `services/preview.py` (`preview_project` → `PreviewBlock`); `renderers/rendered_document.py`; `templates/epub_preview.html` (structure-only today); export writer `services/export_book.py` (**do not call**). |
| WV-006 | `qa/checks.py:12` (`Severity` 3-tier); `storage/schema.sql:42` (segment-status CHECK = the only valid set); dead branches in `_segment.html` + `workspace.html`. |
| WV-003 | `storage/db.py:13` (`SCHEMA_VERSION = 8`, no `review_status` column yet); `storage/migrations.py`; `services/workspace_edit.py` (txn pattern). |
| WV-005 | `templates/project.html`; `services/project_tree.py`; `services/job_store.py`. |
| WV-004 | `templates/base.html:21-25` (topbar); `partials/_sidebar.html`; `templates/project.html:21-27` (duplicated subnav); `api/ui_context.py` (layout modes). |

**Tests required.** None new. Run the baseline once to confirm green start: `uv run pytest -q` (expect **1043 passed / 4 skipped**).

**Acceptance criteria.**
- Branch `feat/workflow-coherence-p` exists off `main`; `git status` clean; no `desktop/` files in the diff.
- Anchor map re-confirmed (or drift documented).
- Baseline suite green.

**Handoff notes.** After P0, hand off **P1 (WV-001)** first. Do not batch stages. Each subsequent stage is its own PR.

---

## P1 — WV-001 Generate Candidate / Draft in the UI  ★ O-GATE

**Status: ✅ COMPLETE**

**Detail:** audit §WV-001.

**Goal.** Let a user **generate** a translation candidate (and a character-page draft) from the cockpit. Today generation exists only as services + JSON routes; the Candidates/Drafts review pages are dead-ends with no in-UI content source.

**In-scope.**
- A UI route + button for **per-segment** candidate generation in the editor (`_segment.html`), `hx-post` → re-rendered candidate card (reuse `_candidates_list.html` shape, like `ui_candidates_rerender_card`), with an `htmx-indicator`.
- A UI route + button for **character-draft** generation on `character_drafts.html`; re-render via `_drafts_list.html`; handle the "no character content" (`None`) case with a clear empty message.
- Provider/segment errors surfaced as an **HTMX error fragment** (reuse the existing error-fragment pattern), never a 500.

**Out-of-scope.**
- **Chapter/selection batch generation** — synchronous batch can exceed the request timeout; it needs `JobRegistry`. File it as a follow-up. Ship **per-segment** only.
- Any "apply on generate" shortcut. Generation creates a `pending` candidate and **must not** mutate the current translation.
- Generation logic in the UI route (thin adapter only — call the existing service).

**Files touched.** `api/routers/ui.py` (`ui_candidate_generate`, `ui_draft_generate`), `templates/partials/_segment.html`, `templates/character_drafts.html`.

**Tests.** UI tests with `FakeProvider` proving generate → pending → approve → apply; "no character content" path tested.

**Acceptance criteria.**
- ✅ From the editor, a user generates a candidate for a segment without leaving the page; it appears `pending`; the live translation is untouched until apply.
- ✅ Character drafts generate from the Drafts page; "no content" handled.
- ✅ Provider failure renders an inline error fragment, not an exception page.

**Handoff notes.** This is the single highest-leverage fix and **half of the O-gate**. Keep generation and apply cleanly separated. Do not touch the apply path's existing behavior.

---

## P2 — WV-002 Reading / output Preview  ★ O-GATE

**Status: ✅ COMPLETE**

**Detail:** audit §WV-002.

**Goal.** A read-only **Reading Preview** that renders the **translated** chapter/volume as it will read after export, plus a **Before/After** (source ↔ translation) view. Today the only preview shows *source* structure.

**In-scope.**
- A new **read-only service** (`services/reading_preview.py`) returning rendered translated chapter HTML **as a value/string** built from `renderers/rendered_document` blocks. **Writes nothing to disk.**
- UI routes `GET /ui/projects/{name}/volumes/{volume_id}/preview` (+ per-chapter variant) rendering a new `templates/reading_preview.html` with two modes: **Reading** (translated flow), **Before/After** (from `services/preview.preview_project`).
- Mirror the export **publishable rule** (`status ∈ {translated, manual}` AND `source_hash` matches latest attempt, else source fallback) so **preview == export**.

**Out-of-scope.**
- Calling `export_book` / `export_bundle` or writing any `output/` artifact.
- Any provider call or mutation (strictly read-only).
- A full reader app (pagination engine, bookmarks, settings, TTS, etc.). Furigana/ruby/vertical-text fidelity is unverified (WV-014, Sprint Q) — render what blocks contain; do not promise it.
- New image-byte endpoints (the Sprint M gated one already exists if needed).

**Files touched.** New `services/reading_preview.py`, new `templates/reading_preview.html`, `api/routers/ui.py` (`ui_volume_reading_preview`, `ui_chapter_reading_preview`). Reused `renderers/rendered_document.py`, `services/preview.py`.

**Tests.** Test asserting **zero files written** during preview; publishable-vs-fallback decision matches exporter; `prefers-reduced-motion` honored.

**Acceptance criteria.**
- ✅ A user previews the translated chapter/volume flow in-app; a Before/After toggle shows source↔translation per segment; no artifact is created on disk.

**Handoff notes.** After P2 passes gate-green, **the O-gate is satisfied** — record it.

---

## P3 — WV-003 Review status (persisted) + Review Queue

**Status: ✅ COMPLETE**

**Detail:** audit §WV-003.  *(This is the one stage that legitimately proves a migration is necessary.)*

**Goal.** Model the **human review** axis (distinct from automatic Validation) and give it a queue. Today "Reviewed/Approved" is not trackable.

**In-scope.**
- **Migration v8 → v9 (additive):** `segments.review_status TEXT NOT NULL DEFAULT 'not_reviewed'` with a CHECK over the five canonical values (`not_reviewed / needs_review / needs_revision / approved / rejected`, per SOURCEOFARCHITECTURE §5.2). Mirrored in `schema.sql` for fresh DBs.
- Service `services/segment_review.set_review_status(...)` — writes through one transaction; validates; raises `WeaverError` on bad input.
- Review Queue page `GET /ui/projects/{name}/volumes/{volume_id}/review` listing segments by review status with filter actions (`All/Not reviewed/Needs review/Needs revision/Approved/Rejected`).

**Out-of-scope.**
- Renaming any DB enum values (would force churn).
- A `segment_reviews` side-table (over-modeling for P; a column suffices).
- The fuller resolution action set from WORKFLOW_BLUEPRINT §5 (acceptable to trail).
- Auto-setting `review_status = approved` on candidate apply — **NO** (kept orthogonal; documented in PR).

**Files touched.** `storage/migrations.py`, `storage/schema.sql`, `storage/db.py` (bump `SCHEMA_VERSION` to 9), new `services/segment_review.py`, new `templates/review_queue.html`, `api/routers/ui.py` (`ui_review_queue`).

**Tests.** Migration **forward** test + **idempotency** test. Service unit tests. UI test: queue reflects status within one HTMX swap.

**Acceptance criteria.**
- ✅ Review status persists across reloads; Review Queue is functional; migration is additive, forward-only, idempotent, tested; review status is independent of translation status and candidate state.

---

## P4 — WV-004 Navigation coherence  *(reconcile only — no new hubs)*

**Status: ✅ COMPLETE**

**Detail:** audit §WV-004.

**Goal.** Remove triplicated/inconsistent navigation: one global nav shell + one contextual project panel; fix the "Dashboard" topbar label that opens a page titled "Projects"; drop the project-page subnav that duplicates the sidebar.

**In-scope.**
- Reconcile labels so the Dashboard topbar entry and the `/ui` page title agree ("Dashboard" everywhere); fix breadcrumb labels.
- Add Jobs entry to sidebar (was missing).
- Remove the project-page subnav duplication (`project.html`) — keep those entries only in the contextual sidebar.
- Dashboard breadcrumb root added to all child pages (`workspace.html`, `reading_preview.html`, `review_queue.html`, `epub_preview.html`).
- Standardize "Back to project" buttons.

**Out-of-scope.**
- Building any cross-project hub content (Queue/Resources/Providers/Exports/Analytics) — that is WV-010 / Sprint Q.
- Renaming HTMX hooks. Breaking the three layout modes (`ui_context.py`).

**Files touched.** `templates/dashboard.html`, `templates/partials/_sidebar.html`, `templates/project.html`, `templates/workspace.html`, `templates/reading_preview.html`, `templates/review_queue.html`, `templates/epub_preview.html`, `tests/unit/api/test_ui_shell.py`, `tests/unit/api/test_ui_workspace.py`, `tests/unit/api/test_ui_layout.py`.

**Tests.** Updated `test_ui_shell.py`, `test_ui_workspace.py`. Added 6 navigation coherence tests to `test_ui_layout.py`.

**Acceptance criteria.**
- ✅ No duplicated nav entry; labels agree; Dashboard is root crumb on all child pages; keyboard navigable; back buttons consistent.

**Handoff notes.** Highest template-diff item; kept after O-gate per plan recommendation.

---

## P5 — WV-005 Project Overview

**Status: ✅ COMPLETE**

**Detail:** audit §WV-005.

**Goal.** A Project Overview surface (summary · translation progress · health · current activity · quick actions) as the project landing tab, replacing the tree-first page.

**In-scope.**
- Overview section from **cheap reads**: volume/chapter/segment counts, translated/manual/pending tallies, review counts, current activity (last job), quick-action links.
- Per-volume summary cards with progress bars and review counts.
- Workflow rail for guidance.
- Tree, import, export panels kept on same page (below overview) — not moved to separate tabs.

**Out-of-scope.**
- **Auto-running any novel-wide QA scan on Overview render** (Gate B1) — ✅ no auto-QA.
- Cross-project analytics.

**Files touched.** `services/project_overview.py` (new), `templates/project.html`, `api/routers/ui.py` (`project_view`).

**Tests.** UI tests for overview counts; Gate B1 enforced (no QA on render).

**Acceptance criteria.**
- ✅ Overview is visible on project open; counts are cheap (no QA on render); tree/import/export still reachable; review counts display per volume.

**Handoff notes.** Counts are free; QA is not — never blend them on render. Reuses WV-006 labels.

---

## P6 — WV-006 Status taxonomy + remove dead branches

**Status: ✅ COMPLETE**

**Detail:** audit §WV-006.  *(Recommended to execute right after P2 — see the sequencing note.)*

**Goal.** One canonical status vocabulary mapped consistently DB → API → UI; remove status strings the DB can never produce.

**In-scope.**
- Presentation helper `api/status_labels.py` (pure functions) mapping DB enum → human label per axis. **DB enum values unchanged** (no migration).
- Replace inline status-label logic in `_segment.html` and `workspace.html` with the helper; **delete** the dead `reused / tm / memory` branches.
- Jinja2 globals wired in `api/app.py`.

**Out-of-scope.** Renaming DB enum values (forces migration + breaks history/tests). Touching `jobs.status` values (SSE/registry depend on them) — map labels only.

**Files touched.** New `api/status_labels.py`, `templates/partials/_segment.html`, `templates/workspace.html`, `api/app.py`.

**Tests.** Grep test: zero matches for `reused|tm|memory` in templates. Updated `test_ui_shell.py` for changed status copy.

**Acceptance criteria.**
- ✅ All status rendering flows through the helper; no impossible status appears in any template; the `manual` "protected source of truth" nuance is preserved.

**Handoff notes.** Foundation for P3/P4/P5 badges. Executed after P2 per recommended order.

---

## P7 — Final integration gate + PR summary

**Status: ✅ COMPLETE (2026-06-10)**

**Goal.** Prove the whole sprint holds together and produce the handoff/PR summary. No new features.

**In-scope.**
- Run the **full validation suite** (below).
- Confirm every WV-item's acceptance criteria; confirm the **O-gate (WV-001 + WV-002)** is gate-green.
- Append a readiness note to `CLAUDE.md §2.5` (Sprint P row) and tick `§2.4` exit criteria.
- Write the PR summary.

**Out-of-scope.** Any code change that isn't fixing a failure surfaced by the gate. Starting Sprint O.

**Full validation executed:**

```
uv run pytest -q      → 1102 passed, 4 skipped
uv run pyright        → 0 errors, 0 warnings
uv run ruff check .   → all clean
uv run ruff format --check .  → 316 files already formatted
uv run weaver --help  → OK
```

(Plus clean wheel build for the formal phase gate, per CLAUDE.md §2.2.)

**Acceptance criteria — the Sprint P exit gate (all must hold):**
- [x] **O-GATE:** WV-001 + WV-002 complete and gate-green.
- [x] WV-006 taxonomy applied; grep test: no impossible status in any template.
- [x] WV-003 migration v8→v9 forward + idempotency tested; Review Queue functional.
- [x] WV-005 Project Overview shipped; WV-004 navigation reconciled (no duplicated entries; labels agree).
- [x] Full suite green, pyright 0, ruff + format clean, clean wheel build; no new runtime dependency; secrets regression test green; UI tests updated for intentional changes.
- [x] Readiness note in `CLAUDE.md §2.5`.

**Only then may Sprint O begin. `N → O` directly remains forbidden.**

**Sprint P is now CLOSED.** The O-gate (WV-001 + WV-002) is satisfied. Sprint O may begin when Sprint N runtime validation is also complete (Rust + MSVC toolchain).

---

## Targeted (per-stage) validation strategy

Run the **minimum** that proves the stage, not the whole matrix, until P7:

| Stage | Targeted commands |
|---|---|
| P1 | `uv run pytest -q tests/unit/api/test_ui_candidates*.py tests/unit/api/test_ui_layout.py` (+ the new generate test) |
| P2 | `uv run pytest -q tests/unit/services/test_reading_preview*.py tests/unit/api/test_ui_preview*.py` (+ the "no-file-written" test) |
| P3 | `uv run pytest -q tests/unit/storage/test_migrations.py tests/unit/services/test_segment_review*.py` |
| P4 | `uv run pytest -q tests/unit/api/test_ui_shell.py tests/unit/api/test_ui_layout.py` |
| P5 | `uv run pytest -q tests/unit/api/test_ui_layout.py` (+ overview test) |
| P6 | `uv run pytest -q tests/unit/api/test_ui_shell.py` (+ the status grep test) |
| P7 | full suite (see above) |

> Test file names marked "new" are suggestions; mirror the source tree and the existing naming. Always finish with the full suite at P7 before declaring Sprint P done.

---

## Open sub-decisions (resolve in-PR, record the choice)

1. **`error` severity tier (WV-008, deferred from this plan's core set).** Adding it contradicts ADR `008` and needs ADR `013` first; otherwise ship new checks at existing tiers. *Not in P1–P6; listed here so it isn't silently introduced.*
2. **Apply-candidate vs review-status (P3).** Recommended orthogonal — apply sets the translation; a human sets review. Document in the WV-003 PR.
3. **Batch candidate generation (P1).** Out of scope; needs `JobRegistry`. File as a follow-up.
4. **`qa_warnings` persistence (WV-011, secondary).** Decide wire-vs-remove only if the secondary items are reached; not part of the P1–P7 core.

> WV-007 (join structure validation into QA) and WV-008 (new checks + `error` tier) are in the audit's full Sprint P set but are **not** in this plan's P1–P7 core (they are strongly recommended but not the O-gate, and WV-008 needs an ADR). Treat them as an optional **P.2 follow-up** after P7, or fold WV-007 into P5/P6 if time allows. Do not let either block the O-gate.

---

## Handoff order (what to do, in order)

1. Close the `feat/tauri-shell-alpha` PR (Sprint N scaffold) — separate concern.
2. Create `feat/workflow-coherence-p` from `main`.
3. Execute **P0** (audit & branch prep) — verify clean start.
4. Hand off **P1 (WV-001)** first — it is half the O-gate.
5. Then **P2 (WV-002)** — completes the O-gate.
6. Then **P6 (WV-006)** taxonomy, then **P3 → P5 → P4** (recommended order), then **P7**.

Each stage is its own PR and its own gate. Do not advance a stage with a red gate.
