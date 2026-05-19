# Weaver

> Offline-capable, glossary-aware JP→EN novel translation workbench.

A command-line tool for amateur fan-translators working on Japanese light novels and web novels. Weaver turns a Japanese EPUB into a translated EPUB plus a Markdown review file, with glossary consistency, resume safety, and deterministic QA across long projects.

**Status:** v0.1.0 release candidate. Full MVP-0 command set is implemented; PyPI tagging happens after the acceptance pass.

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) for environment management
- An EPUB to translate (public-domain fixture ships in `tests/fixtures/`)

## Install (development)

```bash
git clone https://github.com/Trancend1/weaver-translate.git
cd weaver-translate
uv sync --extra dev
uv run weaver --version
```

Expected:

```
weaver 0.0.1
```

Once published to PyPI, end users install with `uv tool install weaver`.

## Quickstart

This walkthrough runs end-to-end against the bundled fixture EPUB and the zero-dependency `fake` provider — no API key required, works on any machine.

```bash
mkdir scratch && cd scratch
uv run weaver init ../tests/fixtures/aozora_sample.epub
```

Output:

```
Reading ../tests/fixtures/aozora_sample.epub...
Created: scratch/.weaver/aozora_sample/project.toml
Database: scratch/.weaver/aozora_sample/weaver.db
Detected: 2 chapters, 6 segments
Extracted 2 glossary candidates -> scratch/.weaver/aozora_sample/glossary_candidates.tsv

Next:
  weaver glossary review scratch/.weaver/aozora_sample/project.toml
```

Switch the project to the `fake` provider so the rest of the walkthrough needs no API key. Open `.weaver/aozora_sample/project.toml` in any UTF-8 editor and change the `[provider]` block to:

```toml
[provider]
type = "fake"
model = "fake-1"
pattern = "[EN] {source}"
```

Then:

```bash
uv run weaver inspect .weaver/aozora_sample/project.toml
uv run weaver glossary review .weaver/aozora_sample/project.toml   # press q to skip
uv run weaver translate .weaver/aozora_sample/project.toml
uv run weaver export .weaver/aozora_sample/project.toml --mode markdown
uv run weaver export .weaver/aozora_sample/project.toml --mode epub
uv run weaver validate .weaver/aozora_sample/project.toml
```

`weaver translate` prints a summary:

```
Selected: 6
Translated: 6
Failed: 0
Pending: 0
Stale: 0
```

`weaver export --mode epub` writes the translated EPUB:

```
Wrote scratch/.weaver/aozora_sample/output/epub/aozora_sample.translated.epub
Translated blocks: 6 | Fallback blocks: 0
```

`weaver validate` flags the leftover Japanese (the `fake` provider keeps `{source}` inline, so QA correctly reports untranslated text):

```
Total: 6 | critical: 4 | warning: 0 | info: 0
```

Real translation with `deepseek` or `gemini` clears those criticals. The exit code is `1` whenever any `critical` finding exists — useful in CI.

## Providers

| Provider | When | Auth |
|---|---|---|
| `deepseek` | Default cloud, ~$2–4 per novel | `DEEPSEEK_API_KEY` |
| `gemini` | Free-tier cloud (15 req/min, 1M tokens/day) | `GEMINI_API_KEY` |
| `ollama` | Local, requires GPU hardware | none (local) |
| `fake` | Development and CI | none |

Cloud keys come from environment variables only. Weaver never reads them from `project.toml` and never ships shared keys.

## Commands

| Command | Purpose |
|---|---|
| `weaver init <input.epub>` | Create project, segment EPUB, extract glossary candidates. |
| `weaver inspect <project.toml> [--healthcheck]` | Show project status; `--healthcheck` probes the provider. |
| `weaver glossary review <project.toml>` | Interactive approve / edit / reject / skip / undo / quit. |
| `weaver glossary edit <project.toml>` | Open the glossary TSV in `$EDITOR` and resync. |
| `weaver glossary conflicts <project.toml>` | Print approved-term conflicts. |
| `weaver translate <project.toml> [--retry-failed]` | Translate pending segments; resumable. |
| `weaver edit <project.toml> <segment-id>` | Override one translation through `$EDITOR`. |
| `weaver export <project.toml> --mode markdown [--translation-only]` | Per-chapter Markdown review file. |
| `weaver export <project.toml> --mode epub` | Translated EPUB (`.translated.epub`). |
| `weaver validate <project.toml> [--json]` | Run the six deterministic QA checks; exit `1` on any `critical`. |

## Project Layout

```
.weaver/<name>/
├── project.toml            # configuration
├── weaver.db               # SQLite WAL, source of truth for run state
├── glossary_candidates.tsv # pending review
├── glossary.tsv            # approved terms
├── logs/                   # weaver-YYYY-MM-DD.log (rotated daily)
└── output/
    ├── markdown/review.md
    ├── markdown/chapter-001.md
    └── epub/<source>.translated.epub
```

## Exit Codes

`weaver validate` exits `1` when any `critical` finding is present. Other exit codes (per [PRD_v2.md](docs/PRD_v2.md) §10 AC-9):

| Code | Meaning |
|---|---|
| `0` | Success. |
| `1` | Generic failure / critical QA finding. |
| `3` | Provider unavailable (network unreachable, API key invalid, Ollama not running). |
| `4` | EPUB unreadable or unwritable. |
| `5` | Segment id not found (`weaver edit`). |
| `6` | Glossary conflict (`weaver translate` halts). |
| `7` | Config parse failure (malformed or missing required `[project]`/`[provider]`/`[translation]` table). |

## Windows Footguns

- `weaver edit` and `weaver glossary edit` require the `EDITOR` environment variable. Examples: `set EDITOR=notepad` (cmd), `$env:EDITOR = "notepad"` (PowerShell). VS Code: `code -w`.
- PowerShell's `Set-Content -Encoding utf8` writes a UTF-8 BOM that breaks `tomllib`. Use Notepad, VS Code, or `[System.IO.File]::WriteAllText($path, $text, [System.Text.UTF8Encoding]::new($false))` instead. `weaver validate` exits `7` with a clear message if a BOM is detected.
- Windows legacy console codepage CP1252 cannot render Japanese; non-ASCII characters render as `?` in `weaver inspect` and `weaver validate` tables. Underlying files (Markdown, EPUB, JSON) keep UTF-8 fidelity. Switch to Windows Terminal or use `chcp 65001` for proper rendering.

## Glossary Tokenizer Setup

Glossary candidate extraction runs without external tokenizer setup by falling back to deterministic regex. For higher-quality Japanese proper-noun extraction, install MeCab before installing the optional `fugashi` package:

- Linux: install MeCab via your package manager, then `pip install fugashi`.
- macOS: `brew install mecab mecab-ipadic`, then `pip install fugashi`.
- Windows: install a prebuilt MeCab binary, add its `bin` directory to `PATH`, restart the shell, then `pip install fugashi`.

If MeCab is unavailable, `weaver init` still creates `glossary_candidates.tsv`; the candidate list is lower quality but reviewable.

## Development

```bash
uv run pytest -m "not requires_ollama and not requires_cloud"
uv run ruff check .
uv run ruff format --check .
uv run pyright
```

CI runs the same four checks on every push and pull request. Tests marked `requires_ollama` or `requires_cloud` are skipped in CI; run them manually with appropriate environment.

## Documentation

Authoritative specs live in [docs/](docs/):

- [PRD_v2.md](docs/PRD_v2.md) — product requirements and MVP-0 scope.
- [SYSTEM_ARCHITECTURE.md](docs/SYSTEM_ARCHITECTURE.md) — module layout, IR, SQLite schema, provider interface.
- [BLUEPRINT_EXECUTION_PLAN.md](docs/BLUEPRINT_EXECUTION_PLAN.md) — 10-phase build order.
- [ENGINEERING_STANDARDS.md](docs/ENGINEERING_STANDARDS.md) — coding rules.
- [AI_SLOP_PREVENTION.md](docs/AI_SLOP_PREVENTION.md) — feature gates and anti-patterns.
- [PROMPT_DESIGN.md](docs/PROMPT_DESIGN.md) — prompt templates.

## Copyright Notice

Weaver is a tool. It does not ship copyrighted source material, and the project takes no position on the legality of translating material the user does not have rights to. Users are responsible for the copyright status of any EPUB they feed into the tool.

## License

[MIT](LICENSE). Copyright (c) 2026 Farhan Alamsyah.
