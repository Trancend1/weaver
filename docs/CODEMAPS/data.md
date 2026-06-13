<!-- Generated: 2026-06-13 | Files scanned: src/weaver/storage/*.py, src/weaver/storage/schema.sql, src/weaver/services/{export_ledger,workspace_index,translation_qa}.py, remote origin/main:docs/{TRANSLATION_PIPELINE,MAINTENANCE,SECURITY_AND_PERFORMANCE}.md | Token estimate: ~900 -->
# Data

## Store Model
One SQLite database per project (`<name>/weaver.db`), WAL mode, no ORM. Migrations in `src/weaver/storage/migrations.py`; base schema in `src/weaver/storage/schema.sql`. **`SCHEMA_VERSION = 12`** (`src/weaver/storage/db.py`).

## Storage Modules (`src/weaver/storage/`)
- `db.py` -> `initialize_database(path)`, readonly connection support, writable open migration/reset behavior.
- `migrations.py` -> forward migration runner; v9 review status, v10 project UUID, v11 export ledger, v12 drops dead `qa_warnings` only when empty.
- `projects.py` -> project identity; `get_first_project_id` single accessor.
- `volumes.py` -> volumes/chapters lifecycle; ordered helpers used by batch translate/export.
- `segments.py`, `translations.py` -> source text/status/source_hash and per-segment translation rows.
- `candidates.py`, `character_drafts.py` -> reviewable candidate state.
- `glossary.py`, `characters.py`, `translation_memory.py` -> project resources injected into prompts and review flows.
- `export_history.py` -> export ledger rows (v11).

## Core Tables (`schema.sql`)
`projects` (with `uuid`) - `volumes` - `chapters` - `segments` (with `review_status`) - `translations` - `glossary_candidates` - `glossary_terms` - `characters` - `translation_memory` - `job_events` - `jobs` - `job_progress_snapshots` - `export_history`.

## Migration Milestones
- v3: novel/volume/chapter model (active ADR `006`, user label later changed by ADR `011`).
- v4/v5: characters and translation memory become first-class resources.
- v9: review/status workflow baseline; adds `segments.review_status`.
- v10: `projects.uuid` for stable cross-project identity.
- v11: `export_history` ledger (writer in `services/export_ledger.py`).
- v12: conditional drop of dead `qa_warnings`; residual cleanup is code-only.

## On-Disk Project Layout
```txt
.weaver/<name>/
+- project.toml        # [provider], [translation], [glossary], [qa]
+- weaver.db           # SQLite WAL source of truth
+- glossary_candidates.tsv
+- glossary.tsv
+- logs/               # rotated daily
+- output/{epub,txt,html,docx,markdown}/ (+ bundle-<target>.zip when requested)
```
Provider secrets are not stored here; they live in env vars or `~/.weaver/secrets.toml`.

## Import / Translation State
```txt
source file -> readers -> DocumentIR -> deterministic segment ids + source_hash
segments.status: pending/in_progress/translated/manual/failed/stale-like flows
translations row: provider/model output + source_hash for publishability check
manual edits: status=manual and survive retry-failed
```
- Source hash mismatch prevents unsafe publish and makes export fall back to source for that segment.
- Glossary candidates, characters, and TM are review resources, not parallel stores for final translations.

## Export Semantics
- Export never blocks on incomplete translation. A segment is published only when status is `translated` or `manual` and `source_hash` matches; all other segments fall back to source and are counted in `FallbackByStatus`.
- `services/export_book.py` writes volume-aware artifacts and `export_history`; `services/export.py` is legacy CLI path.
- `export_history` is the source of truth for export attempts; `volume_lifecycle` overlay remains deferred.

## Cross-Project Workspace Reads
- `services/workspace_index.py` + workspace hub services read many project DBs through readonly connections.
- Index is mtime-cached, error-isolated, and stale-running reconciling.
- Read paths must not migrate, reset `in_progress`, call providers, run QA scans, or hash source files.

## Maintenance / Safety Rules
- State writes go through services; one segment translation = one transaction.
- Migrations must be forward + idempotency tested; no silent data loss.
- Valuable state writes use atomic patterns; path handling uses `pathlib.Path`.
- Malformed project/source input must fail visibly without crashing the cockpit.

## Forward-Relevant Data Risks
- Legacy v10 projects can show `needs_upgrade` in Exports hub until opened writable for migration.
- `export_history.job_id` is `NULL` because JobRegistry id is known only after closure.
- `<ruby>` import flattens via `itertext()`, leaking furigana into `source_text` (WV-014 follow-up).
- OCR is contract-only; image preview data is manifest/read-only, not imported OCR text.

## Verification Anchors
- `tests/unit/storage/test_migrations.py` covers migration forward/idempotency/non-empty refusal.
- Gate B1 tests/smokes cover readonly hub/list/render paths.
- QA report services are read-only and reuse deterministic `weaver.qa.checks`.
