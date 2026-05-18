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
| 5 | Glossary Workflow — candidate extraction, interactive review | 4 | ⏳ Next |
| 6 | Markdown Export — per-chapter review files | 4 | ⬜ Pending |
| 7 | Manual Edit — `weaver edit <segment>` via `$EDITOR` | 4 (parallel with 6) | ⬜ Pending |
| 8 | EPUB Renderer — translated EPUB roundtrip | 1 + 6 | ⬜ Pending |
| 9 | QA Engine — `weaver validate` deterministic checks | 4 (parallel) | ⬜ Pending |
| 10 | Hardening, Docs, Release — v0.1.0 to PyPI | all | ⬜ Pending |

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

### 2.3 Active Phase — Phase 5: Glossary Workflow

**Goal:** Candidate extraction plus interactive review for approved glossary terms.

**Tasks:** seeded from [BLUEPRINT_EXECUTION_PLAN.md](docs/BLUEPRINT_EXECUTION_PLAN.md) §Phase 5 when work begins.

**Exit criteria:** seeded from [BLUEPRINT_EXECUTION_PLAN.md](docs/BLUEPRINT_EXECUTION_PLAN.md) §Phase 5 when work begins.

**Blockers / open questions:** none.

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

### 2.5 Phase Log

| # | Phase | PR | Outcome |
|---|-------|----|---------|
| 0 | Foundations | [#1](https://github.com/Trancend1/weaver-translate/pull/1) | MIT license, `pyproject.toml` (uv + hatchling), `weaver --version`, `WeaverError` hierarchy, typer CLI skeleton; ruff/ruff-format/pyright/pytest all green locally. |
| 1 | Source Reader & IR | Local sprint | `DocumentIR` dataclasses, ebooklib EPUB reader, deterministic segment IDs/source hashes, and public-domain EPUB fixture covered by unit + integration tests. |
| 2 | State Store | Local sprint | SQLite WAL schema, project bootstrap, repository functions, `weaver init`, `weaver inspect`, stale/reset behavior, and 10,000-segment scan covered by unit + integration tests. |
| 3 | Providers | Local sprint | `LLMProvider` ABC + four providers (`fake`, `deepseek`, `gemini`, `ollama`) via `build_provider()` factory; Jinja2 prompt templates; JSON parser with repair flow; `build_context()` glossary + rolling window; schema v2 migration adds token columns; `weaver inspect --healthcheck` opt-in flag; 82 unit + integration tests cover happy path, repair, error mapping, healthcheck, and migration. |
| 4 | Translation Orchestrator | Local sprint | `weaver translate` drives the configured provider over pending segments with rolling context, one-segment transactions, resume reset, stale detection, failed-segment status, retry-failed selection, Rich progress, and 89-test verification. |

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
