# Weaver
Local-first AI-assisted translation workbench for long-form Japanese novel translation.

Weaver takes a Japanese novel from raw EPUB to finished English export inside a single structured workflow: import, inspect, translate, review, manage terminology, validate, and export. It is built for long-form work, where consistency across hundreds of segments matters more than a fast one-off translation. Everything runs on your own machine, so your books, glossaries, and translation history stay local and under your control.

## Why Weaver Exists

Most translation tools optimize for a single turn: paste text, get raw machine output, move on. They live in a chat box or a one-shot form, with no memory of the book you are working on and no structure to keep a long project coherent.

Weaver optimizes for the opposite. It treats a translation as a long-lived project with structure, terminology, and review history. Glossaries and character names stay consistent across chapters, every translated segment is reviewable and overridable, and nothing leaves your machine. The goal is a workbench you can return to over weeks, not a one-off generator.

## Core Workflow

```text
Import Book → Inspect Structure → Translate → Review Candidates → Glossary & Characters → QA Validation → Export
```

- **Import Book:** an EPUB is parsed into Weaver's structure with its chapters, segments, and images preserved.
- **Inspect Structure:** you review the imported hierarchy to confirm volumes, chapters, and segments before translating.
- **Translate:** segments are translated through a configured AI provider, processed via a queue for long runs.
- **Review Candidates:** generated translation candidates and drafts are reviewed, compared, and accepted or overridden.
- **Glossary & Characters:** terminology and character entries are maintained so names and terms stay consistent across the project.
- **QA Validation:** consistency checks and validation workflows surface issues before the text is finalized.
- **Export:** the finished translation is written back out as a structured EPUB.

## Features

#### Import
- EPUB import into Weaver's project structure.
- Structure preservation across volumes, chapters, and segments.
- Images from the source book are retained.

#### Translation
- Segment-based translation as the unit of work.
- Support for multiple AI translation providers.
- Queue system for running long translation jobs.

#### Review
- Candidate review for comparing and selecting translations.
- Draft review for in-progress segment text.
- Project navigation across the full book hierarchy.

#### Knowledge
- Glossary for managing terminology.
- Characters for tracking names and consistency.
- Translation memory for reusing prior translations.

#### QA
- Consistency checks across the project.
- Validation workflows to confirm readiness before export.

#### Export
- EPUB export of the completed translation.
- Structured output that mirrors the source hierarchy.

#### Desktop
- Native desktop shell that runs the workbench in a local window.
- Local sidecar process that hosts the cockpit backend.
- Self-contained Windows alpha that runs without an external install on PATH.

## Quick Start

### Web Mode

```bash
git clone <repo-url>
cd weaver
uv sync
weaver serve
```

### Desktop Mode

Option A: run the built binary directly.

```bash
desktop/target/release/weaver-desktop.exe
```

Option B: use the installer when available.

```text
Download installer → Install → Launch Weaver
```

Desktop is currently in alpha. Windows only.

## Screenshots

<!-- TODO: Add screenshots for each view below -->
<!-- Required: Workspace, Project Overview, Translation View, Glossary, QA, Desktop Window -->

## Architecture

```text
Workspace
 └── Project
      └── Volume
           └── Chapter
                └── Segment
```

A Workspace is the top-level container for all of your translation projects on a machine. A Project is one book or series, holding its volumes, chapters, glossary, and characters. A Volume groups chapters, a Chapter groups the ordered Segments, and a Segment is the atomic unit of translation that candidates, drafts, and reviews attach to.

## Current Status

- **CLI:** stable
- **Web UI:** active development
- **Desktop:** alpha (Windows)
- **Python:** 3.11+ required
- **Package manager:** uv

## Development

Requires Python 3.11+ and [uv](https://github.com/astral-sh/uv).

```bash
uv sync
uv run ruff check .
uv run pyright
uv run pytest
```

## License
MIT
