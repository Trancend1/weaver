# Sprint 10A — FastAPI vs Flask Parity Audit

> **Audit only.** No Flask routes, templates, or default-serve behavior changed.
> Decision gate: whether Flask can be safely deprecated/removed.
> Date: 2026-06-02 · Branch: `feat/flask-decommission`

---

## 1. Surfaces at a glance

| | Flask cockpit (`weaver serve`) | FastAPI cockpit (`weaver serve-api`) |
|---|---|---|
| Factory | `weaver/web/app.py:create_app` | `weaver/api/app.py:create_api_app` |
| Bind | `127.0.0.1` only, no auth | `127.0.0.1` only, no auth |
| Routes (non-static) | 13 | 41 |
| Data model | **Legacy single-project flat** (`translate_project`, `export_*_project`, glossary candidates) | **Novel → Volume → Chapter (MVP)** |
| Output | **HTML templates (full UI)** — `dashboard`, `cockpit`, `new`, `glossary` | **JSON only (headless API, no UI)** |

The two cockpits are **not 1:1**. FastAPI is a richer domain superset on the new
Novel/Volume/Chapter model, but it is **headless** and is **missing four Flask
capabilities**. Flask is the only surface with a rendered UI.

---

## 2. Parity matrix

Status legend: ✅ full · 🟡 partial/different · ❌ absent.
Parity = does FastAPI cover the Flask capability for an end user.

| Capability | Flask Status | FastAPI Status | Parity | Gap | Action |
|---|---|---|---|---|---|
| **Project discovery / list** | ✅ `GET /` dashboard (HTML) | ✅ `GET /projects` (JSON) | 🟡 | FastAPI has data, no UI | UI later; no blocker for data |
| **Create project (init)** | ✅ `POST /new/init` (browse/upload) | ❌ none (only volume import) | ❌ | No FastAPI "create novel" endpoint | Add endpoint **or** keep CLI `init` |
| **Import volume (EPUB/TXT/HTML)** | ✅ `POST /project/<n>/import` | ✅ `POST /projects/{n}/import` | 🟡 | FastAPI upload-only, no browse | OK (upload covers it) |
| **File browser (sandboxed dir list)** | ✅ `GET /api/browse` | ❌ none | ❌ | Server-side path picker absent | Descope (upload) or port later |
| **Novel→Volume→Chapter tree** | 🟡 read-only inspect mirror | ✅ `GET /projects/{n}/tree` | ✅ | FastAPI superset | none |
| **Workspace read (JP/EN 2-col)** | ❌ none | ✅ `GET …/chapters/{id}/workspace` | ✅ | FastAPI-only feature | none |
| **Workspace save (segment edit)** | ❌ none | ✅ `PATCH …/segments/{id}/translation` | ✅ | FastAPI-only | none |
| **Revision history** | ❌ none | ✅ `GET …/segments/{id}/translations` | ✅ | FastAPI-only | none |
| **Provider / model config write** | ✅ `POST /project/<n>/config` (project/global + **secret store write**) | ❌ none (per-request `provider`/`model` override only; no persist, no secret write) | ❌ | **No FastAPI config/secret-write API** | Add config endpoint **or** keep CLI `secrets`/`init` |
| **Translate — start job** | ✅ `POST …/translate` (whole project) | ✅ chapter / segments / volume / novel | 🟡 | Different granularity (FastAPI finer) | none |
| **Translate — safe retranslate** | ❌ none (`retry_failed` flag only) | ✅ `retranslate` + modes (skip/non-manual/force) | ✅ | FastAPI superset | none |
| **Translate — status / progress** | ✅ SSE `GET …/events` | ✅ `GET …/jobs/{id}` + `/events` SSE | ✅ | parity | none |
| **Translate — stop / cancel** | ✅ `POST …/translate/stop` | ✅ `POST …/jobs/{id}/cancel` | ✅ | parity | none |
| **Batch translation** | ❌ none | ✅ novel/volume/chapter + jobs/SSE | ✅ | FastAPI-only | none |
| **Translation memory** | ❌ none | ✅ `GET/DELETE …/memory` | ✅ | FastAPI-only | none |
| **Glossary — direct CRUD** | ❌ none | ✅ `GET/POST/PATCH/DELETE …/glossary` | ✅ | FastAPI-only | none |
| **Glossary — candidate review** | ✅ `GET/POST …/glossary[/<id>]` (approve/edit/reject, conflicts, per-chapter coverage diff) | ❌ none (CRUD only; no candidate queue/approve/conflicts/diff) | ❌ | **No FastAPI candidate-review flow** | Port later **or** keep CLI `glossary review` |
| **Character DB** | ❌ none | ✅ `GET/POST/PATCH/DELETE …/characters` | ✅ | FastAPI-only | none |
| **Export** | ✅ `POST …/export` (legacy markdown/epub, whole project) | ✅ EPUB/TXT/HTML, volume-aware (novel/volume/chapter) + jobs/SSE | 🟡 | Different model; FastAPI richer, no markdown | OK (EPUB/TXT/HTML cover MVP) |
| **Error handling** | ✅ `WeaverError` → redirect w/ flash flag / `abort(4xx)` | ✅ `WeaverError` → typed HTTP (404/422/502) | ✅ | parity (both surface what/cause/next) | none |
| **Local-only security** | ✅ `127.0.0.1`, no auth, upload cap, sandboxed browse | ✅ `127.0.0.1`, no auth | ✅ | parity (FastAPI has no browse to sandbox) | none |
| **Web UI surface** | ✅ HTML templates (4 pages) | ❌ JSON only | ❌ | **No FastAPI UI at all** | UI build is post-MVP (ADR 005) |

---

## 3. Gaps (FastAPI does NOT cover Flask)

Blocking gaps for Flask removal:

1. **No FastAPI UI.** FastAPI is headless JSON. Flask is the *only* rendered web
   surface. Removing Flask today removes the only browser cockpit.
2. **No config/secret-write endpoint.** Flask `/config` persists provider/model to
   `project.toml`/global config and writes the API key to the secret store.
   FastAPI offers only a per-request `provider`/`model` override — nothing
   persisted, no secret write. *(Reachable via CLI `secrets set` / `init`.)*
3. **No glossary candidate-review flow.** Flask has the approve/edit/reject queue,
   approved-term conflicts, and per-chapter coverage diff. FastAPI glossary is
   direct CRUD only. *(Reachable via CLI `glossary review`/`conflicts`/`diff`.)*
4. **No "create novel" endpoint + no file browser.** FastAPI imports volumes
   (upload only) but cannot create a novel or browse server-side paths.
   *(Reachable via CLI `init` / `new`.)*

Non-blocking differences (FastAPI is a superset or equivalent): tree, workspace
read/save/history, safe retranslate, batch, TM, characters, volume-aware
EPUB/TXT/HTML export, typed error handling, local-only binding.

---

## 4. Risks

- **R1 — UI regression.** Removing Flask before any FastAPI UI leaves Weaver with
  no browser cockpit (CLI only). High impact for the web-first focus.
- **R2 — Capability loss via API.** Config/secret write and glossary candidate
  review have **no FastAPI equivalent**. They survive only on the CLI; an
  API/UI-only user would lose them.
- **R3 — Model mismatch.** Flask drives the legacy flat project; FastAPI the
  Novel/Volume/Chapter model. A straight "port the routes" is not 1:1 — the
  candidate-review/config flows must be re-expressed on the new model.
- **R4 — Low (mitigated).** All four gaps are covered by the CLI today, so no
  capability is *lost from the product* while Flask stays — only from the web
  surface. This makes "keep Flask as fallback" safe and cheap.

---

## 5. Validation (Gate 10A)

| Check | Result |
|---|---|
| `pytest` | **562 passed, 4 skipped** (expected: DeepSeek/Gemini/Ollama live + POSIX file-mode on Windows) |
| `pyright` | **0 errors, 0 warnings** |
| `ruff check` | **All checks passed** |
| `ruff format --check` | **218 files already formatted** |
| CLI smoke | 15 commands + 3 groups (`glossary`/`gl`, `secrets`) load |
| Flask smoke | `create_app` + test_client: `/` → 200, **13 routes** |
| FastAPI smoke | `create_api_app` + TestClient: `/health`·`/version`·`/projects` → 200, **41 routes** |

No code or behavior changed in this stage.

---

## 6. Recommendation

**KEEP Flask — do NOT proceed to removal.**

Per the Sprint 10 decision rules: *"If FastAPI parity is incomplete, do not remove
Flask."* FastAPI parity is **incomplete** on four counts (UI, config/secret write,
glossary candidate review, create-novel/file-browser). Flask is also the **only**
UI surface.

Recommended posture:
- Mark Flask **legacy fallback** (the working web baseline), unchanged.
- Default `weaver serve` stays Flask; `weaver serve-api` stays parallel.
- **Removal is blocked** until either (a) a FastAPI UI ships *and* the config/secret
  and glossary-candidate gaps are ported or explicitly descoped to CLI-only, or
  (b) the maintainer accepts CLI-only coverage for those flows and a headless API.

Suggested follow-up stages (require approval before starting):
- **10B** — close FastAPI gaps deemed in-scope (config/secret-write endpoint;
  decide candidate-review port vs CLI-only; create-novel endpoint).
- **10C** — FastAPI UI (post-MVP polish, ADR 005).
- **10D** — flip default `serve` → FastAPI, then deprecate/remove Flask.

---

## 7. Decision (Gate 10A — maintainer, 2026-06-02)

**KEEP Flask. Do not proceed to Flask removal.**

Rationale: FastAPI is the MVP domain/API superset, but parity is **incomplete** —
FastAPI still lacks (1) a web UI surface, (2) a provider/secret config-write API,
(3) the glossary candidate-review flow, and (4) a create-novel endpoint + file
browser.

Locked posture:
- `weaver serve` stays **Flask** — legacy browser cockpit / fallback.
- `weaver serve-api` stays **FastAPI** — new MVP API foundation.
- **No default flip.** No route/template deletion. No Flask dependency removal.

Next step: **close the four parity gaps first**, then run **another parity audit**
before any decommission work is considered.

> **Gate 10A: CLOSED — decision = KEEP Flask.** Removal stage is not authorized.
> Re-audit required after the four gaps are closed.

---

## 8. Gap-closure progress

| Gap | Stage | Status |
|---|---|---|
| 4 — create-novel endpoint + file browser | **10B** | ✅ **Closed.** `POST /projects/create` (upload or browsed source; 409 on duplicate) + `GET /projects/browse` (sandboxed). Browser logic extracted to framework-agnostic `services/source_browser.py`; Flask `web/file_browser.py` re-exports it (no Flask behavior change). **Sourceless creation** is unsupported by `initialize_project` (name derives from source stem) → out of scope, not built. No UI. |
| 2 — provider/secret config-write API | **10C** | ✅ **Closed.** `GET/PATCH /config` (provider/model, project+global scope) + `POST/DELETE /config/secrets/{env_name}`. Framework-agnostic `services/provider_config.py` reuses `config_writer` + `core/secret_store`. **Secrets keyed by env-var name** (the existing store abstraction; no provider→env map exists) — minor deviation from the suggested `{provider}` path. **Key values never accepted by PATCH and never returned anywhere** (presence bool + names only; verified vs response bodies *and* OpenAPI schema). CLI `secrets` + Flask `/config` untouched. No UI. |
| 3 — glossary candidate-review flow | **10D** | ✅ **Closed.** `GET …/glossary/candidates` (paged + counts + `find`), `POST …/candidates/{id}/{approve,edit,reject}`, `GET …/glossary/conflicts`, `GET …/glossary/diff`. Thin adapter `routers/glossary_review.py` over existing `services/glossary_review` + `services/glossary_diff` — **approve/edit write the same `glossary_terms` rows** (no second store); direct CRUD unchanged & not shadowed. New typed `GlossaryCandidateNotFoundError`→404 (Flask still catches it via `WeaverError`). CLI `glossary review` + Flask `/glossary` untouched. No UI. |
| 1 — web UI surface | — | ⬜ Open |

Re-audit (and any decommission decision) remains gated on gap 1 (web UI) also closing — the **only** remaining parity gap. FastAPI now covers every Flask *capability* headlessly.
