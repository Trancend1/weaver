# Maintenance

How to keep the repo clean, validated, and reviewable. Coding rules: [ENGINEERING_STANDARDS.md](ENGINEERING_STANDARDS.md). Boundaries: [ADR 002](decisions/002-cli-web-boundary-and-maintenance-structure.md).

## Cleanup rules
- Inventory before delete; classify (active / legacy / dead / generated) before touching.
- **Archive, don't hard-delete** docs/decisions with reference value → `docs/archive/`. Rely on git history only for clearly redundant content.
- Migrate important insight out of a doc/ADR before retiring it.
- Generated/runtime dirs (`.weaver/`, `.tmp_*/`, `.ruff_cache/`, `.venv/`) stay gitignored, never committed.
- Keep `CLAUDE.md` short and operational — no sprint-history dump (history → git + `docs/archive/`).

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

## MVP stabilization validation (Sprint 9 baseline)
The exact gate run to lock the MVP baseline — see [MVP_STABILIZATION_REPORT.md](MVP_STABILIZATION_REPORT.md) for the full matrix.
```bash
uv run pytest -q                  # 561 passed, 4 skipped (expected — see below)
uv run pyright                    # 0 errors, 0 warnings
uv run ruff check .               # All checks passed
uv run ruff format --check .      # all files already formatted
uv run weaver --help              # CLI smoke — 15 commands
```
Web smoke (no port binding): construct `create_api_app()` + FastAPI `TestClient` and assert `/health`·`/version`·`/projects` → 200 and the UI `/`→307·`/ui`·`/ui/new`·`/ui/config` → 200.

**Expected skips (4 — none a regression):** `test_deepseek_live.py` (no `DEEPSEEK_API_KEY`), `test_gemini_live.py` (no `GEMINI_API_KEY`), `test_ollama_live.py` (no local Ollama), `test_secret_store.py::…` POSIX file-mode (Windows host). Live-provider tests are gated by `requires_cloud` / `requires_ollama` and need real keys / a running Ollama — they are **not** run in CI by design.

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
