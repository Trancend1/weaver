# Weaver

Offline-capable, glossary-aware **JP→EN** novel translation workbench. CLI tool for amateur fan-translators. Single maintainer.

**Outputs:** translated EPUB + Markdown review file. Nothing else.
**Not:** GUI, SaaS, consumer product, web app.

---

## 1. Documentation Map

All specs live in [docs/](docs/). Read before non-trivial work.

| Doc | Purpose |
|-----|---------|
| [PRD_v2.md](docs/PRD_v2.md) | MVP-0 scope, commands, acceptance criteria, `project.toml` schema |
| [SYSTEM_ARCHITECTURE.md](docs/SYSTEM_ARCHITECTURE.md) | Module layout, IR types, SQLite schema, provider interface |
| [BLUEPRINT_EXECUTION_PLAN.md](docs/BLUEPRINT_EXECUTION_PLAN.md) | 10-phase build order |
| [ENGINEERING_STANDARDS.md](docs/ENGINEERING_STANDARDS.md) | Coding rules, naming, testing |
| [AI_SLOP_PREVENTION.md](docs/AI_SLOP_PREVENTION.md) | Feature gates, anti-patterns |
| [PROMPT_DESIGN.md](docs/PROMPT_DESIGN.md) | Prompt templates (read before Phase 3) |
| [DESIGN_SYSTEM.md](docs/DESIGN_SYSTEM.md) | CLI/UX surface rules |
| [BRAND_DIRECTION.md](docs/BRAND_DIRECTION.md) | Voice and tone |
| [SECURITY_AND_PERFORMANCE.md](docs/SECURITY_AND_PERFORMANCE.md) | Budgets, threat model |
| [FUTURE_ROADMAP.md](docs/FUTURE_ROADMAP.md) | Deferred features |
| [FEATURE_PRIORITY_MATRIX.md](docs/FEATURE_PRIORITY_MATRIX.md) | What ships when |
| [GO_TO_MARKET.md](docs/GO_TO_MARKET.md) | Launch plan |
| [FINAL_STARTUP_VERDICT.md](docs/FINAL_STARTUP_VERDICT.md) | Strategic context |
| [decisions/](docs/decisions/) | ADRs: provider interface, IR shape, segment ID, glossary algorithm, EPUB roundtrip |
| [benchmarks.md](docs/benchmarks.md) | Phase 10 performance budget evidence |
| [release_acceptance.md](docs/release_acceptance.md) | Phase 10.5 AC-1 through AC-9 evidence |

**Rule:** docs are the spec. Code follows docs. If code contradicts docs, ask first.

---

## 2. Progress

Single source of truth for build status. Update at end of every phase. Roadmap, exit criteria, and ordering sourced from [BLUEPRINT_EXECUTION_PLAN.md](docs/BLUEPRINT_EXECUTION_PLAN.md). No calendar estimates here — phase order and dependencies are what matters; ship when exit criteria pass.

### 2.1 Roadmap (MVP-0)

| # | Phase | Depends on | Status |
|---|-------|-----------|--------|
| 0 | Foundations — repo, tooling, CI, `weaver --version` | — | ✅ Complete |
| 1 | Source Reader & IR — EPUB → `DocumentIR`, segment IDs | 0 | ✅ Complete |
| 2 | State Store — SQLite (WAL), migrations, repository fns | 1 | ✅ Complete |
| 3 | Providers — `FakeProvider`, `DeepSeekProvider`, `GeminiProvider`, `OllamaProvider` | 2 | ✅ Complete |
| 4 | Translation Orchestrator — context builder, resumable loop | 3 | ✅ Complete |
| 5 | Glossary Workflow — candidate extraction, interactive review | 4 | ✅ Complete |
| 6 | Markdown Export — per-chapter review files | 4 | ✅ Complete |
| 7 | Manual Edit — `weaver edit <segment>` via `$EDITOR` | 4 (parallel with 6) | ✅ Complete |
| 8 | EPUB Renderer — translated EPUB roundtrip | 1 + 6 | ✅ Complete |
| 9 | QA Engine — `weaver validate` deterministic checks | 4 (parallel) | ✅ Complete |
| 10 | Hardening, Docs, Release — v0.1.0 to PyPI | all | ✅ Complete |

Legend: ✅ complete · 🟡 in progress · ⏳ next · ⬜ pending · 🚫 blocked.

Critical path: Phases 1→4 are strict; no reordering. Phases 5/6/7/9 may overlap once 4 ships.

### 2.2 Reusable Phase Gate

Before starting any next phase, always run this gate:

1. Read the current active phase in §2.3 and its source section in [BLUEPRINT_EXECUTION_PLAN.md](docs/BLUEPRINT_EXECUTION_PLAN.md).
2. List the active phase's exit criteria in plain language.
3. Verify each exit criterion with a concrete command, test, file check, or manual inspection.
4. State what is usable now, what is internal-only, and what is still not user-facing.
5. If every exit criterion passes, update §2.1 Roadmap, §2.3 Active Phase, §2.4 Exit Criteria, and §2.5 Phase Log.
6. If any exit criterion fails or is unverified, do not proceed to the next phase. Mark the phase blocked or keep it active, then record the missing proof.

Required reminder before phase transition: **"Check exit criteria first. No next phase until evidence exists. Explain the detail for manual inspection."**

### 2.3 Active Phase — Phase 10: Hardening, Docs, Release

**Goal:** ship `v0.1.0` to PyPI with documentation, ADRs, and a verified acceptance pass against the fixture EPUB.

**Sub-sprint plan** (one PR per slice; §PR Rules ENGINEERING_STANDARDS):

- **Sprint 10a — bugs + README + CHANGELOG (✅ done).** Three AC bugs fixed: `weaver export --help` listed only markdown (now includes epub); `_exit_with_error` only mapped codes 5/6 (now adds 3/4/7 per AC-9); `weaver glossary review` was missing example sentences (now shows up to 2). Added `weaver.core.config.load_project_config` to centralize TOML parsing across 8 call-sites with `ConfigError` messages carrying field + expected type. Added `provider.healthcheck()` preflight at the start of `translate_project` so a dead provider exits `3` cleanly. README rewritten end-to-end against the bundled fixture using the `fake` provider. `CHANGELOG.md` seeded with `[Unreleased]` + `[0.1.0]` entries. 142 tests pass (was 136).
- **Sprint 10b — five ADRs in `docs/decisions/` (✅ done).** ADRs `0001-provider-interface.md`, `0002-ir-shape.md`, `0003-segment-id.md`, `0004-glossary-algorithm.md`, `0005-epub-roundtrip.md` written per [ENGINEERING_STANDARDS.md](docs/ENGINEERING_STANDARDS.md) §Documentation Of Decisions format (Context / Decision / Consequences, one page each). Each cites the implementing module and references the spec source. Documentation Map updated.
- **Sprint 10c — benchmarks + scale fixture (✅ done).** Added `bench/generate_synthetic_fixture.py`, `bench/run_performance_budgets.py`, `tests/fixtures/synthetic_200_chapter.epub`, and [docs/benchmarks.md](docs/benchmarks.md). Latest budget run: init `2.25s`, glossary extraction `1.95s`, inspect `0.01s`, resume scan `0.08s`, fake translate `5.63 ms/segment`, markdown export `0.43s`, EPUB export `0.71s`, validate `0.09s`, DB size `5.95 MB`; all measured budgets pass. `weaver status` remains N/A because MVP-0 ships `weaver inspect` as the status surface.
- **Sprint 10d — MkDocs + GitHub Pages (✅ done).** Added [mkdocs.yml](mkdocs.yml), [docs/index.md](docs/index.md), [docs/quickstart.md](docs/quickstart.md), and [.github/workflows/pages.yml](.github/workflows/pages.yml). `uv run --extra dev mkdocs build --strict` passes.
- **Sprint 10e — release gate (✅ code/docs done; publish/tag pending credentials).** Added [docs/release_acceptance.md](docs/release_acceptance.md) from `bench/run_acceptance_gate.py`; AC-1 through AC-9 all PASS in the hands-on gate. Version bumped to `0.1.0`; classifier moved to `Development Status :: 3 - Alpha`; package build produced `dist/weaver-0.1.0.tar.gz` and `dist/weaver-0.1.0-py3-none-any.whl`.

**Exit criteria:** seeded from [BLUEPRINT_EXECUTION_PLAN.md](docs/BLUEPRINT_EXECUTION_PLAN.md) §Phase 10 when work begins. Plus the [PRD_v2.md](docs/PRD_v2.md) §10 acceptance criteria (AC-1 through AC-9) verified hands-on per the §Phase 10.5 gate.

**Blockers / open questions:** PyPI publish and `v0.1.0` tag require final credential-backed `uv publish` success before tag/push.

**Update protocol when phase closes:**
1. Flip roadmap status: `⏳ Next` (or `🟡 In Progress`) → `✅ Complete`.
2. Append a row to §2.5 Phase Log with PR link + one-line outcome.
3. Replace §2.3 with the next phase's goal/tasks/exit criteria from [BLUEPRINT_EXECUTION_PLAN.md](docs/BLUEPRINT_EXECUTION_PLAN.md).
4. Set the next phase's roadmap row to `⏳ Next`, flip to `🟡 In Progress` once work begins.
5. If something blocks progress, mark the row `🚫 Blocked` and record the reason under §2.3 Blockers.

### 2.4 Exit Criteria

This section is the reusable evidence ledger for phase gates. Before any phase transition, update the relevant row with command output, file checks, and manual inspection notes.

#### Phase 1 — Source Reader & IR

Status: `✅ Passed`

Plain-language criteria:

1. Reading the fixture EPUB must produce a deterministic `DocumentIR`.
2. Reading the same fixture EPUB twice must produce identical segment IDs.
3. Changing a paragraph's source text must produce a new `source_hash`, making the segment stale-eligible.

Evidence:

| Criterion | Proof | Status |
|---|---|---|
| Fixture EPUB produces `DocumentIR` | `tests/integration/readers/test_epub.py::test_read_epub_fixture_end_to_end_produces_document_ir` asserts metadata, spine order, chapter titles, block kinds, source text, normalized text, markup context, and assets. | ✅ Passed |
| Re-read produces identical segment IDs | `tests/integration/readers/test_epub.py::test_read_epub_fixture_is_deterministic_across_runs` compares block IDs from two `read_epub()` calls. | ✅ Passed |
| Text change produces new `source_hash` | `tests/integration/readers/test_epub.py::test_read_epub_source_hash_changes_when_paragraph_text_changes` compares original paragraph hash with modified paragraph hash. | ✅ Passed |
| Segment ID is stable and DOM-sensitive | `tests/unit/core/test_segment.py` covers deterministic IDs, DOM path changes, normalized hashing, and stale detection. | ✅ Passed |

Verification command:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\core\test_segment.py tests\integration\readers\test_epub.py
```

Latest observed result: `7 passed`.

Manual inspection:

- `src/weaver/core/ir.py` defines `DocumentMetadata`, `AssetIR`, `EpubMarkupContext`, `BlockIR`, `ChapterIR`, and `DocumentIR`.
- `src/weaver/readers/epub.py` exposes `read_epub(path: Path) -> DocumentIR` and uses `ebooklib.epub.read_epub`.
- `src/weaver/core/segment.py` exposes `normalize_japanese_text`, `compute_segment_id`, `compute_chapter_id`, `compute_source_hash`, and `is_source_stale`.
- `tests/fixtures/aozora_sample.epub` is present as the Phase 1 fixture.

Usability:

- Usable now: internal Python API for reading an EPUB fixture into IR and computing segment identity/hash.
- Internal-only: `DocumentIR`, EPUB markup context, segment ID/hash helpers.
- Not user-facing yet: no `weaver init`, no SQLite project database, no `weaver inspect`, no translation/export commands.

#### Phase 2 — State Store

Status: `✅ Passed`

Plain-language criteria:

1. `weaver init` on the fixture EPUB writes a complete SQLite database.
2. `weaver inspect` reads the database and prints a status panel.
3. Resume scan on a 10,000-segment database completes in under 5 seconds.

Evidence:

| Criterion | Proof | Status |
|---|---|---|
| `weaver init` writes a complete database | Manual command in `.tmp_phase2_manual`: `weaver init ..\tests\fixtures\aozora_sample.epub` created `.weaver/aozora_sample/project.toml` and `.weaver/aozora_sample/weaver.db`; output reported 2 chapters and 6 segments. | ✅ Passed |
| `weaver inspect` reads and prints status | Manual command: `weaver inspect .weaver\aozora_sample\project.toml` printed project name, source, provider/model, chapter count, segment count, status counts, glossary counts, and output path. | ✅ Passed |
| 10,000-segment resume scan under 5 seconds | `tests/unit/storage/test_repositories.py::test_reset_in_progress_and_10000_segment_pending_scan_stays_under_budget` passed; latest focused run: `1 passed in 0.22s`. | ✅ Passed |
| Full Phase 2 repository behavior | `tests/unit/storage/test_db.py`, `tests/unit/storage/test_repositories.py`, and `tests/integration/test_cli_state_store.py` cover WAL, foreign keys, `in_progress` reset, stale detection, repository functions, `init`, and `inspect`. | ✅ Passed |

Verification commands:

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m pytest tests\unit\storage\test_repositories.py::test_reset_in_progress_and_10000_segment_pending_scan_stays_under_budget -q
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m ruff format --check src tests
.\.venv\Scripts\pyright.exe --pythonpath .\.venv\Scripts\python.exe
```

Latest observed result: full suite `18 passed`; 10,000-segment focused test `1 passed in 0.22s`; Ruff check/format passed; Pyright `0 errors`.

Manual inspection:

- `src/weaver/storage/schema.sql` defines the Phase 2 SQLite schema and indexes.
- `src/weaver/storage/db.py` enables WAL, foreign keys, schema application, read-only inspect connections, transaction wrapper, and interrupted segment reset.
- `src/weaver/storage/projects.py`, `src/weaver/storage/segments.py`, and `src/weaver/storage/translations.py` expose repository functions.
- `src/weaver/services/project.py` owns project initialization/inspection; CLI does not write SQLite directly.
- Manual SQLite check on the generated DB showed `journal_mode=wal`, `projects=1`, `chapters=2`, `segments=6`, `pending=6`.

Usability:

- Usable now: `weaver init <input.epub>` creates `.weaver/<name>/project.toml` and `weaver.db`; `weaver inspect <project.toml>` prints a read-only status panel.
- Internal-only: repository functions, schema migration/bootstrap, transaction wrapper, stale detection, 10,000-segment pending scan.
- Not user-facing yet: provider healthchecks, translation, glossary review, edit, export, and validate.

#### Phase 3 — Providers

Status: `✅ Passed`

Plain-language criteria:

1. All four providers (`fake`, `deepseek`, `gemini`, `ollama`) register through one factory and conform to the `LLMProvider` ABC.
2. `FakeProvider` runs end-to-end through the fixture EPUB with zero network calls.
3. `weaver inspect --healthcheck` returns a `ProviderStatus` row; plain `weaver inspect` stays offline.
4. Schema migration adds `input_tokens` and `output_tokens` to `translations` on v1 databases without losing data.

Evidence:

| Criterion | Proof | Status |
|---|---|---|
| Four providers register through `build_provider()` | `tests/unit/providers/test_registry.py` covers Fake dispatch, missing-type error, unknown-type error. | ✅ Passed |
| FakeProvider runs end-to-end on fixture | `tests/integration/providers/test_fake_end_to_end.py::test_fake_provider_runs_end_to_end_through_fixture_epub` reads EPUB → builds context → translates → records translation with token columns → updates segment status. | ✅ Passed |
| `weaver inspect --healthcheck` wired | `tests/integration/test_cli_healthcheck.py` covers flag-on (Healthcheck row prints `healthy`) and flag-off (no Healthcheck row). Manual smoke against fixture printed `Healthcheck | healthy — 0 ms` with provider rewritten to `fake`. | ✅ Passed |
| Plain `weaver inspect` stays offline | Same integration test asserts the row is absent without the flag; default code path never calls `build_provider()`. | ✅ Passed |
| v1 → v2 schema migration adds token columns | `tests/unit/storage/test_migrations.py` covers fresh-DB lands at v2, v1 legacy DB upgrades to v2 via `apply_migrations`, and idempotent re-run. Manual SQLite check confirmed `user_version=2` and `translations` carries `input_tokens` / `output_tokens`. | ✅ Passed |
| Live cloud paths are gated | `tests/integration/providers/test_deepseek_live.py` and `test_gemini_live.py` carry `@pytest.mark.requires_cloud`; `test_ollama_live.py` carries `@pytest.mark.requires_ollama`. CI command `pytest -m "not requires_ollama and not requires_cloud"` skips them. | ✅ Passed |
| Provider unit coverage | `tests/unit/providers/test_parser.py`, `test_fake.py`, `test_prompts.py`, `test_deepseek.py`, `test_gemini.py`, `test_ollama.py` cover happy path, repair flow, timeout / auth / rate-limit / unknown error mapping, and healthcheck status assembly. | ✅ Passed |
| Context builder rules | `tests/unit/services/test_translation.py` covers substring filtering, 20-term cap, 5-segment / 600-token window cap, case sensitivity, honorific policy validation. | ✅ Passed |

Verification commands:

```powershell
.\.venv\Scripts\python.exe -m pytest -m "not requires_ollama and not requires_cloud"
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m ruff format --check src tests
.\.venv\Scripts\pyright.exe --pythonpath .\.venv\Scripts\python.exe
```

Latest observed result: `82 passed, 3 deselected`; Ruff lint + format clean; Pyright `0 errors`.

Manual inspection:

- `src/weaver/providers/base.py` defines `LLMProvider` ABC and `ProviderStatus`; `types.py` defines `GlossaryTerm`, `TranslationContext`, `TranslationRequest`, `TranslationResponse` per [SYSTEM_ARCHITECTURE.md](docs/SYSTEM_ARCHITECTURE.md):305-346.
- `src/weaver/providers/{fake,deepseek,gemini,ollama}.py` each subclass `LLMProvider`; `registry.py` exposes `build_provider()` and registers all four.
- `src/weaver/providers/parser.py` implements direct JSON → regex fallback (`r"\{.*\}"`, `re.DOTALL`) per [PROMPT_DESIGN.md](docs/PROMPT_DESIGN.md):156-178; raises `ParserError` on failure.
- `src/weaver/providers/prompts.py` loads templates from `providers/templates/` via cached Jinja2 `Environment(StrictUndefined)`. `balanced_system.txt`, `balanced_user.jinja2`, and `repair.txt` follow [PROMPT_DESIGN.md](docs/PROMPT_DESIGN.md) verbatim.
- `src/weaver/services/translation.py` ships `build_context()` only; orchestrator loop deferred to Phase 4.
- `src/weaver/storage/glossary.py` adds `list_glossary_terms(connection, project_id)` against the existing `glossary_terms` table.
- `src/weaver/storage/migrations.py` tracks schema via `PRAGMA user_version`; v1 → v2 adds `input_tokens` / `output_tokens` columns to `translations`.
- `src/weaver/cli/main.py` adds `--healthcheck/-H` to `inspect`; renders `Healthcheck | <state> — <latency_ms> ms[ — <message>]`.
- `pyproject.toml` declares new runtime deps: `jinja2>=3.1`, `httpx>=0.27`, `openai>=1.40`, `google-generativeai>=0.7`.
- Manual smoke against fixture EPUB confirmed `user_version=2` and `translations` columns `[segment_id, attempt, text, source_hash, provider, model, created_at, raw_response, input_tokens, output_tokens]`.

Usability:

- Usable now: provider implementations callable from Python; `weaver inspect --healthcheck` probes the configured provider.
- Internal-only: `LLMProvider`, `build_provider`, `build_context`, prompt templates, parser, glossary repository, schema migrations.
- Not user-facing yet: `weaver translate` command, glossary review, manual edit, Markdown/EPUB export, QA engine.

#### Phase 4 — Translation Orchestrator

Status: `✅ Passed`

Plain-language criteria:

1. A full fixture EPUB translates end-to-end with `FakeProvider`.
2. Interrupted `in_progress` work resets on restart and translation resumes from committed state.
3. `weaver translate --retry-failed` retries failed segments without re-running translated/manual segments.
4. Changed source hashes are surfaced as stale and not silently overwritten.
5. Provider failures mark segments failed and are visible in CLI/project status.

Evidence:

| Criterion | Proof | Status |
|---|---|---|
| Full fixture translates with FakeProvider | `tests/unit/services/test_translation_orchestrator.py::test_translate_project_runs_fixture_end_to_end_with_fake_provider` and `tests/integration/test_cli_translate.py::test_weaver_translate_runs_fake_provider_project` assert 6 fixture segments translated and persisted. | ✅ Passed |
| Correct context enters provider calls | `tests/unit/services/test_translation_orchestrator.py::test_translate_project_sends_previous_chapter_window_to_provider` asserts the second request receives the first translated source/target pair as previous context. | ✅ Passed |
| Interrupted work resumes | `tests/unit/services/test_translation_orchestrator.py::test_translate_project_resets_interrupted_segment_and_resumes` seeds `in_progress`, opens the DB through normal startup, and verifies all 6 segments become translated with no `in_progress` rows left. | ✅ Passed |
| `--retry-failed` retries only failed rows | `tests/unit/services/test_translation_orchestrator.py::test_translate_project_leaves_failed_segments_until_retry_failed` leaves one failed row untouched on normal translate, then translates exactly that row with `retry_failed=True`. | ✅ Passed |
| Stale source change is surfaced | `tests/unit/services/test_translation_orchestrator.py::test_translate_project_syncs_source_and_marks_changed_segment_stale` forces an outdated source hash and verifies the row becomes `stale`. | ✅ Passed |
| Failed segment path | `tests/unit/services/test_translation_orchestrator.py::test_translate_project_marks_provider_failure_failed` injects a provider that always raises and verifies all selected rows become `failed` with no translation rows written. | ✅ Passed |

Verification commands:

```powershell
.\.venv\Scripts\python.exe -m pytest -m "not requires_ollama and not requires_cloud"
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m ruff format --check src tests
.\.venv\Scripts\pyright.exe --pythonpath .\.venv\Scripts\python.exe
```

Latest observed result: `89 passed, 3 deselected`; Ruff lint + format clean; Pyright `0 errors`.

Manual inspection:

- `src/weaver/services/translation.py` now exposes `translate_project()` and `TranslationRunSummary`; it reads the current EPUB, syncs segment state, builds per-segment context, drives the configured provider, records token-aware translations, and marks `translated` / `failed`.
- `src/weaver/storage/segments.py` adds `list_segments_for_translation()` for pending vs retry-failed selection.
- `src/weaver/storage/translations.py` adds `list_previous_translated_segments()` for the same-chapter rolling context window.
- `src/weaver/cli/main.py` adds `weaver translate <project.toml>` with `--retry-failed/-r`, Rich progress, and summary counts.
- Manual smoke in `.tmp_phase4_manual`: `weaver init`, config rewritten to `fake`, `weaver translate .weaver\aozora_sample\project.toml` printed `Selected: 6`, `Translated: 6`, `Failed: 0`, `Pending: 0`, `Stale: 0`; `weaver inspect` then showed `Pending 0`, `Translated 6`, `Failed 0`, `Stale 0`.

Usability:

- Usable now: `weaver translate <project.toml>` translates pending segments; `weaver translate --retry-failed <project.toml>` retries failed segments.
- Internal-only: transaction orchestration, previous-segment context assembly, retry-failed selection, token totals in `TranslationRunSummary`.
- Not user-facing yet: glossary candidate extraction/review, manual edit, Markdown/EPUB export, QA engine.

#### Phase 5 — Glossary Workflow

Status: `✅ Passed`

Plain-language criteria:

1. `weaver init` extracts glossary candidates, stores them in SQLite, and writes `glossary_candidates.tsv`.
2. A user can approve, edit, reject, skip, undo, and resume review through `weaver glossary review`.
3. Approved glossary terms are copied into `glossary_terms` and appear in subsequent translation contexts.
4. Conflicting approved/edited glossary candidates halt translation with a clear error.
5. Windows users are not blocked by missing MeCab; extraction falls back to deterministic regex and README documents the optional MeCab/fugashi path.

Evidence:

| Criterion | Proof | Status |
|---|---|---|
| Synthetic extraction works | `tests/unit/services/test_glossary.py` covers katakana, honorific, variant clustering, singleton filtering, and conflict detection. | ✅ Passed |
| Review actions persist | `tests/unit/storage/test_glossary.py::test_candidate_review_actions_persist_and_update_terms` covers approve/edit/reject state and `glossary_terms` updates. | ✅ Passed |
| `init` writes candidate TSV | `tests/integration/test_cli_glossary.py::test_weaver_init_extracts_glossary_candidates_and_writes_tsv` asserts DB candidates and TSV header are created. | ✅ Passed |
| Interactive review persists | `tests/integration/test_cli_glossary.py` covers approving the first candidate and editing target/notes through `weaver glossary review`. | ✅ Passed |
| Approved terms enter translation context | `tests/unit/services/test_translation_orchestrator.py::test_translate_project_injects_approved_glossary_terms_into_matching_prompt` asserts an approved term is present in the provider request context. | ✅ Passed |
| Glossary conflicts halt translation | `tests/unit/services/test_translation_orchestrator.py::test_translate_project_halts_when_approved_glossary_conflicts` verifies `GlossaryConflictError`; CLI maps that error class to exit code 6. | ✅ Passed |

Verification commands:

```powershell
.\.venv\Scripts\python.exe -m pytest -m "not requires_ollama and not requires_cloud"
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m ruff format --check src tests
.\.venv\Scripts\pyright.exe --pythonpath .\.venv\Scripts\python.exe
```

Latest observed result: `98 passed, 3 deselected`; Ruff lint + format clean; Pyright `0 errors`.

Manual inspection:

- `src/weaver/services/glossary.py` adds candidate extraction with optional `fugashi` proper-noun tokenization and deterministic regex fallback for katakana, honorifics, CJK/title fallback, TSV write, TSV sync, and conflict checks.
- `src/weaver/storage/glossary.py` adds candidate records, review actions, term upsert/removal, undo restore, status counts, and conflict listing.
- `src/weaver/services/project.py` now extracts/stores candidates during `weaver init` and writes `glossary_candidates.tsv`.
- `src/weaver/cli/main.py` adds `weaver glossary review`, `weaver glossary edit`, and `weaver glossary conflicts`; glossary conflict errors exit with code 6.
- `src/weaver/services/translation.py` blocks translation when approved/edited glossary candidates conflict.
- `README.md` documents optional MeCab/fugashi setup and the regex fallback.
- Manual smoke in `.tmp_phase5_manual`: `weaver init` on the fixture printed `Extracted 2 glossary candidates`; `weaver glossary review` approved one candidate; `weaver inspect` showed `Glossary Candidates 2` and `Glossary Terms 1`. On legacy PowerShell codepage, Japanese candidate text degraded to `???` instead of crashing; UTF-8 terminals render the underlying TSV/database text normally.

Usability:

- Usable now: `weaver init` produces candidates + TSV; `weaver glossary review <project.toml>` can approve/edit/reject candidates; approved terms feed `weaver translate`.
- Internal-only: tokenizer fallback details, TSV sync implementation, conflict scan helpers.
- Not user-facing yet: manual segment edit, EPUB export, QA engine.

#### Phase 6 — Markdown Export

Status: `✅ Passed`

Plain-language criteria:

1. `weaver export --mode markdown` creates a top-level `review.md` index and one Markdown file per chapter.
2. Default output shows source text and translated text in reviewable pairs.
3. `--translation-only` hides source blocks and keeps translated text/markers.
4. Failed, stale, and missing segments are rendered as visible markers.
5. Chapter file order matches EPUB spine order.

Evidence:

| Criterion | Proof | Status |
|---|---|---|
| Index and per-chapter files | `tests/integration/test_cli_export_markdown.py::test_weaver_export_markdown_writes_review_index_and_chapter_files` asserts `review.md`, two fixture chapter files, index links, source labels, translation labels, and `EN:` translated text. | ✅ Passed |
| Translation-only mode | `tests/integration/test_cli_export_markdown.py::test_weaver_export_markdown_translation_only_omits_source_blocks` asserts source labels are omitted and translated text remains. | ✅ Passed |
| Failed/stale/missing markers | `tests/integration/test_cli_export_markdown.py::test_weaver_export_markdown_marks_failed_stale_and_missing_segments` seeds failed/stale/pending segments and verifies `[FAILED: ...]`, `[STALE: ...]`, and `[MISSING: ...]` markers. | ✅ Passed |

Verification commands:

```powershell
.\.venv\Scripts\python.exe -m pytest -m "not requires_ollama and not requires_cloud"
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m ruff format --check src tests
.\.venv\Scripts\pyright.exe --pythonpath .\.venv\Scripts\python.exe
```

Latest observed result: `101 passed, 3 deselected`; Ruff lint + format clean; Pyright `0 errors`.

Manual inspection:

- `src/weaver/services/export.py` adds `export_markdown_project()` and renders `output/markdown/review.md` plus `chapter-NNN.md` files from the current EPUB + latest matching SQLite translations.
- `src/weaver/cli/main.py` adds `weaver export <project.toml> --mode markdown` and `--translation-only`.
- Manual smoke in `.tmp_phase6_manual`: `weaver init`, config rewritten to `fake`, `weaver translate`, then `weaver export .weaver\aozora_sample\project.toml --mode markdown` printed `Wrote ...\output\markdown\review.md` and `Chapters: 2`; output directory contained `review.md`, `chapter-001.md`, and `chapter-002.md`.

Usability:

- Usable now: `weaver export <project.toml> --mode markdown` creates review files; add `--translation-only` for cleaner reading.
- Internal-only: Markdown rendering helpers and latest-translation lookup.
- Not user-facing yet: manual segment edit, EPUB export, QA engine.

#### Phase 7 — Manual Edit

Status: `✅ Passed`

Plain-language criteria:

1. `weaver edit <project.toml> <segment-id>` opens the segment in `$EDITOR` and persists the saved text.
2. Saving a non-empty edit stores a new `translations` row and sets the segment status to `manual`.
3. `manual` segments survive `weaver translate` and `weaver translate --retry-failed`.
4. A non-existent segment id produces a clear error and a non-zero exit code.

Evidence:

| Criterion | Proof | Status |
|---|---|---|
| Editor flow stores manual translation | `tests/integration/test_cli_edit.py::test_weaver_edit_opens_editor_and_marks_segment_manual` writes a stub editor, runs `weaver edit`, and asserts `segments.status='manual'` plus a `translations` row with `provider='manual'`. | ✅ Passed |
| Manual translation records new attempt over existing run | `tests/unit/services/test_manual_edit.py::test_apply_manual_translation_overrides_previous_translation_with_new_attempt` confirms attempt 2 is recorded after a Fake translate run. | ✅ Passed |
| Manual translation survives `--retry-failed` | `tests/unit/services/test_manual_edit.py::test_manual_translation_survives_retry_failed` marks other rows failed, runs retry, and asserts the manual row keeps `status='manual'` and the latest translation provider stays `manual`. | ✅ Passed |
| Empty saved text is rejected | `tests/unit/services/test_manual_edit.py::test_apply_manual_translation_rejects_empty_text` raises `ValueError`. | ✅ Passed |
| Non-existent segment id raises | `tests/unit/services/test_manual_edit.py::test_apply_manual_translation_unknown_segment_id_raises` and `tests/integration/test_cli_edit.py::test_weaver_edit_missing_segment_id_exits_with_clear_error` confirm `SegmentNotFoundError` and CLI exit code 5. | ✅ Passed |
| Missing `$EDITOR` is reported cleanly | `tests/integration/test_cli_edit.py::test_weaver_edit_missing_editor_env_exits_with_config_hint` confirms `ConfigError` mentions `EDITOR` and exits non-zero. | ✅ Passed |

Verification commands:

```powershell
.\.venv\Scripts\python.exe -m pytest -m "not requires_ollama and not requires_cloud"
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m ruff format --check src tests
.\.venv\Scripts\pyright.exe --pythonpath .\.venv\Scripts\python.exe
```

Latest observed result: `109 passed, 3 deselected`; Ruff lint + format clean; Pyright `0 errors`.

Manual inspection:

- `src/weaver/services/manual_edit.py` exposes `apply_manual_translation()` (pure) and `edit_segment()` (opens `$EDITOR` with a temp file, reads the result with `utf-8-sig` to drop a possible BOM, and delegates).
- `src/weaver/cli/main.py` adds `weaver edit <project.toml> <segment-id>`. `ValueError` (empty save) → exit code 1; `SegmentNotFoundError` → exit code 5; `ConfigError` for missing `$EDITOR` → standard CLI error path.
- `src/weaver/storage/segments.py` adds `get_segment()`. `src/weaver/storage/translations.py` adds `get_latest_translation_text()` to pre-fill the editor with the current translation when available.
- Phase 7 smoke in `.tmp_phase7_manual`: `weaver init`, provider rewritten to `fake`, `weaver translate` produced 6 translated segments, `weaver edit <segment_id>` with a `.cmd` editor stub printed `Saved. Segment 8732df9c64e0a7ce marked manual.`; SQLite then showed `status=manual` and latest translation `(2, 'Manual smoke override.', 'manual')`.

Usability:

- Usable now: `weaver edit <project.toml> <segment-id>` overrides a translation through `$EDITOR`. Manual segments persist across translate runs.
- Internal-only: `apply_manual_translation()` pure helper used by tests, `get_latest_translation_text()` for editor pre-fill, `get_segment()` lookup.
- Not user-facing yet: EPUB export, QA engine.

#### Phase 8 — EPUB Renderer

Status: `✅ Passed`

Plain-language criteria:

1. `weaver export --mode epub` writes a `.translated.epub` that reopens with `ebooklib`.
2. Translated blocks show the translated text in the rendered EPUB; segments without a usable translation fall back to source text.
3. EPUB metadata (title, language, identifier) and spine order match the source.
4. Asset items (CSS, images) carry through to the rendered EPUB.

Evidence:

| Criterion | Proof | Status |
|---|---|---|
| `--mode epub` writes a reopenable EPUB | `tests/integration/test_cli_export_epub.py::test_weaver_export_epub_writes_translated_epub_that_reads_back` runs `init` → `translate` (FakeProvider) → `export --mode epub`, reopens with `ebooklib`, and asserts `EN: ` appears inside `text/chapter01.xhtml`. CLI prints `Translated blocks: 6 | Fallback blocks: 0`. | ✅ Passed |
| Pending segments fall back to source text | `tests/integration/test_cli_export_epub.py::test_weaver_export_epub_falls_back_to_source_for_pending_segments` exports without translating; rendered chapter still contains `吾輩は猫である` and CLI reports `Translated blocks: 0 | Fallback blocks: 6`. | ✅ Passed |
| Renderer replaces text only for matching segments | `tests/unit/renderers/test_epub.py::test_render_translated_epub_replaces_text_for_known_segments` injects per-block translations and asserts they appear in chapter 1. | ✅ Passed |
| Renderer falls back when translation missing | `tests/unit/renderers/test_epub.py::test_render_translated_epub_falls_back_to_source_when_translation_missing` translates only block 0 and asserts block 1's source text remains. | ✅ Passed |
| Metadata, spine, and assets preserved | `tests/unit/renderers/test_epub.py::test_render_translated_epub_preserves_metadata_spine_and_assets` compares title, language, spine ordering, and asset paths between source and rendered EPUB. | ✅ Passed |
| `--mode epub --translation-only` rejected | `tests/integration/test_cli_export_epub.py::test_weaver_export_epub_rejects_translation_only_flag` asserts a non-zero exit and a flag-mismatch message. | ✅ Passed |

Verification commands:

```powershell
.\.venv\Scripts\python.exe -m pytest -m "not requires_ollama and not requires_cloud"
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m ruff format --check src tests
.\.venv\Scripts\pyright.exe --pythonpath .\.venv\Scripts\python.exe
```

Latest observed result: `115 passed, 3 deselected`; Ruff lint + format clean; Pyright `0 errors`.

Manual inspection:

- `src/weaver/renderers/epub.py` adds `render_translated_epub()` plus `EpubRenderResult`. Registers the XHTML and EPUB namespaces with ElementTree, groups blocks by chapter href, walks each block's `markup_context.xpath` step-by-step using local-name comparison, and replaces the matched element's `text` (clearing children — known trade-off documented in [PRD_v2.md](docs/PRD_v2.md) §6 Output).
- Missing or unmatched segments increment `fallback_blocks` and keep the source text untouched.
- `_ensure_navigation_items()` adds an `EpubNcx` entry when the source EPUB does not ship one. Without this, `ebooklib.write_epub` emits `<spine toc="ncx">` referencing a nonexistent manifest item, and the resulting EPUB cannot be reopened by `ebooklib` (and is rejected by strict EPUB 2 readers).
- `src/weaver/services/export.py` adds `export_epub_project()` and `_load_publishable_translations()` (latest translation per segment whose status is `translated` or `manual` and whose `translations.source_hash` still matches the segment hash).
- `src/weaver/cli/main.py` extends `weaver export` to accept `--mode epub`. `--translation-only` with `--mode epub` exits with code 1 and a clear message.
- Phase 8 smoke in `.tmp_phase8_manual`: `weaver init`, provider rewritten to `fake`, `weaver translate` produced 6 translated segments, `weaver export --mode epub` printed `Wrote .../aozora_sample.translated.epub` and `Translated blocks: 6 | Fallback blocks: 0`. Reopening the rendered EPUB with `ebooklib` showed translated text in `chapter01.xhtml` (e.g. `<h1>EN: 第一章</h1>`, `<p class="lead">EN: 名前はまだ無い。</p>`), preserved `xmlns="http://www.w3.org/1999/xhtml"`, preserved CSS asset, and the added `EpubNcx` item at `toc.ncx`.

Usability:

- Usable now: `weaver export <project.toml> --mode epub` writes `<output_dir>/epub/<source-stem>.translated.epub`.
- Internal-only: `_load_publishable_translations()`, `_ensure_navigation_items()`, ElementTree namespace registration, xpath resolution helpers.
- Not user-facing yet: QA engine, hardening/docs/release.

#### Phase 9 — QA Engine

Status: `✅ Passed`

Plain-language criteria:

1. Seeded warnings in test fixtures are detected.
2. `weaver validate` exits with code `1` when any `critical` finding is present, else `0`.
3. `--json` mode emits a machine-readable report with stable shape.
4. Six deterministic checks run as pure functions in `qa/checks.py` (no I/O).
5. False positives below 5% on the fixture novel.

Evidence:

| Criterion | Proof | Status |
|---|---|---|
| Per-check correctness | `tests/unit/qa/test_checks.py` covers empty, untranslated Japanese (4+ vs ≤3 char boundary), length ratio, glossary mismatch (including case-sensitive flag), failed, and stale; aggregator respects `[qa]` disable flags but always runs status checks. | ✅ Passed |
| End-to-end CLI clean run = exit 0 | `tests/integration/test_cli_validate.py::test_weaver_validate_reports_clean_run_when_no_issues_exit_zero` runs init → fake translate with ASCII-only pattern → validate; exits `0` and prints `No QA warnings.`. | ✅ Passed |
| Untranslated Japanese = critical exit 1 | `tests/integration/test_cli_validate.py::test_weaver_validate_detects_untranslated_japanese_exit_one` uses default fake pattern `EN: {source}`, expects exit `1` with `untranslated_japanese` and `critical` in output. | ✅ Passed |
| Failed segment = critical exit 1 | `tests/integration/test_cli_validate.py::test_weaver_validate_flags_failed_segment_exit_one` seeds a `failed` row and confirms exit `1` plus `failed_segment` in output. | ✅ Passed |
| Warning-only run = exit 0 | `tests/integration/test_cli_validate.py::test_weaver_validate_warning_only_exits_zero` seeds a `stale` row and confirms exit `0` plus `stale_segment` visible. | ✅ Passed |
| `--json` shape | `tests/integration/test_cli_validate.py::test_weaver_validate_json_output_shape` asserts `project`, `total_segments`, `summary` (info/warning/critical), and `findings` keys; verifies `critical >= 1` and at least one `untranslated_japanese` finding. | ✅ Passed |

Verification commands:

```powershell
.\.venv\Scripts\python.exe -m pytest -m "not requires_ollama and not requires_cloud"
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m ruff format --check src tests
.\.venv\Scripts\pyright.exe --pythonpath .\.venv\Scripts\python.exe
```

Latest observed result: `136 passed, 3 deselected`; Ruff lint + format clean; Pyright `0 errors`.

Manual inspection:

- `src/weaver/qa/checks.py` defines `SegmentInput`, `QAWarning`, six pure check fns (`check_empty_translation`, `check_untranslated_japanese`, `check_length_ratio`, `check_glossary_mismatch`, `check_failed_segment`, `check_stale_segment`), and `run_all_checks()` aggregator. `JP_LEAK_PATTERN` is `re.compile(r"[぀-ゟ゠-ヿ㐀-䶿一-鿿]{4,}")` (Hiragana + Katakana + CJK Ext-A + CJK Main; matches 4+ contiguous = ">3").
- `src/weaver/services/qa.py` exposes `validate_project()` and `format_report_json()`. Reads `[qa]` config flags (`detect_empty_output`, `detect_untranslated_japanese`, `detect_glossary_mismatch`, `minimum_length_ratio`) with defaults `True`/`True`/`True`/`0.3`. Loads latest translation per segment via the same CTE pattern as `services/export.py`. Pulls glossary via `list_glossary_terms()`. Returns `ValidationReport` with severity counts. JSON output is `ensure_ascii=True` so Windows legacy codepage stdout cannot crash on JP characters.
- `src/weaver/cli/main.py` registers `weaver validate <project.toml>` with `--json/-j`. Critical findings raise `typer.Exit(code=1)` after rendering. Rich table render runs through `console.capture()` + `_safe_echo` so a Windows console codepage that cannot encode JP degrades to `?` instead of raising `UnicodeEncodeError`.
- Severity policy: empty / untranslated Japanese / failed = `critical`; length ratio / glossary mismatch / stale = `warning`. Locked in plan, reflected in `qa/checks.py`.
- No writes to `qa_warnings` table (stateless validate). Schema row remains in `storage/schema.sql` for a future surface.

Manual smoke (`.tmp_phase9_manual/`):

1. `weaver init ..\tests\fixtures\aozora_sample.epub` → 2 chapters, 6 segments, 2 glossary candidates.
2. Rewrote `project.toml` to `type = "fake"`, `model = "fake-1"`, `pattern = "EN: {source}"`.
3. `weaver translate .weaver\aozora_sample\project.toml` → `Selected: 6, Translated: 6, Failed: 0`.
4. `weaver validate .weaver\aozora_sample\project.toml` → exit `1`, Rich table prints 4 `untranslated_japanese` critical rows; JP literal degrades to `?` on PowerShell 5.1 CP1252.
5. `weaver validate .weaver\aozora_sample\project.toml --json` → emits parseable JSON (`\uXXXX`-escaped JP), `summary.critical = 4`.
6. Seeded a `failed` segment via `_seed_failed.py`; re-ran `weaver validate --json` → `summary.critical = 5`, checks present: `failed_segment, untranslated_japanese`.

Usability:

- Usable now: `weaver validate <project.toml>` runs all six checks and exits `1` on any critical; `--json` for tooling.
- Internal-only: `SegmentInput`, `QAWarning`, `ValidationReport`, `run_all_checks()`, `_load_segments()` SQL.
- Not user-facing yet: hardening, docs site, ADRs, release.

### 2.5 Phase Log

| # | Phase | PR | Outcome |
|---|-------|----|---------|
| 0 | Foundations | [#1](https://github.com/Trancend1/weaver-translate/pull/1) | MIT license, `pyproject.toml` (uv + hatchling), `weaver --version`, `WeaverError` hierarchy, typer CLI skeleton; ruff/ruff-format/pyright/pytest all green locally. |
| 1 | Source Reader & IR | Local sprint | `DocumentIR` dataclasses, ebooklib EPUB reader, deterministic segment IDs/source hashes, and public-domain EPUB fixture covered by unit + integration tests. |
| 2 | State Store | Local sprint | SQLite WAL schema, project bootstrap, repository functions, `weaver init`, `weaver inspect`, stale/reset behavior, and 10,000-segment scan covered by unit + integration tests. |
| 3 | Providers | Local sprint | `LLMProvider` ABC + four providers (`fake`, `deepseek`, `gemini`, `ollama`) via `build_provider()` factory; Jinja2 prompt templates; JSON parser with repair flow; `build_context()` glossary + rolling window; schema v2 migration adds token columns; `weaver inspect --healthcheck` opt-in flag; 82 unit + integration tests cover happy path, repair, error mapping, healthcheck, and migration. |
| 4 | Translation Orchestrator | Local sprint | `weaver translate` drives the configured provider over pending segments with rolling context, one-segment transactions, resume reset, stale detection, failed-segment status, retry-failed selection, Rich progress, and 89-test verification. |
| 5 | Glossary Workflow | Local sprint | `weaver init` extracts candidates and writes TSV; `weaver glossary review/edit/conflicts` handles approval, edit, rejection, TSV sync, undo, and conflict display; approved terms feed translation context; conflicts block translate with exit code 6; 98-test verification. |
| 6 | Markdown Export | Local sprint | `weaver export --mode markdown` writes `review.md` plus per-chapter files, supports source+translation and translation-only modes, and renders failed/stale/missing markers; 101-test verification. |
| 7 | Manual Edit | Local sprint | `weaver edit <project.toml> <segment-id>` opens `$EDITOR`, writes a new translation row with `provider='manual'`, sets `segments.status='manual'`, and survives `--retry-failed`; missing-id surfaces `SegmentNotFoundError` with exit code 5; 109-test verification. |
| 8 | EPUB Renderer | Local sprint | `weaver export --mode epub` rewrites translated block text by `markup_context.xpath`, preserves metadata/spine/assets, falls back to source text when no translation exists, and adds an `EpubNcx` item so `ebooklib`/EPUB 2 readers can reopen the output; 115-test verification. |
| 9 | QA Engine | Local sprint | `weaver validate <project.toml>` runs six deterministic pure-function checks (empty, untranslated Japanese, length ratio, glossary mismatch, failed, stale); critical (empty / JP-leak / failed) exits `1`, warnings exit `0`; `--json` mode with stable shape and `ensure_ascii=True` for codepage safety; Rich table render captured through `_safe_echo` for Windows console safety; stateless (no `qa_warnings` writes); 136-test verification. |
| 10 | Hardening, Docs, Release | Local sprint | Benchmarks, MkDocs/GitHub Pages, release acceptance gate, v0.1.0 metadata, and package build completed; 142-test verification, Ruff, Pyright, MkDocs strict build, perf budgets, and AC-1..AC-9 gate passed. PyPI publish/tag remain credential-gated. |

---

## 3. Stack (Locked)

**Use:** Python 3.11+ · uv · pyproject.toml · ruff · pyright (basic) · pytest · typer · rich · pydantic v2 · tomllib · sqlite3 (WAL, no ORM) · ebooklib · fugashi + ipadic-neologd · openai SDK · google-generativeai · Jinja2.

**Rejected (no reintroduction without ADR):** Django · Flask · FastAPI · SQLAlchemy · Celery · RQ · Docker · asyncio · Sentry · OpenTelemetry.

**Providers (MVP-0):**

| Provider | Role | Auth |
|----------|------|------|
| `deepseek` | Default cloud | `DEEPSEEK_API_KEY` |
| `gemini` | Free-tier cloud | `GEMINI_API_KEY` |
| `ollama` | Local, optional | None (local) |
| `fake` | CI/dev default | None |

---

## 4. AI Instructions

### 4.1 Before Coding
- Read relevant doc section. Docs are authoritative.
- Match phase order. No jumping ahead.
- Before starting a new phase, run the reusable phase gate in §2.2 and check exit criteria first.
- Use exact names/values from docs for types, schemas, exit codes. No improvisation.
- When unsure: ask. Do not invent fields, prompts, commands, exit codes.

### 4.2 Code Rules (Non-Negotiable)

Source: [ENGINEERING_STANDARDS.md](docs/ENGINEERING_STANDARDS.md).

- Type hints on every public function. Pyright basic must pass.
- One concept per file. Split if >400 lines or >5 public functions.
- Forbidden filenames: `utils.py`, `helpers.py`, `manager.py`. Name modules for what they do.
- No `**kwargs` in public APIs.
- No `except: pass`. No `except Exception: pass` outside CLI boundary.
- All errors via `WeaverError` hierarchy in `src/weaver/errors.py`.
- User-facing errors: **what failed / likely cause / next command**.
- State writes go through services. CLI never touches SQLite directly.
- One segment translation = one transaction.
- API keys via env vars only, never config files. Never log keys.
- `@dataclass(frozen=True)` for value types. Mutability only for state machines.
- File paths via `pathlib.Path`. Atomic writes (`tempfile` + `replace`) for valuable state.
- Tests mirror source tree. Use `FakeProvider`, never live LLMs in CI. Fixtures = public domain only.

### 4.3 Anti-Slop

Source: [AI_SLOP_PREVENTION.md](docs/AI_SLOP_PREVENTION.md).

- No "smart" / "AI-powered" / "magical" / "intelligent" feature names.
- No chat UIs, assistant avatars, sparkle animations, fortune-cookie loaders.
- Deterministic by default. LLM only when determinism impossible AND output is verifiable AND user can override.
- No config flags for unbuilt features.
- No stub functions, no commented-out code, no abstractions with one caller.

### 4.4 Scope Discipline

- MVP-0 ships only what [PRD_v2.md](docs/PRD_v2.md) §6 lists.
- Deferred items (PRD §7) get no scaffolding "for later".
- Not in acceptance criteria (PRD §10) → do not build.
- One PR = one concern. No bundled refactor + feature.

### 4.5 Communication

- Terse, technical. No filler, no apology, no marketing language.
- Reference files as `[name](path/file.md)` or `src/weaver/foo.py:42`.
- State decisions directly.

### 4.6 Contribution Identity

- Agentic AI must not appear as a GitHub contributor, author, committer, co-author, or bot identity.
- Do not add `Co-Authored-By`, `Generated-By`, `Assisted-By`, or similar trailers for Claude, Codex, ChatGPT, Anthropic, OpenAI, or other agentic AI tools.
- Commit author and committer identity must stay on the maintainer/user account only.
- Before any commit or PR, scan the pending commit message and recent history for `Co-Authored-By`, `Claude`, `Anthropic`, `Codex`, `ChatGPT`, `OpenAI`, and AI no-reply emails.
- The repo hook in `.githooks/commit-msg` is mandatory local guardrail. Keep `git config core.hooksPath .githooks` enabled.
- If an AI attribution trailer or bot author is found after commit, stop phase work and clean history before opening or updating PRs.
