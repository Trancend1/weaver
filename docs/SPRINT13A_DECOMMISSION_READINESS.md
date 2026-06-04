# Sprint 13A — Post-Flip Stability + Flask Decommission Readiness

**Type:** Readiness audit only. No code removed, no dependency removed, no flip changed.
**Date:** 2026-06-04
**Branch:** `feat/flask-decommission`
**Precondition:** Sprint 12B flipped `weaver serve` → FastAPI UI; Flask retained as `weaver serve-flask`.

---

## 1. Stability Result

The flipped default is **stable**. All validation green, no regressions attributable to the serve flip.

| Check | Command | Result |
|---|---|---|
| Test suite | `uv run pytest -q` | **688 passed, 4 skipped**, 1 warning (99s) |
| Types | `uv run pyright` | **0 errors** |
| Lint | `uv run ruff check .` | **All checks passed** |
| Format | `uv run ruff format --check .` | **238 files already formatted** |
| CLI help | `uv run weaver --help` | 16 commands; `serve` / `serve-api` / `serve-flask` all present |

The 4 skips are the standard environment set — 3 live-provider tests (`DEEPSEEK_API_KEY`/`GEMINI_API_KEY` unset, Ollama unreachable) + 1 POSIX-only file-mode test on Windows. Identical to the Gate 12B baseline; no new skips, no Flask-related skip.

### Serve routing (help text)

| Command | Behavior | Help assertion |
|---|---|---|
| `weaver serve` | FastAPI UI cockpit (default, :8765, opens browser) | "FastAPI UI", "127.0.0.1", points to `serve-flask` |
| `weaver serve-api` | Same FastAPI app, headless (:8000) | "FastAPI cockpit headless… Same app as `weaver serve`" |
| `weaver serve-flask` | Legacy Flask cockpit (fallback, :8765) | "legacy Flask web cockpit", "Legacy fallback" |

### FastAPI UI smoke (TestClient, no live server)

88 route objects · 49 JSON (in-schema) · 34 UI route objects.

| Path | Status |
|---|---|
| `/health` | 200 |
| `/version` | 200 |
| `/` | 307 → `/ui` |
| `/ui` (dashboard) | 200 |
| `/ui/new` | 200 |
| `/ui/config` | 200 |

### Flask fallback smoke (test client, no live server)

14 url-map rules (13 functional + static). `GET /` → **200**. Flask app still constructs and serves end-to-end via `weaver serve-flask`.

**Conclusion:** the flip introduced no regression. The new default works; the fallback still works.

---

## 2. Flask Dependency Map

### 2.1 Modules (`src/weaver/web/**`) — 872 LoC Python + 5 templates + 2 static

| Module | LoC | Flask-only? | Notes |
|---|---:|---|---|
| `web/__init__.py` | 7 | yes | package marker |
| `web/app.py` | 80 | yes | `create_app` / `run_server`; registers 6 blueprints |
| `web/job_manager.py` | 196 | **yes** | Flask-only job/SSE manager. FastAPI uses its own `api/jobs.py` `JobRegistry`. No overlap. |
| `web/routes_config.py` | 65 | yes | blueprint over shared services |
| `web/routes_export.py` | 49 | yes | blueprint over shared services |
| `web/routes_glossary.py` | 114 | yes | blueprint over shared services |
| `web/routes_new.py` | 143 | yes | blueprint; imports `web/file_browser` |
| `web/routes_projects.py` | 77 | yes | blueprint over shared services |
| `web/routes_translate.py` | 113 | yes | blueprint; imports `web/job_manager` |
| `web/file_browser.py` | 28 | **shim** | pure re-export of `services/source_browser.py`. No logic. |
| `web/templates/*.html` | 5 | yes | `base`, `cockpit`, `dashboard`, `glossary`, `new` |
| `web/static/*` | 2 | yes | `cockpit.css`, `htmx.min.js` (Flask copy; FastAPI has its own under `api/static/`) |

### 2.2 Inbound references to `weaver.web` (who would break on removal)

| Source | Line | Kind | Removal impact |
|---|---|---|---|
| `cli/main.py` | 1291 | **runtime import** `from weaver.web.app import run_server` | inside `serve-flask` body only — removed with the command |
| `services/source_browser.py` | 9 | docstring mention | none (text) |
| `api/__init__.py` | 6 | docstring mention | none (text) |

**The only runtime coupling outside the package is the `serve-flask` command.** No `services/`, no `api/`, no `core/` module imports `weaver.web`. Coupling is 🟢 Low and one-directional (web → services, never services → web).

### 2.3 Shared logic that must NOT be removed with Flask

- `services/source_browser.py` — the real browser logic; `web/file_browser.py` is only a re-export shim. FastAPI uses `services/source_browser` directly. **Keep.**
- All `services/*` consumed by the blueprints are shared with FastAPI. **Keep.**

### 2.4 Tests (42 in the Flask orbit)

| File | Disposition on decommission |
|---|---|
| `tests/unit/web/test_job_manager.py` | Flask-only → remove with `job_manager.py` |
| `tests/unit/web/test_file_browser.py` | tests the re-export path; shared logic already covered by `tests/unit/services/test_source_browser.py` → remove with shim |
| `tests/integration/test_web_cockpit.py` | Flask blueprints → remove with Flask |
| `tests/integration/test_cli_serve_routing.py` | **mixed** — covers `serve`→FastAPI **and** `serve-flask`→Flask. Must be *edited* (drop Flask-routing assertions), not deleted, to keep `serve`/`serve-api` coverage. |

### 2.5 Dependencies (`pyproject.toml`)

```toml
web = [
    "flask>=3.0",          # <-- Flask-only; removable in 13
    "fastapi>=0.115",      # keep
    "uvicorn>=0.30",       # keep
    "python-multipart>=0.0.9",  # keep (FastAPI form/upload)
]
```

`flask>=3.0` is the only Flask-specific dependency in the `web` extra. No other module imports `flask`. Removing it leaves the FastAPI stack intact.

### 2.6 Docs referencing Flask

Active docs that mention Flask and would need an update on decommission: `ARCHITECTURE.md`, `COCKPIT_WORKFLOW.md`, `QUICKSTART.md`, `README.md` (root), `DECISIONS.md`, `MAINTENANCE.md`, `MVP_SCOPE.md`, `PROVIDER_AND_MODEL_CONFIG.md`, `TRANSLATION_PIPELINE.md`, ADR `002`/`004`/`007`, plus the sprint audits (`SPRINT10`, `SPRINT12`). Archive docs (`docs/archive/**`, ADR `0016`/`0019`) are historical — leave as-is.

---

## 3. Removal Risk List

| # | Item | Risk | Reason / mitigation |
|---|---|---|---|
| R1 | Delete `src/weaver/web/**` | 🟢 Low | Self-contained package; only inbound runtime user is `serve-flask`. |
| R2 | Remove `serve-flask` command | 🟡 Medium | User-facing CLI surface change. Anyone scripting `weaver serve-flask` breaks. Mitigate: announce in CHANGELOG; the FastAPI default has been the `serve` default since 12B. |
| R3 | Remove `flask>=3.0` from `web` extra | 🟢 Low | No other importer. FastAPI/uvicorn/multipart unaffected. |
| R4 | Edit `test_cli_serve_routing.py` | 🟡 Medium | Must keep `serve`/`serve-api` assertions; only drop Flask-routing test. Do not delete the whole file. |
| R5 | Delete `web/file_browser.py` shim | 🟢 Low | Confirm no test/import targets `weaver.web.file_browser` after web removal (`test_file_browser.py` goes with it). Shared logic stays in `services/source_browser.py`. |
| R6 | Loss of Flask cockpit as fallback | 🟡 Medium | After removal there is no second browser UI if a FastAPI UI regression appears. Mitigate: only proceed once FastAPI UI has lived as default through real use without a UI-blocking defect. |
| R7 | Docs drift | 🟢 Low | Mechanical doc sweep (§2.6); ADR `004`/`007` get a closing note. |
| R8 | `job_manager.py` orphan | 🟢 Low | Confirmed Flask-only (FastAPI uses `api/jobs.py`). Removed cleanly with the package. |

No 🔴 High risks remain **for the code change itself**. The residual concern is operational (R6): removal deletes the only fallback browser UI.

---

## 4. Recommended Decommission Plan

**Recommendation: POSTPONE the actual removal one short interval; proceed to *stage* it as Sprint 13B once the maintainer confirms real-world use of the flipped default.**

Rationale:
- Code readiness is **fully met**: parity proven (Sprint 12A, 12/12 superset), coupling is 🟢 Low and one-directional, the dependency map is clean, removal touches a well-bounded package + one CLI command + one dependency line.
- The **only** thing not yet evidenced is *operational soak* — the flip landed in Sprint 12B; there is no record yet of the FastAPI default being exercised in real day-to-day translation work (not just smoke/CI) since the flip. CLAUDE.md Sprint 13 is explicitly gated on the flip "proving stable **and** explicitly approved."
- Therefore: do not delete Flask in this sprint. Treat 13A as the green-light *readiness* gate, and let the maintainer decide between the two ready-to-execute paths below.

### Decision options for Gate 13A (maintainer)

- **Option A — Proceed to 13B now (decommission).** Justified if the maintainer has already used the FastAPI default for real translation work since 12B and is satisfied. Execute the staged plan below.
- **Option B — Postpone (recommended default).** Keep `serve-flask` for one more usage cycle; revisit after the maintainer has run a real novel end-to-end on the FastAPI default. Lowest regret; cost is carrying 872 LoC + 1 dep a bit longer.
- **Option C — Keep Flask fallback indefinitely.** Only if the maintainer wants a permanent second UI. Not recommended — it perpetuates dual maintenance against ADR `004` direction.

### Staged removal plan (for 13B, when authorized)

One PR, one concern (decommission), in this order:

1. Remove `serve-flask` command + `run_server` import from `cli/main.py`; keep `serve` / `serve-api`.
2. Edit `tests/integration/test_cli_serve_routing.py` — drop Flask-routing test, keep FastAPI `serve`/`serve-api` coverage.
3. Delete `tests/unit/web/`, `tests/integration/test_web_cockpit.py`.
4. Delete `src/weaver/web/**` (10 py + 5 templates + 2 static).
5. Remove `flask>=3.0` from the `web` extra in `pyproject.toml`; lock refresh.
6. Doc sweep (§2.6): update active docs; add closing note to ADR `004`/`007`; mark Sprint 13 done in CLAUDE.md.
7. Re-validate: pytest / pyright / ruff check / ruff format / `weaver --help` (15 commands) / FastAPI UI smoke. Expect ~646 tests (688 − 42 Flask) ±, adjusted for the edited routing test.

---

## 5. Gate 13A

- **Stability:** ✅ green across the board; no regression from the serve flip.
- **Flask dependency map:** ✅ documented (§2) — self-contained package, one CLI entry point, one dependency line, shared logic already extracted.
- **Removal risk:** ✅ listed (§3) — no 🔴 code risk; residual risk is operational fallback loss (R6) + user-facing CLI change (R2).
- **Recommendation:** **Postpone removal (Option B)** pending maintainer confirmation of real-world soak; readiness itself is **met** and 13B is fully staged and ready to execute on approval.

> **Do not remove Flask in 13A.** This document is the readiness evidence; the kill switch is the maintainer's Gate 13A decision.
