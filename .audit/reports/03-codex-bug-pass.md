# Weaver Bug-Focused Audit

Role: senior Python/FastAPI bug hunter

Scope covered:
- FastAPI route registration
- Provider configuration handling
- Translation job lifecycle
- Cancellation, progress, and SSE behavior
- Glossary, character, and translation memory paths
- Workspace/editor save flow
- Import/export paths
- Migrations and backwards compatibility
- Tests that pass while missing the runtime behavior

Notes:
- No code was modified.
- Route registration was mechanically enumerated with `uv run python -c "from weaver.api.app import create_api_app; ..."`; the app registers the expected JSON and UI routers. The route-key issues below are not missing registrations, but path-shape bugs.
- This pass is bug-focused, not style/refactor-focused.

## High-Confidence Bugs

### 1. Legacy version-0 databases can be stamped as schema v12 without migrations

1. File path: `src/weaver/storage/migrations.py`, `src/weaver/storage/db.py`, `src/weaver/storage/schema.sql`
2. Function/class/route: `apply_migrations()`, `connect_database()`, `initialize_database()`
3. Bug description: A database with `PRAGMA user_version = 0` and an existing `projects` table is treated as already latest. `apply_migrations()` only sets `user_version` to the target and returns, so older version-0 databases with partial schema can be marked v12 while missing later tables/columns.
4. Evidence from code: `apply_migrations()` checks `current == 0`, only verifies the `projects` table exists, then executes `PRAGMA user_version = {target_version}` and returns (`src/weaver/storage/migrations.py:33-57`). `connect_database()` applies migrations on open (`src/weaver/storage/db.py:48-69`). The base schema uses `CREATE TABLE IF NOT EXISTS` (`src/weaver/storage/schema.sql:3`, `:16`, `:38`, `:115`, `:149`, etc.), so applying schema to an old DB does not add missing columns to existing tables.
5. Reproduction path or likely runtime path: Create or encounter a pre-migration Weaver DB whose `projects` table exists but `user_version` is unset/0 and tables such as `jobs`, `translation_memory`, `epub_snapshots`, or later columns are missing. Opening the project through CLI or FastAPI calls `connect_database()`, stamps the DB as v12, and later routes fail with `no such table` or `no such column`.
6. Impact level: High
7. Suggested fix: Distinguish fresh DB creation from legacy version-0 DBs. For `current == 0` with existing schema, either infer a safe starting version from actual table/column shape and run migrations, or fail with a clear `DatabaseError` requiring explicit repair. Do not stamp latest solely because `projects` exists.
8. Test that should be added: A migration test that creates a version-0 DB with only v1/v2-era tables, calls `apply_migrations()` or `connect_database()`, and asserts either all v12 tables/columns exist or a clear repair error is raised without changing `user_version` to v12.
9. Confidence level: High

### 2. EPUB chapter export ignores chapter scope and writes the whole EPUB-shaped volume

1. File path: `src/weaver/services/export_book.py`, `tests/unit/services/test_export_book.py`, `tests/unit/api/test_export.py`
2. Function/class/route: `prepare_export()`, `_build_volume_plan()`, `_render_volume()`, `/projects/{name}/export/chapters/{chapter_id}`
3. Bug description: Chapter-scoped export builds a plan with one `chapter_id`, but the EPUB-source + EPUB-target render path re-reads the entire source EPUB and passes the full document to `render_translated_epub()`. The artifact reports `chapters_exported = 1` while likely containing every source chapter/resource spine item from that volume.
4. Evidence from code: `_build_volume_plan()` sets `chapter_ids = (target_id,)` when `scope == "chapter"` (`src/weaver/services/export_book.py:465-477`). `_render_volume()` filters segment states by `plan.chapter_ids`, but for `target == "epub"` and `plan.source_format == "epub"` it calls `scope_document_to_volume(read_epub(plan.source_path), plan.volume_id)` and passes that full document to `render_translated_epub()` (`src/weaver/services/export_book.py:484-510`). Only TXT/HTML/DOCX and synthesized EPUB paths use `_resolved_chapters()` (`src/weaver/services/export_book.py:520-540`). The result then reports `chapters_exported=len(plan.chapter_ids)` (`src/weaver/services/export_book.py:546-548`).
5. Reproduction path or likely runtime path: Import an EPUB with multiple chapters, translate one chapter, call `/projects/{name}/export/chapters/{chapter_id}` with `target="epub"`, then inspect the produced EPUB spine/content. The API result can say one chapter was exported while the artifact preserves the full source volume.
6. Impact level: High
7. Suggested fix: Make the EPUB preservation render path honor `plan.chapter_ids`. Either filter the document/manifest/spine to the selected chapter before `render_translated_epub()`, or explicitly disallow chapter-scoped preserved EPUB export until a scoped-preservation renderer exists. Keep synthesized EPUB/TXT/HTML/DOCX behavior unchanged.
8. Test that should be added: A service or API test with a multi-chapter EPUB fixture that exports one chapter to EPUB, opens the artifact, and asserts only the requested chapter's text/spine item appears. Do not rely only on `chapters_exported == 1`.
9. Confidence level: High

### 3. Provider config can save an unbuildable provider and report success

1. File path: `src/weaver/services/provider_config.py`, `src/weaver/services/config_writer.py`, `src/weaver/providers/registry.py`, `src/weaver/api/routers/ui_providers.py`, `tests/unit/api/test_ui_providers.py`, `tests/unit/api/test_config.py`
2. Function/class/route: `write_config()`, `set_provider()`, `build_provider()`, `POST /ui/providers/config`, `PATCH /config`
3. Bug description: The config editor/API accepts a free-form provider type such as `not-real` without protocol/model/base URL/key. It saves and renders "Saved", but `build_provider()` cannot instantiate that config because no protocol and no registered provider factory exist.
4. Evidence from code: `set_provider()` documentation says provider types are validated, but it writes supplied fields directly and does not query the registry (`src/weaver/services/config_writer.py:31-95`). `write_config()` delegates to `set_provider()` and returns a fresh view (`src/weaver/services/provider_config.py:128-176`). `build_provider()` raises `ConfigError` when no protocol exists and no registry factory exists (`src/weaver/providers/registry.py:126-143`). UI save marks `saved` when no `WeaverError` was raised (`src/weaver/api/routers/ui_providers.py:114-143`). Tests currently assert the bad behavior: saving `provider_type="not-real"` returns 200/"Saved" (`tests/unit/api/test_ui_providers.py:247-253`) and `PATCH /config` persists it (`tests/unit/api/test_config.py:103-111`).
5. Reproduction path or likely runtime path: Open `/ui/providers`, save project config with provider type `not-real` and no protocol. The form reports success. Starting translation later calls provider build/validation and fails with an incomplete provider configuration.
6. Impact level: High
7. Suggested fix: Validate the resulting provider config shape before saving or before reporting success. Allow legacy provider aliases, registered providers, or `type="custom"`/free-form labels only when a supported `protocol` and required protocol fields are present. Update tests that currently enshrine the broken save.
8. Test that should be added: API and UI config tests that `provider_type="not-real"` without protocol returns an error and does not persist. Add a positive free-form/custom test with `protocol`, `model`, `base_url`, and `api_key_env`.
9. Confidence level: High

### 4. SSE replay uses a writable, migrating database connection on a read stream

1. File path: `src/weaver/api/jobs.py`, `src/weaver/storage/db.py`, `src/weaver/services/job_store.py`
2. Function/class/route: `replay_persisted_events()`, `connect_database()`, translation/batch/export SSE routes
3. Bug description: A GET SSE replay path opens the project database with `connect_database()`, which can apply migrations and write. Event replay should be read-only. This also violates the documented read-path invariant that render/read paths must not mutate project state.
4. Evidence from code: `replay_persisted_events()` opens `connect_database(db_path)` before calling `list_events_after()` (`src/weaver/api/jobs.py:1294-1307`). `connect_database()` applies migrations and commits (`src/weaver/storage/db.py:48-69`). `initialize_database()` also resets interrupted segments (`src/weaver/storage/db.py:17-35`), and cold-start recovery is the intended write path for interrupted jobs (`src/weaver/services/job_store.py:372`). The unified job detail route correctly uses `connect_readonly_database()` (`src/weaver/api/routers/jobs.py:79-109`), showing a safer local pattern exists.
5. Reproduction path or likely runtime path: Connect to `/projects/{name}/jobs/{job_id}/events`, `/batch/jobs/{job_id}/events`, or `/export/jobs/{job_id}/events` against a DB needing migration or with write-sensitive state. A read stream can acquire a write-capable connection and mutate schema metadata before yielding events.
6. Impact level: Medium
7. Suggested fix: Use `connect_readonly_database()` for `replay_persisted_events()`. If the DB is too old to read safely, surface a replay warning/error rather than applying migrations from a GET stream. Keep migration/recovery in startup or explicit maintenance flows.
8. Test that should be added: A regression test that monkeypatches `weaver.storage.db.connect_database` to fail if called during SSE replay and asserts replay uses read-only access. Also assert `PRAGMA user_version` and segment statuses are unchanged after opening an event stream.
9. Confidence level: High

### 5. Translation job cancellation can mark a completed job as cancelled with `result.cancelled=false`

1. File path: `src/weaver/api/jobs.py`, `src/weaver/api/routers/translate.py`, `tests/unit/api/test_jobs.py`, `tests/unit/api/test_translate.py`
2. Function/class/route: `TranslationJob.run()`, `cancel_translation_job()`, `/projects/{name}/jobs/{job_id}/cancel`
3. Bug description: Translation jobs determine terminal status from the job's cancel flag after the runner returns, not from the runner result. A late cancel request after the runner has completed can persist/event `status="cancelled"` while `terminal_data["cancelled"]` is `False` and all selected segments were translated. Batch and export jobs use `result.cancelled`, so translation is inconsistent.
4. Evidence from code: `TranslationJob.run()` sets `terminal_status = "cancelled" if self.should_cancel() else "done"` after `self.runner(...)` returns (`src/weaver/api/jobs.py:349-414`), but terminal data uses `result.cancelled` (`src/weaver/api/jobs.py:385-395`). Batch/export set status from `result.cancelled` (`src/weaver/api/jobs.py:540-565`, `:691-716`). Cancel endpoint is idempotent and can call `job.request_cancel()` on a finished job until the in-memory status is read (`src/weaver/api/routers/translate.py:241-255`). The API test only asserts status is in `{"running", "done", "cancelled"}` (`tests/unit/api/test_translate.py:169-178`), allowing inconsistency.
5. Reproduction path or likely runtime path: Start a very fast fake-provider translation job and issue cancel around completion, or create a runner that returns `ChapterTranslationResult(cancelled=False)` while another thread sets the cancel flag before terminal status is computed. The job row/event can be `cancelled` despite a non-cancelled result.
6. Impact level: Medium
7. Suggested fix: Derive terminal status from `result.cancelled`, or atomically transition to terminal status before accepting further cancel state. Align translation with batch/export semantics.
8. Test that should be added: A unit test where the runner returns a non-cancelled result and then the cancel flag is set before terminal handling; assert final status/event is `done` and `result.cancelled` is false. Add an API test that cancel-after-done remains `done`.
9. Confidence level: High

### 6. Glossary and character keys containing `/` cannot be updated or deleted

1. File path: `src/weaver/api/routers/glossary.py`, `src/weaver/api/routers/characters.py`, `src/weaver/api/routers/ui_admin.py`, `tests/unit/api/test_glossary.py`, `tests/unit/api/test_characters.py`
2. Function/class/route: `PATCH/DELETE /projects/{name}/glossary/{source}`, `PATCH/DELETE /projects/{name}/characters/{jp_name}`, UI admin term/character update/delete routes
3. Bug description: Glossary `source` and character `jp_name` are user-authored database keys, but update/delete routes place them in a single path segment. Values containing `/` cannot be addressed even when URL-encoded as `%2F`.
4. Evidence from code: JSON routes use `{source}` and `{jp_name}` path parameters (`src/weaver/api/routers/glossary.py:88-116`, `src/weaver/api/routers/characters.py:86-116`). UI routes do the same (`src/weaver/api/routers/ui_admin.py:174-203`, `:390-424`). Existing tests cover Japanese Unicode decoding but not separator characters (`tests/unit/api/test_glossary.py:55-82`, `tests/unit/api/test_characters.py:61-83`). Manual TestClient verification in this audit: `POST /projects/alpha/glossary` with `source="A/B"` returned 201; `PATCH /projects/alpha/glossary/A%2FB` and `DELETE /projects/alpha/glossary/A%2FB` returned 404.
5. Reproduction path or likely runtime path: Add a glossary term with source `A/B`, a title-like term containing a slash, or a character alias/name with a slash through POST. Listing works, but update/delete via JSON or UI path fails.
6. Impact level: Medium
7. Suggested fix: Move update/delete keys into request body or query parameters, use stable numeric IDs for mutable resources, or use a path converter that intentionally captures paths and handles ambiguity. Prefer stable IDs for UI operations.
8. Test that should be added: JSON and UI route tests that create glossary and character records with `/` in the key, then update and delete them successfully.
9. Confidence level: High

## Medium-Confidence Bug Risks

### 1. Kind-specific job status/SSE/cancel endpoints lose persisted jobs after process restart

1. File path: `src/weaver/api/routers/translate.py`, `src/weaver/api/routers/batch.py`, `src/weaver/api/routers/export.py`, `src/weaver/api/routers/jobs.py`, `tests/unit/api/test_cold_start_recovery.py`
2. Function/class/route: `_require_job()`, `_require_batch_job()`, `_require_export_job()`, `/projects/{name}/jobs/{job_id}`, `/batch/jobs/{job_id}`, `/export/jobs/{job_id}`
3. Bug description: The persisted unified jobs API works after restart, but kind-specific status/SSE/cancel routes require the in-memory `JobRegistry`. After cold-start recovery, registry dictionaries are intentionally empty, so old status/event URLs can 404 even though the job row and event log exist.
4. Evidence from code: Translation `_require_job()` only checks `_jobs(request).get(job_id)` and project name (`src/weaver/api/routers/translate.py:300-306`). Batch/export have the same pattern (`src/weaver/api/routers/batch.py:175-215`, `src/weaver/api/routers/export.py:199-239`). Unified detail reads SQLite read-only and is explicitly restart-safe (`src/weaver/api/routers/jobs.py:1-9`, `:79-124`). Cold-start tests assert registry job dictionaries are empty after recovery (`tests/unit/api/test_cold_start_recovery.py:90-106`) but do not call the old status/event URLs.
5. Reproduction path or likely runtime path: Start a job, restart the web process, then refresh an old page or client polling `/projects/{name}/jobs/{job_id}` or `/events`. If the UI/client is not exclusively using `/detail`, it receives 404 for a persisted job.
6. Impact level: Medium
7. Suggested fix: Either make kind-specific GET/events routes fall back to the persisted job/event store for terminal/recovered jobs, or update all UI/client links to use the unified job detail route after submission and document old routes as live-only.
8. Test that should be added: Seed a running job, instantiate `create_api_app()` to trigger recovery, then assert the user-facing job detail path works and whichever status/event URL the UI uses after refresh does not 404.
9. Confidence level: Medium

### 2. Volume import can commit a new EPUB volume before snapshot persistence fails

1. File path: `src/weaver/services/import_source.py`, `src/weaver/api/routers/projects.py`
2. Function/class/route: `import_volume()`, `POST /projects/{name}/import`
3. Bug description: `import_volume()` commits the new volume, chapters, segments, glossary candidates, and project source path before it parses and stores the EPUB preservation snapshot. If `parse_epub_structure()`, `compute_source_hash()`, or `store_snapshot()` fails after the first transaction, the API returns an error while the volume remains imported without a snapshot.
4. Evidence from code: The service commits the `create_volume()`, `sync_document_segments()`, glossary extraction, and source-path update transaction at `src/weaver/services/import_source.py:78-103`. Only after closing that transaction does it call `parse_epub_structure()` and `store_snapshot()` for EPUB sources (`src/weaver/services/import_source.py:105-114`). The API maps `WeaverError` to 422 and unlinks only the uploaded temp file (`src/weaver/api/routers/projects.py:431-435`).
5. Reproduction path or likely runtime path: Monkeypatch `store_snapshot()` or `parse_epub_structure()` to raise after an otherwise valid EPUB import. The user receives an import failure, but project tree may show the new volume and later export/structure pages may report missing snapshot.
6. Impact level: Medium
7. Suggested fix: Parse the EPUB preservation snapshot before committing volume rows, or fold snapshot storage into the same logical transaction using the same connection. If partial import is intentional, return a degraded success result and surface the missing snapshot state rather than reporting a failed import.
8. Test that should be added: A service/API test that forces `store_snapshot()` to raise and asserts either full rollback of the new volume/segments or explicit degraded-success semantics with snapshot status `missing`.
9. Confidence level: Medium

### 3. QA/export preflight UI hashes source EPUB files on a render path

1. File path: `src/weaver/api/routers/ui_qa.py`, `docs/CODEMAPS/data.md`
2. Function/class/route: `_snapshot_export_advisories()`, `/ui/projects/{name}/export/preflight`
3. Bug description: The export preflight UI computes source-file hashes for every EPUB-sourced volume during a GET render. Large EPUBs, slow disks, unavailable network paths, or missing sources can block or degrade a UI read path. The operating docs explicitly call out read/render paths as no-hash/no-expensive-scan territory.
4. Evidence from code: `_snapshot_export_advisories()` resolves each source path, checks file existence, calls `compute_source_hash(source_path)`, then calls `snapshot_status()` (`src/weaver/api/routers/ui_qa.py:231-265`). `compute_source_hash()` reads the entire source file in chunks (`src/weaver/services/epub_snapshot.py:49-56`). The data codemap states one DB per project, schema v12, and the repo instructions emphasize no expensive hashing on render paths.
5. Reproduction path or likely runtime path: Open export preflight for a project with several large EPUB volumes or source paths on slow removable/network storage. The route blocks while hashing all sources, even though it is a UI render/advisory path.
6. Impact level: Medium
7. Suggested fix: Use stored snapshot metadata (`snapshot_info`) on the render path and move freshness hashing to an explicit user action or background job. Show "recorded/unknown/stale-check-needed" instead of hashing on every render.
8. Test that should be added: A no-hash render-path regression that monkeypatches `compute_source_hash()` to raise and asserts export preflight still renders without calling it. Add a separate explicit freshness-check test that is allowed to hash.
9. Confidence level: Medium

## Test Gaps That Hide Bugs

- Migration tests cover explicit `user_version` values such as 1, 2, 3, 4, 9, 10, and 11, but not a legacy DB with `user_version = 0` and existing tables.
- Export tests assert counts and artifact existence for chapter scope, but do not inspect EPUB artifact content/spine for chapter-scoped preserved EPUB output.
- Provider config tests currently assert that unbuildable free-form provider types are saved successfully.
- Translation cancel tests allow `"running"`, `"done"`, or `"cancelled"` and do not assert consistency between terminal status, terminal event, and `result.cancelled`.
- SSE tests assert that progress/done events appear, but not that replay uses read-only database access or that opening a stream leaves schema/state untouched.
- Cold-start recovery tests verify persisted rows and empty in-memory registries, but not the user-facing route behavior after restart.
- Glossary/character tests cover Unicode path decoding but not URL-encoded separators or stable-ID alternatives.
- Import tests do not force snapshot parse/store failure after the volume transaction to verify rollback/degraded semantics.
- Workspace/editor save flow has meaningful coverage for manual status/history; no high-confidence bug found in `save_segment_translation()` in this pass.

## Suggested Fix Order

1. Fix migration handling for version-0 legacy databases first. This is the highest data-safety risk and can silently mark broken DBs as current.
2. Fix provider config validation next. Current tests explicitly bless a config that later fails at runtime.
3. Fix EPUB chapter export scoping. It can produce materially wrong user artifacts while reporting success.
4. Fix job terminal consistency and SSE read-only replay together. They are both small, localized job lifecycle correctness issues.
5. Decide the persisted-job fallback policy for kind-specific routes after restart, then update routes or UI links accordingly.
6. Make import snapshot failure semantics explicit: atomic rollback or degraded success.
7. Replace glossary/character path-key mutations with body/query/stable-ID operations.
8. Move export preflight snapshot freshness hashing out of render paths and add no-hash regression tests.
