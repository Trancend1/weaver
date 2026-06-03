# Sprint 12 — FastAPI UI Parity Audit + Default-`serve` Decision

> **Audit + decision only.** No Flask routes, templates, or dependency removed.
> No default-`serve` flip performed. Stops at **Gate 12A** with a recommendation.
> Date: 2026-06-03 · Branch: `feat/fastAPI-ui-audit`
> Supersedes the functional-only re-audit in [SPRINT10_PARITY_AUDIT.md](SPRINT10_PARITY_AUDIT.md) §9
> by adding the now-shipped **FastAPI UI** surface (Sprint 11).

---

## 1. Surfaces at a glance

| | Flask cockpit (`weaver serve`) | FastAPI cockpit (`weaver serve-api`) |
|---|---|---|
| Factory | `weaver/web/app.py:create_app` | `weaver/api/app.py:create_api_app` |
| Bind | `127.0.0.1` only, no auth | `127.0.0.1` only, no auth |
| Routes (incl. `/static`) | 14 (13 functional) | 53 JSON + 35 UI route entries (`/ui*`, `/`, `/static`) |
| Data model | **Legacy single-project flat** | **Novel → Volume → Chapter (MVP)** |
| UI surface | HTML templates (4 pages) | **HTML templates (Jinja2 + HTMX), 11 pages + 18 partials** |
| UI stack | Jinja2 + vanilla forms/SSE | Jinja2 + vendored HTMX (no Node/build, ADR 007) |

**Change since Gate 10E:** the *only* remaining parity gap in Sprint 10 was "no
FastAPI UI." Sprint 11 closed it (11A shell → 11B workspace/jobs/export → 11C
glossary/character/TM/config). FastAPI now has a rendered browser cockpit that is
a **functional superset** of the Flask UI on the richer Novel/Volume/Chapter model.

Route maps re-enumerated live (not from memory):
- **Flask:** 14 url-map rules (13 functional + `/static`).
- **FastAPI:** 53 JSON/API route objects (incl. 4 auto-docs) + 35 UI entries
  (`/`, `/ui*`, `/static` mount).

---

## 2. Parity matrix (the 12 audited capabilities)

Status legend: ✅ full · 🟡 partial/different model · ❌ absent.
Parity column = **does the FastAPI UI cover the capability for a browser user.**

| Capability | Flask UI | FastAPI UI | FastAPI JSON API | CLI fallback | Parity | Gap | Action |
|---|---|---|---|---|---|---|---|
| **Dashboard / project list** | ✅ `GET /` | ✅ `GET /ui` | ✅ `GET /projects` | `inspect`, `dashboard` | ✅ superset | none | none |
| **Create / import / file browser** | ✅ `POST /new/init`, `POST …/import`, `GET /api/browse` | ✅ `GET/POST /ui/new`, `POST …/import`, `GET /ui/browse` | ✅ `POST /projects/create`, `…/import`, `GET /projects/browse` | `init`, `new`, `import` | ✅ superset | none | none |
| **Project tree** | 🟡 legacy flat inspect mirror | ✅ `GET /ui/projects/{name}` (Novel/Vol/Chapter) | ✅ `GET …/tree` | `inspect` | ✅ superset | Flask = flat; FastAPI = Vol/Chapter | none |
| **Workspace read / save / history** | ❌ none | ✅ `GET …/chapters/{id}`, `POST …/segments/{id}`, `GET …/segments/{id}/history` | ✅ `GET …/workspace`, `PATCH …/translation`, `GET …/translations` | `edit`, `preview` | ✅ FastAPI-only | Flask never had it | none |
| **Translate / retranslate / job progress** | 🟡 translate + SSE + stop; **no safe retranslate** | ✅ translate + retranslate modes + self-polling job panel + cancel | ✅ `…/translate[-segments]`, `…/retranslate[-segments]`, `…/jobs/{id}` + `/events` + `/cancel` | `translate` | ✅ superset | Flask lacks retranslate modes + Vol/Novel scope | none |
| **Export trigger / status** | 🟡 legacy markdown/epub, whole project | ✅ EPUB/TXT/HTML, volume-aware + job panel + cancel | ✅ `…/export/{novel\|volumes\|chapters}` + jobs/SSE | `export` | ✅ superset | Flask = legacy md; FastAPI = volume-aware EPUB/TXT/HTML | none |
| **Glossary CRUD** | ❌ none (review only) | ✅ term add/update/delete | ✅ `GET/POST/PATCH/DELETE …/glossary` | `glossary` | ✅ FastAPI-only | Flask never had direct CRUD | none |
| **Glossary candidate review** | ✅ approve/edit/reject + conflicts + diff | ✅ candidates approve/edit/reject + conflicts + coverage diff | ✅ `…/glossary/candidates`, `…/{approve,edit,reject}`, `…/conflicts`, `…/diff` | `glossary review` | ✅ parity | none | none |
| **Character DB** | ❌ none | ✅ add/update/delete | ✅ `GET/POST/PATCH/DELETE …/characters` | (none — API/UI only) | ✅ FastAPI-only | Flask never had it | none |
| **Translation memory** | ❌ none | ✅ read + delete entry | ✅ `GET/DELETE …/memory` | (none — API/UI only) | ✅ FastAPI-only | Flask never had it | none |
| **Provider / model config** | ✅ `POST …/config` (project+global) | ✅ `GET/POST /ui/config` (project+global scope) | ✅ `GET/PATCH /config` | `init`, `doctor` | ✅ parity | none | none |
| **Secret config write** | ✅ writes secret store via `/config` | ✅ `POST /ui/config/secrets` set + delete (value never rendered back) | ✅ `POST/DELETE /config/secrets/{env_name}` | `secrets set/list/remove` | ✅ parity | none | none |

**Summary:** FastAPI UI = **12 / 12 capabilities covered**, and is a **strict
superset** of the Flask UI. Flask UI covers only 7 of the 12 (it lacks workspace
read/save/history, safe retranslate, glossary direct CRUD, character DB, and
translation memory). Every capability Flask renders, FastAPI also renders — plus
the full MVP workflow on the Novel/Volume/Chapter model.

---

## 3. Model / behavior differences (not regressions)

These are deliberate model differences, not missing capabilities:

- **Project model.** Flask drives the legacy flat single-project; FastAPI drives
  Novel → Volume → Chapter. FastAPI's tree/workspace/export are richer, not a port.
- **Export format.** Flask emits legacy markdown/epub for the whole project;
  FastAPI emits volume-aware EPUB/TXT/HTML per the MVP export design. Markdown is
  not reproduced in FastAPI (out of MVP scope).
- **Translate granularity.** Flask translates the whole project (with a
  `retry_failed` flag); FastAPI translates at chapter/volume/novel scope and adds
  safe-retranslate modes (`skip_existing` / `retranslate_non_manual` /
  `force_selected`).
- **UI polish.** FastAPI UI is **functional parity, not visual polish** (ADR 005
  rubric deferred; ADR 007 stack: server-rendered Jinja2 + HTMX, no SPA). It is
  usable end-to-end but intentionally unstyled beyond a minimal `app.css`.

CLI-only capabilities (no UI on either surface): `doctor`, `validate`, `preview`,
TUI `dashboard`. Not in scope for this parity audit.

---

## 4. Gaps

**Functional gaps blocking a default flip: none.** FastAPI UI covers all 12
audited capabilities and is a superset of the Flask UI.

Non-blocking, decision-relevant observations:

1. **Visual polish.** FastAPI UI is functional, not polished (by design, ADR 005).
   A default flip would change the cockpit a browser user sees to the unpolished
   surface. This is a UX-quality consideration, not a capability gap.
2. **Legacy markdown export.** Only Flask emits markdown. If any workflow depends
   on markdown output, it must move to EPUB/TXT/HTML or stay on `serve` until
   markdown is added (out of MVP scope; no current consumer identified).
3. **Operational surface.** Scripts/users invoking `weaver serve` expecting the
   Flask flat-project UI would land on the Novel/Volume/Chapter UI after a flip.
   Needs a changelog note + (if flipped) a `serve-flask` alias for continuity.

---

## 5. Validation (Gate 12A)

| Check | Result |
|---|---|
| `pytest` | **683 passed, 4 skipped** (expected: DeepSeek/Gemini/Ollama live + POSIX file-mode on Windows) |
| `pyright` (basic, venv interpreter) | **0 errors, 0 warnings, 0 informations** |
| `ruff check` | **All checks passed** |
| `ruff format --check` | **237 files already formatted** |
| CLI smoke | 15 commands (incl. `serve`, `serve-api`) + `glossary` / `secrets` groups load |
| Flask smoke | `create_app` + test_client: `GET /` → **200**, **14 url-map rules** (13 functional) |
| FastAPI UI smoke | `GET /` → **307** → `/ui`; `/ui`, `/ui/new`, `/ui/config` → **200**; 35 UI route entries / 53 JSON route objects |

No code or behavior changed in this stage (audit only).

---

## 6. Decommission / flip risk assessment

| Risk | Severity | Detail / mitigation |
|---|---|---|
| **UI regression on flip** | 🟢 Low | FastAPI UI is a functional superset; nothing a browser user can do in Flask is lost. Only "polish" differs (deferred by ADR 005). |
| **Markdown export loss** | 🟡 Medium | FastAPI has no markdown target. Mitigate: keep `serve` (Flask) reachable as `serve-flask`; no markdown consumer identified. |
| **Operational / script breakage** | 🟡 Medium | `weaver serve` semantics change on flip. Mitigate: add `serve-flask` alias + changelog/deprecation note before flipping. |
| **Code coupling** | 🟢 Low | Flask is a thin layer over shared `services/*`; only shared touchpoint is `web/file_browser.py` → re-export shim of `services/source_browser.py`. No core logic in Flask. |
| **Test coverage on eventual removal** | 🟡 Medium | Flask has its own route/smoke tests; removal would drop them, but underlying services keep their own coverage. (Removal is **not** this sprint.) |
| **Secret/redaction parity** | 🟢 Low | Both surfaces redact; FastAPI verified to never render key values (11C). No regression. |

---

## 7. Decision options

1. **Keep `weaver serve` = Flask** (status quo). Lowest churn; FastAPI stays on `serve-api`.
2. **Flip `weaver serve` → FastAPI UI**, repoint Flask to `weaver serve-flask` (keep it). Reversible, no removal.
3. **Deprecate Flask but do not remove** (deprecation notice; default unchanged or flipped).
4. **Plan Flask removal only after the default flip proves stable** (Sprint 13, gated + explicitly approved).

---

## 8. Recommendation

**Recommend Option 2 — flip `weaver serve` → FastAPI UI and repoint Flask to
`weaver serve-flask` — pending maintainer approval, then sequence into Option 4.**

Reasoning:
- FastAPI parity is now **complete and a superset** (12/12 capabilities; §2). The
  Gate 10E blocker ("no FastAPI UI") is closed.
- The project posture is **web-cockpit-first** and **FastAPI-first** (ADR 004).
  Keeping the legacy flat-project Flask UI as the default contradicts the locked
  direction now that the FastAPI UI exists.
- Option 2 is **reversible and removes nothing**: Flask stays fully available as
  `serve-flask`, satisfying the "do not remove Flask in Sprint 12" rule and giving
  a fallback for markdown export / legacy scripts.
- **Removal (Sprint 13) stays gated:** proceed to Option 4 only after the flipped
  default proves stable in real use **and** is explicitly approved.

Conservative alternative: if the maintainer wants the default cockpit to reach
ADR-005 visual polish *before* it becomes the default `serve`, choose **Option 1**
now and revisit the flip after a polish pass. This trades direction-alignment for
UX-quality-at-default.

> **Gate 12A: STOP.** Parity = complete (FastAPI UI is a superset). Recommendation
> = **Option 2 (flip + keep Flask as `serve-flask`), then Option 4 for removal** —
> awaiting explicit maintainer approval. No flip, deprecation, removal, route/
> template deletion, or dependency change performed in this sprint.

---

## 9. Decision (Gate 12A — maintainer, 2026-06-03)

**Option 2 — flip `weaver serve` → FastAPI UI; keep Flask as `weaver serve-flask`.**

Approved command layout:
- `weaver serve` → FastAPI cockpit (UI), default.
- `weaver serve-api` → FastAPI app headless (no browser), explicit API command.
- `weaver serve-flask` → legacy Flask cockpit, fallback.

Constraints (honored in Sprint 12B): do **not** remove Flask, do **not** delete
Flask routes/templates, do **not** remove the Flask dependency, do **not**
deprecate Flask yet. Default-command flip only; reversible.

Rationale: the audit shows the FastAPI UI is a strict functional superset (12/12
vs Flask's 7/12), so the default should align with the FastAPI-first direction
(ADR 004) while Flask remains as an operational-safety fallback.

> **Gate 12A: CLOSED — decision = Option 2 (flip + keep Flask).** Implemented in
> **Sprint 12B** (`weaver serve` → FastAPI; `serve-api` headless; `serve-flask`
> legacy). Flask removal is **Sprint 13**, gated on the flip proving stable **and**
> explicit approval.

---

## 10. Sprint 12B — Default-`serve` Flip (implementation)

Default-command flip only — no Flask route/template/dependency removal; reversible.

**CLI (`src/weaver/cli/main.py`):**
- New shared helper `_run_fastapi_cockpit(port, books_dir, open_browser, reload)` —
  Uvicorn factory (`weaver.api.app:create_api_app`), optional `chdir` to apply
  `--books-dir` (the factory derives its root from cwd), `threading.Timer`
  browser-open. Host fixed to `127.0.0.1`.
- `serve` → FastAPI cockpit (UI), default. Options `--port` (8765),
  `--books-dir`, `--no-browser`, `--reload`. Opens a browser unless `--no-browser`.
- `serve-api` → same FastAPI app **headless** (no browser), `--port` 8000.
- `serve-flask` → **new** command running the verbatim former `serve` body
  (`weaver.web.app.run_server`), `--port` 8765, `--books-dir`, `--no-browser`.

**Tests:** `tests/integration/test_cli_serve_routing.py` (+5) — `serve` launches
the FastAPI factory (Flask `run_server` asserted *not* called); `serve-flask`
launches Flask `run_server`; help-text routing for all three. Existing
`test_serve_command_help_mentions_loopback` and the `serve-api` help test still pass.

**Docs:** QUICKSTART, COCKPIT_WORKFLOW, ARCHITECTURE, CLAUDE.md updated.

**Validation (Gate 12B):**

| Check | Result |
|---|---|
| `pytest` | **688 passed, 4 skipped** (+5 routing tests) |
| `pyright` (basic, venv) | **0 errors** |
| `ruff check` / `format --check` | **clean / 238 files** |
| CLI smoke | **16 commands** (added `serve-flask`) + groups load |
| `serve --help` | FastAPI UI, mentions `127.0.0.1` + `serve-flask` |
| `serve-api --help` | FastAPI cockpit, headless |
| `serve-flask --help` | legacy Flask, `127.0.0.1` |
| FastAPI UI smoke | `/`→307, `/ui`·`/ui/new`·`/ui/config`→200 |
| Flask fallback smoke | `serve-flask` app `/`→200 |

> **Gate 12B: complete.** Default flipped to FastAPI; Flask preserved as
> `serve-flask`. Flask removal remains **Sprint 13** (gated + explicit approval).
