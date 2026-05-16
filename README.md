# Weaver

> Offline-capable, glossary-aware JP→EN novel translation workbench.

A command-line tool for amateur fan-translators working on Japanese light novels and web novels. Weaver turns a Japanese EPUB into a translated EPUB and a Markdown review file, with glossary consistency and resume safety across long projects.

**Status:** Pre-alpha (Phase 0). Skeleton only. The full MVP-0 command set is not yet implemented — see [docs/BLUEPRINT_EXECUTION_PLAN.md](docs/BLUEPRINT_EXECUTION_PLAN.md).

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) for environment management

## Quickstart

```bash
git clone https://github.com/Trancend1/weaver-translate.git
cd weaver-translate
uv sync --extra dev
uv run weaver --version
```

Expected output:

```
weaver 0.0.1
```

## Development

```bash
uv run pytest -m "not requires_ollama and not requires_cloud"
uv run ruff check .
uv run ruff format --check .
uv run pyright
```

CI runs the same four checks on every push and pull request.

## Documentation

Authoritative specs live in [docs/](docs/):

- [PRD_v2.md](docs/PRD_v2.md) — product requirements and MVP-0 scope.
- [SYSTEM_ARCHITECTURE.md](docs/SYSTEM_ARCHITECTURE.md) — module layout, IR, SQLite schema, provider interface.
- [BLUEPRINT_EXECUTION_PLAN.md](docs/BLUEPRINT_EXECUTION_PLAN.md) — 10-phase build order.
- [ENGINEERING_STANDARDS.md](docs/ENGINEERING_STANDARDS.md) — coding rules.
- [AI_SLOP_PREVENTION.md](docs/AI_SLOP_PREVENTION.md) — feature gates and anti-patterns.

## Copyright Notice

Weaver is a tool. It does not ship copyrighted source material, and the project takes no position on the legality of translating material the user does not have rights to. Users are responsible for the copyright status of any EPUB they feed into the tool.

## License

[MIT](LICENSE). Copyright (c) 2026 Farhan Alamsyah.
