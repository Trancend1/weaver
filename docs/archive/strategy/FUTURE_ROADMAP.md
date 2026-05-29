# Weaver Future Roadmap

Long-term direction without dates. Dates are commitments; this document is intent. Treat each version as a destination, not a deadline.

## V1.0 (After MVP-0 Ships)

V1 is MVP-0 with bug fixes and smoothing. The product the world first sees.

Focus:

- Stabilize the workflow described in `PRD_v2.md`.
- Fix bugs reported by early users.
- Improve error messages based on real-world confusion.
- Documentation hardening.

Explicitly out of scope:

- Any new feature.

A v1.0 release happens only after a stretch of zero new bug reports for two weeks on the most-recent pre-1.0 build. This is a quality gate, not a calendar event.

## V1.5 (Quality Hardening)

The first round of legitimate additions. Pulled from `FEATURE_PRIORITY_MATRIX.md` SHOULD HAVE column.

Likely candidates:

- `weaver new` interactive wizard.
- Honorific policy `localize` and `hybrid` modes.
- EPUBCheck integration.
- `weaver retry-failed` first-class command.
- Better progress reporting with rolling segments/min and ETA.
- Glossary diff across chapters (signature feature).

Selection criterion: each feature must have three or more user requests from real users before promotion.

## V2.0 (Workflow Depth)

Once v1.5 stabilizes, depth features that improve translator workflow.

Candidates:

- Chapter summary memory (with explicit AI Slop discipline per `AI_SLOP_PREVENTION.md`).
- Character voice memory.
- Markdown diff view between translation runs.
- Project versioning: compare multiple translation runs of the same source.
- TMX import/export.
- Optional TUI dashboard via Textual.

V2 should not introduce hosting, multi-user, or cloud-only features.

## V2.5 (Source Language And Format Expansion)

If user demand exists, expand the input surface.

Candidates:

- Korean source language.
- Plain text input (for users with non-EPUB sources they've cleaned themselves).
- Web Novel scraper for one or two major sites, with strict legal-disclaimer handling.

Korean and PDF support require new tokenization and reader work. They are gates, not assumptions.

## Long-Term Expansion Opportunities

These exist as possibilities, not commitments.

### EN → ID (English to Indonesian)

Real audience exists in Indonesian fan-translator communities. Adding a second target language path would:

- Validate the IR is truly source/target-agnostic.
- Open Weaver to a new community.
- Require new glossary heuristics and possibly Indonesian-specific quality checks.

Conditions for build: at least 200 Weaver users active on the JP→EN workflow, plus three or more Indonesian translators requesting it.

### Multiple Cloud Providers

Beyond DeepSeek, add providers based on user demand:

- Anthropic Claude (strong on literary prose, expensive).
- Google Gemini (cheap, mixed quality).
- OpenAI GPT (familiar, expensive).
- Local LLMs beyond Ollama (vLLM, llama.cpp direct).

Each provider added requires:

- An adapter passing the full provider test suite.
- Documented cost-per-novel estimates.
- Default model recommendations.

### Translation Memory Diffing

Compare a Weaver-produced translation against a known good translation (a published official translation, where one exists and is legally permissible to use locally). The user provides the reference; Weaver produces a diff report. Real signature feature for power users.

### Project Versioning

Treat each `weaver translate` run as a versioned artifact. Allow users to:

- Translate the same source with multiple models.
- Diff translations between versions.
- Revert to a previous version.

This requires schema changes and significant storage discipline. Not until V2.

## Enterprise Opportunities (Heavily Caveated)

Weaver is not optimized to become enterprise software. If someone wanted to use it commercially, the realistic shape:

- Self-hosted internal version for in-house localization teams.
- Custom provider adapters for company-private LLMs.
- TMX integration with translation memory tools they already use (memoQ, Trados).

The product would need:

- Support contract structure.
- Hardened auditing and access logs (currently zero).
- Custom invoicing and licensing (currently MIT/Apache).

This is a different product. Weaver as-is is not the right starting point. Anyone serious about this should fork or commission a derivative.

## API Opportunities

A future `weaver-core` library could expose the IR, segmentation, and orchestration layer as a Python API, separate from the CLI.

Use cases:

- Custom workflow scripts.
- Integration into existing translator tooling.
- Third-party glossary tools building on top.

This is a refactor, not a feature. The current internal API is already close to library-shaped because of layer discipline. Promoting to public API would mean stability guarantees, which are a real commitment.

Possible after V2.

## Platform Opportunities

Not pursued. Platforms are different products with different audiences and resourcing requirements. Anyone wanting a translation platform should build one; Weaver remains a tool.

## Features That Should Never Be Built

These are explicitly out of scope for Weaver, permanently. Forks are welcome to do these, but they are not Weaver.

- **Real-time collaborative editing.** Wrong tool shape. Google Docs exists.
- **Hosted multi-user SaaS.** Wrong product. Different team needed.
- **Mobile apps.** Wrong device for translation work.
- **Browser extensions that overlay translations on web pages.** LunaTranslator does this well.
- **AI-generated cover art.** Disrespectful to the original artist.
- **AI-generated chapter summaries that ship in the output EPUB.** Adds AI-generated content to the user's distributed artifact without their consent.
- **Voice narration of translations.** Off-mission.
- **Community glossary marketplace.** Quality moderation nightmare; legal exposure.
- **"AI agent" framing.** The product is deterministic where it can be; calling it an agent obscures the actual workflow.
- **Chat-style UI for "talking to your novel".** A trend; not a tool.

The list above is binding. New ideas in these directions are rejected without architectural discussion.

## Expansion Traps

Failure modes to avoid:

### Trap 1: Becoming A Platform

Open source tools that grow successful are tempted to add user accounts, hosted versions, social features. This dilutes focus, fragments the product, and creates support burden disproportionate to value. Weaver remains a tool.

### Trap 2: Bundling Adjacent Features

After Weaver translates a novel, what next? Editing tools? Publishing platforms? Reader software? Resist. Each adjacency is a different product. Solve one problem well.

### Trap 3: Premature Generalization

"Weaver should work for any source format, any target language, any LLM." The temptation to abstract is constant. Resist for the first three real use cases; only generalize when the third one proves the abstraction is correct.

### Trap 4: Acquiring Maintainers Who Want To Build Their Own Vision

External contributors are welcome; PR review is rigorous. Maintainer-level commitment requires shared product direction. Weaver's product direction is small and disciplined; contributors who want to ship rapidly and broadly should fork.

### Trap 5: Investor Logic

There are no investors. Weaver is open source. Decisions are made for users, not for valuation.

## Defensibility Opportunities

Real moats that Weaver can build:

### Moat 1: Glossary Workflow Depth

No competing tool has spent serious design effort on the glossary review experience. Investment here compounds: better candidate extraction, better conflict detection, better diffing across chapters, better term clustering.

### Moat 2: Reputation In MTL Communities

Trust is the moat. Translators recommend tools that have not burned them. Reliability over years beats feature velocity for this audience.

### Moat 3: EPUB Roundtrip Quality

No widely-used translation tool produces clean EPUBs. If Weaver becomes the obvious choice when you need a publishable EPUB, that is the moat.

### Moat 4: Documentation And Examples

Most open-source translation tools have terrible docs. Weaver's docs become the moat: clear, tested, complete examples.

### Moat 5: Reviewability And Trust

Translators using LLMs need to verify output. Tools that hide LLM behavior lose trust. Weaver's commitment to visible failure, visible cost, and user override is itself a moat.

## Review Cadence

This document is revisited at every major release. Items move:

- From "Long-term" to a specific version when conditions are met.
- From any column to "Never Built" when user demand proves absent.
- From "Never Built" to "Long-term" only if a strong case is made via ADR.

Movement is documented. Vague reshuffling is rejected.

## Closing Posture

Weaver's roadmap is deliberately small. The mistake most open-source projects make is sprawling roadmaps that promise more than the maintainer can deliver. Weaver's promise is the opposite: a small, focused tool that ships reliably and improves incrementally.

If the project succeeds, the success looks like:

- A translator says: "I use Weaver for my JP→EN novel work."
- Another translator says: "It just works."
- A third says: "I've used it for two years and it has not lost my work once."

That is the destination. Everything else is in service of getting there.
