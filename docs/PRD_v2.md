# Weaver PRD v2

Refined product requirements after Council audit. Replaces ambiguity in `PRD-dev.md` and `PRD-proc.md`. Source of truth for MVP-0 build.

## 1. Product Vision

Weaver is an offline-capable, glossary-aware translation workbench for Japanese light novels and web novels. It is a developer tool for power users in the amateur translator community, not a consumer product.

Weaver exists to make machine-assisted JP→EN novel translation reproducible, resumable, and reviewable. The product produces a translated EPUB and a Markdown review file as its two output artifacts.

Weaver does not attempt to replace human translation. It assists translators who already do machine-translation-aided work and need consistency, resumability, and structural integrity that ad-hoc ChatGPT prompting cannot give them.

## 2. Problem Statement

Amateur Japanese-to-English novel translators currently use one of three workflows:

- Direct ChatGPT/Claude prompting per paragraph. No glossary consistency, no resume safety, no structural preservation, character names drift across chapters.
- DeepL/Sugoi machine translation pipelines. Decent literal output, no honorific handling, no character voice retention, no EPUB roundtrip.
- Custom Python scripts. Fragile, abandoned within months, not shareable.

None of these handle the four hard problems of long-form novel translation:

1. **Glossary consistency.** A character's name, a skill, a place, a custom term must translate identically across thousands of segments.
2. **Resume safety.** A 200,000-character novel cannot be translated in one session. Crashes and partial runs must not corrupt prior work.
3. **Reviewability.** Translators want to inspect output before committing to it. Raw chat history is not a workflow.
4. **EPUB roundtrip.** Source is EPUB; output should be EPUB. Reconstructing EPUB by hand is painful.

Weaver addresses all four explicitly.

## 3. Ideal Customer Profile

Primary ICP, in order of priority:

1. **Amateur fan-translators** publishing on personal blogs, Scribble Hub, Royal Road, or private circles. Comfortable with CLI, Python, Git. Already use Ollama or pay for OpenAI/DeepSeek for translation. Translate one novel for love over weeks or months.
2. **MTL editors** who clean up raw machine translation output. Currently use Sugoi + manual editing. Would adopt Weaver as a structured replacement.
3. **Language learners** translating novels as study material. Want bilingual review output more than polished EPUB.

Out of scope as ICP:

- Professional commercial translators (different tooling expectations, legal posture).
- Casual readers who want one-click translation (use TranslateBros browser extensions).
- Publishers (commercial licensing concerns).

## 4. Jobs To Be Done

When I am a fan translator, I hire Weaver to:

- Convert a Japanese EPUB into a translated EPUB while preserving the structure my readers expect.
- Keep my character names, skill names, and world terms consistent across the entire novel, even when I take breaks for days or weeks.
- Let me pause translation at any time and resume without redoing work.
- Show me which segments failed or look suspicious so I can fix them before publishing.
- Let me hand-edit any translation when the LLM gets it wrong.

## 5. User Pain Points (Validated From MTL Forums)

- "ChatGPT translated 護衛 as 'escort' in chapter 3 and 'bodyguard' in chapter 7."
- "Sugoi crashed at chapter 14. I have no idea where it stopped."
- "I lost three hours of work because the browser tab closed."
- "I have to rebuild the EPUB by hand and it broke in Calibre."
- "I can see the translation is wrong but I don't know which segments to fix."
- "Reading 200 paragraphs side by side in a Google Doc is unbearable."

Weaver's success is measured against these specific complaints.

## 6. MVP Scope (MVP-0)

MVP-0 must ship the following commands and behaviors. Nothing more.

### Commands

```
weaver init <input.epub>          # create project, segment EPUB, extract glossary candidates
weaver inspect <project.toml>     # show project status
weaver glossary review <project>  # interactive approve/reject/edit
weaver glossary edit <project>    # open TSV in $EDITOR
weaver translate <project.toml>   # run translation, resumable
weaver edit <project> <segment>   # manually override a single segment
weaver export <project> --mode markdown
weaver export <project> --mode epub
weaver validate <project.toml>    # deterministic QA
```

### Provider Coverage at MVP-0

MVP-0 ships four providers:

1. `deepseek` — **default**. Cloud, cheap (~$0.01/chapter), good JP literary quality. BYO API key via `DEEPSEEK_API_KEY`.
2. `gemini` — free tier option. Gemini Flash via Google AI Studio. 15 req/min, 1M tokens/day free. BYO API key via `GEMINI_API_KEY`. Added specifically for hardware-limited users and developers who cannot run local models.
3. `ollama` — local, free, requires GPU hardware. Optional; not required to use Weaver.
4. `fake` — deterministic, zero dependencies. Primary tool for development and CI.

**Rationale for this provider order:**

Shipping Ollama-only at MVP-0 was a mistake in PRD v1. Most amateur translators — and the maintainer themselves — do not have local hardware capable of running 14B models at acceptable JP literary quality. Ollama-only gates the entire userbase to a hardware-rich minority.

`deepseek` is the recommended default because the cost for a full novel is trivially low ($2–4 USD). `gemini` is the recommended option for users who want zero-cost cloud translation. `ollama` remains available for users with adequate local hardware who prioritize privacy.

**Developer note:** A hardware-limited development environment is fully supported. `FakeProvider` handles 100% of unit and integration testing. `DeepSeek` or `Gemini` handle manual translation quality verification. `Ollama` is never required during development — OllamaProvider implementation can be tested via mocks or in CI with a hosted Ollama service container.

### Translation Quality

MVP-0 ships one mode: `balanced`. Removed from MVP-0: `careful` mode references in config. Adding a config flag for an unbuilt mode is feature theater.

Context used per segment in `balanced`:

- Current segment text.
- Previous translated segment (target language).
- Previous source segment.
- Approved glossary terms (filtered by surface form match in current segment).
- Last 5 translated segments in current chapter (rolling window).
- Honorific policy.

The PRD v1 "chapter-level context placeholder" is replaced with a concrete rolling window. No summarization at MVP-0.

### Glossary Candidate Extraction (Specified)

MVP-0 candidate extraction algorithm:

1. Tokenize source text per chapter with a JP tokenizer (fugashi + ipadic-neologd).
2. Extract proper nouns (人名, 地名, 組織名 tags), katakana sequences of length ≥ 2, and explicit honorific patterns (`Xさん`, `Xちゃん`, `X様`).
3. Compute frequency across the whole document.
4. Filter: minimum frequency 2 occurrences OR appears in chapter title.
5. Cluster surface variants (`護衛` and `護衛たち` collapse to root).
6. For each candidate, prompt the LLM provider once for an initial suggested target translation.
7. Write candidates to `glossary_candidates.tsv` with status `pending`.

This is the documented baseline. Improvements are tracked separately.

### Output

Two artifacts. In this order:

1. **Markdown review file.** Per-chapter file. Default mode shows source + translation side by side. `--translation-only` flag for cleaner reading. Failed/missing segments rendered as visible markers.
2. **Translated EPUB.** Preserves: metadata, spine order, image assets, CSS references, internal hrefs. Replaces only text node content for paragraphs that have approved translations. Does not preserve: ruby/furigana with full fidelity, complex footnotes, vertical text layout.

### QA Checks (Deterministic, MVP-0)

- Empty translation.
- Translation contains > 3 contiguous Japanese characters.
- Translation length < 30% of source length.
- Approved glossary term's source appears in segment but target does not appear in translation.
- Segment marked `failed`.
- Segment marked `stale`.

All other QA checks deferred.

## 7. Non-MVP Scope (Explicitly Deferred)

The following are removed from MVP-0 and live in `FUTURE_ROADMAP.md`:

- `weaver new` interactive wizard (MVP-1).
- Status dashboard with rich formatting (MVP-1).
- Careful mode draft + polish (MVP-1).
- TUI dashboard (MVP-1, optional).
- Honorific policy `localize` and `hybrid` (MVP-1; ship `preserve` only at MVP-0).
- Chapter summary memory (MVP-1).
- Character memory (MVP-1).
- EPUBCheck integration (MVP-1).
- Bilingual EPUB (deferred indefinitely).
- Cloud provider variety beyond DeepSeek (added on demand).
- Hosted service references (removed from product entirely).
- Prompt profiles (removed).
- Per-stage model routing (removed).
- Web novel scraper (removed).
- Indonesian target (removed from PRD; users can fork).
- Korean source (removed).
- Community glossary sharing (removed).
- Fine-tuned models (removed).
- Collaborative editing (removed).
- GUI (removed).
- PDF input (removed).

The PRD v1 listed ~40 deferred features across three phases. This is roadmap delusion. Half are deleted, half are deferred without timeline.

## 8. User Flows

### Flow A: First-time use

```
$ weaver init novel.epub
Reading novel.epub...
Detected: 18 chapters, 1,842 paragraphs
Created: ./weaver-novel/project.toml
Extracted 67 glossary candidates → ./weaver-novel/glossary_candidates.tsv

Next:
  weaver glossary review weaver-novel/project.toml
```

### Flow B: Review glossary

```
$ weaver glossary review weaver-novel/project.toml
Pending: 67  Approved: 0  Rejected: 0

[1/67]
Source: 主人公
Candidate target: protagonist
Category: role
Frequency: 412
Examples:
  - 主人公は剣を振り上げた。
  - 主人公の名はカイ。

[a]pprove [e]dit [r]eject [s]kip [u]ndo [f]ind [q]uit ?
```

### Flow C: Translate

```
$ weaver translate weaver-novel/project.toml
Provider: deepseek (deepseek-chat)
Pending: 1,842 segments

Chapter 1 [######......] 412/1024 segs
Latest: ch1-seg-0413 ok
```

### Flow D: Edit a wrong translation

```
$ weaver edit weaver-novel/project.toml ch3-seg-0091
Opening ch3-seg-0091 in $EDITOR...
[edited]
Saved. Segment marked translated.
```

### Flow E: Export

```
$ weaver export weaver-novel/project.toml --mode markdown
Wrote ./weaver-novel/output/review.md (847 KB)

$ weaver export weaver-novel/project.toml --mode epub
Wrote ./weaver-novel/output/novel.translated.epub (1.2 MB)
```

## 9. Project Configuration Schema

Full `project.toml` that `weaver init` generates. This is the authoritative schema; `core/config.py` pydantic model must match exactly.

```toml
[project]
name = "example-novel"
source_file = "../input.epub"          # relative to project dir
project_dir = ".weaver/example-novel"
database_path = ".weaver/example-novel/weaver.db"
output_dir = ".weaver/example-novel/output"
schema_version = 1                     # bumped on breaking prompt/schema changes

[languages]
source = "ja"
target = "en"

[provider]
type = "deepseek"                      # deepseek | gemini | ollama | fake
model = "deepseek-chat"                # deepseek-chat | gemini-1.5-flash | qwen3:14b | (any ollama model)
base_url = "http://localhost:11434"    # only used for ollama; ignored for cloud providers

[translation]
quality = "balanced"                   # balanced only at MVP-0
honorifics = "preserve"               # preserve only at MVP-0
context_window_segments = 5           # rolling window per chapter
timeout_seconds = 180
max_retries = 2

[glossary]
candidate_path = ".weaver/example-novel/glossary_candidates.tsv"
approved_path = ".weaver/example-novel/glossary.tsv"
require_review = true                  # false: auto-approve candidates (power user)
max_terms_per_segment = 20

[output]
default_mode = "markdown"
epub_enabled = true

[qa]
detect_untranslated_japanese = true
detect_empty_output = true
detect_glossary_mismatch = true
minimum_length_ratio = 0.3

[logging]
level = "INFO"                         # DEBUG | INFO | WARNING | ERROR
raw_responses = true                   # false: skip storing raw LLM output
log_dir = ".weaver/example-novel/logs"
```

Field constraints enforced by pydantic at config parse time:

- `provider.type` must be one of `deepseek`, `gemini`, `ollama`, `fake`.
- `translation.quality` must be `balanced` at MVP-0 (fail-fast if any other value).
- `translation.honorifics` must be `preserve` at MVP-0.
- `translation.context_window_segments` must be 1–10.
- `translation.timeout_seconds` must be 30–600.
- `translation.max_retries` must be 0–5.
- `glossary.max_terms_per_segment` must be 1–50.
- `qa.minimum_length_ratio` must be 0.1–0.9.
- All path fields resolved relative to `project_dir` at load time.

## 10. Acceptance Criteria (MVP-0)

MVP-0 is done when all of the following pass on a real 5-chapter public-domain EPUB fixture.

### AC-1: `weaver init`

- Creates `project.toml` with all fields populated correctly.
- Creates `weaver.db` with valid schema.
- Creates segment records for every paragraph and heading in the EPUB.
- Creates `glossary_candidates.tsv` with at least one candidate.
- Prints a "Next:" hint pointing to `weaver glossary review`.
- Runs in under 30 seconds on the fixture.
- Produces identical segment IDs when run twice on the same input.

### AC-2: `weaver inspect`

- Displays: project name, source file, provider/model, chapter count, segment count, glossary candidate/approved/conflict counts, output artifact status.
- Does not modify database.
- Exits cleanly in under 1 second.

### AC-3: `weaver glossary review`

- Shows one term at a time with source, candidate target, category, frequency, and example sentences.
- `[a]` saves the term as approved; status becomes `approved`.
- `[r]` saves as rejected; status becomes `rejected`.
- `[e]` opens an inline edit prompt; user can change target and notes; status becomes `edited`.
- `[s]` skips without changing status.
- `[u]` reverts the previous action.
- `[q]` exits; progress is persisted; session can be resumed.
- Approved terms appear in subsequent translation prompts.
- Unapproved (pending) terms are never injected into translation prompts.

### AC-4: `weaver translate`

- Sends each pending segment to the configured provider with correct context (glossary, rolling window, honorific policy).
- Stores every translation result in SQLite with the correct `source_hash`.
- Marks segments `translated` or `failed` correctly.
- `kill -9` mid-run followed by restart picks up correctly from the last committed segment.
- `--retry-failed` flag re-runs only failed segments.
- Unapproved glossary candidates are NOT injected into any prompt.
- Glossary conflict (same source, different targets) halts translation with exit code 6.

### AC-5: `weaver edit`

- Opens the specified segment's translation in `$EDITOR`.
- After save, stores the edited text and sets status to `manual`.
- `manual` translations survive `weaver translate --retry-failed`.
- Non-existent segment ID produces a clear error.

### AC-6: `weaver export --mode markdown`

- Generates a Markdown file per chapter plus a top-level `review.md` index.
- Default: source text and translated text shown side by side.
- `--translation-only` flag: shows only translated text.
- Segments with status `failed` or `stale` are clearly marked (`[FAILED: {segment_id}]`).
- Chapter order matches EPUB spine order.
- Output file is well-formed Markdown that renders correctly in GitHub.

### AC-7: `weaver export --mode epub`

- Generates a `.translated.epub` in the `output_dir`.
- Opens without error in Calibre.
- EPUB metadata (title, author, language, identifier) is preserved.
- Spine order is identical to the source EPUB.
- Image assets are present and intact.
- CSS asset references are preserved.
- Translated text replaces source text in all translated segments.
- Segments with no translation fall back to source text (not left blank).

### AC-8: `weaver validate`

- Detects and reports: empty translations, segments containing > 3 contiguous Japanese characters, translations below 30% length ratio, approved glossary term present in source but absent in translation, failed segments, stale segments.
- Reports severity per finding (`info` / `warning` / `critical`).
- Exits with code 0 if no criticals, code 1 if any criticals.
- Outputs a machine-readable `--json` format.

### AC-9: Error Handling

- Every CLI error follows the three-line format: what failed / likely cause / next command.
- Provider unavailable: exit code 3 with Ollama/DeepSeek-specific recovery instruction.
- EPUB unreadable: exit code 4 with file path.
- Config parse failure: exit code 7 with field name and expected type.
- No error silently swallowed.

## 11. Success Metrics (MVP-0)

Six months after public release, MVP-0 is successful if:

- 100+ GitHub stars.
- 10+ external contributors with merged PRs.
- 5+ public blog posts or YouTube videos walking through Weaver workflows.
- 3+ translators publicly publish a translated novel produced with Weaver.
- Issue tracker shows real bug reports (not just spam), indicating users beyond the author exist.

Vanity metrics avoided: download counts (npm/PyPI numbers are noisy), Discord member counts.

## 12. Retention Strategy

Open-source tool retention ≠ SaaS retention. Users return to Weaver when:

- They start translating another novel.
- Weaver shipped a feature that fixes a pain they hit (release notes matter).
- Their existing project file format still works (no breaking changes mid-translation).

Concrete commitments:

- Project file format stable from v0.1 onward. Migrations always automatic.
- Glossary TSV format stable. Editable in any text editor.
- Release cadence: one feature release every 4–8 weeks for the first year.
- Changelog written like users actually exist.

## 13. Monetization Strategy

None at MVP-0.

The PRD v1 referenced "hosted scalability" and "billing tracking". Removed. Weaver is an open-source CLI. There is no monetization plan and the product is not designed to need one.

If, after 12 months, the project has > 1,000 active users (measured by anonymous opt-in telemetry), a paid managed routing service (`weaver cloud`) could be introduced. Until then: zero monetization assumptions, zero monetization scaffolding, zero billing code.

## 14. Constraints

- Single maintainer for the foreseeable future. All architecture choices must respect this.
- Python ecosystem. Switching languages is not considered.
- No paid infrastructure required at MVP-0. The tool must run on a translator's laptop.
- Legal posture: tool-first, content-agnostic. Documentation must include a clear copyright disclaimer.

## 15. Risk Analysis

| Risk | Probability | Severity | Mitigation |
|------|-------------|----------|------------|
| Local LLM quality on JP literary text is insufficient | High | High | Ship DeepSeek provider at MVP-0 |
| Glossary extraction produces noise | High | Medium | Documented algorithm, user can bulk-reject |
| EPUB output breaks in some readers | High | Medium | Markdown export is primary fallback |
| Legal takedown from licensing concerns | Medium | High | Strong disclaimer, no upload feature, fixture corpus uses public domain |
| Maintainer burnout | High | High | MVP-0 scope is deliberately small; deferred features are not promises |
| Forking by upstream MTL community without contributing back | Medium | Low | Permissive license accepted |
| Cost spike from cloud provider abuse | Low | Medium | Cloud provider is BYO API key only; no shared key |
| Hardware-limited developer cannot test Ollama locally | Medium | Low | FakeProvider covers development; OllamaProvider tested via CI service container or external contributor |

## 16. Out of Scope (Permanent)

These will never be built in Weaver. Forks welcome.

- GUI desktop app.
- Hosted multi-user service.
- Real-time collaborative editing.
- Translation memory sharing platform.
- Paid model marketplace.
- Mobile apps.
- Browser extensions.

If the project grows enough to support these, they become separate products under a different name.
