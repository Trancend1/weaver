# Weaver System Architecture

Production architecture for MVP-0. Optimized for a local CLI tool maintained by one engineer. Not optimized for hypothetical hosted scale.

## Design Principles

1. **Local-first, no network required.** Network is opt-in via cloud provider.
2. **SQLite is the source of truth for run state.** No external state services.
3. **Intermediate Representation decouples source format from translation logic.** EPUB readers swap out; translator does not care.
4. **Synchronous-by-default execution.** No asyncio, no queues, no workers at MVP-0. (Post-MVP **Phase 12** adds a single background **thread** for the web cockpit's translate job — still no asyncio, no queue/worker framework. See [feature_plan/web-architecture.md](feature_plan/web-architecture.md).)
5. **Pluggable providers behind a single interface.** Cloud providers added without touching orchestrator.
6. **Plain text formats wherever possible.** TSV for glossary, TOML for config, Markdown for review.

## Tech Stack

| Layer | Choice | Reason |
|-------|--------|--------|
| Language | Python 3.11+ | Mature EPUB/JP ecosystem, single-maintainer-friendly |
| Package manager | uv (with pyproject.toml) | Fast, reproducible installs |
| Config | tomllib + pydantic v2 | stdlib parse, pydantic validation |
| Database | SQLite (WAL) | Single-file, embedded, transactional |
| DB access | sqlite3 stdlib + lightweight query helpers | No ORM; raw SQL is reviewable |
| EPUB | ebooklib | Most maintained option for EPUB 2/3 |
| JP tokenization | fugashi + ipadic-neologd | De facto standard for JP NER; degrades to regex fallback if MeCab unavailable |
| LLM SDK | openai + google-generativeai | DeepSeek uses OpenAI-compat; Gemini uses native SDK |
| CLI | typer | Pleasant ergonomics, generates --help |
| Terminal output | rich | Progress bars, color, tables |
| Testing | pytest | Standard. No pytest-asyncio — codebase is synchronous (no asyncio). |
| Lint/format | ruff | Single tool replaces flake8 + isort + black |
| Type check | pyright (basic mode) | Faster than mypy, good enough |

Explicitly rejected (MVP-0):

- Django, Flask, FastAPI — no web server in MVP. **Update:** post-MVP **Phase 12** reopens **Flask (sync only)** for a local web cockpit via ADR `0016`. Django, FastAPI, and asyncio stay rejected. See [feature_plan/web-architecture.md](feature_plan/web-architecture.md).
- SQLAlchemy ORM — query patterns are simple; raw SQL is clearer.
- Celery, RQ, Dramatiq — no background workers in MVP.
- Docker — CLI installs via pip/uv; containers add friction.
- Sentry, OpenTelemetry — local tool, file logs are sufficient.

## High-Level Architecture

```
┌───────────────────────────────────────────────────────────────┐
│  CLI (typer)                                                   │
│  weaver init | translate | export | validate | glossary | edit │
└───────────────┬───────────────────────────────────────────────┘
                │
┌───────────────▼───────────────┐
│  Application Services Layer    │
│  - ProjectService              │
│  - GlossaryService             │
│  - TranslationService          │
│  - ExportService               │
│  - QAService                   │
└───────────────┬───────────────┘
                │
   ┌────────────┼────────────┬─────────────┬──────────────┐
   ▼            ▼            ▼             ▼              ▼
┌────────┐  ┌────────┐  ┌──────────┐  ┌─────────┐  ┌───────────┐
│ Source │  │  IR    │  │ Provider │  │  State  │  │ Renderer  │
│ Reader │→ │ Layer  │  │ Adapters │  │  Store  │  │           │
└────────┘  └────────┘  └──────────┘  └─────────┘  └───────────┘
   │            │            │             │              │
   ▼            ▼            ▼             ▼              ▼
 EPUB        Document     Ollama         SQLite        Markdown
 reader        IR         DeepSeek       (WAL)         + EPUB
              Chapter     Fake
              IR
              Block IR
```

## Module Boundaries

```
src/weaver/
├── cli/                   # typer commands; thin glue
│   ├── init.py
│   ├── translate.py
│   ├── export.py
│   ├── validate.py
│   ├── glossary.py
│   └── edit.py
├── services/              # application orchestration
│   ├── project.py
│   ├── glossary.py
│   ├── translation.py
│   ├── export.py
│   └── qa.py
├── core/                  # domain types, IR, value objects
│   ├── ir.py              # DocumentIR, ChapterIR, BlockIR
│   ├── segment.py         # segment_id, source_hash logic
│   ├── glossary.py        # term types, conflict detection
│   └── config.py          # pydantic schemas for project.toml
├── providers/             # LLM adapters
│   ├── base.py            # LLMProvider ABC
│   ├── ollama.py
│   ├── deepseek.py
│   ├── fake.py
│   └── parser.py          # JSON output parser + repair
├── readers/               # source format readers
│   └── epub.py
├── segmenter/             # block extraction from IR
│   └── paragraph.py
├── extraction/            # glossary candidate extraction
│   ├── tokenize.py
│   ├── candidates.py
│   └── clustering.py
├── storage/               # SQLite layer
│   ├── schema.sql
│   ├── migrations/
│   ├── db.py              # connection, WAL, transactions
│   ├── projects.py
│   ├── segments.py
│   ├── translations.py
│   └── glossary.py
├── qa/                    # deterministic checks
│   └── checks.py
├── renderers/             # output
│   ├── markdown.py
│   └── epub.py
└── logging.py             # stdlib logging config
```

CLI knows about services. Services know about core, storage, providers, renderers. Core has no internal dependencies. Storage has no service dependencies. No circular imports allowed; CI lint enforces this.

## Module Structure (Complete)

```
src/weaver/
├── errors.py              # exception hierarchy; no dependencies on other weaver modules
├── cli/
│   ├── init.py
│   ├── translate.py
│   ├── export.py
│   ├── validate.py
│   ├── glossary.py
│   └── edit.py
├── services/
│   ├── project.py
│   ├── glossary.py
│   ├── translation.py
│   ├── export.py
│   └── qa.py
├── core/
│   ├── ir.py
│   ├── segment.py
│   ├── glossary.py
│   └── config.py
├── providers/
│   ├── base.py
│   ├── deepseek.py
│   ├── gemini.py
│   ├── ollama.py
│   ├── fake.py
│   ├── parser.py
│   └── templates/        # Jinja2 prompt templates
│       ├── balanced_system.txt
│       ├── balanced_user.jinja2
│       ├── repair.txt
│       ├── glossary_suggestion_system.txt
│       └── glossary_suggestion_user.jinja2
├── readers/
│   └── epub.py
├── segmenter/
│   └── paragraph.py
├── extraction/
│   ├── tokenize.py
│   ├── candidates.py
│   └── clustering.py
├── storage/
│   ├── schema.sql
│   ├── migrations/
│   ├── db.py
│   ├── projects.py
│   ├── segments.py
│   ├── translations.py
│   └── glossary.py
├── qa/
│   └── checks.py
├── renderers/
│   ├── markdown.py
│   └── epub.py
└── logging.py
```

`errors.py` is explicitly separate from all domain modules so every module can import it without creating circular dependencies. The exception hierarchy defined there:

```python
class WeaverError(Exception): ...
class ConfigError(WeaverError): ...
class EpubReadError(WeaverError): ...
class EpubWriteError(WeaverError): ...
class ProviderError(WeaverError):
    retryable: bool = False
class ProviderTimeout(ProviderError):
    retryable: bool = True
class ProviderUnavailable(ProviderError):
    retryable: bool = False
class ProviderResponseError(ProviderError):
    retryable: bool = True
class GlossaryConflictError(WeaverError): ...
class ParserError(WeaverError): ...
class SegmentNotFoundError(WeaverError): ...
class DatabaseError(WeaverError): ...
```

## Intermediate Representation

Source readers emit `DocumentIR`. Translation services only operate on IR. Renderers consume IR + translation store.

```python
@dataclass(frozen=True)
class DocumentIR:
    metadata: DocumentMetadata
    assets: list[AssetIR]
    chapters: list[ChapterIR]

@dataclass(frozen=True)
class ChapterIR:
    id: str
    title: str
    href: str
    order: int
    blocks: list[BlockIR]

@dataclass(frozen=True)
class BlockIR:
    id: str
    chapter_id: str
    order: int
    kind: Literal["paragraph", "heading", "quote", "other"]
    source_text: str
    normalized_source_text: str
    markup_context: dict  # opaque, reader-specific; renderer only writes back
```

`markup_context` is reader-specific. EPUB reader stores `xml_node_path` and `attrs`. EPUB renderer uses these to surgically replace text nodes. Translator never reads `markup_context`.

## Complete Type Definitions

All types defined here are the authoritative spec. Implementation must match.

```python
# core/ir.py

@dataclass(frozen=True)
class DocumentMetadata:
    title: str
    author: str | None
    language: str           # source language tag, e.g. "ja"
    identifier: str | None  # EPUB unique identifier
    publisher: str | None
    description: str | None

@dataclass(frozen=True)
class AssetIR:
    href: str               # internal EPUB href (relative to EPUB root)
    media_type: str         # MIME type, e.g. "image/jpeg", "text/css"
    content: bytes          # raw asset bytes; carried through to renderer

@dataclass(frozen=True)
class BlockIR:
    id: str                 # segment_id (see Segment Identity section)
    chapter_id: str
    order: int              # 0-indexed position within chapter
    kind: Literal["paragraph", "heading", "quote", "other"]
    source_text: str        # original text, UTF-8
    normalized_source_text: str  # NFKC-normalized, half/full-width corrected
    markup_context: EpubMarkupContext  # see below

@dataclass(frozen=True)
class ChapterIR:
    id: str                 # blake2b of (book_identifier + spine_href), 8 hex chars
    title: str | None
    href: str               # EPUB spine href, e.g. "text/chapter01.xhtml"
    order: int              # 0-indexed spine position
    blocks: list[BlockIR]

@dataclass(frozen=True)
class DocumentIR:
    metadata: DocumentMetadata
    assets: list[AssetIR]
    chapters: list[ChapterIR]
```

```python
# readers/epub.py

@dataclass(frozen=True)
class EpubMarkupContext:
    """EPUB-specific location data so the renderer can write back."""
    file_href: str          # XHTML file within the EPUB, e.g. "text/chapter01.xhtml"
    xpath: str              # XPath to the element containing the text node
                            # Example: "/html/body/div[2]/p[4]"
                            # Always absolute from document root.
                            # Only standard XPath axes used; no predicates beyond [N].
    tag: str                # Local tag name, e.g. "p", "h1", "blockquote"
    attrs: dict[str, str]   # Original element attributes preserved verbatim
    text_node_index: int    # Which text node within the element (0 for sole text, 1+ for mixed content)
```

```python
# providers/base.py

@dataclass
class GlossaryTerm:
    source: str
    target: str
    category: str | None
    notes: str | None
    case_sensitive: bool = False

@dataclass
class TranslationContext:
    """Context injected alongside source text for each translation call."""
    previous_segments: list[tuple[str, str]]  # [(source, translation), ...], oldest first, max 5
    glossary_terms: list[GlossaryTerm]        # pre-filtered: only terms matching current segment
    honorific_policy: str                     # "preserve" | "localize" | "hybrid"

@dataclass
class TranslationRequest:
    segment_id: str
    source_text: str
    normalized_source_text: str
    source_language: str    # "ja"
    target_language: str    # "en"
    context: TranslationContext
    provider_model: str     # e.g. "qwen3:14b", "deepseek-chat"

@dataclass
class TranslationResponse:
    translation: str
    notes: list[str]
    uncertain_terms: list[str]
    raw_response: str       # stored for debug; not shown in output
    input_tokens: int | None    # None if provider doesn't report
    output_tokens: int | None

@dataclass
class ProviderStatus:
    healthy: bool
    provider_name: str
    model: str
    message: str | None     # human-readable error if not healthy
    latency_ms: int | None  # ping latency, None if unavailable
```

## Segment Identity

```python
segment_id = blake2b(chapter_href + dom_path + paragraph_index, digest_size=8).hexdigest()
source_hash = sha256(normalized_source_text).hexdigest()
```

`blake2b` over `sha256` for segment_id: shorter, fast, collision-resistant enough at this scale.

Stale rule: if `segment_id` exists and `source_hash` differs from stored value, segment marked `stale`, previous translation invalidated. Translator must re-run.

## State Store (SQLite)

Single-file `weaver.db` per project. WAL mode enabled at first connection.

Schema (abridged):

```sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE projects (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  source_path TEXT NOT NULL,
  source_lang TEXT NOT NULL,
  target_lang TEXT NOT NULL,
  created_at TEXT NOT NULL,
  schema_version INTEGER NOT NULL
);

CREATE TABLE chapters (
  id TEXT PRIMARY KEY,
  project_id INTEGER REFERENCES projects(id),
  title TEXT,
  href TEXT,
  spine_order INTEGER NOT NULL
);

CREATE TABLE segments (
  id TEXT PRIMARY KEY,
  chapter_id TEXT REFERENCES chapters(id),
  block_order INTEGER NOT NULL,
  kind TEXT NOT NULL,
  source_text TEXT NOT NULL,
  source_hash TEXT NOT NULL,
  status TEXT NOT NULL  -- pending|in_progress|translated|failed|stale|skipped|manual
);

CREATE TABLE translations (
  segment_id TEXT REFERENCES segments(id),
  attempt INTEGER NOT NULL,
  text TEXT NOT NULL,
  source_hash TEXT NOT NULL,
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  created_at TEXT NOT NULL,
  raw_response TEXT,  -- nullable; user-disableable
  PRIMARY KEY (segment_id, attempt)
);

CREATE INDEX idx_segments_status ON segments(status);
CREATE INDEX idx_segments_chapter ON segments(chapter_id, block_order);

CREATE TABLE glossary_candidates (
  id INTEGER PRIMARY KEY,
  project_id INTEGER REFERENCES projects(id),
  source TEXT NOT NULL,
  target TEXT,
  category TEXT,
  notes TEXT,
  status TEXT NOT NULL,  -- pending|approved|rejected|edited
  frequency INTEGER NOT NULL
);

CREATE TABLE glossary_terms (
  id INTEGER PRIMARY KEY,
  project_id INTEGER REFERENCES projects(id),
  source TEXT NOT NULL,
  target TEXT NOT NULL,
  category TEXT,
  notes TEXT,
  case_sensitive INTEGER NOT NULL DEFAULT 0,
  UNIQUE(project_id, source)
);

CREATE TABLE qa_warnings (
  id INTEGER PRIMARY KEY,
  segment_id TEXT REFERENCES segments(id),
  check_name TEXT NOT NULL,
  severity TEXT NOT NULL,  -- info|warning|critical
  message TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE job_events (
  id INTEGER PRIMARY KEY,
  project_id INTEGER REFERENCES projects(id),
  event TEXT NOT NULL,
  data_json TEXT,
  created_at TEXT NOT NULL
);
```

Transaction rules:

- Each segment translation = one `BEGIN ... COMMIT`. Failure between LLM call and commit = no DB write; segment remains `pending` on next run.
- On startup, any segment in `in_progress` is reset to `pending`. PRD v1 specified this; preserved here.
- Schema migrations versioned via `schema_version` column. Migration runs at every startup if version < current.

Performance target: SQLite must remain responsive at 10,000 segments. WAL mode plus indexes above achieve this trivially. No optimization beyond standard PRAGMA + indexes needed.

## Provider Interface

```python
class LLMProvider(ABC):
    name: str

    @abstractmethod
    def translate(self, req: TranslationRequest) -> TranslationResponse: ...

    @abstractmethod
    def healthcheck(self) -> ProviderStatus: ...
```

Providers shipped at MVP-0:

- `DeepSeekProvider`: OpenAI-compatible `/v1/chat/completions` endpoint. Model `deepseek-chat`. API key via env var `DEEPSEEK_API_KEY`. **Default provider.**
- `GeminiProvider`: Google Gemini Flash via `google-generativeai` SDK. Model `gemini-1.5-flash`. Free tier: 15 req/min, 1M tokens/day. API key via env var `GEMINI_API_KEY`. Recommended for hardware-limited users.
- `OllamaProvider`: HTTP POST to `http://localhost:11434/api/generate`. Requires local GPU hardware. Optional.
- `FakeProvider`: deterministic, zero dependencies, used in development and CI. Returns `[FAKE-TRANSLATED] {source}` by default; configurable response pattern and fail rate.

Cloud providers always require explicit user-supplied API key. Weaver never ships with shared keys.

**Development strategy for hardware-limited environments:**
`FakeProvider` handles all automated testing. Manual quality verification uses `DeepSeek` or `Gemini`. `OllamaProvider` can be tested in CI via a hosted Ollama service container (`services: ollama:` in the GitHub Actions job) or delegated to a contributor with adequate hardware. Local Ollama installation is never required for development.

## Translation Orchestrator

Single-threaded execution. Loop:

```
for segment in pending_segments_in_spine_order(project):
    mark in_progress
    ctx = build_context(segment)  # prev segment + glossary + rolling chapter window
    try:
        resp = provider.translate(TranslationRequest(segment, ctx))
        parsed = parse_json_or_repair(resp)
        insert translation, mark translated, commit
    except ProviderError as e:
        log + mark failed, commit
        if e.retryable: enqueue retry
```

No concurrency at MVP-0. Adding concurrency later requires:

- Per-segment isolation (already true via PK).
- Provider rate limit awareness (deferred until added).
- Progress bar refactor.

This deferral is intentional; concurrency adds debugging cost and is not on the critical path.

## QA Engine

Pure functions over `(Segment, Translation, GlossaryTerm[])`. No I/O. Returns `list[QAWarning]`. Renderer consumes warnings to mark issues in Markdown output and exit codes.

## Renderer

Markdown renderer iterates `DocumentIR` + queries translation store. Outputs per-chapter `.md` files plus a top-level `review.md` index.

EPUB renderer:

- Loads original EPUB via ebooklib.
- Walks XHTML files in spine order.
- For each block in `BlockIR.markup_context.xml_node_path`, locates node, replaces text content with translated text.
- Preserves attributes, sibling nodes, image references.
- Writes new EPUB with `.translated.epub` suffix.
- Does not modify metadata language tag (deferred decision; configurable in `project.toml`).

## CI/CD

Targets one workflow file in `.github/workflows/ci.yml`:

```yaml
- ruff check
- ruff format --check
- pyright
- pytest -m "not requires_ollama and not requires_cloud"
```

Releases manually triggered. PyPI publish via `uv publish`. No automated semver bumping until v0.2.

## Infrastructure

None required at MVP-0.

- Distribution: PyPI.
- Source: GitHub.
- Issue tracker: GitHub Issues.
- Documentation: GitHub Pages (static, MkDocs).

No servers, no databases, no queues, no monitoring services.

## Cost Model

MVP-0 has no recurring infrastructure cost.

User-side cost per provider:

| Provider | Cost | Notes |
|----------|------|-------|
| FakeProvider | Free | Development and CI only |
| Gemini Flash | Free (up to 1M tokens/day) | Google AI Studio free tier; sufficient for most novel projects |
| DeepSeek | ~$2–4 per 200k-char novel | $0.14/1M input + $0.28/1M output; paid but cheap |
| Ollama | Free | Requires local GPU hardware; not required for development |

Recommended path for hardware-limited users: start with Gemini (free), switch to DeepSeek if rate limits become an issue (typically not a problem for serial translation).

Weaver tracks token usage per provider call and surfaces cumulative cost estimate via `weaver inspect`.

## Failure Modes And Handling

| Failure | Detection | Recovery |
|---------|-----------|----------|
| Provider unavailable | healthcheck before run | Exit code 3, clear error message |
| Network timeout mid-translation | provider raises | Segment marked failed, run continues, retried via `weaver translate --retry-failed` |
| Power loss during run | startup scan for `in_progress` | Reset to pending, resume |
| Invalid JSON from provider | parser raises | Single repair retry, then mark failed |
| SQLite corruption | rare; WAL helps | Backup file `.weaver/*/weaver.db.backup.{iso8601}` written before destructive operations |
| EPUB has malformed XHTML | reader catches | Skip block, log warning |
| Out of disk space mid-export | OSError | Existing artifacts left untouched; partial output cleaned up |

## Why This Is Not Overengineered

Things deliberately not built:

- No event bus. Direct function calls between services.
- No plugin loader for providers; new providers are imported in `providers/__init__.py`.
- No internal HTTP API. Services are Python objects.
- No queue. No worker pool.
- No multi-tenancy. One project per directory.
- No user accounts.
- No PostgreSQL migration path coded.
- No abstraction layer over EPUB beyond what IR requires.

These are deferred because they have no MVP-0 user.

## Things That Will Be Painful Later (Acknowledged)

- Migrating from SQLite to a multi-user store will require a real schema migration and ownership model. This is fine because it will only happen if the project pivots to hosted; that is not the plan.
- Adding cloud providers with rate limits will eventually require backoff logic in the orchestrator.
- Supporting multiple source formats (PDF, web novel HTML) will require richer reader abstractions. The IR is ready; the reader contract may need to evolve.

These are accepted future costs, not present problems.
