# Weaver

> Offline-capable, glossary-aware JP→EN novel translation workbench for fan-translators.

Weaver is a local CLI that turns a Japanese EPUB into a translated EPUB and a Markdown review file. It manages glossary consistency, resumable translation runs, and deterministic QA — no GUI, no accounts, no telemetry.

**Status:** v0.6.0 alpha · single maintainer · MIT license

---

## Features

- **Resumable translation** — stop and restart without losing progress
- **Glossary workflow** — extract candidates, review interactively, inject approved terms into every prompt
- **Four providers** — DeepSeek, Gemini, Ollama (local), and a zero-dependency `fake` provider for CI
- **Deterministic QA** — six checks with JSON output and stable schema versioning
- **Manual edit** — override any segment through `$EDITOR`; manual status survives reruns
- **Project templates** — preset `[glossary]`/`[qa]` knobs for light novel, web novel, and classic literature
- **Global config** — `~/.weaver/config.toml` with env-var overrides; no repeated flags
- **Preview** — display source + translation pairs inline without opening an EPUB viewer
- **Sampled translate** — `--first-N` for fast provider/glossary sanity checks
- **Web cockpit** — `weaver serve` creates projects (browse/upload), sets provider/model, runs and stops translates with live progress, reviews the glossary, and exports — all in the browser (loopback only, no auth)

---

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) for environment management
- A Japanese EPUB (public-domain fixture ships in `tests/fixtures/`)

---

## Installation

```bash
git clone https://github.com/Trancend1/weaver.git
cd weaver
uv sync --extra dev
uv run weaver --version
# weaver 0.6.0
```

Once published to PyPI, end users install with:

```bash
uv tool install weaver
```

---

## Quick Start

End-to-end walkthrough using the bundled fixture and the `fake` provider — no API key required.

```bash
mkdir scratch && cd scratch
uv run weaver init ../tests/fixtures/aozora_sample.epub
```

Open the generated `project.toml` and set the provider to `fake`:

```toml
[provider]
type    = "fake"
model   = "fake-1"
pattern = "[EN] {source}"
```

Then run the full workflow:

```bash
uv run weaver inspect  .weaver/aozora_sample/project.toml
uv run weaver glossary review .weaver/aozora_sample/project.toml  # press q to skip
uv run weaver translate .weaver/aozora_sample/project.toml
uv run weaver validate .weaver/aozora_sample/project.toml
uv run weaver export   .weaver/aozora_sample/project.toml --mode markdown
uv run weaver export   .weaver/aozora_sample/project.toml --mode epub
```

Real translation with `deepseek` or `gemini` requires the corresponding API key (see [Providers](#providers)).

---

## Providers

| Provider   | When to use                              | Auth                          |
|------------|------------------------------------------|-------------------------------|
| `deepseek` | Default cloud (~$2–4 per novel)          | `DEEPSEEK_API_KEY`            |
| `gemini`   | Free-tier cloud (15 req/min, 1M tok/day) | `GEMINI_API_KEY`              |
| `ollama`   | Local inference, requires GPU            | none                          |
| `custom`   | Any OpenAI-compatible endpoint           | your `api_key_env` (any name) |
| `fake`     | Development and CI                       | none                          |

The `custom` provider points the OpenAI-compatible engine at any `base_url` + `model`, with the key read from an env var you name via `api_key_env` — e.g. in `project.toml`:

```toml
[provider]
type        = "custom"
base_url    = "https://api.example.com/v1"
model       = "your-model"
api_key_env = "MY_API_KEY"
```

### API keys & the secret store

Keys come from **environment variables** or the dedicated **local secret store** `~/.weaver/secrets.toml` (mode `0o600`, outside any repo). Keys are **never** written to `project.toml` / `~/.weaver/config.toml`, never logged, never rendered. A shell env var always wins over the stored value.

```bash
weaver secrets set DEEPSEEK_API_KEY   # prompts with hidden input
weaver secrets set MY_API_KEY --value sk-...   # non-interactive
weaver secrets list                   # names only — values never shown
weaver secrets rm MY_API_KEY
```

In the web cockpit, the provider form has an API-key field that writes only to the secret store. (Override the store location with `WEAVER_SECRETS_PATH`.)

---

## Configuration

### Global Config

`~/.weaver/config.toml` sets user-wide defaults:

```toml
[defaults]
default_provider = "deepseek"
default_model    = "deepseek-chat"
output_dir       = "~/translations"
editor           = "code -w"
```

**Precedence (highest → lowest):** CLI flag › env var › `project.toml` › `~/.weaver/config.toml` › built-in default

### Environment Variables

| Variable                  | Overrides          |
|---------------------------|--------------------|
| `WEAVER_DEFAULT_PROVIDER` | `default_provider` |
| `WEAVER_DEFAULT_MODEL`    | `default_model`    |
| `WEAVER_OUTPUT_DIR`       | `output_dir`       |

### Project Templates

Use `--from-template` on `weaver init` to write prebaked knobs for your genre:

| Template        | Use case                                              |
|-----------------|-------------------------------------------------------|
| `light-novel`   | Standard LN — required glossary review, generous term budget |
| `web-novel`     | High-volume WN — relaxed review requirements          |
| `aozora-classic`| Classic literature — strict length ratio checks       |

```bash
weaver init my_novel.epub --from-template light-novel
```

---

## Commands

| Command | Description |
|---------|-------------|
| `weaver init <epub> [--from-template <name>]` | Create project, segment EPUB, extract glossary candidates |
| `weaver doctor [<project.toml>] [--healthcheck]` | Diagnose env vars, database, and provider config |
| `weaver inspect <project.toml> [--healthcheck]` | Show project status; `--healthcheck` probes the provider |
| `weaver preview <project.toml> [--segment ID] [--chapter K] [--pager auto]` | Display source + translation pairs inline |
| `weaver glossary review <project.toml> [--find <text>]` | Interactive approve / edit / reject / skip / undo |
| `weaver glossary edit <project.toml> [--yes]` | Open glossary TSV in `$EDITOR`; `--yes` skips diff confirm |
| `weaver glossary conflicts <project.toml>` | Print approved-term conflicts |
| `weaver translate <project.toml>... [--retry-failed] [--provider X] [--model Y] [--dry-run] [--verbose] [--first-N N]` | Translate pending segments; resumable |
| `weaver edit <project.toml> <id \| --first-failed \| --next-stale \| --recent>` | Override one segment via `$EDITOR` |
| `weaver export <project.toml> --mode markdown [--translation-only]` | Write per-chapter Markdown review files |
| `weaver export <project.toml> --mode epub` | Write translated EPUB (`.translated.epub`) |
| `weaver validate <project.toml> [--json] [--schema] [--epub]` | Six deterministic QA checks; `--epub` runs EPUBCheck (requires Java + epubcheck.jar) |
| `weaver new [--yes]` | Interactive wizard: pick EPUB, provider, template, working dir, then run init |
| `weaver dashboard <project.toml> [--no-color]` | Read-only TUI mirror of `weaver inspect` (requires `pip install 'weaver[tui]'`) |
| `weaver glossary diff <project.toml> <A> <B>` | Show which approved terms appear in chapter A but not B, and vice versa |
| `weaver serve [--port 8765] [--books-dir PATH] [--no-browser]` | Launch the local web cockpit (**FastAPI UI**, default); binds `127.0.0.1` only (requires `pip install 'weaver[web]'`) |
| `weaver serve-api [--port 8000] [--reload]` | Run the same FastAPI cockpit **headless** (no browser) |
| `weaver secrets set <ENV_VAR> [--value V]` / `list` / `rm <ENV_VAR>` | Manage API keys in the local secret store (`~/.weaver/secrets.toml`); values never printed |

### Optional extras

```bash
pip install 'weaver[tui]'     # weaver dashboard (Textual TUI)
pip install 'weaver[wizard]'  # weaver new (interactive questionary wizard)
pip install 'weaver[web]'     # weaver serve (local web cockpit)
pip install 'weaver[all]'     # all of the above
```

### Web cockpit

`weaver serve` runs a local, single-user web cockpit for managing projects in
the browser. `serve` runs the **FastAPI cockpit** (UI + JSON API); `weaver
serve-api` runs the same FastAPI app headless.
It binds **`127.0.0.1` only** (no remote access, no authentication —
see [docs/COCKPIT_WORKFLOW.md](docs/COCKPIT_WORKFLOW.md) and ADR `004`), defaults to port `8765`, and discovers every project under
`--books-dir` (default: current directory) so you never type a project path.
API keys are read from environment variables only — never entered, written to
disk, or rendered in the UI.

From the browser you can:

- **Create a project** — browse the sandboxed books directory or upload an EPUB,
  pick a provider and template, and run `init` (no `..` traversal; uploads land
  in `.weaver/_uploads/`).
- **Set provider/model** — write the project `[provider]` table or the global
  `~/.weaver/config.toml` default from a dropdown (keys stay in env).
- **Translate** — start with first-N / retry-failed, watch live Server-Sent
  Events progress, and **stop** a run cooperatively (already-translated segments
  stay committed).
- **Export** — trigger Markdown or EPUB export.
- **Review the glossary** — paginated approve / edit / reject of pending
  candidates, with approved-term conflicts and per-chapter coverage diff surfaced
  read-only.

```bash
pip install 'weaver[web]'
weaver serve                          # http://127.0.0.1:8765, opens a browser
weaver serve --port 9000 --no-browser # custom port, no auto-open
weaver serve --books-dir ~/novels     # discover projects under another root
```

### Shortcuts

| Alias       | Equivalent           |
|-------------|----------------------|
| `weaver tx` | `weaver translate`   |
| `weaver ins`| `weaver inspect`     |
| `weaver gl` | `weaver glossary`    |

Add `--debug` after `weaver` to see the full Python traceback instead of the three-line user error:

```bash
weaver --debug translate .weaver/aozora_sample/project.toml
```

Install shell completion once per shell:

```bash
weaver --install-completion bash   # or zsh / fish / powershell
```

---

## Project Layout

```
.weaver/<name>/
├── project.toml            # configuration
├── weaver.db               # SQLite WAL — source of truth for run state
├── glossary_candidates.tsv # pending review
├── glossary.tsv            # approved terms
├── logs/                   # weaver-YYYY-MM-DD.log (rotated daily)
└── output/
    ├── markdown/chapter-001.md
    └── epub/<source>.translated.epub
```

---

## Exit Codes

| Code | Meaning |
|------|---------|
| `0`  | Success |
| `1`  | Generic failure / critical QA finding |
| `3`  | Provider unavailable (network, bad key, Ollama not running) |
| `4`  | EPUB unreadable or unwritable |
| `5`  | Segment ID not found (`weaver edit`) |
| `6`  | Glossary conflict (`weaver translate` halts) |
| `7`  | Config parse failure (malformed or missing required table) |

---

## Development

```bash
uv run pytest -m "not requires_ollama and not requires_cloud"
uv run ruff check .
uv run ruff format --check .
uv run pyright
```

CI runs the same four checks on every push and pull request. Tests marked `requires_ollama` or `requires_cloud` are skipped in CI; run them manually with the appropriate environment variables set.

### Glossary Tokenizer (Optional)

Candidate extraction falls back to deterministic regex without any setup. For higher-quality Japanese proper-noun extraction, install MeCab first:

- **Linux:** `<package-manager> install mecab mecab-ipadic`, then `pip install fugashi`
- **macOS:** `brew install mecab mecab-ipadic`, then `pip install fugashi`
- **Windows:** install a prebuilt MeCab binary, add its `bin/` to `PATH`, then `pip install fugashi`

### Windows Notes

- `weaver edit` and `weaver glossary edit` require `EDITOR` to be set (e.g., `$env:EDITOR = "code -w"`).
- PowerShell's `Set-Content -Encoding utf8` writes a UTF-8 BOM that breaks `tomllib`. Use VS Code or Notepad instead. `weaver validate` exits `7` with a clear message on BOM detection.
- Legacy console codepage CP1252 cannot render Japanese — switch to Windows Terminal or run `chcp 65001`.

---

## License

[MIT](LICENSE) © 2026 Farhan Alamsyah

Weaver is a tool. It ships no copyrighted source material and takes no position on the legality of translating material the user does not have rights to. Users are responsible for the copyright status of any EPUB they process.
