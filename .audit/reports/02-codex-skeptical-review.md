# Weaver — Codex Skeptical Review of Lead Audit

**Date:** 2026-06-13
**Reviewer:** Codex as Skeptical Codebase Reviewer
**Input reviewed:** `audit/reports/2026-06-13-codebase-audit.md`
**Scope:** read-only verification against source, tests, scripts, docs, CLI entrypoint, FastAPI router registration, provider registry, compatibility paths, and stale-module risk.

---

## Executive verdict

The lead audit is mostly careful but too optimistic in wording. I accept the ruby/furigana bug, the three dead-symbol candidates, and the direct coverage gap for EPUB validation. I reject any implication that `deepseek.py`, `gemini.py`, or `ollama.py` are stale just because providers now normalize through registry configuration: those files are still the concrete transport adapters imported and registered by `providers/registry.py`.

Highest-risk correction: do not delete provider adapters, router modules, service compatibility shims, migration/storage code, or `scripts/soak_13a5.py` without targeted entrypoint/runtime tests. The safe cleanup surface is much smaller than the lead audit summary tone suggests.

Skeptical classification summary:

| Lead/related item | Classification | Verdict |
| --- | --- | --- |
| BUG-1 ruby `<rt>` leaks into translation input | Accept | Valid correctness bug. Add fixture before fix. |
| DEAD-1 `get_project_by_uuid` | Safe only with tests | Looks dead by static search, but storage APIs are compatibility-sensitive. |
| DEAD-2 `count_candidates_for_project` | Safe only with tests | Looks dead by static search, but candidate count semantics may be reintroduced via UI/API. |
| DEAD-3 `CompiledTemplate` | Safe only with tests | Looks dead if it exists only as an unused type/symbol; verify templates and pyright after removal. |
| `validate_epub_structure` lacks direct tests | Accept | Valid coverage gap; it is runtime-active, not dead. |
| `soak_13a5.py` cleanup/rename/delete decision | Needs more evidence | Script is an explicit runtime smoke harness. Do not delete from name alone. |
| `fugashi` imported but undeclared | Needs more evidence | Intentional optional dependency fallback exists; packaging decision needs owner call. |
| duplicate private `_count()` helpers | Reject | Not worth cross-module abstraction; deleting/consolidating increases coupling. |
| provider adapters `deepseek.py`, `gemini.py`, `ollama.py` stale | Reject / Do not remove | Registry imports and registers them; docs/tests/CLI still expose these paths. |
| broad “zero orphan modules” claim | Needs more evidence | My reference-map pass found no extra orphan modules, but dynamic framework/CLI paths require ongoing manual checks. |

---

## Findings accepted

### A1 — BUG-1: ruby `<rt>` text leaks into translation input

**Classification:** Accept

**Original finding summary:** `src/weaver/readers/epub.py` uses `ElementTree.itertext()` in `_element_text()`, so ruby reading text from `<rt>` descendants can be concatenated into `source_text` / `normalized_source_text`.

**Why valid:** `itertext()` recursively yields text from child elements. For light-novel EPUBs, `<ruby>漢字<rt>かんじ</rt></ruby>` can flatten into model input as `漢字かんじ`, which is wrong for translation segmentation.

**Additional evidence:**

- `src/weaver/readers/epub.py` imports and calls `validate_epub_structure`, then builds reader output before `_element_text()`.
- `_element_text()` currently returns `collapse_whitespace("".join(element.itertext()))`.
- This path is import/segmentation, not just rendering fidelity; it affects provider input.

**Recommended cleanup order:**

1. Add failing unit test with a minimal XHTML fragment containing `<ruby>漢字<rt>かんじ</rt></ruby>`.
2. Implement ruby-aware text traversal that skips `<rt>` and `<rp>`.
3. Run reader-specific tests first, then full regression.

**Required verification command:**

```powershell
uv run pytest tests/unit/readers -q
uv run pytest tests/unit/services/test_translation.py tests/unit/services/test_translation_orchestrator.py -q
```

### A2 — EPUB validation module needs direct tests

**Classification:** Accept

**Original finding summary:** `src/weaver/readers/epub_validation.py` has no dedicated unit test for `validate_epub_structure`.

**Why valid:** The function is runtime-active via `src/weaver/readers/epub.py`, but direct branch coverage is weak. This is a coverage gap, not dead code.

**Additional evidence:**

- `src/weaver/readers/epub.py` imports `validate_epub_structure` and passes manifest/spine/navigation/images metadata into it.
- Static search showed no direct `tests/` hit for `validate_epub_structure` by name.

**Recommended cleanup order:**

1. Add `tests/unit/readers/test_epub_validation.py` with synthetic metadata cases.
2. Cover missing title, missing spine, missing navigation, missing image references, and no-issue baseline.
3. Keep tests synthetic; no fixture EPUB required for this module.

**Required verification command:**

```powershell
uv run pytest tests/unit/readers/test_epub_validation.py -q
```

### A3 — direct stale-module scan found no obvious extra orphan modules

**Classification:** Accept with narrow scope

**Original finding summary:** Lead audit claimed zero orphan source modules.

**Why valid, with caveat:** A fresh AST/text reference pass over `src/weaver`, `tests`, and `scripts` produced no source module with zero direct imports and one-or-fewer token references. That supports the claim for obvious stale modules. It does not prove dynamic framework paths forever safe.

**Additional evidence:**

- Provider modules are imported directly by `src/weaver/providers/registry.py`.
- UI router modules are registered in `src/weaver/api/app.py`.
- CLI commands are exposed by `pyproject.toml` through `weaver = "weaver.cli.main:app"`.

**Recommended cleanup order:**

1. Treat stale-module findings as hypotheses only.
2. For any file deletion, first prove no static imports, no docs/scripts references, no router/CLI registration, and no migration/runtime import.
3. Delete in one-file commits only.

**Required verification command:**

```powershell
uv run python -c "import compileall; raise SystemExit(0 if compileall.compile_dir('src', quiet=1) else 1)"
uv run pytest -q
```

---

## Findings rejected

### R1 — `deepseek.py`, `gemini.py`, and `ollama.py` are not dead/stale

**Classification:** Reject / Do not remove

**Why likely false positive:** Provider registration did not replace these files. The registry imports adapter classes/config values from them, then registers factories for `deepseek`, `gemini`, `ollama`, `custom`, and `fake`.

**Usage path missed:**

- `src/weaver/providers/registry.py` imports `DeepSeekProvider`, `GeminiProvider`, and `OllamaProvider`.
- `register_provider("deepseek", _build_deepseek)`, `register_provider("gemini", _build_gemini)`, and `register_provider("ollama", _build_ollama)` are present at the bottom of the registry.
- `custom` OpenAI-compatible endpoints reuse `DeepSeekProvider` through `_build_openai_chat()`.
- `src/weaver/services/translation.py`, `candidate_generation.py`, `glossary_suggestion.py`, `project.py`, and `doctor.py` build providers through `build_provider()`.
- CLI help still exposes `--provider deepseek|gemini|ollama|fake`.
- README and dependency docs still document DeepSeek, Gemini, Ollama, and custom providers.

**What should be checked instead:**

- Whether legacy provider type UX should remain as compatibility aliases or be migrated in docs/UI to `type = "custom"` + `protocol = ...`.
- Whether `GeminiProvider.healthcheck()` should request JSON-compatible content instead of `ping`.
- Whether tests cover `build_provider()` for legacy aliases and protocol-based custom config.

### R2 — duplicate private `_count()` helpers should not be consolidated during cleanup

**Classification:** Reject

**Why likely false positive:** Duplicate two-line private helpers are maintenance noise at most. A shared abstraction would cross service boundaries for minimal benefit and could violate the repo’s preference for existing architecture over new utility layers.

**Usage path missed:** These helpers sit near local query logic and keep read models independent. Consolidation risks creating a new generic helper module or coupling unrelated workspace services.

**What should be checked instead:** Only revisit if a concrete bug exists in one count query or if a planned refactor already touches all affected read models.

### R3 — `validate_epub_structure` must not be treated as dead code

**Classification:** Reject if proposed as removal

**Why likely false positive:** It is imported and called by `src/weaver/readers/epub.py`. The right action is direct tests, not removal.

**Usage path missed:** EPUB import/runtime validation path.

**What should be checked instead:** Add focused tests for validation branches and confirm imported EPUB metadata still surfaces validation issues.

---

## Findings needing more evidence

### E1 — DEAD-1: `get_project_by_uuid`

**Classification:** Safe only with tests

**Lead claim:** Defined once and referenced nowhere.

**Skeptical review:** Static search supports this today, but deletion touches storage API surface. Storage functions can be used by scripts, old migrations, or external/manual debugging flows not captured by direct imports.

**Required before removal:**

- Confirm no docs, scripts, tests, migrations, or compatibility commands refer to project UUID lookup.
- Remove only with storage tests and CLI/API smoke tests.

**Verification command:**

```powershell
rg "get_project_by_uuid" .
uv run pytest tests/unit/storage tests/unit/services/test_project.py tests/unit/api/test_projects.py -q
```

### E2 — DEAD-2: `count_candidates_for_project`

**Classification:** Safe only with tests

**Lead claim:** Defined once and referenced nowhere.

**Skeptical review:** Static search supports this today. Risk is lower than provider/router deletion, but candidate counts are UI/API-facing concepts and could be resurrected by dashboard or workspace summaries.

**Required before removal:**

- Confirm no template, API schema, workspace summary, or dashboard code expects candidate counts.
- Run candidate, glossary review, and workspace tests after removal.

**Verification command:**

```powershell
rg "count_candidates_for_project|candidate_count|candidates_count" src tests scripts docs README.md
uv run pytest tests/unit/storage tests/unit/api/test_candidates.py tests/unit/api/test_ui_candidates.py tests/unit/services -q
```

### E3 — DEAD-3: `CompiledTemplate`

**Classification:** Safe only with tests

**Lead claim:** Dead symbol safe to remove.

**Skeptical review:** I did not find a live import path in the compact checks, but template typing can be subtle. If this is a local typing alias/protocol in `api/templating.py`, deletion is safe only after pyright and UI route tests.

**Required before removal:**

- Confirm exact definition site and no type-check-only usage.
- Run pyright and UI router tests.

**Verification command:**

```powershell
rg "CompiledTemplate" src tests scripts docs README.md
uv run pyright
uv run pytest tests/unit/api -q
```

### E4 — `scripts/soak_13a5.py` cleanup/rename/delete

**Classification:** Needs more evidence / Do not remove without owner approval

**Lead claim:** Owner decision on rename/keep/delete.

**Skeptical review:** This script is a deliberate HTTP cockpit soak runner using the fake provider. Its name is ugly, but name ugliness is not dead-code evidence. Deleting it removes a manual runtime verification tool.

**Usage path that may be missed:** Manual QA after web cockpit changes: `python scripts/soak_13a5.py <base_url> <books_dir>`.

**What should be checked instead:**

- Whether docs or handoff notes reference it as a manual smoke test.
- Whether it still passes against `weaver serve-api`.
- If kept, rename with docs update; if deleted, replace with an equivalent documented smoke command.

**Verification command:**

```powershell
rg "soak_13a5|soak" scripts docs README.md .audit audit
uv run python scripts/soak_13a5.py http://127.0.0.1:9000 <books_dir>
```

### E5 — `fugashi` optional dependency packaging

**Classification:** Needs more evidence

**Lead claim:** Imported but undeclared; consider optional extra or doctor check.

**Skeptical review:** The code intentionally degrades when `fugashi` is absent, and README documents manual MeCab/fugashi install because MeCab has system-level prerequisites. Adding a Python extra could create a false sense of complete install on Windows/Linux without system dictionaries.

**Usage path that may be missed:** `services/glossary.py` catches optional tokenizer absence and falls back. Security/performance docs explicitly mention missing tokenizer dictionaries as a known condition.

**What should be checked instead:**

- Decide whether the project wants a best-effort `[glossary]` extra or only a doctor/readme check.
- Do not make `fugashi` a default runtime dependency without ADR/owner approval.

**Verification command:**

```powershell
rg "fugashi|MeCab|mecab" README.md docs src tests pyproject.toml
uv run pytest tests/unit/services/test_glossary.py tests/integration/test_cli_doctor.py -q
```

---

## Missing issues found by Codex

### M1 — Possible Gemini healthcheck false negative with JSON response mode

**Classification:** Needs more evidence

**Issue:** `GeminiProvider` configures `response_mime_type = "application/json"`, but `healthcheck()` calls `_generate("ping")`. DeepSeek already had a similar JSON-mode healthcheck caveat fixed by making the prompt mention JSON. Gemini may return a response error or non-JSON safety/format behavior even when the provider is usable for real translation prompts.

**Evidence:**

- `src/weaver/providers/gemini.py` builds the client with `response_mime_type: application/json`.
- `GeminiProvider.healthcheck()` calls `self._generate("ping")`.
- Unit tests exist for `DeepSeekProvider`, but I did not find equivalent dedicated `GeminiProvider` healthcheck tests.

**Risk:** Provider hub / doctor / inspect healthcheck can report Gemini unhealthy even when translation works.

**Recommended action:** Add a mocked Gemini healthcheck test first. If reproduced, change the healthcheck prompt to request a tiny JSON object.

**Verification command:**

```powershell
uv run pytest tests/unit/providers -q
uv run pytest tests/unit/api/test_ui_providers.py tests/unit/services/test_doctor.py -q
```

### M2 — Provider config consolidation leaves legacy aliases intentionally live

**Classification:** Do not remove

**Issue:** New config prefers `type = "custom"` + explicit `protocol`, but legacy names are compatibility aliases. Cleanup that removes alias defaults or adapter imports will break old project TOML, CLI `--provider`, README examples, doctor checks, and tests.

**Evidence:**

- `src/weaver/providers/registry.py` has `_LEGACY_DEFAULTS` for `deepseek`, `gemini`, `ollama`, and `fake`.
- `normalize_provider_config()` projects legacy built-ins into protocol-based config.
- `src/weaver/services/doctor.py` maps `deepseek` and `gemini` to API-key env names.
- `README.md` still lists `deepseek`, `gemini`, `ollama`, and `custom` as user-facing provider types.

**Recommended action:** Treat these as compatibility shims. Deprecation requires ADR/docs/tests/migration, not cleanup deletion.

### M3 — `__pycache__` appears under tests in local tree

**Classification:** Needs more evidence

**Issue:** `Get-ChildItem -Recurse tests` showed multiple `__pycache__` entries. If tracked, they are cleanup candidates; if untracked, they are local artifact noise and not a codebase finding.

**Recommended action:** Check git tracking before touching.

**Verification command:**

```powershell
git ls-files "tests/**/__pycache__/**"
git status --short -- tests
```

---

## Over-aggressive cleanup suggestions

1. **Provider adapter removal:** Do not remove `deepseek.py`, `gemini.py`, or `ollama.py`. Registry and legacy config still depend on them.
2. **Provider alias removal:** Do not remove `_LEGACY_DEFAULTS` without migration. Old project TOML and CLI overrides can still use built-in names.
3. **Soak script deletion:** Do not delete `scripts/soak_13a5.py` unless an equivalent cockpit runtime smoke path is documented.
4. **Cross-module `_count()` consolidation:** Do not create a utility abstraction for two-line private helpers during audit cleanup.
5. **Optional tokenizer hard dependency:** Do not add `fugashi` to default dependencies without considering MeCab system install failures.

---

## Highest-risk areas in the proposed cleanup plan

1. **Provider stack:** registry normalization, legacy aliases, env-secret behavior, and adapter imports are all runtime-sensitive.
2. **FastAPI router registration:** router modules can look unused by symbol search because decorators and `include_router()` own discovery.
3. **CLI entrypoint:** Typer command functions can look unused because `pyproject.toml` and decorators expose them.
4. **Storage/migrations:** apparently unused storage helpers may be compatibility or manual recovery APIs.
5. **Scripts:** ugly names are not dead-code evidence; scripts may be manual acceptance gates.
6. **Template/UI hooks:** Jinja/HTMX hooks are string-referenced, so simple AST maps undercount usage.

---

## Final safe cleanup order

1. **Test-only coverage first:** add direct tests for `validate_epub_structure` and a ruby fixture reproducing BUG-1.
2. **Fix BUG-1:** implement ruby-aware extraction after the failing test exists.
3. **Provider healthcheck hardening:** investigate Gemini JSON-mode healthcheck with mocked tests; fix only if reproduced.
4. **Tiny dead-symbol deletion:** remove `get_project_by_uuid`, `count_candidates_for_project`, and `CompiledTemplate` only after exact `rg` confirmation and targeted tests.
5. **Script decision:** keep or rename `scripts/soak_13a5.py`; delete only if replaced by a documented smoke test.
6. **Packaging/docs decision:** decide `fugashi` optional-extra vs doctor/readme-only; do not default-install casually.
7. **Full gate:** compile, ruff, pyright, pytest, and CLI help after each cleanup batch.

---

## Commands to run before each cleanup commit

### Before fixing ruby extraction

```powershell
rg "def _element_text|itertext|ruby|rt>|rp>" src tests docs
uv run pytest tests/unit/readers -q
```

### Before adding EPUB validation tests

```powershell
rg "validate_epub_structure" src tests
uv run pytest tests/unit/readers -q
```

### Before touching providers

```powershell
rg "deepseek|gemini|ollama|custom|openai_chat|gemini_generate|ollama_generate|register_provider|build_provider|normalize_provider_config" src tests docs README.md pyproject.toml
uv run pytest tests/unit/providers tests/unit/services/test_provider_config.py tests/unit/services/test_doctor.py tests/unit/api/test_ui_providers.py -q
```

### Before removing dead storage/template symbols

```powershell
rg "get_project_by_uuid|count_candidates_for_project|CompiledTemplate" src tests scripts docs README.md pyproject.toml
uv run pyright
uv run pytest tests/unit/storage tests/unit/api tests/unit/services -q
```

### Before deleting or renaming `scripts/soak_13a5.py`

```powershell
rg "soak_13a5|soak" scripts docs README.md audit .audit
uv run python scripts/soak_13a5.py http://127.0.0.1:9000 <books_dir>
```

### Before changing `fugashi` packaging

```powershell
rg "fugashi|MeCab|mecab" README.md docs src tests pyproject.toml
uv run pytest tests/unit/services/test_glossary.py tests/integration/test_cli_doctor.py -q
```

### Required final gate after every cleanup batch

```powershell
python -m compileall src tests scripts
uv run ruff check .
uv run pyright
uv run pytest -q
uv run weaver --help
```

---

## Handoff: Skeptical Codebase Reviewer

**Track:** T6/T7/T8 review support
**Scope:** Challenge lead audit findings and identify false positives, missing risks, stale-module candidates, and safe cleanup order.
**Files/Areas Touched:** Created `.audit/reports/02-codex-skeptical-review.md` only.
**What Changed:** Added a skeptical review report with accepted/rejected/evidence-needed classifications and cleanup gates.
**What Was Intentionally Not Changed:** No source code, tests, commits, deletion, or dependency changes.
**Validation Performed:** Read lead report; checked `rtk git status --short --branch`; searched provider, router, CLI, docs, storage, validation, and script references; ran a Python AST/text reference-map pass via `uv run python` after sandbox cache approval.
**Known Risks:** Did not run full pytest/pyright gates because this task was read-only report generation; Gemini healthcheck issue is a hypothesis requiring a mocked or live reproduction.
**Recommended Next Role / Next Step:** QA should add failing tests for BUG-1 and `validate_epub_structure` before any cleanup deletion.
