# Web Cockpit — Execution Blueprint

**Phase:** 12 · **Target version:** `0.5.0` · **Status:** Draft (planning, not scheduled)
**Companion docs:** [web-feature-plan.md](web-feature-plan.md) · [web-architecture.md](web-architecture.md) · [master plan](2026-05-29-web-cockpit-phase-12.md)

This doc owns the **build order**. Why/scope lives in [web-feature-plan.md](web-feature-plan.md); how it's built lives in [web-architecture.md](web-architecture.md).

---

## 1. Critical path

```
ADRs 0016/0017/0019  →  12a (serve + discovery + read-only monitor)
                              ↓
       ADR 0018  →  12b (file input + config + translate controls + export)
                              ↓
                     12c (glossary review UI)
```

Strict order. 12a lays the Flask app, discovery, JobManager skeleton, and SSE. 12b layers all write actions on top. 12c moves the most tedious CLI workflow into the browser. ADRs land **before** their matching implementation (phase-gate rule).

---

## 2. ADRs to author first

| ADR | Decision |
|-----|----------|
| `0016-web-cockpit-framework.md` | Reopen stack: allow **Flask (sync)** + HTMX; keep Jinja2 (already locked); **asyncio stays rejected**; React/Node stays rejected. Rationale: thin local UI, sync fits sync services. |
| `0017-localhost-security-model.md` | Bind `127.0.0.1` only; no auth (single-user local); file browser sandboxed to `--books-dir` root; upload size/type limits; never log/render API keys. |
| `0018-config-writer-service.md` | Atomic (`tempfile`+`replace`) writes to `project.toml [provider]` and `~/.weaver/config.toml`; preserve unrelated keys; keys never written to config (env-only rule holds). |
| `0019-job-manager-progress-streaming.md` | In-memory single-job registry; one-job-at-a-time lock; progress via thread-safe queue; SSE contract; cooperative cancel. |

---

## 3. Sub-sprints

### Phase 12a — Discovery + Read-only Monitor (foundation)
**Deliverables:**
- `weaver serve` command, Flask app factory, `127.0.0.1` bind, `--no-browser`.
- `project_discovery` service + Dashboard listing discovered projects (**kills PP1**).
- Project cockpit view (read-only): status table mirroring `inspect`.
- `JobManager` skeleton + SSE endpoint streaming a translate job started **read-only** (no stop yet) (**starts PP3**).
- ADRs `0016`, `0017`, `0019`. Vendored `htmx.min.js`.

**Exit:** browse to localhost, see all projects with no path typing; start a translate from the cockpit and watch live SSE progress to completion.

### Phase 12b — Actions: config, translate controls, export, file input
**Deliverables:**
- File browser (`/api/browse`) + drag-drop upload (→ `.weaver/_uploads/` staging) + `/new/init` (**finishes PP1**, file picker).
- `config_writer` service + provider/model UI (project + global scope) + wizard/`project.toml` provider-discard fix (**kills PP2**). ADR `0018`.
- Translate controls: retry-failed, first-N, **stop** (cancel hook in `translation.py`).
- Export buttons (markdown/epub) + "next action" flow hints (**kills PP4**).

**Exit:** create a project from the browser (browse or upload), set its provider/model from a dropdown, translate with stop/retry, export — without touching the CLI.

### Phase 12c — Glossary Review UI
**Deliverables:**
- Stateless glossary ops in `services/glossary_review.py`.
- Paginated browser review UI: approve / edit / reject / find (**finishes PP5**, the most tedious CLI part).
- Glossary conflicts + diff surfaced read-only in the cockpit.

**Exit:** full glossary review done comfortably in the browser; conflicts visible before translate.

---

## 4. Reusable phase gate (per CLAUDE.md §2.2)

For each sub-sprint, before closing:
1. Read sub-sprint deliverables here + plan source.
2. List exit criteria in plain language.
3. Verify each with a concrete command / browser check / test.
4. State what is usable now vs internal-only.
5. Update CLAUDE.md §2.1 / §2.3 / §2.4 / §2.5 on pass.

**Required reminder before phase transition:** *"Check exit criteria first. No next phase until evidence exists. Explain the detail for manual inspection."*

---

## 5. Global exit criteria (all of Phase 12)

1. ADRs `0016`–`0019` land per ENGINEERING_STANDARDS format.
2. All PRs green; one PR = one concern.
3. AC-1..AC-9 acceptance gate stays PASS.
4. Ruff lint + format clean. Pyright `0 errors`.
5. CLI remains fully wire-compatible (existing tests unchanged).
6. README + `docs/quickstart.md` document `weaver serve`.
7. New deps gated behind optional extra `weaver[web]`.

---

## 6. Risks

| Risk | Note | Mitigation |
|------|------|------------|
| Flask dev server + SSE threading | Dev server prints a "not for production" warning. | **Decided (D1): Flask dev server, `threaded=True`.** No extra dep; warning harmless for localhost single-user. |
| `translate_project` has no cancel path | Stop button needs cooperative cancel. | Add `should_cancel` hook; land in 12b. |
| Glossary session is CLI-shaped | Context-manager loop, not per-request. | Add stateless ops; land in 12c. |
| HTMX from CDN breaks offline ethos | Project is offline-capable. | Vendor `htmx.min.js` in `static/`. |
| File browser path traversal | Browser lists local FS. | Sandbox to `--books-dir`; reject `..` escapes; ADR `0017`. |
| Upload location | Where uploaded EPUBs land. | **Decided (D2): copy to `.weaver/_uploads/`, then init.** |
| Single-job lock UX | Second translate request while one runs. | Block with clear message + link to running job; queue out of scope for v1. |

---

## 7. Resolved decisions

| ID | Decision |
|----|----------|
| D1 | Flask dev server with `threaded=True` (no extra dep). |
| D2 | Uploaded EPUB copied to `.weaver/_uploads/`, then `init` from there. |
| D3 | Optional extra named `weaver[web]`. |

No open blocking questions. ADRs `0016`–`0019` are authored first when the sprint starts.

---

## 8. Roadmap integration

| # | Phase | Depends on | Status |
|---|-------|-----------|--------|
| 12a | Web Cockpit — discovery + read-only monitor | 11c | ⏳ Planned |
| 12b | Web Cockpit — actions (config/translate/export/files) | 12a | ⬜ Pending |
| 12c | Web Cockpit — glossary review UI | 12b | ⬜ Pending |

On 12a start: flip CLAUDE.md §2.1 to add these rows + set §2.3 Active Sprint to 12a.
