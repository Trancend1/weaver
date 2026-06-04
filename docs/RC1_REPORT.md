# Weaver MVP — Release Candidate 1 (RC1) Report

**Date:** 2026-06-05
**Branch:** `main` (clean, synced with `origin/main`)
**Baseline commit:** `4a0c882`
**Verdict:** ✅ **GO for RC1.** No release-blocking defects. All validation gates green; full cockpit soak and clean-install smoke pass. Two doc-accuracy fixes and one validation-script portability fix were applied during this sprint (details in §6).

This is a release-candidate **verification** sprint — no new features, no UI polish, no provider expansion, no architecture migration (per sprint rules). It certifies the MVP "Web Cockpit Foundation" (FastAPI cockpit, export, batch, TM, glossary, character DB) after the Flask decommission.

---

## 1. Scope checklist

| # | Scope item | Result | Evidence |
|---|---|---|---|
| 1 | All recent PRs merged | ✅ | PRs `#1`–`#16` all `MERGED`; working tree clean; `main` == `origin/main` |
| 2 | Full validation | ✅ | §3 — pytest 653/4-skip, pyright 0, ruff + format clean |
| 3 | FastAPI cockpit soak | ✅ | §4 — `scripts/soak_13a5.py` 25/25, "Flask fallback NOT used" |
| 4 | CLI smoke | ✅ | §3 — 15 commands; `serve`/`serve-api` correct; no `serve-flask` |
| 5 | Clean-environment install | ✅ | §5 — wheel built + installed into fresh venv; console script works |
| 6 | README / QUICKSTART accuracy | ✅ (fixed) | §6 — stale Flask-era cockpit bullets in README corrected; QUICKSTART already accurate |
| 7 | No stale Flask references | ✅ (fixed) | §6 — 7 source docstrings/comments corrected; active docs already past-tense; archive/sprint reports/ADRs are intentional history |
| 8 | No secret leaks | ✅ | §7 — key-pattern scan clean; secrets gitignored; `secrets.toml` never tracked |
| 9 | No orphaned artifacts | ✅ | §7 — working tree clean; only intentional public-domain `.epub` fixtures tracked |
| 10 | MVP release notes | ✅ | `CHANGELOG.md` `[Unreleased]` populated; §8 here |

---

## 2. PR / merge status

All 16 PRs are merged into `main`. The cockpit era (Sprints 1–13) is fully landed:

- `#16` no-color via `NO_COLOR` env (TUI dashboard) · `#15` **remove legacy Flask cockpit** · `#14` flip default `serve`→FastAPI · `#13` close Flask parity gaps + full Jinja2/HTMX UI · `#12` MVP stabilization + live-provider E2E · `#11` export · `#10` batch · `#9` TM · `#8` glossary/characters · `#7` provider/AI translate · `#6` workspace · `#5` FastAPI foundation · `#4` Novel/Volume/Chapter model · `#1`–`#3` reset + CLI baseline.

No open PRs block the RC.

---

## 3. Validation results

All commands run on Windows 11 / Python 3.12.7 / `uv` managed env.

| Gate | Command | Result |
|---|---|---|
| Dependency sync | `uv sync --all-extras` | ✅ Resolved 73 / checked 72 packages |
| Tests | `uv run pytest -q` | ✅ **653 passed, 4 skipped, 1 warning** (95s) |
| Types | `uv run pyright` | ✅ **0 errors, 0 warnings** |
| Lint | `uv run ruff check .` | ✅ All checks passed |
| Format | `uv run ruff format --check .` | ✅ 227 files already formatted |
| CLI | `uv run weaver --help` | ✅ **15 commands** |
| Serve | `uv run weaver serve --help` | ✅ FastAPI UI, binds `127.0.0.1`, port 8765 |
| Serve (headless) | `uv run weaver serve-api --help` | ✅ Same FastAPI app headless, port 8000 |

**Skips (all expected, environmental):**
- `test_deepseek_live` / `test_gemini_live` — live-provider API keys not set (CI rule: no live LLMs).
- `test_ollama_live` — no local Ollama running.
- `test_secret_store` (POSIX file-mode) — skipped on Windows.

**Warning (non-blocking):** `StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated; install httpx2 instead` — third-party (FastAPI TestClient) deprecation, test-only. Tracked in §9.

---

## 4. Cockpit soak workflow

`scripts/soak_13a5.py` drove a full realistic novel workflow over HTTP against a **live `weaver serve` FastAPI cockpit** (`127.0.0.1:8765`), `fake` provider, 3 volumes (EPUB + TXT + HTML).

**Result: 25/25 steps passed — "ALL STEPS PASSED — Flask fallback NOT used."**

Highlights:
- create (EPUB) → import TXT (vol 2) → import HTML (vol 3) → tree shows **3 volumes** `[(1,2),(2,2),(3,2)]`
- workspace read → manual save (`status=manual`) → history (5 attempts)
- translate chapter: `translated=3, failed=0` (1 manual segment protected, `skipped=1`)
- retranslate `force_selected`: `translated=4, failed=0`
- glossary CRUD + candidate review · character DB · TM (4 entries) · project-scoped config read/write
- batch novel: `chapters 6/6, segments 19 translated, failed=0`
- export **EPUB / TXT / HTML**: 3/3 artifacts each, all verified present on disk

The soak was run **twice** (with and without forced UTF-8 stdout) to confirm both the workflow and the script-portability fix in §6.

---

## 5. Clean-environment install smoke

Packaging verified end-to-end with no editable/source install:

1. `uv build` → `dist/weaver-0.6.0-py3-none-any.whl` (+ sdist) built successfully.
2. Fresh isolated venv (`uv venv`), then `uv pip install "weaver-0.6.0-...whl[web]"` → 57 packages installed.
3. Console-script smoke:
   - `weaver --version` → `weaver 0.6.0`
   - `weaver --help` → 15 commands present
   - `weaver serve --help` → renders (requires FastAPI; proves `[web]` extra wired)
   - `import flask` → **ABSENT**; `import fastapi` → present; `import weaver` → `0.6.0`

No Flask/Werkzeug present in the resolved dependency set.

---

## 6. Changes made during RC hardening

Doc/comment + tooling only — **zero product-behavior change.** Re-validated green after edits.

**Stale Flask references in source (now factually wrong post-decommission):**
- `src/weaver/api/app.py` — module docstring + UI-mount comment claimed "Flask stays the default `weaver serve` cockpit." → corrected to FastAPI-only.
- `src/weaver/api/routers/ui.py` — claimed "Flask remains the default `weaver serve` cockpit." → corrected.
- `src/weaver/api/routers/ui_admin.py` — "Flask and the JSON API are untouched." → dropped Flask.
- `src/weaver/api/routers/config.py` — "the Flask `/config` route are untouched." → dropped.
- `src/weaver/api/routers/glossary_review.py` — "and Flask `/glossary` surfaces use." → dropped.
- `src/weaver/api/jobs.py` — "no FastAPI or Flask imports" → "no FastAPI imports".

**README cockpit accuracy (carried over from the Flask cockpit):**
- "Export — trigger **Markdown or EPUB** export" → "Export — trigger **EPUB / TXT / HTML** export" (matches the FastAPI export targets in `project.html`).
- Translate bullet "start with **first-N / retry-failed**" → describes the actual UI **retranslate modes** (skip-existing / non-manual / force-selected).
- "upload an **EPUB**" → "upload a source file (**EPUB/TXT/HTML**)".

**Validation-script portability:**
- `scripts/soak_13a5.py` — added a guarded `sys.stdout.reconfigure(encoding="utf-8")` so the soak runs on legacy Windows codepages (cp1252) without a `UnicodeEncodeError` when echoing Japanese. Previously the documented command crashed at the glossary step unless `PYTHONUTF8=1` was set manually.

---

## 7. Security & hygiene audit

- **Secrets:** repo-wide scan for `sk-…`, `AIza…`, `gsk_…`, `sk-ant-…`, PEM private-key headers → **no matches.** `secrets.toml` is gitignored and never tracked; the secret store lives at `~/.weaver/secrets.toml` (mode `0o600`); keys resolve from env or store only and are never rendered/logged (verified by design + tests).
- **Orphaned artifacts:** `git status` clean (no uncommitted/untracked). Only "artifact-looking" tracked files are `tests/fixtures/aozora_sample.epub` and `tests/fixtures/synthetic_200_chapter.epub` — intentional public-domain test fixtures. Local runtime dirs (`.weaver/`, `.venv/`, caches, `dist/`, `.tmp_*`) are gitignored; the personal test novel is gitignored by name.
- **Flask residue:** `flask`/`werkzeug`/`blinker`/`itsdangerous` absent from `uv.lock` and from a clean install; no `weaver.web` module; `serve-flask` command gone.

---

## 8. Release notes (MVP RC1)

Full notes are in `CHANGELOG.md` (`[Unreleased]`). Summary:

- **Added:** FastAPI web cockpit (`weaver serve`) + headless API (`weaver serve-api`); Novel→Volume→Chapter model with EPUB/TXT/HTML import; JP/EN workspace with edit/save/history; in-cockpit provider config + chapter/selection translate + safe-retranslate modes; glossary & character DB with prompt injection + candidate review; translation memory (lookup-before-AI); batch chapter/volume/novel with live progress + cancel; volume-aware EPUB/TXT/HTML export; local secret store.
- **Changed:** web framework is FastAPI (ADR 004); `serve` defaults to the FastAPI cockpit; core stays framework-agnostic.
- **Removed (breaking, web surface):** legacy Flask cockpit (`serve-flask`, `src/weaver/web/**`, `flask` dependency).
- **Fixed:** per-volume chapter/segment id scoping (import re-parenting bug); DeepSeek healthcheck JSON mode.

---

## 9. Known issues (non-blocking)

| Issue | Severity | Notes |
|---|---|---|
| Stale version string `0.6.0` | ✅ Resolved in RC branch | Bumped to **`0.7.0`** (`pyproject.toml`, `src/weaver/__init__.py`, README/QUICKSTART, `uv.lock`) and re-validated green. Validation/clean-install evidence in §3/§5 was captured pre-bump (against the `0.6.0` wheel). |
| `StarletteDeprecationWarning` (httpx + TestClient) | Low | Third-party, test-only. Will resolve on a future FastAPI/Starlette/httpx bump. No action for RC. |
| CHANGELOG had no `0.2.0`–`0.6.0` entries | Low (now mitigated) | Those internal version strings were never released; `[Unreleased]` now consolidates the cockpit era. |
| `Development Status :: 3 - Alpha` classifier | Informational | Consistent with a pre-1.0 RC; revisit if tagging `v1.0.0`. |

No correctness, security, or data-integrity issues found.

---

## 10. Deferred roadmap (out of MVP, intentionally not in RC1)

Consolidated from `docs/MVP_STABILIZATION_REPORT.md` §4 and ADR `005`:

- **DOCX export** — returns HTTP 422 (handled). Deferred out of MVP.
- **Cockpit UI/UX polish** — current UI is functional parity, not visual polish: empty states, layout, visual hierarchy (ADR `005`).
- **Combined EPUB / ZIP bundle export.**
- **Cockpit export/batch monitor UI refinements** beyond the current self-polling panels.
- **Multi-volume legacy CLI** — `weaver translate` / `weaver export` stay single-volume; multi-volume is the cockpit's job (by design).

---

## 11. Recommended version tag

No git tags currently exist; this would be the **first tagged release**.

**Primary recommendation: `v0.7.0-rc.1`.**
Rationale: the stale `0.6.0` string predates the entire FastAPI cockpit and the breaking Flask removal. In 0.x semver, a breaking change bumps the minor; `0.7.0` cleanly marks "first MVP cockpit". The `-rc.1` suffix matches this candidate. On promotion, drop the suffix → `v0.7.0`.

Steps:
1. ✅ Done in this RC branch — `version` bumped to `0.7.0` in `pyproject.toml`,
   `src/weaver/__init__.py`, README/QUICKSTART, and `uv.lock`.
2. Maintainer, on promotion to final: rename `CHANGELOG.md` `[Unreleased]` →
   `[0.7.0] - <date>` and add the compare/tag links.
3. Maintainer: tag `v0.7.0-rc.1` on the merge commit and push.

**Alternative: `v1.0.0-rc.1`** — defensible if the maintainer treats "MVP complete" as the 1.0 milestone. This should also bump the `Development Status` classifier to `4 - Beta` (or `5 - Production/Stable`). Given the project is single-maintainer and still self-labels Alpha, `0.7.0-rc.1` is the more conservative, lower-commitment choice.

---

## 12. After RC1 — next-phase options

Choose one (per the sprint brief):

- **A — UI/UX Polish:** improve cockpit usability, layout, empty states, visual hierarchy (unblocks ADR `005`).
- **B — Provider Expansion:** OpenAI / OpenRouter / Groq / stronger `custom` support.
- **C — Packaging / Distribution:** `pipx`/`uv tool install`, local launcher, release artifacts, PyPI publish.
- **D — Quality Translation Features:** QA checks, consistency checker, terminology warnings.

_No phase is started by this report; it only certifies RC1 and lays out the options._
