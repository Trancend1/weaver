# Quickstart

Get a translated EPUB from a Japanese source using the bundled fixture and the `fake` provider — **no API key required**. Then switch to a real provider.

## Install
```bash
git clone https://github.com/Trancend1/weaver.git
cd weaver
uv sync --extra dev
uv run weaver --version        # weaver 0.7.0
```

## CLI: end-to-end with the `fake` provider
```bash
mkdir scratch && cd scratch
uv run weaver init ../tests/fixtures/aozora_sample.epub
```
Set the provider to `fake` in the generated `project.toml`:
```toml
[provider]
type    = "fake"
model   = "fake-1"
pattern = "[EN] {source}"
```
Run the workflow:
```bash
uv run weaver inspect  .weaver/aozora_sample/project.toml
uv run weaver glossary review .weaver/aozora_sample/project.toml   # press q to skip
uv run weaver translate .weaver/aozora_sample/project.toml
uv run weaver validate  .weaver/aozora_sample/project.toml
uv run weaver export    .weaver/aozora_sample/project.toml --mode markdown
uv run weaver export    .weaver/aozora_sample/project.toml --mode epub
```
Output lands in `.weaver/aozora_sample/output/{markdown,epub}/`. Full flow + flags: [CLI_WORKFLOW.md](CLI_WORKFLOW.md).

> The CLI `export` command is the **legacy single-project** exporter (Markdown / single-EPUB). **Volume-aware EPUB/TXT/HTML export** for the Novel→Volume→Chapter model is the **FastAPI cockpit** surface (`POST /projects/{name}/export/{novel|volumes/{id}|chapters/{id}}`); see [COCKPIT_WORKFLOW.md](COCKPIT_WORKFLOW.md). DOCX output is deferred (out of MVP).

## Web cockpit
```bash
pip install 'weaver[web]'      # or: uv sync --extra web
uv run weaver serve            # FastAPI cockpit, http://127.0.0.1:8765, opens a browser
uv run weaver serve-api        # same FastAPI app, headless (no browser), :8000
```
Binds `127.0.0.1` only, no auth. `weaver serve` is the **FastAPI cockpit** (the only web cockpit). Discover/create projects, set provider/model, translate with live progress + stop, review glossary, export — no path typing. Details: [COCKPIT_WORKFLOW.md](COCKPIT_WORKFLOW.md).

## Real providers
```bash
weaver secrets set DEEPSEEK_API_KEY     # or GEMINI_API_KEY; hidden prompt, stored 0o600
weaver translate .weaver/<name>/project.toml --provider deepseek --model deepseek-chat
```
A shell env var always wins over the secret store. Keys never touch `project.toml`. Provider matrix + precedence: [PROVIDER_AND_MODEL_CONFIG.md](PROVIDER_AND_MODEL_CONFIG.md).

## Checks (development)
```bash
uv run pytest -m "not requires_ollama and not requires_cloud"
uv run ruff check .
uv run ruff format --check .
uv run pyright
```

## Common commands
| Task | Command |
|---|---|
| Diagnose environment | `weaver doctor [--healthcheck]` |
| Resume after interrupt | `weaver translate <project.toml>` (skips done) |
| Retry failures | `weaver translate <project.toml> --retry-failed` |
| Sample N segments | `weaver translate <project.toml> --first-N 5 [--dry-run]` |
| Override provider | `--provider gemini --model gemini-1.5-flash` |
| Manual edit | `weaver edit <project.toml> --first-failed` |
| Full traceback | `weaver --debug <command>` |
| Shell completion | `weaver --install-completion <shell>` |

Windows: set `EDITOR` for `weaver edit` / `glossary edit`; avoid `Set-Content -Encoding utf8` (writes a BOM that breaks `tomllib`); use Windows Terminal / `chcp 65001` for Japanese.
