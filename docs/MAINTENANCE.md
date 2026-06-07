# Maintenance

How to keep the repo clean, validated, and reviewable. Coding rules: [ENGINEERING_STANDARDS.md](ENGINEERING_STANDARDS.md). Boundaries: [ADR 002](decisions/002-cli-web-boundary-and-maintenance-structure.md).

## Cleanup rules
- Inventory before delete; classify (active / legacy / dead / generated) before touching.
- **Prefer git history over a `docs/archive/`.** Once a completed point-in-time doc's conclusions are captured in `CLAUDE.md` / active docs, remove it from the tree — git history is the archive. (The former `docs/archive/` + completed sprint/phase reports were removed on 2026-06-05.)
- Migrate important insight out of a doc/ADR before retiring it.
- Generated/runtime dirs (`.weaver/`, `.tmp_*/`, `.ruff_cache/`, `.venv/`) stay gitignored, never committed.
- Keep `CLAUDE.md` short and operational — no sprint-history dump (history → git).

## Docs update rules
- Docs are the spec; code follows docs. If code contradicts a doc, fix the doc or ask — don't silently diverge.
- Active docs must match the current codebase. Mark unbuilt features **(planned)**; never describe an MVP gap as if it exists.
- When you add/move/remove a doc, update [docs/README.md](README.md), [DECISIONS.md](DECISIONS.md), and the [CLAUDE.md §1](../CLAUDE.md) map. No dangling links.
- New architectural decision → new ADR that supersedes the old one explicitly.

## Testing rules
```bash
uv run pytest -m "not requires_ollama and not requires_cloud"
uv run ruff check .
uv run ruff format --check .
uv run pyright
```
- Tests mirror the source tree. Use `FakeProvider` — **never** a live LLM in CI. Fixtures = public-domain only.
- `requires_ollama` / `requires_cloud` / `slow` markers gate environment-dependent tests; CI skips them.
- Acceptance gate: `uv run python bench/run_acceptance_gate.py` (AC-1..AC-9).

## Phase F EPUB closeout validation
Use this bundle when changing EPUB package parsing, preview, preservation
context, validation, or export fidelity checks:

```bash
uv run pytest -q
uv run pyright
uv run ruff check .
uv run ruff format --check .
uv run weaver --help
```

Targeted smoke before a full run: EPUB structure tests, preview service/API/UI
tests, renderer EPUB tests, import-source tests, and export-fidelity tests.
OCR/vision remains out of scope unless a separate ADR/approval explicitly adds
an adapter, dependency/provider, credential behavior, or image output contract.

## MVP stabilization validation (Sprint 9 baseline)
The exact gate run to lock the MVP baseline — the full matrix lives in git history.
```bash
uv run pytest -q                  # 561 passed, 4 skipped (expected — see below)
uv run pyright                    # 0 errors, 0 warnings
uv run ruff check .               # All checks passed
uv run ruff format --check .      # all files already formatted
uv run weaver --help              # CLI smoke — 15 commands
```
Web smoke (no port binding): construct `create_api_app()` + FastAPI `TestClient` and assert `/health`·`/version`·`/projects` → 200 and the UI `/`→307·`/ui`·`/ui/new`·`/ui/config` → 200.

**Current baseline (Phase D complete, 2026-06-06):** `uv run pytest -q` → **780 passed / 4 skipped** (same expected skips; +77 across the five Phase D items over the Phase B6 703), pyright 0, ruff check + format clean, CLI 15 commands, clean wheel build (DOCX / QA-thresholds / export-bundle / provider-config modules all packaged). **DOCX smoke:** `render_docx` → valid `.docx` ZIP with `[Content_Types].xml`, `_rels/.rels`, `word/{document,styles}.xml`, `word/_rels/document.xml.rels`; `POST /projects/{name}/export/novel {"target":"docx"}` → 202 → job `done` with one `.docx` artifact per volume under `output/docx/`. **Bundle smoke:** `{"target":"txt","bundle":true}` → `result.bundle_path` = `output/txt/bundle-txt.zip`. **QA config smoke:** a `[qa] fallback_heavy_ratio` override changes the report; a bad value → `ConfigError`. **QA tree-badges smoke:** project tree render runs zero `analyze_*`; `GET …/qa/tree-badges` runs novel QA once and returns `hx-swap-oob` badges. **Provider smoke:** bad numeric `[provider]` value → `ConfigError`; API-key value never appears in any error/status. **QA smokes:** JSON `GET /projects/{name}/qa` (+ `…/volumes/{id}/qa`, `…/chapters/{id}/qa`) → 200 with `schema_version: 2`, `badge`, severity counts; UI `/ui/projects/{name}/qa` + `…/chapters/{id}/qa` → 200; export preflight `GET /ui/projects/{name}/export/preflight` → 200 (advisory, never blocks). QA is read-only/deterministic — a regression test asserts the QA path performs no DB write and calls no provider.

**Expected skips (4 — none a regression):** `test_deepseek_live.py` (no `DEEPSEEK_API_KEY`), `test_gemini_live.py` (no `GEMINI_API_KEY`), `test_ollama_live.py` (no local Ollama), `test_secret_store.py::…` POSIX file-mode (Windows host). Live-provider tests are gated by `requires_cloud` / `requires_ollama` and need real keys / a running Ollama — they are **not** run in CI by design.

**Optional `tui` extra (textual):** the Textual dashboard (`weaver dashboard`) is typed against `textual`, which is **not** installed in the base/CI env — so `weaver.tui.*` type errors and the `tui/test_dashboard_app.py` regression tests stay latent unless you install the extra. Before changing `src/weaver/tui/**`, run the gate with it: `uv sync --extra web --extra dev --extra tui --extra wizard`, then `uv run pyright` (must be 0 with textual present) + `uv run pytest -q`.

## Regression checklist (before merge / release)
- [ ] `pytest` green (CI subset)
- [ ] ruff lint + format clean
- [ ] pyright: 0 errors
- [ ] acceptance gate PASS
- [ ] CLI smoke: `weaver --version`, `weaver --help`, a `fake`-provider end-to-end run
- [ ] Web smoke: `weaver serve` (when `weaver[web]`) binds `127.0.0.1`, dashboard loads, a `fake` translate streams
- [ ] No CLI command/flag broken (wire-compatible)
- [ ] Shared/core has no web/CLI framework imports
- [ ] No API key in any config file; secret-scan hook passes
- [ ] No AI attribution trailer / bot author in commits (CLAUDE.md §4.6)
- [ ] Docs match changes; no dangling links

## Web framework discipline (FastAPI, ADR 004)
- The Flask→FastAPI migration is **complete** (Sprint 13B removed Flask; FastAPI is the only web cockpit).
- Keep async confined to `api/`; never leak it into shared-core. Pydantic at the boundary only.
- UI routers stay presentation-only thin adapters over `services/*` — no business logic, no storage access.

## Release / baseline process
- Bump `pyproject.toml` version; update `CHANGELOG.md`.
- Run the full regression checklist + acceptance gate.
- Build wheel (`uv build --wheel`); verify web assets (`templates/*.html`, `static/*`) ship in the wheel when relevant.
- Commit author/committer = maintainer only. PyPI publish/tag is credential-gated.
