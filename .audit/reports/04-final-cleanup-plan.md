# Weaver Final Cleanup Plan

Date: 2026-06-14
Branch observed: `chore/codebase-audit`
Inputs merged:
- `.audit/reports/01-claude-lead-audit.md.md`
- `.audit/reports/02-codex-skeptical-review.md`
- `.audit/reports/03-codex-bug-pass.md`

Rules applied:
- Bugs are separated from cleanup/refactor work.
- Findings challenged by Codex are rejected or downgraded unless current-tree evidence is stronger.
- Deletions are limited to symbols with current `rg` evidence and targeted verification.
- Risky removals require human review.
- No code was modified, no files deleted, and no commits were created while writing this plan.

## 1. Executive Summary

The cleanup phase should start with correctness bugs, not deletion. The highest-value fixes are storage migration safety, provider config validation, EPUB chapter export scoping, and EPUB ruby text extraction. These affect project data integrity or user-visible translation/export correctness.

The safe cleanup surface is small:
- `src/weaver/storage/projects.py:get_project_by_uuid`
- `src/weaver/storage/candidates.py:count_candidates_for_project`
- `src/weaver/api/schemas.py:ErrorResponse`

Current-tree verification found no source occurrence of `CompiledTemplate`; treat the skeptical review's `CompiledTemplate` item as stale or mismatched and do not include it as a deletion target. Current-tree verification also found no tracked `__pycache__` files, so there is no tracked cache cleanup to do.

Do not delete provider adapters, legacy provider aliases, router modules, CLI commands, migration/storage code, template hooks, or `scripts/soak_13a5.py` as generic cleanup. Those areas are runtime-sensitive or explicitly challenged by Codex.

Recommended cleanup style:
- One bug concern per commit.
- One tiny deletion batch for confirmed dead symbols.
- Test-first for every behavior fix.
- Full gate after each bug batch and after deletion batch.

## 2. Confirmed Bugs To Fix First

### BUG-1: version-0 legacy databases can be stamped as schema v12

Priority: P0 data safety

Evidence:
- `src/weaver/storage/migrations.py:33-57` treats `user_version == 0` plus an existing `projects` table as fresh/latest and sets `PRAGMA user_version = target_version`.
- `src/weaver/storage/db.py:48-69` applies migrations from normal writable open.
- `src/weaver/storage/schema.sql` uses `CREATE TABLE IF NOT EXISTS`, which does not add missing columns/tables to legacy tables.
- Bug pass rated this High confidence and High impact.

Fix direction:
- Add a failing migration test for an old DB with `user_version = 0` and partial existing schema.
- Change migration handling so version-0 existing schemas are either migrated from an inferred safe baseline or rejected with a clear repair error.
- Do not stamp v12 solely because `projects` exists.

Verification commands:
```powershell
rg "user_version|apply_migrations|CREATE TABLE IF NOT EXISTS" src\weaver\storage tests\unit\storage
uv run pytest tests/unit/storage/test_migrations.py -q
python -m compileall src tests scripts
uv run ruff check .
uv run pyright
```

### BUG-2: provider config can save an unbuildable provider

Priority: P0 runtime correctness

Evidence:
- `src/weaver/services/config_writer.py:31-95` writes provider fields but does not validate buildability.
- `src/weaver/services/provider_config.py:128-176` returns a fresh view after writing.
- `src/weaver/providers/registry.py:126-143` later raises when no protocol and no registered provider factory exist.
- Current tests assert the broken behavior for `provider_type="not-real"` in `tests/unit/api/test_ui_providers.py` and `tests/unit/api/test_config.py`.

Fix direction:
- Add tests that reject `provider_type="not-real"` without a supported protocol.
- Preserve legacy aliases (`deepseek`, `gemini`, `ollama`, `fake`) and valid custom protocol configs.
- Validate resulting project/global config shape before reporting success.

Verification commands:
```powershell
rg "not-real|provider_type|protocol|build_provider|normalize_provider_config" src tests
uv run pytest tests/unit/api/test_config.py tests/unit/api/test_ui_providers.py tests/unit/services/test_provider_config.py tests/unit/providers -q
uv run pyright
```

### BUG-3: EPUB chapter export can include full EPUB volume content

Priority: P1 user artifact correctness

Evidence:
- `src/weaver/services/export_book.py:465-477` creates a chapter-scoped plan with one `chapter_id`.
- `src/weaver/services/export_book.py:484-510` re-reads the full source EPUB for preserved EPUB export and passes the full document to `render_translated_epub()`.
- Other targets use `_resolved_chapters()` and honor `plan.chapter_ids`.
- Existing tests assert exported counts/path existence but not EPUB artifact content.

Fix direction:
- Add a multi-chapter EPUB test that opens the produced chapter-scoped EPUB and checks content/spine.
- Either filter the preserved EPUB document to the selected chapter or explicitly block preserved EPUB chapter export until scoped preservation exists.

Verification commands:
```powershell
rg "prepare_export|_build_volume_plan|_render_volume|render_translated_epub|_resolved_chapters" src\weaver\services\export_book.py tests
uv run pytest tests/unit/services/test_export_book.py tests/unit/api/test_export.py -q
```

### BUG-4: EPUB ruby `<rt>/<rp>` text leaks into translation input

Priority: P1 translation correctness

Evidence:
- Lead audit and skeptical review both accept the bug.
- `src/weaver/readers/epub.py` uses `ElementTree.itertext()` inside `_element_text()`, which includes descendant `<rt>` ruby readings.
- This affects imported `source_text` / provider input, not just render fidelity.

Fix direction:
- Add a failing reader fixture with `<ruby>漢字<rt>かんじ</rt></ruby>`.
- Implement ruby-aware extraction that skips `<rt>` and `<rp>` while retaining base text.

Verification commands:
```powershell
rg "def _element_text|itertext|ruby|rt>|rp>" src tests docs
uv run pytest tests/unit/readers -q
uv run pytest tests/unit/services/test_translation.py tests/unit/services/test_translation_orchestrator.py -q
```

### BUG-5: translation job terminal status can disagree with `result.cancelled`

Priority: P1 job lifecycle correctness

Evidence:
- `src/weaver/api/jobs.py:349-414` sets translation terminal status from `self.should_cancel()` after the runner returns.
- Terminal data uses `result.cancelled`.
- Batch/export jobs use `result.cancelled`, making translation inconsistent.
- Existing cancel endpoint tests allow `running`, `done`, or `cancelled`, hiding the mismatch.

Fix direction:
- Add a unit test for late cancel after a non-cancelled result.
- Derive terminal status from `result.cancelled`, or reject cancel transition after terminal state is set.

Verification commands:
```powershell
rg "terminal_status|result.cancelled|request_cancel|cancel_translation_job" src\weaver\api tests\unit\api
uv run pytest tests/unit/api/test_jobs.py tests/unit/api/test_translate.py -q
```

### BUG-6: SSE replay uses writable/migrating DB access

Priority: P1 read-path correctness

Evidence:
- `src/weaver/api/jobs.py:1294-1307` uses `connect_database()` inside `replay_persisted_events()`.
- `src/weaver/storage/db.py:48-69` shows `connect_database()` applies migrations and commits.
- `src/weaver/api/routers/jobs.py` uses `connect_readonly_database()` for persisted job detail, proving a safer local pattern exists.

Fix direction:
- Add a regression test proving SSE replay does not call `connect_database()` and does not mutate `user_version` or segment state.
- Change replay to use `connect_readonly_database()`.

Verification commands:
```powershell
rg "replay_persisted_events|connect_database|connect_readonly_database|list_events_after" src\weaver\api src\weaver\storage tests
uv run pytest tests/unit/api/test_jobs.py tests/unit/api/test_cold_start_recovery.py tests/unit/api/test_translate.py -q
```

### BUG-7: glossary and character keys containing `/` cannot be mutated

Priority: P2 route correctness

Evidence:
- `src/weaver/api/routers/glossary.py:88-116` and `src/weaver/api/routers/characters.py:86-116` place user-authored keys in path segments.
- `src/weaver/api/routers/ui_admin.py` repeats the same path-key pattern for UI updates/deletes.
- Existing tests cover Unicode path decoding but not encoded slash.
- Bug pass manually reproduced `POST source="A/B"` as 201 and `PATCH /A%2FB` / `DELETE /A%2FB` as 404.

Fix direction:
- Prefer stable row IDs or body/query key submission for update/delete.
- If using a path converter, document ambiguity and add tests for encoded separators.

Verification commands:
```powershell
rg "glossary/.+source|characters/.+jp_name|terms/{source}|characters/{jp_name}" src tests
uv run pytest tests/unit/api/test_glossary.py tests/unit/api/test_characters.py tests/unit/api/test_ui_admin.py -q
```

## 3. Safe Cleanup Commits

### CLEAN-1: add direct EPUB validation tests

Type: test-only cleanup

Why safe:
- Both lead and skeptical reports agree `validate_epub_structure` is runtime-active and under-tested, not dead.
- Adding direct tests reduces risk before reader/export cleanup.

Scope:
- Add `tests/unit/readers/test_epub_validation.py`.
- Cover no-issue baseline, missing title, missing spine, missing navigation, missing image reference, and malformed metadata branch cases.

Verification commands:
```powershell
rg "validate_epub_structure" src tests
uv run pytest tests/unit/readers/test_epub_validation.py -q
uv run pytest tests/unit/readers -q
```

### CLEAN-2: remove `get_project_by_uuid`

Type: safe deletion after preflight

Why deletion is safe:
- Current-tree `rg` over `src tests scripts docs README.md pyproject.toml .audit` found only the definition in `src/weaver/storage/projects.py:138` plus audit report references.
- It is not router-, CLI-, template-, migration-, or docs-referenced in the current tree.
- Codex downgraded this to "safe only with tests" because storage APIs are compatibility-sensitive; that condition is satisfied by exact preflight and targeted storage/service/API tests.

Scope:
- Delete `get_project_by_uuid` only.
- Do not change project UUID schema, indexes, migration code, or project lookup behavior.

Verification commands:
```powershell
rg "get_project_by_uuid" src tests scripts docs README.md pyproject.toml
uv run pytest tests/unit/storage tests/unit/services/test_project.py tests/unit/api/test_projects.py -q
uv run pyright
```

### CLEAN-3: remove `count_candidates_for_project`

Type: safe deletion after preflight

Why deletion is safe:
- Current-tree `rg` found only the definition in `src/weaver/storage/candidates.py:256` plus audit references.
- Candidate counts that remain live use other read paths; this exact function has no current caller.
- Codex downgraded it to "safe only with tests"; use candidate, glossary review, UI candidate, and storage tests.

Scope:
- Delete `count_candidates_for_project` only.
- Do not alter candidate list/count behavior in services or API schemas.

Verification commands:
```powershell
rg "count_candidates_for_project|candidate_count|candidates_count" src tests scripts docs README.md pyproject.toml
uv run pytest tests/unit/storage tests/unit/api/test_candidates.py tests/unit/api/test_ui_candidates.py tests/unit/services -q
uv run pyright
```

### CLEAN-4: remove unused `ErrorResponse`

Type: safe deletion after preflight

Why deletion is safe:
- Lead audit identified `src/weaver/api/schemas.py:123`.
- Current-tree `rg` found only `class ErrorResponse(BaseModel)` in source plus audit references.
- FastAPI errors use `HTTPException` / `{"detail": ...}` paths, not this schema.
- The skeptical report's `CompiledTemplate` item is rejected for this plan because `CompiledTemplate` is absent from current source; `ErrorResponse` is the live dead schema candidate.

Scope:
- Delete `ErrorResponse` only.
- Do not alter error response formats or app exception handlers.

Verification commands:
```powershell
rg "ErrorResponse" src tests scripts docs README.md pyproject.toml
uv run pytest tests/unit/api -q
uv run pyright
```

## 4. Risky Cleanup Requiring Human Review

### RISK-1: `scripts/soak_13a5.py`

Decision needed: keep, rename, or replace before deletion.

Why not safe to delete now:
- Codex challenged deletion because the script is an explicit manual HTTP cockpit soak runner.
- Current-tree `rg` found `scripts/soak_13a5.py:10` usage instructions.
- The name is stale, but name staleness is not deletion evidence.

Safe options:
- Keep as-is for this cleanup.
- Rename to a generic smoke/soak name and update docs/handoff.
- Delete only after replacing it with an equivalent documented runtime smoke test.

Verification commands before any rename/delete:
```powershell
rg "soak_13a5|soak" scripts docs README.md .audit
uv run python scripts/soak_13a5.py http://127.0.0.1:9000 <books_dir>
```

### RISK-2: `fugashi` / MeCab packaging

Decision needed: optional extra, doctor/readme-only, or no change.

Why not safe as generic cleanup:
- Lead report says `fugashi` is imported but not declared.
- Codex correctly notes absence is intentional and README documents manual MeCab/fugashi setup.
- MeCab has system-level dictionary/binary requirements; adding a Python extra can mislead users.

Safe options:
- Add doctor/check documentation only.
- Add `[glossary]` optional extra with clear system dependency notes.
- Do not add to default dependencies without ADR/approval.

Verification commands:
```powershell
rg "fugashi|MeCab|mecab" README.md docs src tests pyproject.toml
uv run pytest tests/unit/services/test_glossary.py tests/integration/test_cli_doctor.py -q
```

### RISK-3: persisted job fallback for kind-specific routes

Decision needed: old kind-specific routes are live-only, or they must read persisted terminal jobs after restart.

Why human review:
- Unified `/projects/{name}/jobs/{job_id}/detail` is restart-safe.
- Kind-specific routes currently use in-memory registry and can 404 after restart.
- Fixing this can change API semantics and client expectations.

Verification commands before behavior change:
```powershell
rg "_require_job|_require_batch_job|_require_export_job|jobs/{job_id}/detail|recover_all_projects" src tests
uv run pytest tests/unit/api/test_cold_start_recovery.py tests/unit/api/test_jobs_persistence.py tests/unit/api/test_ui_jobs.py -q
```

### RISK-4: EPUB import snapshot failure semantics

Decision needed: full rollback or degraded-success import.

Why human review:
- `import_volume()` commits volume/segment rows before storing EPUB snapshot.
- If snapshot persistence fails, the project can retain an imported volume while the API reports failure.
- Both possible fixes are product decisions: atomic import rollback vs. visible degraded success with snapshot repair.

Verification commands before behavior change:
```powershell
rg "import_volume|parse_epub_structure|store_snapshot|snapshot_status|volume.imported" src tests
uv run pytest tests/unit/services/test_epub_export_fidelity.py tests/unit/api/test_snapshot_endpoints.py tests/unit/api/test_create_and_browse.py -q
```

### RISK-5: export preflight hashing on render path

Decision needed: strict no-hash render path vs. explicit freshness check UX.

Why human review:
- Bug pass found `_snapshot_export_advisories()` computes source hashes during GET preflight.
- This violates the current no-expensive-read-path direction, but changing it alters what confidence/advisory state users see.

Verification commands before behavior change:
```powershell
rg "_snapshot_export_advisories|compute_source_hash|snapshot_status|snapshot_info|export/preflight" src tests docs
uv run pytest tests/unit/api/test_ui_qa.py tests/unit/api/test_snapshot_endpoints.py tests/unit/services/test_epub_snapshot.py -q
```

### RISK-6: Gemini healthcheck JSON-mode false negative

Decision needed: reproduce first, then patch if confirmed.

Why human review:
- Codex marked this as a hypothesis, not a confirmed bug.
- Provider behavior can depend on SDK and mocked/live response shape.

Verification commands:
```powershell
rg "GeminiProvider|response_mime_type|healthcheck|_generate(\"ping\"" src tests
uv run pytest tests/unit/providers tests/unit/services/test_doctor.py tests/unit/api/test_ui_providers.py -q
```

### RISK-7: duplicate private `_count()` helpers

Decision: do not consolidate during cleanup.

Why:
- Codex rejected this as over-abstraction.
- The helpers are tiny, private, and local to separate read models.
- Consolidating creates cross-module coupling for no proven bug.

Verification if revisited later:
```powershell
rg "def _count" src tests
```

## 5. Do-Not-Touch Areas

Do not touch these without ADR, explicit owner approval, or a bug-specific test plan:

- Provider adapters: `src/weaver/providers/deepseek.py`, `gemini.py`, `ollama.py`.
- Provider legacy aliases and registry compatibility: `_LEGACY_DEFAULTS`, `register_provider(...)`, `normalize_provider_config(...)`.
- CLI command modules and Typer-decorated functions that look unused by static search.
- FastAPI router modules and Jinja/HTMX hooks that are decorator/string registered.
- Storage migrations and schema code except for the specific version-0 migration bug.
- `workspace_index` and other read models except for specific no-hash/no-mutation bug fixes.
- `scripts/soak_13a5.py` until a human decides keep/rename/replace/delete.
- Optional tokenizer behavior around `fugashi`/MeCab until packaging policy is decided.
- Duplicate private `_count()` helpers.
- Provider/docs examples for `deepseek`, `gemini`, `ollama`, `fake`, and `custom` until a migration/deprecation plan exists.
- Tracked-cache cleanup: none found. `git ls-files "tests/**/__pycache__/**" "src/**/__pycache__/**" "scripts/**/__pycache__/**"` returned no files.

## 6. Suggested Branch/Commit Sequence

Suggested branch:
```powershell
git switch -c chore/weaver-audit-cleanup
```

If staying on `chore/codebase-audit`, keep each commit small and do not mix unrelated bugs with cleanup deletions.

### Commit 1: `fix(storage): handle version-zero legacy databases safely`

Work:
- Add failing migration/backcompat test.
- Implement safe version-0 behavior.

Verification:
```powershell
uv run pytest tests/unit/storage/test_migrations.py -q
python -m compileall src tests scripts
uv run ruff check .
uv run pyright
```

### Commit 2: `fix(config): reject unbuildable provider config`

Work:
- Change tests that currently accept `not-real` without protocol.
- Validate resulting config before reporting success.

Verification:
```powershell
uv run pytest tests/unit/api/test_config.py tests/unit/api/test_ui_providers.py tests/unit/services/test_provider_config.py tests/unit/providers -q
uv run pyright
```

### Commit 3: `fix(export): honor chapter scope for preserved epub export`

Work:
- Add artifact-content test.
- Fix or explicitly reject unsupported preserved EPUB chapter scope.

Verification:
```powershell
uv run pytest tests/unit/services/test_export_book.py tests/unit/api/test_export.py -q
```

### Commit 4: `fix(readers): skip ruby annotation text during epub import`

Work:
- Add failing ruby fixture test.
- Implement ruby-aware text extraction.

Verification:
```powershell
uv run pytest tests/unit/readers -q
uv run pytest tests/unit/services/test_translation.py tests/unit/services/test_translation_orchestrator.py -q
```

### Commit 5: `fix(jobs): keep translation cancellation terminal state consistent`

Work:
- Add late-cancel terminal-status test.
- Align translation terminal status with `result.cancelled`.

Verification:
```powershell
uv run pytest tests/unit/api/test_jobs.py tests/unit/api/test_translate.py -q
```

### Commit 6: `fix(jobs): replay persisted events read-only`

Work:
- Add read-only replay regression.
- Switch SSE replay to `connect_readonly_database()`.

Verification:
```powershell
uv run pytest tests/unit/api/test_jobs.py tests/unit/api/test_cold_start_recovery.py tests/unit/api/test_translate.py -q
```

### Commit 7: `fix(resources): make glossary and character key mutations slash-safe`

Work:
- Add encoded-slash tests.
- Move mutation keys out of raw path segments or introduce stable IDs.

Verification:
```powershell
uv run pytest tests/unit/api/test_glossary.py tests/unit/api/test_characters.py tests/unit/api/test_ui_admin.py -q
```

### Commit 8: `test(readers): cover epub structure validation directly`

Work:
- Add direct `validate_epub_structure` tests.

Verification:
```powershell
uv run pytest tests/unit/readers/test_epub_validation.py -q
uv run pytest tests/unit/readers -q
```

### Commit 9: `chore(storage): remove unused storage helpers`

Work:
- Delete `get_project_by_uuid`.
- Delete `count_candidates_for_project`.

Why deletion is safe:
- Current source/tests/scripts/docs references are definition-only.
- No router/CLI/template/migration use.
- Targeted storage/API/service tests cover nearby behavior.

Verification:
```powershell
rg "get_project_by_uuid|count_candidates_for_project" src tests scripts docs README.md pyproject.toml
uv run pytest tests/unit/storage tests/unit/services/test_project.py tests/unit/api/test_projects.py tests/unit/api/test_candidates.py tests/unit/api/test_ui_candidates.py -q
uv run pyright
```

Expected `rg` after deletion:
- No matches outside `.audit` reports.

### Commit 10: `chore(api): remove unused error response schema`

Work:
- Delete `ErrorResponse`.

Why deletion is safe:
- Current source/tests/scripts/docs references are definition-only.
- App error behavior uses `HTTPException`/`detail`, not this model.

Verification:
```powershell
rg "ErrorResponse" src tests scripts docs README.md pyproject.toml
uv run pytest tests/unit/api -q
uv run pyright
```

Expected `rg` after deletion:
- No matches outside `.audit` reports.

### Deferred human-review commits

Do not schedule until decisions are made:
- Rename/delete/replace `scripts/soak_13a5.py`.
- Add `[glossary]` extra or doctor-only MeCab/fugashi guidance.
- Persisted-job fallback for kind-specific routes.
- Import snapshot rollback vs degraded success.
- Export preflight no-hash UX.
- Gemini healthcheck prompt hardening after reproduction.

## 7. Final Validation Checklist

Run after each bug batch and after final cleanup:

```powershell
python -m compileall src tests scripts
uv run ruff check .
uv run pyright
uv run pytest -q
uv run weaver --help
```

Run route registration smoke after API/job/resource route changes:
```powershell
uv run python -c "from weaver.api.app import create_api_app; app=create_api_app(); print(len([r for r in app.routes if hasattr(r, 'methods')]))"
```

Run focused runtime smoke after export/provider/job changes:
```powershell
uv run pytest tests/unit/api/test_export.py tests/unit/api/test_translate.py tests/unit/api/test_ui_providers.py -q
uv run pytest tests/unit/services/test_export_book.py tests/unit/services/test_workspace_translate.py -q
```

Run optional manual web soak only if a live server and books directory are available:
```powershell
uv run python scripts/soak_13a5.py http://127.0.0.1:9000 <books_dir>
```

Before marking cleanup complete:
- `rtk git status --short --branch` shows only intended files.
- `rg "Co-Authored-By|Generated with Claude|Claude Code|OpenAI|ChatGPT" .git . --glob "!uv.lock"` finds no attribution metadata in commit-facing files.
- No provider adapter, router module, migration, CLI command, template hook, or script was removed unless explicitly scheduled above.
- Every deletion commit has a pre-delete `rg` note and a post-delete `rg` result showing no live references.
- The handoff note records exact commands run and pass/fail output.
