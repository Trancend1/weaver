# Weaver Design System

The Weaver "design system" is a CLI design system. There is no GUI at MVP-0. This document defines the standards that produce a coherent terminal experience and prepare for a future docs site.

## Scope

Three surfaces total:

1. **CLI output** — the actual product UX. The most important.
2. **README and documentation** — first surface users encounter.
3. **Docs website** — static MkDocs site, simple, after MVP-0 ships.

The landing wireframe in `weaver-landing-wireframe.html` is replaced by a docs-first approach. See `BRAND_DIRECTION.md` for rationale.

## CLI Visual Language

### Color Usage

Colors are decoration, not load-bearing information. Every color signal must also be communicated via text. Users running with `NO_COLOR=1` or in pipes must see identical content.

Palette (via `rich` named colors):

| Purpose | Color | Use |
|---------|-------|-----|
| Success | `green` | Completed translation, valid output |
| Warning | `yellow` | QA warnings, deprecation notices |
| Error | `red` | Failed segments, exit-code errors |
| Info | `cyan` | Section headers, status panels |
| Muted | `bright_black` | Secondary metadata, hints |
| Default | terminal default | Body text |

Do not introduce additional colors. Resist the urge to ship a "themed" palette. The terminal is the user's environment.

### Typography

Two typographic patterns only:

- **Plain text** for content (translations, source text, log lines).
- **Headers** rendered as bold text with a blank line above. No ASCII art, no Unicode rule lines, no boxed dashboards.

Specifically avoided:

- `╔══════════╗` box drawing for section headers. Wastes space in narrow terminals.
- Emoji status icons (✅, ❌, ⚠️). Inconsistent rendering, accessibility issues.
- Gradient backgrounds via Rich `Panel` for decoration. Functional panels only.

### Layout Patterns

Standard output blocks:

**Progress.** Single line, updates in place. `rich.progress.Progress` with one task. Shows: current chapter / total chapters, segments completed, elapsed time, ETA.

```
Translating: ch3/18 | seg 412/1842 | 00:14:32 elapsed | ~01:21:00 remaining
```

**Status panel.** Plain key-value pairs, aligned. Used by `weaver inspect` and `weaver status`.

```
Project:     example-novel
Source:      ./novel.epub
Provider:    deepseek (deepseek-chat)
Chapters:    18
Segments:    1842 total | 412 translated | 0 failed | 0 stale
Glossary:    67 candidates | 48 approved | 12 pending | 0 conflicts
Output:      markdown ready | epub not generated
Next:        weaver translate weaver-novel/project.toml
```

**Interactive prompts.** Single question, bracketed key options, prompt character `>`. No multi-line menus, no fancy form widgets.

```
[1/67] Term: 主人公 -> protagonist
  Category: role
  Frequency: 412
  Example: 主人公は剣を振り上げた。

  [a]pprove [e]dit [r]eject [s]kip [u]ndo [f]ind [?]help [q]uit
  > _
```

**Error blocks.** Three lines minimum:

```
Error: Ollama model qwen3:14b is unavailable.
Cause: Connection to http://localhost:11434 refused.
Next:  Start Ollama with `ollama serve`, then retry.
Log:   .weaver/example-novel/logs/weaver-2026-05-14.log
```

### Information Density

- Status panels: maximum 12 lines on a 24-row terminal.
- Progress bars: one line each, maximum two simultaneous.
- Glossary review: one term per screen, no scroll-back.
- Log files: full verbosity. Console output: summarized.

### Accessibility

- All color signal is duplicated as text.
- All progress information is also written to logs.
- `--json` output mode for every command. Machine-readable, deterministic.
- `NO_COLOR=1` respected.

## CLI Command Naming

Verbs are present-tense, action-first: `init`, `translate`, `export`, `validate`. Nouns avoided.

Subcommands group cohesively: `weaver glossary review`, `weaver glossary edit`, `weaver glossary conflicts`. Never reach three levels deep (`weaver glossary candidate review` is wrong).

Flag conventions:

- Short flags for frequent operations: `-r` for `--retry-failed`.
- Long flags spelled out, kebab-case: `--translation-only`, `--mode`.
- Boolean flags follow `--enable-X` / `--disable-X` only when not obvious; otherwise plain `--X` / `--no-X`.

## Documentation Visual Language

### README

Structure:

1. **One-line tagline.** Concrete, not aspirational.
2. **30-second pitch.** Three sentences. What it does, who it's for, why it exists.
3. **Quickstart.** `pip install weaver` plus 5 commands that produce visible output.
4. **Example output.** Real terminal output, not mockup screenshots.
5. **Status.** Honest. "MVP-0, expect rough edges."
6. **Disclaimer.** Copyright responsibility, single paragraph.
7. **Links.** Docs site, issue tracker, license.

No badges beyond: PyPI version, license. No "made with love" banners. No "powered by AI" boilerplate.

### Docs Site

MkDocs Material theme, default settings, minimal customization. Sections:

- Getting Started
- CLI Reference
- Project Configuration
- Glossary Workflow
- Provider Setup (Ollama, DeepSeek)
- Troubleshooting
- Contributing

Each page: one concept, one purpose, runnable examples. No marketing pages. No testimonials. No "trusted by" sections.

Code samples are syntax highlighted plain code blocks. No animated GIFs of typing.

## Future GUI/TUI Direction (Not MVP)

If a TUI is added in MVP-1+, follow these constraints:

- Built with Textual, not custom Curses.
- Functional only. No animated splash. No gradient panes.
- Keyboard-driven; mouse optional.
- All CLI functionality reachable via TUI; TUI does not introduce new business logic.

The web GUI is no longer hypothetical: **Phase 12 (Local Web Cockpit)** adopts these constraints (Flask + HTMX, local-only). See [feature_plan/web-feature-plan.md](feature_plan/web-feature-plan.md) and [feature_plan/web-architecture.md](feature_plan/web-architecture.md). Constraints for the Phase 12 web cockpit:

- Single-page, minimal-framework (**HTMX** — chosen; no React/Node build step).
- Light theme default. Dark theme follows system.
- No glass morphism. No gradients on primary surfaces. No "AI shimmer" effects.
- Monospace where text is data (translations, segment IDs).
- Sans-serif for navigation and prose.
- Two type sizes max for body content.
- Color use restricted to status, links, and inline highlights.

## What Weaver Visuals Should Never Look Like

Patterns that signal generic AI-startup template UI:

- Glassmorphic green/teal gradient hero with a "Currently in development" pill.
- Floating dashboard mockups with placeholder chapter cards.
- "Built with [framework]" footer badges.
- Stock illustrations of robots, brains, or sparkles.
- Animated typewriter effects on landing copy.
- Curved "wave" section dividers.
- Soft-shadow card grid pretending to be a feature comparison.

The current `weaver-landing-wireframe.html` is an example of this aesthetic. It looks like a thousand other AI SaaS landing pages. Weaver is not that product.

## Replacement For The Landing Wireframe

For now: README + GitHub Pages docs site.

When a marketing page is eventually justified (more than 500 users actively contributing), the page should:

- Show real terminal output as the hero. Static `<pre>` block, not animated.
- Lead with `pip install weaver` and a 5-step example.
- Have one screenshot only: a Markdown review file diffed against original text.
- Avoid all decorative gradients and glass effects.
- Use a serif typeface for body text (this signals literary, not techbro).
- Single accent color (suggestion: deep indigo or rust, not green-mint).
- Maximum two CTAs: "Read the docs" and "Star on GitHub". No "Get started free" SaaS framing.

## Microcopy

Three rules:

1. **Tell the user what to do next.** Every output ends with a recommended next command when applicable.
2. **Specific over generic.** "Translated 412 of 1,842 segments" beats "Translation in progress".
3. **No celebration.** "Done" beats "✨ Translation complete! ✨".

Avoided phrasing:

- "Awesome!", "Great!", "Yay!".
- "Let's get started!".
- "Powered by AI" anywhere.
- "Magic" as a noun applied to a feature.

## Empty, Loading, And Error States

CLI equivalents of design-system states:

| Web term | CLI manifestation |
|----------|-------------------|
| Empty state | First-run hint after `weaver init` showing next steps |
| Loading state | Inline progress with ETA |
| Error state | Three-line error block (problem / cause / next) |
| Success state | One-line confirmation + file path |
| Partial state | `weaver status` showing failed/stale counts visibly |

## Visual Identity Summary

Weaver should feel:

- Quiet. Like a Unix tool.
- Honest. No theatrical polish.
- Literary. The product is for books; the visuals can borrow from that.
- Functional. Every pixel earns its place.

Weaver should not feel:

- Aspirational. Avoid "transform your translation workflow" language.
- Magical. Avoid AI-sparkle aesthetics.
- Premium SaaS. Avoid emerald-mint glass gradient territory entirely.
