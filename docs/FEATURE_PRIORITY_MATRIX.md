# Weaver Feature Priority Matrix

Every feature in the original PRD plus features added during Council review, ranked by build priority.

## Methodology

Each feature is scored on:

- **User value** (0–5): how much it matters to the target translator user.
- **Complexity** (0–5): build cost, 5 being highest.
- **Retention impact** (0–5): does this make users come back.
- **Monetization impact** (0–5): N/A for most; included for future reference.
- **AI Slop risk** (0–5): how likely this feature is to look impressive but produce nothing.

Decision categories:

- **MUST HAVE** — MVP-0 blocker.
- **SHOULD HAVE** — MVP-1, real value, deferred only by capacity.
- **NICE TO HAVE** — future, may or may not ship.
- **KILL IMMEDIATELY** — should not be built. Often AI Slop.

## MUST HAVE (MVP-0)

| Feature | UV | C | R | M | Slop | Reasoning |
|---------|----|---|---|---|------|-----------|
| EPUB reader producing DocumentIR | 5 | 3 | 5 | 0 | 0 | Foundation. Without it, nothing works. |
| Paragraph segmentation with stable IDs | 5 | 2 | 5 | 0 | 0 | Foundation. Resume safety depends on this. |
| SQLite state store with WAL + transactions | 5 | 2 | 5 | 0 | 0 | Resume safety = primary moat over raw ChatGPT. |
| OllamaProvider | 4 | 2 | 4 | 0 | 1 | Free option matters for budget users. |
| DeepSeekProvider (cloud, cheap) | 5 | 2 | 4 | 0 | 1 | Quality floor. Local-only ships dead. |
| FakeProvider for tests | 5 | 1 | 0 | 0 | 0 | Untestable code is dead code. |
| JSON-output parser with one repair retry | 5 | 2 | 4 | 0 | 0 | LLM output reliability layer. |
| Glossary candidate extraction (per algorithm) | 5 | 4 | 5 | 0 | 2 | Differentiator. Must be specified, not vague. |
| Interactive glossary review CLI | 5 | 3 | 5 | 0 | 0 | Where translators actually spend time. |
| Glossary conflict detection | 4 | 2 | 4 | 0 | 0 | Quiet bugs are worse than loud ones. |
| Translation orchestrator with resume | 5 | 3 | 5 | 0 | 0 | The core workflow. |
| Previous-segment context | 4 | 1 | 3 | 0 | 0 | Cheap, real quality lift. |
| Rolling 5-segment chapter window | 4 | 2 | 4 | 0 | 1 | Replaces "chapter-level placeholder" vagueness. |
| Approved-glossary injection in prompt | 5 | 2 | 5 | 0 | 0 | Whole point of the glossary. |
| Honorific policy: preserve | 4 | 1 | 3 | 0 | 0 | Ship one mode well. |
| Markdown export with source+translation | 5 | 2 | 5 | 0 | 0 | Primary review surface. |
| Failed/stale segment markers in Markdown | 4 | 1 | 4 | 0 | 0 | Without this, QA is invisible. |
| EPUB renderer with basic preservation | 5 | 4 | 5 | 0 | 0 | The output users actually want. |
| Manual segment edit command | 5 | 2 | 5 | 0 | 0 | Trust requires correctability. |
| Deterministic QA: empty, JP-residue, length, glossary mismatch, failed, stale | 4 | 2 | 4 | 0 | 0 | Cheap, valuable signals. |
| Project.toml config (pydantic-validated) | 4 | 1 | 3 | 0 | 0 | Single source of project config. |
| Exit codes per PRD table | 3 | 1 | 2 | 0 | 0 | Scriptability for power users. |
| Three-line error blocks (problem/cause/next) | 5 | 1 | 4 | 0 | 0 | Most-felt UX win for almost no cost. |
| API keys via env vars only | 5 | 1 | 0 | 0 | 0 | Security baseline. |

## SHOULD HAVE (MVP-1)

| Feature | UV | C | R | M | Slop | Reasoning |
|---------|----|---|---|---|------|-----------|
| `weaver new` interactive wizard | 4 | 3 | 3 | 0 | 1 | Nice for first-timers; not a blocker. |
| Honorific policy: localize, hybrid | 4 | 2 | 3 | 0 | 1 | Demand exists; ship after `preserve` proves out. |
| EPUBCheck integration | 4 | 3 | 3 | 0 | 0 | Catches reader-breaking output. |
| Rich status dashboard (color, panel) | 3 | 2 | 3 | 0 | 2 | Skip until plain-text version is sufficient. |
| Chapter summary memory | 4 | 4 | 4 | 0 | 3 | Real quality lift; needs care to not become Slop. |
| Character voice memory | 4 | 5 | 4 | 0 | 4 | High value if real; high Slop risk if vibes-based. |
| Retry-failed segment command | 4 | 2 | 4 | 0 | 0 | Genuinely useful. |
| Better progress reporting (segments/min, ETA) | 3 | 2 | 3 | 0 | 0 | Quality-of-life. |
| Glossary diff across chapters | 5 | 3 | 5 | 0 | 0 | **Signature feature.** Real moat. |
| Style drift detector | 4 | 4 | 3 | 0 | 3 | Real if scoped tight; vapor if not. |
| Markdown diff view between runs | 3 | 3 | 3 | 0 | 0 | Useful when re-running with new models. |
| TMX import/export | 4 | 3 | 3 | 0 | 0 | Pro-translator credibility. |
| TUI dashboard (Textual) | 2 | 4 | 2 | 0 | 3 | Optional; CLI is enough. |
| Telemetry opt-in (anonymous) | 3 | 3 | 1 | 0 | 1 | Only if user count justifies it. |

## NICE TO HAVE (Future, No Commitment)

| Feature | UV | C | R | M | Slop | Reasoning |
|---------|----|---|---|---|------|-----------|
| Additional cloud providers (Gemini, Claude, OpenAI) | 3 | 2 | 3 | 0 | 1 | Add on demand from real users. |
| EN→ID target | 4 | 4 | 3 | 0 | 1 | Real audience exists in Indonesia. Defer until JP→EN proves out. |
| Web Novel ingestion (scraper) | 3 | 5 | 3 | 0 | 2 | Legal exposure high. Build careful or skip. |
| Bilingual EPUB output | 3 | 3 | 3 | 0 | 1 | Niche-but-real audience. |
| Local Web UI | 2 | 5 | 2 | 0 | 4 | High Slop risk. CLI is enough. |
| Translation memory diffing against published official translations | 4 | 4 | 4 | 0 | 1 | Signature feature if executed right. |
| EPUB roundtrip fidelity report | 4 | 3 | 3 | 0 | 0 | Trust through measurement. |
| Project versioning (compare multiple translation runs) | 4 | 3 | 4 | 0 | 0 | Power-user feature, real value. |
| Prompt template library (community shared) | 3 | 3 | 2 | 0 | 2 | Likely to attract bad prompts. |

## KILL IMMEDIATELY

These should not be built. Most are AI Slop or premature scaling theater.

| Feature | Reasoning |
|---------|-----------|
| Hosted multi-user service | Out of scope per `PRD_v2.md`. Different product. |
| PostgreSQL migration path | Scaling for hypothetical 10k users while still hunting first 10. |
| API quota and billing tracking | Premature. No paid product exists. |
| Object storage for EPUBs | Local CLI does not need cloud storage. |
| Multi-stage prompt routing per quality mode | Configuration theater. One mode shipped well > four modes promised. |
| "Careful mode" config flag at MVP-0 | Flag for an unbuilt feature. Pure feature theater. |
| Prompt profiles (user-saved prompt variants) | Splits the userbase into incompatible workflows. |
| Cloud adapter generic abstraction layer | OpenAI-compatible covers 80%. Ship adapters, not frameworks. |
| Korean source language support | Different problem space. Build a separate tool if ever. |
| PDF input | Different problem space. Different domain. |
| Fine-tuned model experiments | Capacity-burning research with low product value. |
| Collaborative editing | Wrong shape for the tool. |
| Community glossary sharing | Quality moderation nightmare. Legally exposed. |
| Hosted translation queue | Hosted service, see above. |
| Built-in payment integration | No paid tier exists. |
| Mobile app | Wrong device for translators. |
| Browser extension overlay translator | Different product (LunaTranslator already does this). |
| AI-generated cover art for translated EPUBs | Pure Slop. Translators want the original art. |
| LLM-generated chapter summaries for output EPUB | Slop. Adds AI-generated content to user output without consent. |
| Voice/audio narration of translation | Wildly off-mission. |
| "AI agent" framing where Weaver "decides" workflow | Hides the deterministic workflow behind a chat illusion. |
| Chat-style UI for "talking to your novel" | The wrong product. |
| Discord bot integration | Solves no real problem. |
| GitHub-style social feed of translation projects | Audience does not exist. |

## Decision Logic Summary

A feature graduates from KILL or NICE to SHOULD or MUST when:

1. Real users (not hypothetical) ask for it three or more times via issues or direct messages.
2. The feature has clear scope and acceptance criteria.
3. The feature does not require infrastructure beyond what MVP-0 already needs.
4. The feature's AI Slop risk score is below 3, or the user value is 5 and the AI Slop risk is mitigable with explicit scope.

A feature that scores high on AI Slop risk and low on user value is rejected on sight.

## Honorable Mentions: Almost-MUST

These were considered for MUST HAVE but cut to keep MVP-0 shippable:

- **Glossary diff across chapters.** Signature feature but MVP-0 ships without it. Promoted to first MVP-1 release.
- **Manual segment edit command.** Made it to MUST HAVE only after Council review revealed that the original PRD had no edit path. This was a near-miss.
- **DeepSeek provider.** Original PRD said Ollama-only at MVP-0. Council corrected this. Now MUST HAVE.

## Features That Sound Important But Aren't (Yet)

- **Detailed token usage analytics.** Not a translator pain. Defer.
- **Auto-update notifications.** PyPI handles this; users `pip install -U weaver`.
- **Profile management.** One tool, one workflow. No profiles needed.
- **Multi-project workspace.** Each project is a folder. The user's filesystem is the workspace.
- **Export to Word/PDF/HTML.** Markdown is the universal interchange format. Other formats follow downstream tools, not Weaver.

## Re-evaluation Cadence

This matrix is re-evaluated after each major release. Features can move between categories based on:

- User feedback signal.
- Maintainer capacity.
- Strategic shifts (rare; document in ADRs if it happens).
