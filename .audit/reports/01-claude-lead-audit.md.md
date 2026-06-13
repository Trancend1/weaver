# Weaver — Codebase Cleanup & Bug Audit

**Date:** 2026-06-13
**Branch:** `chore/codebase-audit`
**Auditor:** Lead Codebase Auditor (Claude, orchestrator role)
**Scope:** `src/weaver`, `tests/`, `scripts/`, packaging/config (`pyproject.toml`, `uv.lock`)
**Mode:** Read-only audit. No code modified, no files deleted, no commits created.

---

## Executive Summary

The codebase is in **excellent health**. Every automated gate passes against the live tree:

| Gate | Command | Result |
|---|---|---|
| Compile | `python -m compileall src tests scripts` | exit 0 |
| Lint | `uv run ruff check .` | exit 0 (clean) |
| Types | `uv run pyright` | **0 errors, 0 warnings, 0 info** |
| Tests | `uv run pytest -q` | **1404 passed, 4 skipped** in 5m54s |

The 4 skips are environment-gated and expected: `DEEPSEEK_API_KEY`/`GEMINI_API_KEY` not set, Ollama not running, and one POSIX-only file-mode test (Windows host).

Structural checks are equally clean:

- **All 27 routers registered** in `api/app.py` (no orphaned router).
- **Zero orphan modules** — every source module is imported via a resolved AST reference map (`from pkg import leaf` resolution included).
- **No** bare `except:`, `TODO`/`FIXME` debt, mutable default args, `== None`, `shell=True`, `eval(`, `exec(`, or `os.system`.
- **No SQL injection vector** — all `f"...{table}..."` SQL strings interpolate hardcoded internal literals (table names / integer PRAGMA values that SQLite cannot parameterize); the variable value is always passed via `?` binding.

Findings are therefore few and high-confidence: **3 truly dead symbols** safe to remove, **1 confirmed correctness bug** (already tracked as WV-014), and a small set of low-priority cleanup/observation items.

---

## High-Confidence Bugs

### BUG-1 — Furigana (`<rt>`) leaks into translation input (WV-014, confirmed present)

1. **File:** `src/weaver/readers/epub.py`
2. **Location:** `_element_text()` at line 1430; output feeds `source_text` / `normalized_source_text` at lines 1417–1418.
3. **Category:** Logic / translation-correctness bug.
4. **Evidence:**
   ```python
   def _element_text(element: ElementTree.Element) -> str:
       return collapse_whitespace("".join(element.itertext()))
   ```
   `ElementTree.itertext()` recursively yields all descendant text, including the `<rt>` reading inside `<ruby>` elements. That text becomes `source_text` → `normalized_source_text`, i.e. the exact JP string sent to the provider. A ruby like `漢字(かんじ)` flattens to `漢字かんじ` in the model input. Renderer preservation is **not** the defect — this is on the import/segmentation path.
5. **Impact:** **Medium-High** — silently degrades translation input on any EPUB using ruby (common in light novels).
6. **Recommended fix:** Strip/skip `<rt>` (and `<rp>`) subtrees before text extraction; extract base text only, optionally retaining the reading in separate metadata rather than inline.
7. **Cleanup complexity:** Medium (ruby-aware text walk + ruby fixture test).
8. **Safe to remove immediately:** N/A (behavior fix, not removal).
9. **Confidence:** High (code confirmed; matches documented WV-014 carry-forward in `CLAUDE.md` §2.3).
10. **Verification command:** add a unit test with a `<ruby>漢字<rt>かんじ</rt></ruby>` fixture asserting `source_text == "漢字"`; `uv run pytest tests/unit/readers/test_epub_ruby_spike.py -q`.

> No other behavioral bugs found. The provider JSON-repair retry (`deepseek.py:89-109`) correctly **re-raises** on a double parse failure (fail-visible). The `except BaseException: … raise` in `source_browser.py:181` is a correct temp-file cleanup-then-reraise.

---

## High-Confidence Safe Removals (dead code)

All three are defined once and referenced **nowhere** in `src/`, `tests/`, `scripts/`, templates, or docs. Verified via AST reference map + full-repo grep; `storage/__init__.py` has no `__all__`/re-export.

### DEAD-1 — `get_project_by_uuid`
1. **File:** `src/weaver/storage/projects.py`
2. **Location:** function `get_project_by_uuid`, line 138 (~30 lines).
3. **Category:** Dead code (unused storage function).
4. **Evidence:** only repo-wide occurrence is the `def` site.
5. **Impact:** Low (maintenance noise).
6. **Fix:** Delete the function.
7. **Complexity:** Small.
8. **Safe to remove immediately:** Yes.
9. **Confidence:** High.
10. **Verify:** `grep -rn "get_project_by_uuid" .` → only def site; then `uv run pytest tests/unit/storage -q`.

### DEAD-2 — `count_candidates_for_project`
1. **File:** `src/weaver/storage/candidates.py`
2. **Location:** function `count_candidates_for_project`, line 256 (~20 lines).
3. **Category:** Dead code (unused storage function).
4. **Evidence:** single repo-wide occurrence (def site only).
5. **Impact:** Low.
6. **Fix:** Delete the function.
7. **Complexity:** Small.
8. **Safe to remove immediately:** Yes.
9. **Confidence:** High.
10. **Verify:** `grep -rn "count_candidates_for_project" .` → only def site; then `uv run pytest tests/unit/storage/test_repositories.py tests/unit/api/test_candidates.py -q`.

### DEAD-3 — `ErrorResponse` schema
1. **File:** `src/weaver/api/schemas.py`
2. **Location:** class `ErrorResponse`, line 123.
3. **Category:** Dead code (unused pydantic model).
4. **Evidence:** single repo-wide occurrence; error responses use `JSONResponse(... {"detail": ...})` / `HTTPException` directly (e.g. `api/app.py:144`), not this model.
5. **Impact:** Low.
6. **Fix:** Delete the class.
7. **Complexity:** Small.
8. **Safe to remove immediately:** Yes.
9. **Confidence:** High.
10. **Verify:** `grep -rn "ErrorResponse" .` → only def site; then `uv run pytest tests/unit/api -q`.

---

## Medium-Confidence Cleanup Candidates

### CLN-1 — Stale migration soak driver
1. **File:** `scripts/soak_13a5.py`
2. **Location:** whole file (module-level script).
3. **Category:** Stale dev artifact.
4. **Evidence:** Header: *"Sprint 13A.5 — FastAPI default soak driver … Reusable for the Sprint 13B decommission re-validation cycle."* Sprint 13B (Flask removal) is long complete (ADR 004; current line is post-Sprint R). Referenced by no CI, githook, or doc.
5. **Impact:** Low (not imported; cannot affect runtime).
6. **Fix:** Owner decides — if the manual end-to-end soak harness is still wanted, rename/relocate to a generic `scripts/soak.py` and update the header; otherwise delete.
7. **Complexity:** Small.
8. **Safe to remove immediately:** **No** — potentially reusable manual harness; owner decision.
9. **Confidence:** Medium.
10. **Verify:** `grep -rn "soak" . --include=*.py --include=*.yml --include=*.toml` and check `.githooks/`.

---

## Suspicious But Do-Not-Remove Yet

- **`assert ... # guarded by caller`** type-narrowing guards (`api/jobs.py:915`, `services/batch_translate.py:398/409`, `export_book.py:416/427/466/468`, `workspace_index.py:143`). Stripped under `python -O`. They are invariants, not validation, so normal-run behavior is unchanged. **Leave as-is**; be aware they vanish under optimized bytecode. No action unless `-O` enters packaging.
- **`_extract_fugashi_proper_nouns` import guards** (`services/glossary.py:247,252`, `except Exception`). Slightly broad (`ImportError`/init-failure would be more precise) but an intentional optional-dependency fallback returning `[]`. Leave as-is.

---

## Duplicate / Legacy Logic

- **`_count(connection, table_name)`** appears verbatim in `services/project.py:443`, `project_overview.py:183`, `workspace_index.py:353`, `workspace_resources.py:220` (identical 2-line body). Within the project's "one concept per file" discipline; each is private. Consolidating crosses module boundaries for marginal benefit. **Low priority — note only, no action** without an explicit refactor decision. (Read-only count logic, safe either way.)
- No legacy parallel implementations found. The Flask cockpit was fully removed (ADR 004); no Flask residue in `src/`.

---

## Dependency / Config Cleanup

- **All declared runtime deps are used:** `typer`, `rich`, `pydantic`, `ebooklib`, `jinja2`, `httpx` (direct in `providers/ollama.py`), `openai` (deepseek/custom), `google-generativeai` (gemini). Optional extras `textual` (tui), `questionary` (wizard), `fastapi`/`uvicorn`/`python-multipart` (web) all imported. **No unused dependency.**
- **OBS-1 — `fugashi` is imported but not declared** (`services/glossary.py:246`). Documented as a manual install in `README.md:293-295` (MeCab needs system binaries); code degrades gracefully to `[]` when absent. **Recommendation (low):** consider a `[glossary]` optional extra or a doctor-check cross-reference for discoverability. Not a defect.
- No unused config keys or pyproject sections; ruff/pyright/pytest config all active and matching enforced rules.

---

## Test Coverage Gaps

- **GAP-1 — `readers/epub_validation.py` (`validate_epub_structure`, 264 lines)** has **no dedicated unit test**; only transitively exercised via `readers/epub.py` tests. Largest untested-by-name module; validation branches deserve direct coverage. **Confidence: Medium.** Verify: `grep -rn "validate_epub_structure" tests/` (no hits today).
- `api/schemas.py`, `api/templating.py`, `api/ui_context.py`, `readers/html_blocks.py`, `readers/synthetic_document.py` lack name-level tests but are well covered transitively (UI router tests, reader integration tests). **Acceptable — no action.**
- The 3 dead symbols (DEAD-1/2/3) have no tests, consistent with being dead.

---

## Prioritized Cleanup Plan

Ranked by maintenance impact vs. implementation/regression risk:

| # | Action | Impact | Impl risk | Regression risk | Suggested branch |
|---|---|---|---|---|---|
| 1 | **Fix BUG-1** (ruby/furigana leak, WV-014) — ruby-aware extraction + fixture test | High | Medium | Low (new test + existing reader suite) | `fix/epub-ruby-furigana` |
| 2 | **Remove DEAD-1/2/3** (3 unused symbols) in one commit | Low | Low | Very low | `chore/remove-dead-symbols` |
| 3 | **GAP-1** — add dedicated `test_epub_validation.py` | Medium | Low | None (test-only) | bundle with #1 or standalone |
| 4 | **CLN-1** — owner decision on `soak_13a5.py` (rename/keep/delete) | Low | Low | None | `chore/scripts-cleanup` |
| 5 | **OBS-1** — optional `[glossary]` extra for `fugashi` | Low | Low | None | docs/packaging |

**Do-not-touch without ADR/approval** (per `CLAUDE.md` §2.3 carry-forward invariants): `workspace_index` / read-only workspace services (no mutation/hashing on render paths), provider `complete()` domain-agnosticism, migrations, single-project-DB rule. None of the recommended changes cross those lines.

**Per-batch verification (run after each cleanup commit):**
```
python -m compileall src tests scripts
uv run ruff check .
uv run pyright
uv run pytest -q
weaver --help    # entry-point smoke (project.scripts: weaver.cli.main:app)
```

---

## Audit Method (evidence trail)

- **Reference map:** AST walk of all `src/weaver/*.py`, resolving `import X`, `from X import leaf` (incl. `pkg.leaf` module resolution) across `src/`, `tests/`, `scripts/`. Cross-checked router registration in `api/app.py`, Typer command decorators in `cli/main.py`, and decorator-registered FastAPI handlers (excluded from dead-code suspects as framework auto-discovery).
- **Symbol-level dead-code:** every public top-level `def`/`class` whose bare name appears ≤1× repo-wide flagged, then manually filtered against decorator-registered entry points → 3 genuine dead symbols.
- **Bug patterns:** grep for bare/broad `except`, `BaseException`, `TODO/FIXME`, mutable defaults, `== None`, `is`-with-literal, missing f-string prefixes, `shell=True`/`eval`/`exec`/`os.system`, SQL string interpolation in `execute()`, `subprocess` call sites — each hit read in context.
- **Security:** confirmed all `subprocess.run` calls use list-form args (no `shell=True`); pager/editor sourced from `$PAGER`/`$EDITOR` (standard); all dynamic-table SQL uses hardcoded literals with `?`-bound values.
- **Validation tooling:** `compileall` (0), `ruff` (0), `pyright` (0/0/0), `pytest` (1404 passed / 4 skipped).

**No code was modified, deleted, or committed during this audit.**
