# Weaver Go-To-Market

GTM for an open-source niche tool. Not GTM for a venture-funded SaaS. Most generic startup-marketing advice does not apply.

## Honest Framing

Weaver does not need a GTM the way a SaaS product needs one. There is no funnel to optimize, no CAC to recover, no churn to manage. What Weaver needs is **distribution within a small, specific community** and **a reputation for not breaking**.

The audience is small. Estimate: 1,000–3,000 active fan translators globally working on JP→EN novel content. Weaver does not need to convert all of them. Reaching 50–200 active users in the first year is success.

## Positioning Statement

For Japanese fan translators who need consistency and resumability across long novel projects, Weaver is a local-first CLI translation workbench that turns an EPUB into a reviewed translation, with a glossary the translator controls. Unlike raw ChatGPT or paid translation SaaS, Weaver runs on the translator's machine, saves progress at the segment level, and outputs a Markdown review file and a translated EPUB.

This positioning statement is the source of all messaging downstream.

## Launch Strategy

Three phases. Conservative timing. No fireworks.

### Phase 1: Quiet Pre-Release (Weeks 1–4 Post-MVP-0)

- Invite five known fan translators in MTL communities to try the alpha.
- Solicit feedback via direct messages, not public channels.
- Incorporate the most critical feedback before a public release.
- Avoid public announcements during this phase.

Why: a fragile release at this stage destroys trust permanently. Better to be invisible than buggy.

### Phase 2: Targeted Public Release (Weeks 4–8)

Channels:

- **Reddit /r/LightNovels** — single launch post: clear, technical, no marketing copy. Title format: "[Tool] Weaver: a local CLI for translating JP light novels (alpha)".
- **MTL Discord servers** — post in tools/projects channels with maintainer presence. No spam to general channels.
- **Personal blog or GitHub Discussions** — long-form write-up of design decisions, suitable for HN if the author wants to risk it.
- **GitHub repo** — README, issues, discussions. The hub.

Channels to avoid:

- **Product Hunt** — wrong audience. Tech enthusiasts there are not translators.
- **Twitter/X "build in public" threads** — signals startup framing, not on-brand.
- **TikTok or YouTube Shorts** — wrong format and audience.
- **Hacker News** — possible launch site, but the comments will critique the AI angle harshly and the audience is not the target user. Use cautiously.

### Phase 3: Sustained Community Engagement (Ongoing)

- Respond to issues within 72 hours during the first three months.
- Write release notes that read like a real human change log, not marketing.
- Maintain a project Discord or stick to GitHub Discussions. One channel; not both.
- Cross-link from documentation to community resources.

Sustained engagement matters more than launch noise. A consistent quarterly release pattern over two years builds more reputation than any single launch event.

## Distribution

### Primary Distribution

- **PyPI:** `pip install weaver`. Versions published with each release.
- **GitHub:** source of truth, issues, releases, docs site via Pages.

### Secondary Distribution

- **Homebrew (Mac):** `brew install weaver-translator` post-v1.0, if maintenance burden is acceptable.
- **Conda-forge:** community-maintained if interest exists; not maintainer-driven.

### Anti-Distribution

- **Docker image:** unnecessary for a Python CLI; adds friction.
- **One-click installers:** mismatched with the technical audience.
- **App store listings:** the product is not an app.

## Content Strategy

Three content types, in priority order:

### Type 1: Documentation

The primary marketing surface. Every feature has docs. Docs include runnable examples. Docs are honest about limitations.

This is the bulk of GTM work. Treat docs as a product.

### Type 2: Release Notes

Each release has notes that:

- Describe what changed in plain language.
- Link to relevant issues.
- Note breaking changes prominently.
- Include before/after examples for visible UX changes.

Release notes are read more carefully than landing pages by the target audience.

### Type 3: Long-Form Posts

Occasional (one or two per year) posts about:

- Design decisions in Weaver (e.g., "Why Weaver doesn't have a chat UI").
- Translation workflow experiments.
- Comparisons between providers for JP literary translation.

Long-form posts attract the right audience and signal seriousness. Avoid clickbait titles. Avoid "10 reasons" listicle format.

## SEO Opportunities

Modest, targeted. Weaver does not compete for "AI translation tool" generally; that SERP is saturated and the wrong audience.

Target queries:

- "translate japanese light novel epub"
- "fan translation glossary tool"
- "japanese epub to english"
- "MTL workflow tool"
- "Ollama japanese translation"
- "resume translation after crash"
- "preserve epub structure when translating"

Strategy:

- README and docs site target these queries naturally through content, not keyword stuffing.
- A "comparison" docs page (Weaver vs. Sugoi vs. ChatGPT vs. DeepL) that is fair and honest.
- Long-form posts on the author's blog that link to the project.

Resist:

- Buying ads.
- Hiring an SEO consultant.
- Writing "10 best AI translation tools" listicles that mention Weaver.

## Referral Mechanics

Weaver has no built-in referral system and should not. Open-source tools spread through:

- Word of mouth in target communities.
- Tutorial posts and YouTube videos by users.
- Forum recommendations.

The maintainer's role:

- Make the tool good enough that users want to recommend it.
- Make it easy to share by having clean docs and clear examples.
- Thank contributors and amplifiers publicly.

No referral codes. No "share to unlock" features. No friend-invite flows.

## Viral Loops

There are no viral loops in this product. That is fine. Viral mechanics are for products with network effects; Weaver has none.

What Weaver has instead:

- A **trust loop**: each released novel produced with Weaver is implicit advertising. A translator credits the tool; readers notice. Slow but real.
- A **glossary loop** (potential future): if community glossaries become a feature, sharing them creates light viral motion. Weaver does not currently plan this because of moderation and legal concerns.

## Pricing Psychology

Weaver is free.

If `weaver cloud` is ever built (not planned), pricing would follow these principles:

- Honest, per-use or low monthly tier. Not "Enterprise: Contact Sales".
- No dark patterns. No annual billing tricks.
- The free CLI remains the full product. Cloud is an opt-in convenience.

## Conversion Funnel

There is no conversion funnel because there is no conversion.

What replaces a funnel:

| Step | Goal | Measurement |
|------|------|-------------|
| Discovery | User hears about Weaver | GitHub stars, Reddit mentions |
| Read README | User decides if it fits their need | Inbound links, time on README |
| Install | User runs `pip install weaver` | PyPI downloads (noisy but directional) |
| First successful translation | User produces a Markdown review | Self-reported on issues/discussions |
| Repeat use | User starts a second project | Self-reported |
| Advocacy | User recommends Weaver to others | Inbound issues mentioning referrers |

Track the qualitative signals. Ignore vanity metrics.

## Activation Strategy

A new user is "activated" when they successfully translate at least one chapter and produce a Markdown review file.

To increase activation:

- README quickstart must be reproducible in 10 minutes.
- First-run error messages must be helpful.
- `weaver init` on a known-good fixture must always succeed.
- Sample EPUBs (public domain) bundled with the repo for users without their own.
- A "first time" tutorial in docs that walks through every command on the bundled sample.

Activation should require zero account creation, zero billing setup, zero confirmation emails.

## Retention Strategy

For an open-source CLI, retention means users keep using it for new projects. Drivers:

- File format stability: a translator's existing `.weaver/` directory works with new versions forever.
- Release cadence: releases every 4–8 weeks signal the project is alive.
- Bug fix responsiveness: users do not abandon tools that respond to their issues.
- Feature additions that match real needs: chosen from `FEATURE_PRIORITY_MATRIX.md` based on user feedback.

What does not drive retention for this audience:

- Email newsletters.
- Push notifications.
- Gamification (badges, streaks).
- "Reminder to translate" prompts.

## Retention Loops

The natural retention loop:

1. Translator starts a new novel.
2. Runs `weaver init`.
3. Translates over weeks or months.
4. Finishes, exports EPUB.
5. Starts the next novel.

The maintainer's role is to keep step 5 friction-free. New project should feel as smooth as the first.

## Anti-Patterns To Avoid

Generic startup marketing advice that does not apply here:

- "Build an audience before you build the product." — Audience is the existing MTL community. Build the product first.
- "Launch on Product Hunt." — Wrong audience.
- "Get on the TechCrunch front page." — Wrong audience. They will not understand the product.
- "Hire growth marketers." — Single-maintainer open source. No.
- "Add in-app upsells." — There is no app.
- "Build a Discord with thousands of members." — Numbers do not equal engagement. Smaller, focused community works better.
- "Run paid ads on Reddit/Twitter." — Will not reach the target translator audience meaningfully.
- "Sponsor influencer videos." — Translator influencers do not exist meaningfully on YouTube.

## Cost Structure

Cash cost to run Weaver as a project, per year:

- Domain (optional): $15
- GitHub Pages: $0
- PyPI: $0
- Author time: substantial, unpaid
- Cloud testing (optional, if benchmarking): $50–200

Total: under $250/year. Sustainable indefinitely.

## Success Metrics (GTM)

Year one:

- 200+ GitHub stars.
- 50+ active users (loosely: people who file issues or contribute).
- 5+ external contributors with merged PRs.
- 3+ blog posts or videos by users.
- 1+ published translated novel produced with Weaver, where the translator credits the tool.

Year two:

- 1,000+ GitHub stars.
- 200+ active users.
- 20+ external contributors.
- 10+ published novels.
- Recognition in at least one major MTL community as a recommended tool.

Beyond year two:

- Whatever the community needs Weaver to be, within the scope defined in `PRD_v2.md` and `FUTURE_ROADMAP.md`.

## Closing Note

The best GTM for a niche open-source tool is to make the tool excellent. Marketing without product quality is friction. Product quality without marketing is slow but durable. Weaver should be slow and durable.
