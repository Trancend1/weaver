# AI Slop Prevention

How Weaver avoids becoming another forgettable AI product. Operational standards, not motivational guidance.

## Definition

"AI Slop" in this document means features, content, or products that:

- Use AI as decoration rather than as load-bearing infrastructure.
- Present LLM output without any verification layer.
- Replicate generic LLM behaviors (chat UI, magical-sparkle copy) without earning them.
- Add complexity that exists only to look impressive.
- Promise capabilities the underlying model cannot reliably deliver.
- Substitute prompt engineering for product engineering.

Weaver is an AI-assisted product. The risk of becoming AI Slop is real and continuous. This document is the operational defense.

## Anti-Patterns To Reject In Reviews

### Generic UX Patterns That Signal Slop

- A chat box on the home screen. Translation is not a conversation.
- An assistant avatar with a name (Wendy, Aiko, etc.).
- "Try asking Weaver: 'translate chapter 3 in a poetic style'". The CLI takes arguments; it does not roleplay.
- A "magic" button. Self-evident dishonesty.
- Loading screens with rotating fortune-cookie prompts ("Reweaving prose...").
- Confetti or sparkle animations when a translation completes.
- "AI is thinking..." messages. Say what's happening: "Calling provider; awaiting response."

### Fake AI Features

- "Smart suggestions" that are just LLM completions with no verification.
- "AI-powered" tags on features that are just deterministic regex.
- "Auto-improvement" that runs unverifiable polish passes.
- "Predictive QA" that hallucinates concerns.
- "Translation insights" that are vague LLM-generated platitudes.

If a feature label includes the word "smart", "intelligent", "AI-powered", or "magical", justify why a deterministic name would not work. Usually one does.

### Prompt-Wrapper Syndrome

Patterns to reject:

- A new "feature" that is one new prompt template wrapping the same LLM call.
- A "mode" that changes only the system prompt.
- Multiple "personas" that the user picks between.

Adding features by adding prompts is the cheapest form of product development. Weaver resists this. Real features change the data flow, the state machine, or the user's workflow — not just the prompt.

### Template UI Syndrome

The `weaver-landing-wireframe.html` file is a textbook example: glass-morphic gradients, "Currently in development" pill, floating chapter mockup. It exists, but it shouldn't be the brand surface. For cockpit UI direction see [decisions/005-cockpit-ui-ux-direction.md](decisions/005-cockpit-ui-ux-direction.md) (archived brand/design notes: `archive/strategy/BRAND_DIRECTION.md`, `archive/strategy/DESIGN_SYSTEM.md`).

Visual patterns to reject when building Weaver's surfaces:

- Soft-shadow card grids.
- Hero illustrations with abstract gradients.
- Three-column feature lists with icon + heading + paragraph.
- Customer logo strip (Weaver has no customers).
- Testimonial carousel (no testimonials).
- "Trusted by 10,000+ translators" (untrue; remove).
- Animated typewriter taglines.
- Curved section dividers.

### Fake Complexity

- Microservices for a single-user local CLI.
- Plugin systems with zero plugins.
- Configuration sections for features that don't exist.
- "Architecture diagrams" that show non-existent components.
- "Roadmap" entries that are vibes, not commitments.

### Low-Value Automation

- Automatically opening the EPUB after export. The user chose to export; they know where it is.
- Sending a notification when translation completes. The terminal already says so.
- Cloud-syncing project state. The user did not ask.
- Auto-emailing failure reports.

## Product Quality Gates

A feature ships only if all gates pass.

### Gate 1: Real Pain

The feature addresses a specific user complaint that exists in the wild. Evidence required:

- A linked GitHub issue.
- A forum/Discord post.
- An ADR explaining the decision.

"It would be cool if..." is not evidence. "Three users on day one asked for X" is.

### Gate 2: Falsifiable Spec

The feature has acceptance criteria that pass or fail. Vague specs are slop incubators.

Example bad spec:

> Add intelligent glossary suggestions.

Example acceptable spec:

> Add a `--auto-approve-frequency >= N` flag to `weaver glossary review`. When set, candidates appearing N or more times are pre-approved with a `[bulk-approved]` note in the TSV. Conflict detection still runs.

### Gate 3: Deterministic Where Possible

If a feature can be implemented deterministically, it is. Only when determinism is impossible does the feature use an LLM. When an LLM is used, the output is verifiable.

Example:

- "Detect untranslated Japanese" — deterministic (regex over translation text).
- "Detect translation style drift" — not deterministic. Therefore needs explicit verification UX (show user the comparison; user decides).

### Gate 4: User Can Override

Every AI-produced artifact must be editable by the user. No exceptions.

- Translated segments: editable via `weaver edit`.
- Glossary candidates: approve/reject/edit.
- QA warnings: dismissable.
- Chapter summaries (if added): editable.

If a user cannot override an AI output, that output is not a feature; it is an imposition.

### Gate 5: Failure Visible

Users see when AI output failed. Not silently substituted, not auto-retried-forever, not hidden under "we'll figure it out".

- A failed segment is marked `failed` in DB, rendered visibly in Markdown, surfaced in `weaver status`.
- A glossary candidate that the LLM could not suggest a target for is marked `pending` with notes.
- Provider unavailability is a hard error with exit code 3, not a "try again later" warning.

### Gate 6: Cost Visible

Cloud LLM costs are tracked and visible. Users know what their translation cost before they run it.

- `weaver inspect` estimates cost for cloud providers.
- `weaver translate` shows per-segment cost in DEBUG logs.
- `weaver status` shows cumulative cost.

Hiding cost is a slop pattern in cloud-AI tools.

## UX Quality Standards

Quality bar for every user-visible surface:

- A new user reading the README in 60 seconds understands what Weaver does and what it does not do.
- The first command a user runs (`weaver init`) succeeds or fails with a comprehensible error in under 30 seconds.
- Every error message tells the user what to do next.
- No marketing language anywhere in the product binary or CLI output.
- No telemetry without explicit opt-in.
- No phone-home behavior.
- No license check.

## Engineering Quality Standards

Quality bar for code:

- Every function has a clear single responsibility.
- Every external boundary (LLM, filesystem, network) is wrapped in a service with documented error modes.
- No dead code.
- No "smart" abstractions with one caller.
- Tests use the FakeProvider, not live LLMs.
- No CI step depends on network access to external providers.

If a contributor proposes a refactor that "prepares for the hosted version", reject. The hosted version does not exist and may never exist.

## AI Feature Audit Process

Before any AI-touching feature ships, the maintainer runs through this audit:

1. **Does the feature work without the LLM?** If yes, why is the LLM here?
2. **What happens when the LLM is wrong?** Is the failure visible? Recoverable?
3. **How does the user verify the output?** Is verification built into the UX?
4. **Is the prompt versioned?** Changes to prompts must be tracked like code changes.
5. **Is there a deterministic fallback?** Even a degraded one.
6. **What does this look like at 10x scale?** Cost, latency, failure rate.
7. **Would removing the LLM make the feature better?** Sometimes yes.

If the audit raises red flags, the feature does not ship.

## Launch-Readiness Standards

A release is "launch-ready" only if:

- The README describes the product accurately, not aspirationally.
- The CHANGELOG documents real changes, not marketing rephrases.
- The example output in the README is reproducible.
- The example EPUB output, if shown, was actually produced by the released version.
- No screenshot, video, or marketing asset shows a feature that does not work.
- No claim is made about model quality that is not benchmarked.
- Issue tracker shows recent activity (not abandoned).

Failing any of these blocks release.

## Specific Slop Risks Identified In Weaver's PRD

| Risk | Mitigation |
|------|------------|
| Glossary candidate extraction unspecified | Algorithm pinned in `archive/PRD_v2.md` (archived ADR `0004-glossary-algorithm`) |
| "Careful mode" config flag pre-implementation | Removed from MVP-0 |
| "Chapter-level context placeholder" hand-wave | Replaced with concrete 5-segment rolling window |
| "Hosted scalability" section in MVP PRD | Removed |
| Landing page wireframe in template-SaaS aesthetic | Deferred; replaced by docs-first approach |
| Roadmap with 40+ deferred features | Trimmed; rejected items moved to KILL list |
| "Future targets" config field | Removed from MVP-0 |
| "Prompt profiles" Phase 2 entry | Removed entirely |
| "Per-stage model routing" Phase 2 entry | Removed entirely |
| Conditional fallback messaging ("Careful not available; falling back...") | Removed entirely; flag does not exist |

## Maintainer Disciplines

Personal disciplines for the maintainer:

- Resist the urge to publicly tease unreleased features.
- Resist the urge to make Weaver look like a "real startup" in social media presence.
- Resist the urge to add AI features because they are easy to demo.
- Resist the urge to write "we" when "I" is more accurate.
- Resist the urge to apologize for the product's smallness.

The defense against AI Slop is not a checklist. It is a stance. The maintainer maintains it.

## Litmus Tests

Quick tests applied whenever a feature is proposed:

**The Translator Test.** Show the feature to a fan translator. If they say "yes I want that", consider building it. If they say "huh", do not build it. If they say "that sounds like ChatGPT-but-worse", definitely do not build it.

**The Calibre Test.** Could a Calibre-style power-user tool include this feature? If yes, it is on-brand. If no, it is probably mission creep.

**The Five-Year Test.** Imagine Weaver in five years. Is this feature still there? Is it still useful? Was it the right feature at the right time? If five-year Weaver doesn't need it, current Weaver probably doesn't either.

## When To Remove Features

Removing features is harder than adding them. The maintainer should:

- Once per quarter, review usage signals on existing features.
- Mark features for deprecation with a clear timeline.
- Communicate removals in CHANGELOG and release notes.
- Actually remove deprecated features; do not let them rot.

A bloated product is a slop product, even if each feature individually passed the gates.
