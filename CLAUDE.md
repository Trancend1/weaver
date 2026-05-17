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
| 3 | Providers — `FakeProvider`, `DeepSeekProvider`, `GeminiProvider`, `OllamaProvider` | 2 | ⏳ Next |
| 4 | Translation Orchestrator — context builder, resumable loop | 3 | ⬜ Pending |
| 5 | Glossary Workflow — candidate extraction, interactive review | 4 | ⬜ Pending |
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

### 2.3 Active Phase — Phase 3: Providers

**Goal:** `FakeProvider`, `OllamaProvider`, `DeepSeekProvider` callable through one interface.

**Tasks:**

- [ ] Read [PROMPT_DESIGN.md](docs/PROMPT_DESIGN.md) in full before coding this phase.
- [ ] `LLMProvider` ABC, `TranslationRequest`, `TranslationResponse`, `TranslationContext` types per [SYSTEM_ARCHITECTURE.md](docs/SYSTEM_ARCHITECTURE.md).
- [ ] `FakeProvider` with deterministic and parametrizable responses (configurable pattern, configurable fail rate). Ship and test this first.
- [ ] Jinja2 template loader from `providers/templates/`.
- [ ] `build_context()` function in `services/translation.py` — assembles glossary terms + rolling window into `TranslationContext`.
- [ ] JSON output parser with regex fallback and single repair-retry per [PROMPT_DESIGN.md](docs/PROMPT_DESIGN.md).
- [ ] `DeepSeekProvider`: OpenAI-compatible client via `openai` SDK pointed at DeepSeek base URL. API key via `DEEPSEEK_API_KEY`.
- [ ] `GeminiProvider`: Google Gemini Flash via `google-generativeai` SDK. API key via `GEMINI_API_KEY`.
- [ ] `OllamaProvider`: HTTP POST to `/api/generate`, configurable model and base URL. Unit test via mock; integration test via `@pytest.mark.requires_ollama`.
- [ ] API key handling via env vars only.
- [ ] Provider healthcheck command behavior.
- [ ] Token usage tracking in all cloud providers (DeepSeek, Gemini).

**Exit criteria:** three providers register and pass `weaver inspect` healthcheck; Fake provider runs end-to-end with no external dependencies; Ollama runs end-to-end if Ollama is installed (skipped in CI); DeepSeek runs end-to-end if `DEEPSEEK_API_KEY` is set (skipped in CI).

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
.\.venv-codex\Scripts\python.exe -m pytest tests\unit\core\test_segment.py tests\integration\readers\test_epub.py
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
.\.venv-codex\Scripts\python.exe -m pytest
.\.venv-codex\Scripts\python.exe -m pytest tests\unit\storage\test_repositories.py::test_reset_in_progress_and_10000_segment_pending_scan_stays_under_budget -q
.\.venv-codex\Scripts\python.exe -m ruff check src tests
.\.venv-codex\Scripts\python.exe -m ruff format --check src tests
.\.venv-codex\Scripts\pyright.exe --pythonpath .\.venv-codex\Scripts\python.exe
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

### 2.5 Phase Log

| # | Phase | PR | Outcome |
|---|-------|----|---------|
| 0 | Foundations | [#1](https://github.com/Trancend1/weaver-translate/pull/1) | MIT license, `pyproject.toml` (uv + hatchling), `weaver --version`, `WeaverError` hierarchy, typer CLI skeleton; ruff/ruff-format/pyright/pytest all green locally. |
| 1 | Source Reader & IR | Local sprint | `DocumentIR` dataclasses, ebooklib EPUB reader, deterministic segment IDs/source hashes, and public-domain EPUB fixture covered by unit + integration tests. |
| 2 | State Store | Local sprint | SQLite WAL schema, project bootstrap, repository functions, `weaver init`, `weaver inspect`, stale/reset behavior, and 10,000-segment scan covered by unit + integration tests. |

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
