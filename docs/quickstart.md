# Quickstart

Weaver is a Python CLI. The v0.6.0 release is designed for local use with a
user-owned EPUB and a user-owned provider key.

## Install From Source

```powershell
git clone https://github.com/Trancend1/weaver.git
cd weaver
uv sync --extra dev
uv run weaver --version
```

## Run The Fixture Workflow

```powershell
uv run weaver init tests/fixtures/aozora_sample.epub
uv run weaver inspect .weaver/aozora_sample/project.toml
uv run weaver glossary review .weaver/aozora_sample/project.toml
uv run weaver translate .weaver/aozora_sample/project.toml
uv run weaver validate .weaver/aozora_sample/project.toml
uv run weaver export .weaver/aozora_sample/project.toml --mode markdown
uv run weaver export .weaver/aozora_sample/project.toml --mode epub
```

For deterministic local testing, set the generated `project.toml` provider to
`fake` before translation. Real translation uses `deepseek`, `gemini`, or
`ollama` with credentials and setup described in the README.

## Pick A Provider Per Run

`weaver translate` accepts `--provider` and `--model` to override the
configured `[provider]` section without editing `project.toml`:

```powershell
uv run weaver translate .weaver/aozora_sample/project.toml --provider fake --model fake-1
uv run weaver translate .weaver/aozora_sample/project.toml --provider gemini --dry-run
```

`--dry-run` counts selected segments and estimates input tokens without
contacting the provider. `--verbose` echoes per-segment token I/O.

## Custom Provider & API Keys

Beyond the built-ins (`deepseek`, `gemini`, `ollama`, `fake`), the `custom`
provider targets any OpenAI-compatible endpoint:

```toml
[provider]
type        = "custom"
base_url    = "https://api.example.com/v1"
model       = "your-model"
api_key_env = "MY_API_KEY"
```

`api_key_env` names the env var holding the key. Keys live in the environment or
the local secret store `~/.weaver/secrets.toml` (mode `0o600`) — never in
`project.toml`, never logged, never shown. A shell env var beats the store.

```powershell
uv run weaver secrets set DEEPSEEK_API_KEY        # hidden prompt
uv run weaver secrets set MY_API_KEY --value sk-...
uv run weaver secrets list                        # names only
uv run weaver secrets rm MY_API_KEY
```

Set `WEAVER_SECRETS_PATH` to relocate the store. In the web cockpit, the provider
form has an API-key field that writes only to the secret store.

## Shell Completion

Install once per shell:

```powershell
uv run weaver --install-completion powershell
```

`bash` and `zsh` are also supported by passing the matching shell name.
Restart the shell, then `weaver <TAB>` lists commands and project paths.

## Diagnose Setup

Before the first translate run, surface missing env vars or DB issues:

```powershell
uv run weaver doctor                                      # host checks only
uv run weaver doctor .weaver/aozora_sample/project.toml   # +project checks
uv run weaver doctor .weaver/aozora_sample/project.toml --healthcheck
```

Exits 0 when every check passes, 1 otherwise.

## Shortcuts For Power Users

| Shortcut | Equivalent |
|---|---|
| `weaver tx <project.toml>` | `weaver translate <project.toml>` |
| `weaver ins <project.toml>` | `weaver inspect <project.toml>` |
| `weaver gl review <project.toml>` | `weaver glossary review <project.toml>` |
| `weaver edit <project.toml> --first-failed` | edit the earliest failed segment |
| `weaver edit <project.toml> --next-stale` | edit the earliest stale segment |
| `weaver edit <project.toml> --recent` | edit the most recently translated segment |

Add `--debug` after `weaver` to see Python tracebacks instead of the
three-line user error (e.g. `weaver --debug translate proj.toml`).

## Global Config

Set user-wide defaults in `~/.weaver/config.toml` so you don't repeat flags
on every command:

```toml
[defaults]
default_provider = "deepseek"
default_model    = "deepseek-chat"
output_dir       = "~/translations"
editor           = "code -w"
```

Precedence: **CLI flag > env var > `project.toml` > `~/.weaver/config.toml` > built-in default**.

Override without a config file via env vars:

```powershell
$env:WEAVER_DEFAULT_PROVIDER = "gemini"
$env:WEAVER_DEFAULT_MODEL    = "gemini-1.5-flash"
$env:WEAVER_OUTPUT_DIR       = "D:\translations"
```

## Project Templates

Use `--from-template` on `weaver init` to write prebaked `[glossary]` and
`[qa]` knobs for your genre instead of editing the TOML by hand:

```powershell
uv run weaver init my_novel.epub --from-template light-novel
uv run weaver init my_novel.epub --from-template web-novel
uv run weaver init my_novel.epub --from-template aozora-classic
```

Available templates: `light-novel`, `web-novel`, `aozora-classic`.

## Preview Translations

`weaver preview` renders source + translation pairs without opening an EPUB
viewer:

```powershell
uv run weaver preview .weaver/aozora_sample/project.toml
uv run weaver preview .weaver/aozora_sample/project.toml --segment <hex-id>
uv run weaver preview .weaver/aozora_sample/project.toml --chapter 1
uv run weaver preview .weaver/aozora_sample/project.toml --pager auto
```

`--pager auto` pipes output through `$PAGER` (or `less` on Unix) when output
exceeds terminal height.

## Sampled Translate

`--first-N` translates only the first N selected segments and stops, leaving
project state consistent. Useful for a fast-fail sanity check before
committing to a full run:

```powershell
uv run weaver translate .weaver/aozora_sample/project.toml --first-N 5
uv run weaver translate .weaver/aozora_sample/project.toml --first-N 5 --dry-run
```

## Interactive New-Project Wizard

`weaver new` walks through provider, template, and output directory selection
before calling `weaver init`:

```powershell
# requires: pip install 'weaver[wizard]'
uv run weaver new
uv run weaver new --yes   # skip confirmation step
```

## TUI Dashboard

`weaver dashboard` opens a read-only Textual TUI that mirrors `weaver inspect`.
Press `r` to refresh, `q` to quit:

```powershell
# requires: pip install 'weaver[tui]'
uv run weaver dashboard .weaver/aozora_sample/project.toml
uv run weaver dashboard .weaver/aozora_sample/project.toml --no-color
```

## Glossary Term Diff

Compare which approved glossary terms appear in chapter A vs chapter B:

```powershell
uv run weaver glossary diff .weaver/aozora_sample/project.toml 1 2
```

## EPUBCheck Validation

`weaver validate --epub` runs the EPUBCheck tool on the exported EPUB.
Requires Java 8+ and an epubcheck.jar on the discovery path:

```powershell
uv run weaver export .weaver/aozora_sample/project.toml --mode epub
uv run weaver validate .weaver/aozora_sample/project.toml --epub
```

If epubcheck.jar is not found, Weaver skips the check with a notice rather
than failing. Set `EPUBCHECK_JAR=/path/to/epubcheck.jar` to point Weaver at
a custom installation.

## Web Cockpit

`weaver serve` launches a local web cockpit: a browser dashboard that discovers
every project under `--books-dir` — no typed paths — and lets you create,
configure, translate, and export projects without leaving the browser. It binds
**`127.0.0.1` only**, runs without authentication (single-user local tool, ADR
`0017`), and never writes or renders API keys.

```powershell
# requires: pip install 'weaver[web]'
uv run weaver serve                          # http://127.0.0.1:8765, opens a browser
uv run weaver serve --port 9000 --no-browser # custom port, no auto-open
uv run weaver serve --books-dir D:\novels    # discover projects under another root
```

In the browser:

1. **New project** — browse the sandboxed books directory or upload an EPUB, pick
   a provider and template, and create it. Uploads stage under `.weaver/_uploads/`.
2. **Cockpit** — view status (mirrors `weaver inspect`), set provider/model
   (project or global scope), translate with first-N / retry-failed, **stop** a
   run cooperatively, and export Markdown or EPUB.
3. **Glossary review** — paginated approve / edit / reject of pending candidates,
   with approved-term conflicts and a per-chapter coverage diff shown read-only.

One translate job runs at a time; live progress streams over Server-Sent Events.
