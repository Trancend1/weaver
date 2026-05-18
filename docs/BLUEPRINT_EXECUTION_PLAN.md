# Weaver Blueprint Execution Plan

Realistic ship plan for one full-time-equivalent engineer. Calibrated against the MVP-0 scope in `PRD_v2.md`. Phases assume 30–35 productive hours per week.

## Hardware Requirements For Development

**Minimum:** A laptop/desktop that can run Python 3.11 and make HTTPS requests. No GPU required.

`FakeProvider` handles 100% of automated testing with zero external dependencies. `DeepSeek` and `Gemini Flash` (both free-tier or low-cost cloud) handle manual quality verification. Ollama is never required during development.

| Task | Required hardware | Required network |
|------|-------------------|-----------------|
| Unit tests | Any machine | None |
| Integration tests | Any machine | None (FakeProvider) |
| Manual translation quality check | Any machine | HTTPS to DeepSeek or Gemini API |
| Ollama provider testing | GPU recommended (8GB+ VRAM) | None (local) |

If you do not have local GPU hardware: use `@pytest.mark.requires_ollama` to skip Ollama tests and validate OllamaProvider via CI service container instead.

## Phase 0: Foundations (Week 1)

Goal: a working repository with one passing test, on day one.

- Initialize repo, license (suggest MIT or Apache 2.0; decide before any code lands).
- `pyproject.toml`, `uv` lockfile, baseline `ruff` + `pyright` configs.
- CI workflow: lint, type-check, test on push.
- Skeleton CLI with `typer`: `weaver --version` works.
- Single test that asserts version is set.
- Add `tests/fixtures/` with a tiny public-domain Aozora Bunko EPUB.

Exit criteria:

- `pip install -e .` succeeds.
- `weaver --version` prints.
- CI is green.
- A new contributor could follow `README.md` and reproduce the above in 10 minutes.

## Phase 1: Source Reader And IR (Week 2)

Goal: turn an EPUB into `DocumentIR` with chapters and blocks.

- Define `DocumentIR`, `ChapterIR`, `BlockIR` dataclasses with full typing.
- Implement EPUB reader using `ebooklib`:
  - Parse metadata.
  - Walk spine order.
  - Extract paragraph and heading blocks.
  - Capture `markup_context` with `xml_node_path` and original attributes.
- JP text normalization (`unicodedata.normalize("NFKC", ...)` + half/full-width handling).
- `segment_id` and `source_hash` computation.
- Unit tests for ID stability and stale detection.
- Integration test reading the fixture EPUB end-to-end.

Exit criteria:

- Reading fixture EPUB produces a deterministic IR.
- Re-reading produces identical segment IDs.
- Modifying a paragraph's text produces a new `source_hash` and the segment becomes stale-eligible.

## Phase 2: State Store (Week 3)

Goal: persistent project state via SQLite.

- Schema in `storage/schema.sql` matching `SYSTEM_ARCHITECTURE.md`.
- Migration runner: apply schema if `schema_version` < current.
- WAL mode enabled at first connection.
- Repository functions: `insert_segment`, `update_segment_status`, `record_translation`, `list_pending_segments`.
- Transaction wrapper.
- Tests:
  - Crash mid-translation: `in_progress` resets to `pending` on next startup.
  - Stale detection: old translation invalidated when source hash changes.
  - 10,000-segment performance test (synthetic).

Exit criteria:

- `weaver init` on the fixture EPUB writes a complete database.
- `weaver inspect` reads it and prints a status panel.
- Resume scan on 10,000-segment DB completes in under 5 seconds.

## Phase 3: Providers (Week 4)

Goal: `FakeProvider`, `OllamaProvider`, `DeepSeekProvider` callable through one interface.

**Before coding this phase: read `PROMPT_DESIGN.md` in full.** The prompt template design is finalized there. Do not improvise prompt structure during implementation.

- `LLMProvider` ABC, `TranslationRequest`, `TranslationResponse`, `TranslationContext` types per `SYSTEM_ARCHITECTURE.md`.
- `FakeProvider` with deterministic and parametrizable responses (configurable pattern, configurable fail rate). **Ship and test this first — it unblocks everything downstream.**
- Jinja2 template loader from `providers/templates/`.
- `build_context()` function in `services/translation.py` — assembles glossary terms + rolling window into `TranslationContext`.
- JSON output parser with regex fallback and single repair-retry per `PROMPT_DESIGN.md`.
- `DeepSeekProvider`: OpenAI-compatible client via `openai` SDK pointed at DeepSeek base URL. API key via `DEEPSEEK_API_KEY`. **Implement second — primary real-provider for development.**
- `GeminiProvider`: Google Gemini Flash via `google-generativeai` SDK. API key via `GEMINI_API_KEY`. Free tier sufficient for testing.
- `OllamaProvider`: HTTP POST to `/api/generate`, configurable model and base URL. **Implement last.** Unit test via mock; integration test via `@pytest.mark.requires_ollama` skipped in normal CI.
- API key handling via env vars only.
- Provider healthcheck command behavior.
- Token usage tracking in all cloud providers (DeepSeek, Gemini).

**CI configuration for Ollama testing (optional):**
Add a separate CI job `test-ollama` that runs `services: ollama:latest` as a Docker service container. Trigger only on PRs that touch `providers/ollama.py`. This allows OllamaProvider to be integration-tested without local GPU hardware.

Exit criteria:

- Three providers register and pass `weaver inspect` healthcheck.
- Fake provider runs end-to-end with no external dependencies.
- Ollama runs end-to-end if Ollama is installed (skipped in CI).
- DeepSeek runs end-to-end if `DEEPSEEK_API_KEY` is set (skipped in CI).

## Phase 4: Translation Orchestrator (Week 5)

Goal: `weaver translate` produces translations, resumable.

- Context builder: previous segment, rolling 5-segment chapter window, approved glossary terms with surface-match filtering.
- Prompt template (single template, JSON-output contract).
- Orchestrator loop: select pending, mark in-progress, call provider, parse, commit, repeat.
- Progress bar via `rich`.
- Cost estimator for cloud providers (token usage tracked).
- Tests with `FakeProvider`:
  - Full run on the fixture EPUB.
  - Interruption mid-run; resume continues correctly.
  - Stale source change invalidates old translation.
  - Failed segment recorded and surfaced.

Exit criteria:

- A full fixture EPUB translates end-to-end with `FakeProvider`.
- Killing the process mid-run and restarting picks up where it stopped.
- `weaver translate --retry-failed` retries only failed segments.

## Phase 5: Glossary Workflow (Week 6)

Goal: candidate extraction + interactive review.

**Platform note — Windows:** `fugashi` requires MeCab to be installed. On Windows, this means installing a pre-built MeCab binary and adding it to PATH before `pip install fugashi` will succeed. `ipadic-neologd` requires a separate dictionary build step. Document the Windows setup process in the README before this phase ships; do not let Windows users discover the failure at runtime with a cryptic `import fugashi` error.

Platform support matrix for Phase 5:
- Linux: `fugashi[unidic]` or `fugashi + ipadic` via pip — straightforward.
- macOS: `brew install mecab mecab-ipadic` then `pip install fugashi` — documented.
- Windows: MeCab installer from taku910.github.io, then `pip install fugashi` — must be documented explicitly with tested steps.

Fallback: if MeCab is unavailable, gracefully degrade to regex-only extraction (katakana sequences + honorific patterns) and log a warning. This is a lower-quality candidate set but does not block the user.

- Tokenization with `fugashi` + `ipadic-neologd` with the degraded-regex fallback.
- Candidate extraction algorithm per `PRD_v2.md`:
  - Proper nouns, katakana runs, honorific patterns.
  - Frequency threshold, clustering, LLM-suggested initial target.
- Storage in `glossary_candidates` table and parallel TSV export.
- `weaver glossary review`: interactive CLI per `DESIGN_SYSTEM.md`.
- `weaver glossary edit`: opens TSV in `$EDITOR`, validates on close.
- Conflict detection across approved terms; halts `translate`.
- Tests:
  - Synthetic JP corpus produces expected candidates.
  - Approval state survives session restarts.
  - Conflicting approved terms produce a clear error.

Exit criteria:

- A real user can extract, review, approve glossary candidates on the fixture EPUB.
- Approved glossary terms appear in subsequent translation prompts.
- Conflicting glossary entries block `weaver translate` with a clear message.

## Phase 6: Markdown Export (Week 7)

Goal: `weaver export --mode markdown` produces a usable review file.

- Per-chapter Markdown files plus top-level index.
- Default: source + translation side by side (block quote / paragraph pair).
- `--translation-only` flag.
- Failed segments rendered as visible markers (`> [FAILED: ch3-seg-0091]`).
- Stale segments marked similarly.
- Heading hierarchy preserved.
- Tests for ordering and missing-segment markers.

Exit criteria:

- Exporting the fixture project produces a Markdown file that opens cleanly in any editor.
- Reviewing the Markdown is faster than reviewing the SQLite database.

## Phase 7: Manual Edit Command (Week 7, parallel)

Goal: `weaver edit <project> <segment-id>` overrides a translation.

- Opens segment in `$EDITOR`.
- On save, validates content is non-empty, marks status `manual`.
- `manual` translations are preserved across re-runs.
- Test: edited segment survives `weaver translate --retry-failed`.

Exit criteria:

- A user can manually fix a bad translation and that edit persists.

## Phase 8: EPUB Renderer (Week 8–9)

Goal: `weaver export --mode epub` produces a usable EPUB.

- Load original EPUB via `ebooklib`.
- Walk XHTML in spine order.
- For each block, locate node via `markup_context.xml_node_path`, replace text content.
- Preserve metadata, spine, asset references, internal hrefs.
- Write `.translated.epub` suffix to output directory.
- Tests:
  - Opens in Calibre.
  - Opens in Apple Books (manual smoke test, not CI).
  - Image assets preserved.
  - CSS references preserved.

Exit criteria:

- An EPUB produced by Weaver opens in at least two readers without visible structural damage.
- The user can clearly see translated text in the rendered book.

## Phase 9: QA Engine (Week 9, parallel)

Goal: `weaver validate` runs the six deterministic checks.

- Pure-function checks in `qa/checks.py`.
- Each check returns `QAWarning` with severity.
- Output: human-readable summary + JSON mode.
- Exit code 1 if any `critical` warnings present.

Exit criteria:

- Seeded warnings in test fixtures are detected.
- False positives below 5% on the fixture novel.

## Phase 10: Hardening, Docs, Release (Week 10)

Goal: release v0.1.0 to PyPI.

- README finalized with quickstart and example output.
- MkDocs docs site published to GitHub Pages.
- Five ADRs written: provider interface, IR shape, segment ID, glossary algorithm, EPUB roundtrip strategy.
- Performance baseline benchmarks recorded in `docs/benchmarks.md`.
- `weaver init` runs in under 30s on a 200-chapter fixture.
- Release notes drafted.
- Tag v0.1.0, publish to PyPI.

Exit criteria:

- A new user can install Weaver and translate a 5-chapter novel within 30 minutes.

## Technical Sequencing Notes

- Phases 1–4 are critical-path. Order matters.
- Phases 5–7 can overlap with Phase 4 if a second contributor exists.
- Phase 8 depends on Phase 1 (markup_context) and Phase 6 (output dir conventions).
- Phase 9 can run anytime after Phase 4.

## Phase 10.5: Validate Acceptance Criteria (Before Release)

Before tagging v0.1.0, explicitly verify every acceptance criterion in `PRD_v2.md §10`.

- Run through AC-1 through AC-9 on the 5-chapter fixture EPUB.
- Each criterion either passes explicitly or has a linked issue explaining why it does not block release.
- No criterion is "probably fine" — verify it hands-on.

## QA Checklist Before Release

- [ ] CI green on main.
- [ ] `pytest` coverage ≥ 70%.
- [ ] All ADRs merged.
- [ ] README quickstart manually verified on Linux, macOS, Windows.
- [ ] EPUB output opens in Calibre and one mobile reader.
- [ ] Markdown output opens cleanly in Obsidian, VS Code, and GitHub.
- [ ] `weaver --help` reads coherently to a fresh reader.
- [ ] No `# TODO` without linked issue.
- [ ] No `# FIXME` without justification.
- [ ] Performance budgets met (per `ENGINEERING_STANDARDS.md`).

## Beta Rollout Strategy

Beta is targeted, not public:

1. **Week 11.** Share with five known fan translators in MTL communities (Reddit r/LightNovels, MTL Discord servers). Direct DM, not public post.
2. **Week 12.** Incorporate critical feedback. Ship v0.1.1.
3. **Week 13.** Write a launch post on a personal blog or GitHub Discussions. Cross-post to /r/LightNovels and one or two relevant Discord servers.
4. **Week 14.** Triage incoming issues, refuse scope creep, focus on bug fixes.

Avoid:

- Product Hunt launch (wrong audience).
- Hacker News (likely to fail; product is too niche; HN crowd will critique the AI angle).
- Twitter "build in public" thread (signals startup framing, alienates target users).

## Post-Launch Priorities (First 90 Days)

- Triage bugs daily for first two weeks, then weekly.
- One feature release every 4–6 weeks.
- MVP-1 features picked from this priority order:
  1. EPUBCheck integration.
  2. `weaver new` interactive wizard.
  3. Honorific `localize` and `hybrid` modes.
  4. Better progress reporting and TUI option.
  5. Chapter summary memory.

Do not promise dates publicly. Ship when ready.

## Scaling Milestones (When To Reconsider Architecture)

These are decision triggers, not predictions:

| If this happens | Reconsider |
|-----------------|------------|
| 1,000+ active users | Telemetry opt-in, structured issue templates |
| 50+ contributors | More structured contributor docs, code owners |
| 10,000+ segment translations per user | Concurrent provider calls |
| Hosted-service request volume | Build `weaver cloud` as a separate product, do not couple to MVP |
| Multiple paid users | Consider paid-tier monetization (see `GO_TO_MARKET.md`) |

## Rewrites To Avoid

The following are forbidden until at least v0.5:

- Replacing SQLite with Postgres.
- Switching from typer to a different CLI framework.
- Introducing a plugin system.
- Adding a web server.
- Introducing async runtimes for provider calls.

Each of these has a specific cost and zero MVP-0 benefit. The temptation to refactor must be resisted.

## Resourcing Reality

This plan assumes one engineer working full-time for ~10 weeks. If part-time, multiply by 2–3. If solo and learning Python concurrently, multiply by 4.

The plan does not assume designers, marketers, or QA. If those exist, they accelerate landing pages and docs but do not change the engineering critical path.

Realistic v0.1.0 release window: 10 weeks full-time, 20 weeks half-time, 30+ weeks part-time. Anything faster is optimism. Anything slower is scope creep.
