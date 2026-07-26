# Handoff: Release Captain — v0.7.3 M5 Validation & Release Gate

**Track:** T9 (Release & Final Gate), with T6 (QA) and T0 (Docs)
**Date:** 2026-07-26
**Branch:** `chore/v073-release-gate`
**Verdict:** 🟡 **Release-ready offline; tag deliberately withheld.** Every gate reachable
without live credentials is green. Four live/tooling validations were **deferred by the
owner on 2026-07-26**, so §2.4's live criteria stay open and **`v0.7.3` is not tagged**.

---

**Scope:** Run the full bench suite + acceptance gate with before/after evidence, add the
missing gated live tests (Gemini `requires_cloud`, first-ever `requires_ollama`), bump the
version, cut the CHANGELOG, work the `docs/MAINTENANCE.md` regression checklist, and decide
tag readiness.

**Files/Areas Touched:**

| File | Change |
| --- | --- |
| `tests/integration/providers/test_gemini_live.py` | **new** — gated live Gemini test over `…/v1beta/openai` |
| `tests/integration/providers/test_ollama_live.py` | **new** — first-ever `requires_ollama` test, keyless `:11434/v1` |
| `src/weaver/providers/registry.py` | gemini shim default model `gemini-1.5-flash` → `gemini-2.5-flash` |
| `src/weaver/__init__.py` | `__version__` `0.7.0` → `0.7.3` (**was a shipped bug**, see below) |
| `pyproject.toml` · `uv.lock` | version `0.7.2` → `0.7.3` |
| `desktop/tauri.conf.json` | synced to `0.7.3` via `sync-version.ps1` |
| `desktop/scripts/check-version.ps1` | now also guards `src/weaver/__init__.py` |
| `tests/unit/test_version.py` | **new drift guards** vs `pyproject.toml` + `tauri.conf.json` |
| `CHANGELOG.md` | `[0.7.3]` section; note on the stale `[Unreleased]` block |
| `CLAUDE.md` · `AGENTS.md` | §2.1/§2.3/§2.4/§2.5 updated; AGENTS.md re-synced (was 2 milestones behind) |
| `git config core.hooksPath` | `.git/hooks` → `.githooks` (**local config, not a tracked file**) |

---

## Two latent release bugs the gate caught

Both had shipped. Neither was in the M5 plan; both are exactly what a release gate is for.

### 1. `weaver --version` under-reported through two releases

`src/weaver/__init__.py` held `__version__ = "0.7.0"` while `pyproject.toml` (documented in
`docs/MAINTENANCE.md` as the **single source of truth**) had moved to `0.7.2`. So
`weaver --version`, `GET /version`, and the OpenAPI `version` field all reported **0.7.0**
across the v0.7.1 **and** v0.7.2 releases.

Why nothing caught it — every existing assertion was self-referential:

```python
assert weaver.__version__ in result.output          # tests/unit/test_version.py
assert app.version == __version__                   # tests/unit/api/test_app.py
assert response.json() == {"name": "weaver", "version": __version__}
```

These stay green for *any* value of `__version__`. `check-version.ps1` compared pyproject ↔
tauri ↔ tag but never looked at the Python package.

Fix: `test_package_version_matches_pyproject` parses `pyproject.toml`, and
`check-version.ps1` gained the same check so the release workflow fails on drift too.
**Proven load-bearing by watching it fail before the bump:**

```
>       assert weaver.__version__ == _pyproject_version()
E       AssertionError: assert '0.7.0' == '0.7.2'
```

### 2. The mandatory githooks had never been running

CLAUDE.md §4.2: "`.githooks/` are mandatory. Keep `git config core.hooksPath .githooks`
enabled." It was set to `D:\DevSpace\Projects\weaver\.git\hooks`, which contains **only
`.sample` files** — so the secret-scan `pre-commit` and the conventional-commit `commit-msg`
hook were inert.

Re-pointed at `.githooks` and proven by staging a fake key rather than by assuming:

```
$ sh .githooks/pre-commit
Commit rejected: staged diff contains a value that looks like an API key.
Matched lines:
+api_key = "sk-AAAAAAAAAAAAAAAAAAAAAAAA"
HOOK_EXIT=1
```

(Test file removed; nothing committed.) Note this is **local git config** — it does not
travel with the branch, so any fresh clone needs the same `git config` line.

---

## Validation Performed

**Static gates** (after all edits): `uv run ruff check .` → *All checks passed!* ·
`uv run ruff format --check .` → *395 files already formatted* · `uv run pyright` →
**0 errors, 0 warnings, 0 informations**.

**Full offline suite** — `uv run pytest -q -m "not requires_cloud and not requires_ollama"`:
exit 0, **1733 passed, 1 skipped, 3 deselected** in 345.76 s.
The 1 skip is `test_secret_store.py:104` (POSIX file mode, expected on Windows); the 3
deselections are the live tests (DeepSeek, plus the two added here). Baseline was 1731 at
M4 exit — **+2** from the new version drift guards.

**Bench** (`PYTHONPATH=. uv run python bench/run_performance_budgets.py`, **exit 0** read from
a file, not through a pipe — per the M1 carry-forward): **all budgets PASS.**

| Budget | Target | Measured | Audit baseline (2026-07-13) |
| --- | --- | --- | --- |
| translate concurrency scaling | ≥ 2.4× | **2.78×** (14.85 s → 5.35 s, 24 seg @ 0.3 s) | n/a (feature did not exist) |
| rolling-window flat cost | < 1.2× growth | **0.74×** (76.3 µs → 56.6 µs) | **1.96×** — criterion failed |
| translate, fake provider | < 50 ms/seg | **0.68 ms/seg** over 10,000 segments | 72.9 s total / growth 1.96× |
| export epub | < 30 s | 0.86 s | budget never actually ran (N1) |
| export markdown | < 10 s | 0.42 s | budget never actually ran (N1) |
| validate | < 15 s | 0.16 s | budget never actually ran (N1) |
| glossary extraction | < 20 s | 2.26 s | — |
| `weaver inspect` | < 1 s | 0.03 s | — |
| resume scan on startup | < 5 s | 0.01 s | — |
| providers-hub render | < 2 s | 0.04 s | — |
| queue render | < 2 s | 0.04 s | — |
| SQLite DB size | < 100 MB | 9.37 MB | — |

**Acceptance gate** (`bench/run_acceptance_gate.py`, **exit 0**): **AC-1…AC-9 all PASS**,
including AC-9 provider-unavailable exit=3, unreadable EPUB exit=4, config parse exit=7.

**Wheel** — `uv build --wheel` → `dist/weaver-0.7.3-py3-none-any.whl` (246 entries).
Asset audit: **71** templates, **4** static files (`app.css`, `htmx.min.js`, brand svg),
`schema.sql`, and all three provider prompt templates (`balanced_system.txt`,
`balanced_user.jinja2`, `repair.txt`) ship.

**CLI smoke** — `weaver --version` → `weaver 0.7.3` (was `0.7.0` before the fix);
`weaver --help` lists every command unchanged. Fake end-to-end runs are covered by AC-4/AC-5.

**Web smoke** — `weaver serve-api --port 8391`:

| Check | Result |
| --- | --- |
| `/healthz` | 200 |
| `/version` | `{"name":"weaver","version":"0.7.3"}` — end-to-end proof of the drift fix |
| `/ui` dashboard | 200 |
| `/static/app.css` | 200 |
| `http://192.168.1.7:8391/healthz` (LAN interface) | **000 — refused**, 127.0.0.1-only binding holds |
| after `kill` | no listener, no orphan process |

**Boundary + secret checks** — no `fastapi`/`typer`/`starlette`/`rich` imports anywhere in
`core/`, `services/`, `storage/`, `providers/`, `readers/`, `renderers/`; `git grep` for
key-shaped literals across tracked files (excluding the hook's own pattern) → clean.

**Version guard, all three sources** — `check-version.ps1` → *Version OK: 0.7.3*;
`-Tag v0.7.3` passes; negative control `-Tag v9.9.9` → *Tag mismatch: tag=9.9.9
pyproject=0.7.3* (guard proven, not assumed).

---

## What Was Intentionally Not Changed

- **No `v0.7.3` tag, no push.** Owner chose "full gate, hold the tag"; tagging is
  outward-facing and triggers the release workflow.
- **The stale `CHANGELOG.md` `[Unreleased]` block.** It describes Phase D/E work that
  shipped before v0.7.1; 0.7.1 and 0.7.2 were tagged without changelog cuts. Reconstructing
  two releases' history from memory would mean inventing entries, so it is annotated in
  place instead. Pre-existing debt, not v0.7.3's.
- **`docs/PROMPT_DESIGN.md`** still names `gemini-1.5-flash` — it sits under an explicit
  "Historical (pre-ADR 018)" banner, so it is accurate as history.
- **`__version__` is still a literal**, not derived from `importlib.metadata`. Deriving it
  would make drift structurally impossible, but PyInstaller onedir sidecars (ADR 016) can
  omit `dist-info` metadata, and the desktop build cannot be smoke-tested here (no
  Rust/MSVC toolchain). Guard-by-test was the lower-risk choice; revisit when the desktop
  toolchain is available.
- No perf/feature work. M5 is a gate.

---

## Known Risks / Open Gaps

1. **All live validation is unrun (blocks the tag).** Environment probe: no `GEMINI_API_KEY`
   in shell env or `~/.weaver/secrets.toml` (which holds only `ENV_TR` /
   `WEAVER_CONN_TOKENROUTER`); no `ollama` binary and nothing listening on `:11434`; no
   `java`/`epubcheck`; no `py-spy`. Both new tests **fail rather than skip** once opted into,
   so a future green run is real evidence (§4.3 gate 5).
2. **`gemini-2.5-flash` is unverified against a live endpoint.** It replaces a model that is
   definitely retired, so it is strictly better, but it is still an untested constant. The
   Gemini live test will confirm or reject it in one run.
3. **The 2.78× concurrency figure is simulated latency**, not network. §2.4's live ≥ 2×
   spot-check is a genuinely different measurement — do not let the bench number stand in.
4. **`enforce_repair` default is unconfirmed.** The E2 token-cost delta needs a live run.
5. **`core.hooksPath` is local config.** Any fresh clone silently loses the secret-scan
   again. Worth a documented setup step or a repo-level check.
6. **Desktop was not smoke-tested** (no Rust/MSVC toolchain). `tauri.conf.json` moved to
   0.7.3, which is version-only, but ADR 017's release flow runs `cargo tauri build` on CI.

---

## Recommended Next Role / Next Step

**Role:** Repository Owner (live validation), then Release Captain for the tag.

**Next step — one command, on the owner machine:**

```powershell
$env:GEMINI_API_KEY = "<key>"; uv run pytest -m requires_cloud -q
```

That single run closes gap 1 (Gemini half) and gap 2 together. Then Ollama
(`ollama serve` + `ollama pull qwen3:14b` → `uv run pytest -m requires_ollama -q`), the live
`--max-concurrent 2` spot-check, and the E2 delta. Tag **only** after those — CI's
`check-version.ps1 -Tag v0.7.3` will verify all three version sources agree.
