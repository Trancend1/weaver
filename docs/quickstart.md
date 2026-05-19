# Quickstart

Weaver is a Python CLI. The v0.1.0 release is designed for local use with a
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
