# Sprint 13A.5 — FastAPI Default Soak Test

**Type:** Operational soak. No code/dependency/flip change. Decision B from Gate 13A (postpone removal, prove the flipped default on a real workflow first).
**Date:** 2026-06-04
**Branch:** `feat/flask-decommission`
**Posture under test:** `weaver serve` = FastAPI UI (default) · `serve-api` = headless · `serve-flask` = legacy fallback.

---

## 1. Method

Drove a **full novel workflow against a live `weaver serve` FastAPI cockpit** over real HTTP on `127.0.0.1:8802` — the exact process a user gets from the flipped default (`uvicorn` factory `weaver.api.app:create_api_app`, launched via the CLI `serve` command with `--books-dir`). Flask was **not** started.

- Provider: **`fake`** (repo rule §4.2 — no live LLM in CI/soak; live-provider translation was already proven in Sprint 9C via Groq). The soak validates the *workflow + UI surface*, not model quality.
- Sources (multi-format, multi-volume): real public-domain `aozora_sample.epub` (vol 1) + a JP narrative `.txt` (vol 2) + a JP `.html` (vol 3).
- Driver: [`scripts/soak_13a5.py`](../scripts/soak_13a5.py) — 25 assertions, exits non-zero on first failure; reusable for the 13B re-validation cycle.

---

## 2. Soak Result — ✅ ALL 25 STEPS PASSED

| # | Capability | Route(s) exercised | Result |
|---|---|---|---|
| 1 | Liveness | `GET /health`, `/version` | 200 · v0.6.0 |
| 2 | Create project (EPUB import) | `POST /projects/create` | `aozora_sample`, 2 ch / 6 seg, 2 candidates |
| 3 | List projects | `GET /projects` | project present |
| 4 | Import TXT (vol 2) | `POST /projects/{n}/import` | volume_id 2, 2 ch / 4 seg |
| 5 | Import HTML (vol 3) | `POST /projects/{n}/import` | volume_id 3, 2 ch / 5 seg |
| 6 | Tree | `GET /projects/{n}/tree` | **3 volumes**, chapters disjoint (11B-1.5 guard holds) |
| 7 | Workspace read | `GET …/chapters/{id}/workspace` | 4 segments |
| 8 | Manual save | `PATCH …/segments/{id}/translation` | status → **`manual`** |
| 9 | Revision history | `GET …/segments/{id}/translations` | attempts recorded |
| 10 | Translate chapter | `POST …/translate` + `GET …/jobs/{id}` | translated 3, failed 0, **skipped 1 (manual protected)** |
| 11 | Safe retranslate (force) | `POST …/retranslate` (`force_selected`) | translated 4, failed 0 (manual overwritten only on force) |
| 12 | Glossary CRUD + review | `POST/GET/PATCH /glossary`, `GET /glossary/candidates` | JP key `魔王` create→edit; 5 pending candidates |
| 13 | Character DB | `POST/GET /characters` | `エリナ`→Elina |
| 14 | Translation memory | `GET /projects/{n}/memory` | 4 entries; **manual edit stored as TM source-of-truth** (`provider=manual`) |
| 15 | Provider config R/W | `GET/PATCH /config?project=` | read `fake`; write project-scope model `fake-model` |
| 16 | Batch translate (novel) | `POST /batch/novel` + `GET /batch/jobs/{id}` | 6 chapters, **11 translated, failed 0**, 4 skipped (manual chapter protected) |
| 17 | Export EPUB (novel) | `POST /export/novel` (`epub`) | 3 artifacts, **3/3 on disk** |
| 18 | Export TXT (novel) | `POST /export/novel` (`txt`) | 3 artifacts, **3/3 on disk** |
| 19 | Export HTML (novel) | `POST /export/novel` (`html`) | 3 artifacts, **3/3 on disk** |

Artifacts written under `…/.weaver/aozora_sample/output/{epub,txt,html}/volume-0N-idN.*` and verified present on disk.

Invariants observed: `translated + failed == selected` everywhere; manual segment protected under `skip_existing` (translate + batch) and only overwritten under `force_selected`; TM populated from the run (fake rows) with the manual edit kept as the manual-provider source-of-truth row; multi-volume chapter IDs disjoint (no re-parenting).

---

## 3. Was the Flask Fallback Used?

**No.** `weaver serve-flask` was never started during the soak. The entire create → import (×3 formats) → workspace → translate/retranslate → glossary/character/TM/config → batch → export(×3 targets) workflow completed on the FastAPI default alone. No step required falling back.

---

## 4. Blockers / Regressions

**None.** No functional regression surfaced from the Sprint 12B default flip.

Two non-blocking environment notes (driver-side, not product defects):

1. **Job terminal status string** is `done` (not `succeeded`) — corrected in the driver. Product behavior correct; this was a test-author assumption.
2. **Windows console encoding** — printing Japanese API responses crashed under the default `cp1252` stdout; resolved by running the driver with `PYTHONUTF8=1`. Not a server/HTTP issue (the API returns correct UTF-8 JSON); only affects console echo of the test driver.

Neither touches the cockpit itself.

---

## 5. Validation (Gate 13A.5)

| Check | Result |
|---|---|
| `uv run pytest -q` | **688 passed, 4 skipped** (standard skip set) |
| `uv run pyright` | 0 errors, 0 warnings |
| `uv run ruff check .` | All checks passed (incl. new `scripts/soak_13a5.py`) |
| `uv run ruff format --check .` | clean |
| CLI smoke | 16 commands; `serve` / `serve-api` / `serve-flask --help` all OK |
| FastAPI UI smoke | `/`→307 · `/ui`,`/ui/new`,`/ui/config`→200 |
| Flask fallback smoke (optional) | 14 url-map rules · `/`→200 (still constructs/serves) |
| **Live soak** | **25/25 steps green; Flask not used** |

---

## 6. Recommendation

**Proceed to Sprint 13B (Flask decommission) — on maintainer approval.**

Justification:
- Code readiness was already met at Gate 13A (parity superset, low one-directional coupling, clean dependency map).
- The missing piece — *operational soak of the flipped default on a real, multi-format, multi-volume novel workflow* — is now **evidenced end-to-end**, and the **Flask fallback was never needed**.
- No regression, no blocker, fallback unused → the operational risk that motivated postponement (R6: losing the only working browser UI) is now substantially retired.

Residual caveat (honest scope): this soak used the `fake` provider and a small fixture corpus driven programmatically over the FastAPI HTTP API — it exercises the same app the browser UI calls, but not a human clicking through `/ui` on a large real novel. If the maintainer wants belt-and-suspenders before deleting Flask, one manual browser pass over `/ui` on a real EPUB is the only remaining gap; otherwise the evidence supports proceeding.

**Decision options for Gate 13A.5 (maintainer):**
- **A — Proceed to 13B now** (recommended): execute the staged removal plan in [SPRINT13A_DECOMMISSION_READINESS.md](SPRINT13A_DECOMMISSION_READINESS.md) §4.
- **B — One manual browser pass first**, then 13B: close the only residual gap (human `/ui` click-through on a real novel) before removal.
- **C — Keep Flask one more cycle**: only if the maintainer is not yet ready to lose the fallback; no technical blocker requires this.

> Per the standing rules, **nothing was removed, deprecated, or flipped in 13A.5.** This document is the soak evidence; the kill switch is the maintainer's Gate 13A.5 decision.
