# Weaver Final Verdict

Investor-style evaluation, with the caveat that Weaver is not a startup. The framing in the original prompt assumed it was. The honest evaluation requires reframing the question.

## The Two Questions

**Question 1: As a startup-shaped product, is Weaver investable or fundable?**

No.

**Question 2: As an open-source niche tool, is Weaver worth building?**

Yes.

The rest of this document explains both answers.

## Is This Differentiated?

**Verdict: Yes, within its niche.**

Within the JP fan-translation tooling space, Weaver's combination of:

- Manual glossary control with candidate extraction
- Segment-level resume safety
- EPUB roundtrip as a first-class output
- Local-first design with optional cloud provider

is genuinely differentiated. No other widely-used tool combines these four. The competitive landscape is:

| Tool | Differentiator | Weakness vs. Weaver |
|------|----------------|---------------------|
| Raw ChatGPT/Claude | Quality, ease | No glossary persistence, no resume, no EPUB output |
| Sugoi Translator | Free, fast, local NMT | No glossary, no LLM context, dated output |
| LunaTranslator | Real-time game/manga overlay | Wrong format for novels |
| DeepL | Polished cloud | No glossary control, no EPUB, cloud-only |
| Custom Python scripts | Fully custom | Not maintained, not shared |

The differentiation is real but narrow. The niche is small. This is fine — niche tools can succeed without being investable startups.

Outside the niche, Weaver is just one of many AI-assisted translation tools and would lose in any apples-to-apples comparison with funded competitors.

## Is This Realistically Buildable?

**Verdict: Yes, by one engineer in 10–20 weeks.**

The MVP-0 scope per `PRD_v2.md` is achievable. Risks:

- **Glossary candidate extraction quality.** Pinning an algorithm makes it buildable; making it good requires iteration.
- **EPUB renderer fidelity.** EPUB is a hostile format. The MVP target ("opens in Calibre, basic structure preserved") is realistic. Pixel-perfect roundtrip is not.
- **Provider reliability.** Local Ollama is unreliable at quality. DeepSeek adds cost but improves quality dramatically. The shift from Ollama-only to multi-provider is critical for shipability.

These risks are manageable for a competent Python engineer. They become hard if the engineer also has to learn Python ecosystem tooling concurrently.

## Is The UX Premium Enough?

**Verdict: N/A. The product is not premium.**

The original prompt's UX rubric assumed a polished consumer or SaaS product. Weaver is a CLI tool. The right UX bar is:

- Commands do what they say.
- Errors are useful.
- Progress is visible.
- Output is reviewable.
- Surprises are absent.

Against that bar, the PRD direction is competent. The redesigned `DESIGN_SYSTEM.md` standards (three-line error blocks, single progress line, plain status panels) are appropriate for the tool's shape.

The landing wireframe is a separate problem. It applies SaaS visual language to a CLI tool. Council corrected this in `BRAND_DIRECTION.md`. The wireframe should be cut or replaced.

## Is The Engineering Maintainable?

**Verdict: Yes, if discipline holds.**

The architecture in `SYSTEM_ARCHITECTURE.md` is appropriate-scale:

- SQLite over Postgres.
- Synchronous over async.
- Single-file CLI over microservices.
- ABC-based providers over plugin framework.

These choices are sustainable for one engineer over years. The temptation to over-engineer is significant (the original PRD already showed signs: "hosted scalability", "PostgreSQL migration"). `ENGINEERING_STANDARDS.md` codifies the discipline needed to avoid it.

Failure mode to watch: the maintainer rewriting parts of the codebase for elegance instead of function. The codebase will not get a chance to "stabilize" if it is rewritten quarterly.

## Is The AI Meaningful?

**Verdict: Yes, but it must be earned every release.**

The LLM is load-bearing. Translation is the product. The LLM provides translation quality.

What makes the AI meaningful here:

- LLM output is verifiable (the user reads the Markdown review).
- LLM output is overrideable (the user can edit any segment).
- LLM failure is visible (segments marked failed; visible in QA).
- LLM cost is visible (token tracking, pre-flight estimates).

What would make the AI meaningless:

- Hidden "AI-powered" features that produce vague output.
- Auto-applied "improvements" the user cannot inspect.
- Chat UI that obscures the actual workflow.
- Promises the model cannot reliably keep ("preserves character voice automatically").

`AI_SLOP_PREVENTION.md` codifies the discipline. The maintainer is responsible for upholding it.

## Would Users Genuinely Care?

**Verdict: A small number of users will care a lot.**

Translation tools are deeply personal. Fan translators settle on a workflow and use it for years. Weaver entering this space will:

- Be tried by 50–200 fan translators in year one.
- Be adopted as primary by perhaps 20–50 of them.
- Be abandoned by the rest after either: a bug they hit, a feature they need that Weaver doesn't have, or a translator preference for an alternative.

The 20–50 who stick will be vocal, helpful, and patient. They are the audience.

Most users elsewhere on the AI translation spectrum will not care. Casual users want one-click; Weaver is not that. Commercial users want enterprise; Weaver is not that.

## Biggest Risks

In order of probability and severity:

### 1. Maintainer Burnout

Open-source single-maintainer projects have a high mortality rate. Six months in, the maintainer has translated their own novel, learned everything Weaver had to teach, and faces support burden disproportionate to fun.

Mitigation:

- Aggressive scope discipline (this is what `FUTURE_ROADMAP.md` enforces).
- Set support boundaries early (issue response within 72h is the cap; not 24h).
- Communicate honestly about pace.
- Welcome contributors who share the product vision.

### 2. Local LLM Quality Insufficient

Ollama running 14B models produces middling JP literary translation. If users try Weaver with Ollama-only setups and the output is worse than free ChatGPT, they leave.

Mitigation: DeepSeek provider at MVP-0 (Council correction). Users see quality immediately.

### 3. Legal Takedown

Translating copyrighted Japanese novels into English without rights is widespread but legally exposed. A maintainer named on a notice could face real consequences.

Mitigation:

- Tool framed as tool-only, not service.
- No upload features, no hosted content, no community sharing of translated works.
- Strong disclaimer in README.
- Fixture data uses public domain only.
- No example in docs shows a copyrighted novel by name.

This is not a complete defense. It is a reasonable posture.

### 4. Glossary Extraction Quality

If glossary candidates are mostly noise, users reject them all and the differentiating feature dies. Quality of candidate extraction is the make-or-break differentiator.

Mitigation: pinned algorithm in `PRD_v2.md`, iteration with real users, quality benchmarks committed to the repo.

### 5. Roadmap Creep

The original PRD listed 40+ deferred features. The temptation to build them is real. Each one adds maintenance burden and dilutes the product.

Mitigation: `FEATURE_PRIORITY_MATRIX.md` is enforced. New features require user-evidence gates. KILL list is binding.

## Biggest Opportunities

In order of leverage:

### 1. Glossary Workflow Depth

No tool has invested seriously in the glossary workflow. Weaver can own this space. Each iterative improvement (better extraction, better diffing, better conflict resolution) compounds.

### 2. EPUB Roundtrip Quality

EPUB is hated for a reason: it is hard. Weaver becoming the obvious choice when EPUB output matters is a real moat.

### 3. Documentation As Marketing

Most translation tools have bad docs. Weaver's docs can be the marketing surface. Investment here is durable.

### 4. Community Trust In MTL Spaces

The MTL community is small, tight, and skeptical. Earning trust takes years. Once earned, recommendations propagate.

### 5. Architecture-Compatible With Future Hosted Direction

`SYSTEM_ARCHITECTURE.md` is designed so that, if the maintainer ever wanted to add a hosted service (against current intent), the layers do not require a rewrite. This is option value, not a commitment.

## Execution Probability

Given:

- Clear MVP-0 scope.
- Realistic 10–20 week timeline for one engineer.
- Stable architecture decisions.
- Disciplined feature matrix.
- No outside pressure to ship by a date.

Estimate: **60–70% probability of shipping v0.1.0** within 6 months, assuming continuous maintainer engagement.

Reasons it might not ship:

- Maintainer interest fades after 2–3 months (common).
- Hits a hard problem in EPUB roundtrip and stalls.
- Decides to rewrite in another language.
- Real-life priorities shift.

Reasons it likely will ship:

- Scope is small enough to be tractable.
- Author has skin in the game (presumably wants to translate a specific novel).
- Architecture is sound.
- Community of one matters less than community of zero.

## Final Brutal Recommendation

**Ship Weaver as an open-source CLI tool. Do not try to be a startup.**

Specific guidance:

1. **Cut the SaaS framing entirely.** Remove the hosted-scalability section from the PRD. Remove the landing page wireframe in its current form. Stop positioning the product as something investors would fund.

2. **Ship DeepSeek at MVP-0.** Ollama-only ships dead.

3. **Pin the glossary candidate extraction algorithm.** The vague description in the original PRD is the single most likely point of failure.

4. **Drop "Careful mode" entirely until built.** A config flag for an unbuilt feature is theater.

5. **Cut Phase 3 from the roadmap.** Six speculative product directions in one document is roadmap delusion.

6. **Invest in documentation as if it were product code.** This is the actual marketing.

7. **Set support boundaries before launching.** Burnout is the highest risk.

8. **Be honest about the project's smallness.** This audience appreciates honesty.

9. **Resist every temptation to add chat UI, AI agent framing, or community sharing features.**

10. **Plan for the maintainer enjoying the project in five years, not for hypothetical hyper-scale.**

## What Must Happen Before Launch

The non-negotiables:

- [ ] DeepSeek provider works end-to-end.
- [ ] Ollama provider works end-to-end.
- [ ] FakeProvider passes CI without external dependencies.
- [ ] Resume after kill -9 succeeds.
- [ ] Glossary review interactive CLI works.
- [ ] Glossary conflict halts translation.
- [ ] Manual edit command works.
- [ ] Markdown export with source+translation works.
- [ ] EPUB output opens in Calibre.
- [ ] README quickstart reproducible by a fresh user in 10 minutes.
- [ ] Three-line error blocks consistent across CLI surfaces.
- [ ] Token cost visible for cloud providers.
- [ ] Five ADRs documented.
- [ ] No `# TODO` or `# FIXME` without linked issue.
- [ ] Performance budgets met (per `SECURITY_AND_PERFORMANCE.md`).
- [ ] Legal disclaimer in README clear and prominent.
- [ ] Fixture EPUBs use public domain content only.

## Closing

Weaver is a worthwhile project. It is not a startup. The maintainer should build it because they want the tool to exist, not because they want to raise money or build a company.

If shipped with the scope, discipline, and posture described across these documents, Weaver can:

- Serve a small but real audience.
- Earn trust over years.
- Stay small enough to remain enjoyable to maintain.
- Avoid the AI Slop traps that plague this category.

If the maintainer drifts toward startup ambitions — hosted versions, paid tiers, investor narratives — the product loses focus, the audience loses trust, and the maintainer loses the project.

**Stay small. Ship reliably. Respect the work.**
