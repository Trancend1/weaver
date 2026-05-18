# Weaver Brand Direction

Positioning, voice, and identity for Weaver. The brand should resemble a serious tool for translators, not a venture-backed AI startup.

## Strategic Position

Weaver is a craftsman's tool. The target audience is fan translators and amateur literary translators who care deeply about novels. They are skeptical of commercial AI products that promise effortless translation. They want a tool that respects the work of translation.

This shapes everything below.

## Brand Personality

Four traits, in priority order:

1. **Disciplined.** Weaver does one thing carefully. It does not try to be a platform.
2. **Literary.** The product is for books. Visual and verbal language can borrow from literature: paragraphs, marginalia, manuscripts, drafts.
3. **Honest.** The product is software for a hard problem. It does not pretend to solve translation; it assists translation.
4. **Quiet.** Confidence without volume. No exclamation points, no marketing theater.

Traits explicitly rejected:

- "Bold", "innovative", "cutting-edge". Empty signaling.
- "Magical", "effortless", "seamless". AI-product clichés.
- "Friendly" in the cartoony sense. Friendly is fine; mascots are not.
- "Disruptive". Translators don't need disruption.

## Tone Of Voice

Voice principles:

- **Tell, don't sell.** Describe what the tool does. The reader decides if they want it.
- **Specific over generic.** "Translates a 200,000-character novel to a Markdown review file" beats "Powerful translation workflow".
- **Plain language.** Avoid jargon when a normal word exists.
- **Restraint.** When in doubt, say less.

Sample register:

> Weaver is a command-line tool for translating Japanese novels.
> It reads an EPUB, helps you build a glossary of names and terms, runs translation through a language model of your choice, and produces a Markdown review file and a translated EPUB.
> It runs on your laptop. It saves its progress. It does not upload your work anywhere.

That paragraph is the entire elevator pitch.

What this register avoids:

- "Empower yourself to translate at the speed of thought."
- "AI-powered, glossary-aware, context-rich literary translation reimagined."
- "The future of fan translation is here."

These sentences are AI-generated default settings. Weaver's voice rejects them.

## Emotional Positioning

Translators using Weaver should feel:

- Like they are using a tool a translator might have built.
- Like the tool respects their judgment.
- Like the tool will not lose their work.
- Like the tool is small enough to understand.

They should not feel:

- Like the tool is doing magic they don't understand.
- Like the tool is competing with their judgment.
- Like the tool is trying to sell them something.
- Like the tool will be discontinued next quarter.

## Messaging Framework

Three messages, in priority order:

### Primary Message
> Translate Japanese novels with consistency you can review.

This is the headline. It says: novels (specific domain), consistency (the actual hard problem), review (the workflow shape).

### Supporting Messages

> Names, places, and terms stay the same from chapter one to chapter forty.

> Your work resumes where it stopped. Even after a crash.

> Read the translation as Markdown before you commit to an EPUB.

### Defensive Messages

For when users ask "is this just ChatGPT?":

> Weaver uses language models, including local ones via Ollama. The product is the workflow around the model: glossary, segmentation, resumability, review, and EPUB roundtrip. Replace the model and the workflow stays.

## Visual Identity Direction

### Mark / Logo

Wordmark, not icon. Lowercase `weaver` set in a literary serif (Source Serif, Inter Display, or similar). No glyph beside it. No abstract swoosh suggesting "AI weaving threads together".

Optional ornament: a single hairline rule below the wordmark, evoking a manuscript margin. No gradient, no glow.

### Color

Restrained palette. One dominant ink, one paper, one accent.

| Role | Color | Hex (suggested) |
|------|-------|-----------------|
| Ink | Near-black warm | #1a1814 |
| Paper | Off-white warm | #f6f3ec |
| Accent | Deep indigo or rust | #2e3a8c or #8c3a2e |
| Muted | Warm gray | #7a7568 |

Explicitly rejected:

- Mint green, teal, emerald (the AI startup default).
- Neon gradient combinations.
- Pure white backgrounds (too sterile for a literary product).
- Multi-stop gradients on primary surfaces.

### Typography

- **Serif** for body content. Source Serif 4, Lora, EB Garamond, or Charter.
- **Sans-serif** for UI controls and nav. Inter or system stack.
- **Monospace** for code, segment IDs, file paths. JetBrains Mono or system mono.

Two type sizes max for prose. One scale for UI. No display weights, no condensed faces.

### Imagery

- **No 3D renders.** No abstract isometric illustrations.
- **No stock photos.** No fan-art of translators looking thoughtful.
- **No AI-generated illustrations.** Particularly: no "robot reading a book" imagery.
- **Acceptable imagery:** photographs of physical books, scans of manuscript pages, public domain illustrations from old novels.

If illustration is needed at all (rare), prefer minimal line art or printer's-flower-style ornaments. Anything that looks at home in a printed novel's frontispiece.

### Layout

- Generous margins. Books are read with white space.
- Long-form text in a single column, max 720px wide.
- Asymmetry over centered everything. Marginalia as a layout pattern when applicable.
- No hero "above the fold" framing. The page can scroll.

## Landing Page Direction (When It Exists)

The current `weaver-landing-wireframe.html` is a thousandth-generation AI SaaS landing template: glass-morphic emerald gradients, "Currently in development" pill, floating chapter-card mockup, "powered by AI" subtext implied. It is the visual opposite of what Weaver should be.

Replacement direction:

- Open with a paragraph, not a hero panel.
- First content: a real screenshot of terminal output or a Markdown review file.
- Second content: install command and five-line example.
- Third content: status and changelog.
- No CTA buttons floating in glass. Plain links suffice.

Reference inspirations:

- The websites of literary publishers (NYRB Classics, Pushkin Press, New Directions).
- Tool documentation sites that are confident and quiet (Sourcehut, Mosh, ripgrep's README).
- Personal sites of working translators.

Reference anti-inspirations:

- Generic AI startup landing pages of 2024–2026.
- Notion-templated "build in public" pages.
- VC-firm-coached pitch decks.

## Competitive Positioning

| Competitor | Their Position | Weaver's Counter |
|------------|----------------|------------------|
| Raw ChatGPT/Claude | "Just paste paragraphs and translate" | Glossary persistence and resumability across sessions |
| Sugoi Translator | Local NMT, fast, free | Glossary control + EPUB roundtrip + LLM context |
| LunaTranslator | Live game/manga overlay | Long-form novel workflow with state |
| DeepL / Google | Cloud, polished, no glossary | Author-controlled glossary and review |
| Custom Python scripts | "I built my own" | Same shape, but documented, tested, resumable |

The pitch in one sentence: **Weaver is what a fan translator would build for themselves if they had time to build it.**

## Brand Differentiation

Weaver's defensible differentiation, in priority order:

1. **Glossary workflow with manual approval.** Most tools auto-extract or ignore terms entirely. Weaver puts the translator in charge of the glossary as the first-class workflow.
2. **Resume safety.** Most tools fail on long jobs. Weaver is designed for the 200k-character novel.
3. **EPUB roundtrip as primary.** Most tools output text dumps. Weaver outputs the format users actually distribute.
4. **Local-first.** Most cloud-translation tools store user data. Weaver does not transmit anything the user has not explicitly opted into.

These four are the moat. Everything else is undifferentiated commodity tooling that Weaver borrows from.

## Brand Don'ts

Things the Weaver brand should never resemble:

- A productivity SaaS with "10x your translation workflow" headlines.
- An AI assistant product with a chat-bubble icon and an avatar.
- A startup pitching at YC demo day.
- A web3 project with mysticism around "preserving meaning on-chain".
- A consumer mobile app with cartoony onboarding.
- A "build-in-public" Twitter aesthetic with metrics dashboards as flex.
- A community SaaS with public Discord stat pages.

## Naming

"Weaver" works:

- Literary association (weaving a translation).
- Available domain space.
- Short, memorable.
- Pronounceable across the target audiences (EN, JP, ID).

Sub-product naming rules (if ever needed):

- Avoid feature names that suggest commercial tiers (`Weaver Pro`, `Weaver Cloud`).
- Avoid AI-suffixing (`WeaverGPT`, `WeaverAI`).
- Prefer descriptive names (`weaver glossary`, `weaver export`).

## Brand Voice Examples

Bad (AI-template):

> Welcome to Weaver! Your AI-powered translation workspace, reimagined for the modern translator. Get started in seconds and unlock the magic of seamless, intelligent literary translation.

Better (current direction):

> Weaver is a command-line tool that translates Japanese EPUBs into English. It is designed for fan translators who care about consistency across long projects. Install it, point it at a file, and review the result.

Bad (over-corrected, faux humility):

> Weaver is a small open-source experiment. Probably nothing! Have fun if you try it.

Better:

> Weaver is in early development. The core workflow ships in MVP-0. Useful enough to translate a novel; rough enough that you will hit bugs.

## Brand Decision Log

| Decision | Choice | Why |
|----------|--------|-----|
| Visual aesthetic | Literary, restrained | Audience is book people, not SaaS buyers |
| Color | Indigo / rust / warm neutrals | Avoid AI-startup mint-green default |
| Imagery | Minimal, no AI illustration | AI imagery is the cliché the product must avoid |
| Voice | Specific, quiet, restrained | Reflects the work of translation |
| Mascot | None | Mascots signal consumer-product framing |
| Logo glyph | None initially, wordmark only | Less to get wrong |
| Tagline | "Translate Japanese novels with consistency you can review." | Concrete, not aspirational |
