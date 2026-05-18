# Weaver Engineering Standards

Operating rules for contributors. Designed to prevent the codebase from devolving into AI-generated sludge.

## Audience

Anyone modifying Weaver code, including the original author six months from now.

## Language And Tooling

- Python 3.11 minimum. Type hints required on all public functions.
- `uv` for environment and dependency management. `pyproject.toml` is canonical.
- `ruff` for linting and formatting. Configuration in `pyproject.toml`.
- `pyright` in `basic` mode for type checking.
- `pytest` for tests. Markers: `requires_ollama`, `requires_cloud`, `slow`.

CI must pass before merge. No exceptions for "small fixes".

## Folder Structure

```
src/weaver/{cli,services,core,providers,readers,segmenter,extraction,storage,qa,renderers}/
tests/{unit,integration,fixtures}/
docs/
.github/workflows/ci.yml
pyproject.toml
README.md
```

Rules:

- One concept per file. If a file exceeds 400 lines or 5 public functions, split it.
- Test files mirror source tree: `tests/unit/core/test_segment.py` corresponds to `src/weaver/core/segment.py`.
- No `utils.py` files. If something lives in utils, it belongs in a properly named module.
- No `helpers.py` files. Same reason.
- No `manager.py` files. Same reason.

## Naming Conventions

| Construct | Convention | Example |
|-----------|------------|---------|
| Module | lowercase, no underscores if possible | `segment.py`, `glossary.py` |
| Class | PascalCase | `TranslationService` |
| Function | snake_case | `extract_candidates` |
| Constant | SCREAMING_SNAKE_CASE | `DEFAULT_TIMEOUT` |
| Private | leading underscore | `_normalize_text` |
| Type alias | PascalCase | `SegmentId` |
| Test | `test_<unit>_<scenario>` | `test_segment_id_stable_across_runs` |

Avoid:

- Hungarian-style prefixes (`strName`, `lstSegments`).
- Abbreviations that aren't industry-standard (`trnsl`, `cfg`).
- Class names ending in `Manager`, `Helper`, `Handler` unless they really are that pattern (rare).

## Function And Class Standards

- Public functions: type-hint every parameter and return.
- Private helpers: type hints encouraged, not enforced.
- Functions longer than 50 lines or with more than 4 parameters require justification in code review.
- Classes should be `@dataclass(frozen=True)` when modeling values. Mutability only when state machines require it.
- Avoid `**kwargs` in public APIs. Be explicit.

## Error Handling

- Define a project exception hierarchy in `src/weaver/errors.py`:

```python
class WeaverError(Exception): ...
class ConfigError(WeaverError): ...
class ProviderError(WeaverError): ...
class ProviderTimeout(ProviderError): ...
class ProviderUnavailable(ProviderError): ...
class GlossaryConflictError(WeaverError): ...
class ParserError(WeaverError): ...
```

- Catch broad `Exception` only at CLI boundaries. Anywhere else, catch specific subclasses.
- Never use `except: pass`. Never use `except Exception: pass`.
- Errors that exit the process must use the exit code table in PRD v2.
- Errors shown to users must include: what failed, likely cause, next command.

Bad:

```python
try:
    translate(seg)
except Exception:
    pass
```

Good:

```python
try:
    response = provider.translate(req)
except ProviderTimeout as e:
    logger.warning("segment %s timed out: %s", seg.id, e)
    mark_failed(seg, reason="timeout")
```

## Logging

- Use stdlib `logging`. Get a module-level logger: `logger = logging.getLogger(__name__)`.
- Levels:
  - `DEBUG` for raw LLM I/O.
  - `INFO` for run progress, key state changes.
  - `WARNING` for recoverable problems.
  - `ERROR` for failures that affect output.
- Log files: `.weaver/<project>/logs/weaver-{date}.log`. Rotated daily.
- Raw LLM responses logged at DEBUG only. User can disable raw logging via `[logging] raw_responses = false`.
- Never log API keys. CI grep test enforces this.

## State Management

- All state changes go through service-layer functions. CLI never writes to SQLite directly.
- Every state mutation is wrapped in a single transaction.
- Reads can bypass services for read-only display logic, but writes never can.

## Provider Implementation Rules

- Every provider implements `LLMProvider`.
- Every provider has a paired test fixture and at least one unit test.
- New providers must be registered in `providers/__init__.py` and listed in CLI help text.
- API keys come from environment variables, never from config files. The convention is `<PROVIDER>_API_KEY`.
- Timeouts and retries are provider-configurable but default to the values in `project.toml` `[translation]`.

## Testing Expectations

- Every public service function must have at least one unit test.
- The translation orchestrator must have integration tests using `FakeProvider`.
- Glossary candidate extraction must have unit tests with a small synthetic Japanese corpus.
- EPUB reader and renderer must have integration tests using a fixture EPUB committed to `tests/fixtures/`.
- Fixtures use public domain text (e.g., Aozora Bunko excerpts). Never commit copyrighted novel content.
- Coverage target: 70% line coverage. Not 100%. Don't chase coverage; chase meaningful tests.
- Tests run in CI with `pytest -m "not requires_ollama and not requires_cloud"`.

Test file structure:

```python
def test_segment_id_is_deterministic_across_runs():
    block = BlockIR(...)
    assert compute_segment_id(block) == compute_segment_id(block)

def test_segment_id_changes_when_dom_path_changes():
    a = BlockIR(...)
    b = BlockIR(..., markup_context={"xml_node_path": "different"})
    assert compute_segment_id(a) != compute_segment_id(b)
```

## Git Workflow

- Branches: `feat/<short-name>`, `fix/<short-name>`, `docs/<short-name>`, `chore/<short-name>`.
- Commit messages follow Conventional Commits: `feat(translate): add retry-failed flag`.
- Squash merges into main. No merge commits.
- Force push prohibited on `main`.

## Pull Request Rules

- One PR = one concern. Refactors and feature work do not mix.
- PR description includes: problem, approach, tradeoffs, test plan.
- PRs above 500 lines net change require split or strong justification.
- All PRs require CI green and one reviewer approval. Solo-maintainer override is allowed for trivial PRs (typos, docs).

## Performance Budgets

- `weaver init` on a 200-chapter EPUB: < 30 seconds total, including glossary extraction.
- `weaver translate` resume startup with 10,000 segments: < 5 seconds before first new translation.
- `weaver export markdown` on 10,000 segments: < 10 seconds.
- `weaver export epub` on 10,000 segments: < 30 seconds.
- Memory peak: < 1 GB for any 10,000-segment project.

Regressions exceeding 20% on any benchmark require explicit explanation in the PR.

## Security Checklist

For any PR that touches I/O or external systems, verify:

- Input parsed via pydantic schemas, not raw `tomllib.loads().get()` chains.
- No API keys logged.
- No user-controlled string passed to `os.system`, `subprocess.shell=True`, `eval`, `exec`.
- File paths joined via `pathlib.Path`, not string concatenation.
- File writes use atomic patterns (`tempfile` + `replace`) when overwriting valuable state.
- Cloud provider HTTPS only.
- Glossary TSV parser handles malformed input without crashing.

## Documentation Standards

- Every public service function has a docstring with: one-line summary, args, returns, raises.
- README has a working "five-minute quickstart" section that is tested in CI (`pytest tests/integration/test_readme.py`).
- New CLI commands require: `--help` text, README section, example output.
- Changelog updated in every release PR.

## Feature Flags

Not used at MVP-0. The product is small enough to release behind tagged releases. Avoid feature flags until they are demonstrably needed.

## Technical Debt Prevention

- Every TODO has an associated GitHub issue. No anonymous TODOs.
- Every `# HACK` or `# FIXME` requires a comment explaining the cleanup plan.
- Quarterly review of TODOs. Decide: do, defer, delete.
- Dead code deleted on sight. Git history is the archive.

Patterns explicitly forbidden:

- Stub functions left in place "for future use".
- Commented-out code blocks. Delete or commit.
- "Smart" abstractions with one caller. Inline first; abstract on the third use.
- Mocking your own code in tests. Mock external boundaries (LLM providers, filesystem-when-necessary) only.
- Adding a config option to defer a decision. Make the decision.

## Code Review Heuristics

When reviewing a PR, ask:

1. Does this change solve a real, current problem?
2. Is the simplest version of the change in the PR, or has scope crept?
3. Are the new boundaries well-defined?
4. What will this look like in two years?
5. If we removed this code today, what would break?

Approve when the answers are clean. Request changes when they aren't.

## Documentation Of Decisions

Major decisions are recorded in `docs/decisions/<NNNN>-<short-title>.md` (ADR-style). One-page maximum. Format:

```
# NNNN: <Title>

Date: YYYY-MM-DD
Status: accepted | superseded by NNNN

## Context
What problem are we deciding about?

## Decision
What did we decide?

## Consequences
What does this make easier? Harder?
```

ADRs are not retrospective documentation; they capture decisions when made.

## Anti-Patterns (Caught And Rejected In Review)

- Inheritance hierarchies more than two levels deep.
- "Service" classes with only one method that should be a function.
- Premature interface extraction (`AbstractGlossaryRepositoryProtocolInterface`).
- Catch-all `try/except: log.error(e)` with continuation.
- `if/elif/elif/elif` chains over types instead of polymorphism.
- Magic strings instead of enums or constants.
- Circular imports "solved" with deferred imports inside functions.
- Adding a new top-level config section for a feature that ships off-by-default.

## Onboarding Checklist For New Contributors

1. Clone repo, run `uv sync`.
2. Run `pytest -m "not requires_ollama and not requires_cloud"` — must pass.
3. Read `PRD_v2.md`, `SYSTEM_ARCHITECTURE.md`, this file.
4. Run `weaver init tests/fixtures/sample.epub` against the bundled fixture.
5. Read three ADRs in `docs/decisions/`.
6. First PR should be docs, fixture data, or a small fix. Architecture changes after at least one merged PR.
