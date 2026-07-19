# Weaver

Offline-capable, glossary-aware **JP→EN light-novel translation workbench** with a **CLI** and local **web cockpit**. Development is **web-cockpit-first**, with the CLI serving as a supporting interface for automation and power-user workflows.

**Not a SaaS platform, consumer-facing product, hosted service, collaborative platform, or complex SPA.**

> **Operating Manual:** This repository follows the global agent workflow defined in `@WORKFLOW.md`. This document serves as the repository-level coordination layer and references supporting documentation rather than duplicating strategy, process, or implementation details.
>
> **Current Orchestrator:** Repository Owner (Trancend1) + Claude acting as Lead Technical Orchestrator.
>
> **Current Phase:** **v0.7.3 — Performance & Reliability Release (in progress; M1+M2+M3 done).** v0.7.2 is tagged; audit blockers H1–H3 merged via PR #56. Sources of truth: [execution plan 2026-07-05](docs/superpowers/specs/2026-07-05-v073-performance-execution-plan.md) + [ADR 020 draft](docs/decisions/020-bounded-translate-concurrency.md) (Proposed) + **[measured audit 2026-07-13](audit_weaver_073.md)** (verifies F1–F8/A1–A8 against current code and adds findings **N1–N8** with real measurements — absorbed into the §2.3 milestones).
>
> **Status:** **M1+M2+M3 complete, none merged/pushed.** M1 on `perf/v073-storage-quick-wins` (`ef3bbe3`/`fe4a1c2`/`eeb63ee`); M2 on `fix/v073-audit-carryforward` (stacked on M1; `631ce46`…); **M3 on `feat/v073-enforcement-provenance`** (stacked on M2; `a898753`…`f735406`, one commit per slice) closes A4a/A4b/A5 + F6/N2/N7. Gates green 2026-07-18 (ruff / format / pyright clean; **full suite 1683 passed, 1 skipped**; bench all budgets PASS incl. flat cost **0.97×**; acceptance gate AC-1…AC-9 PASS). Schema now **v14** (enforcement provenance columns on `translations`). ADR 020 must be Accepted before M4 (concurrency). **Next: owner decision at M3 exit — ship M4 in v0.7.3 or slip to v0.7.4; then M5.** Merge order: M1 PR → M2 PR → M3 PR.

> **Current Objective:** Execute the v0.7.3 milestones in order (M1 bench-baseline + storage/algorithmic quick wins ✅ → M2 reliability + input-safety carry-forward ✅ → M3 enforcement provenance + honest cost accounting ✅ → **M4 bounded concurrency (blocked on ADR 020; may slip to v0.7.4 — owner decision)** → M5 validation/release gate). One milestone = one branch = one PR.
>
> **Current Sprint:** v0.7.3 (§2.3). After v0.7.3: **Cross-Platform Desktop (macOS/Linux)** with a fresh plan + ADR (§2.1.1).

---

## 1. Documentation Map

Docs are the spec. Code follows docs. If code contradicts docs, ask first.

| Topic                                                        | Source of truth                                                                                                                                                                                                              |
| ------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| User-facing: install, quickstart, commands                   | [README.md](README.md)                                                                                                                                                                                                       |
| Navigation supplement — module map, CLI/web flow, data, deps | [docs/CODEMAPS/architecture.md](docs/CODEMAPS/architecture.md) · [backend](docs/CODEMAPS/backend.md) · [frontend](docs/CODEMAPS/frontend.md) · [data](docs/CODEMAPS/data.md) · [dependencies](docs/CODEMAPS/dependencies.md) |
| Runtime contract for Tauri (or any) host shell               | [docs/SIDECAR_CONTRACT.md](docs/SIDECAR_CONTRACT.md)                                                                                                                                                                         |
| Testing, regression, release, migration discipline           | [docs/MAINTENANCE.md](docs/MAINTENANCE.md)                                                                                                                                                                                   |
| Architecture decisions (ADR `001`–`020`)                     | [docs/DECISIONS.md](docs/DECISIONS.md) · [docs/decisions/](docs/decisions/)                                                                                                                                                  |
| Active reference specs                                       | [docs/PROMPT_DESIGN.md](docs/PROMPT_DESIGN.md) · [docs/SECURITY_AND_PERFORMANCE.md](docs/SECURITY_AND_PERFORMANCE.md)                                                                                                        |
| Historical sprint archive (pre-v0.7.3; not authority)       | [docs/SPRINT_HISTORY.md](docs/SPRINT_HISTORY.md)                                                                                                                                                                             |
| RTK shell tooling rule                                       | `C:\Users\transcend\.claude\RTK.md`                                                                                                                                                                                          |
| Global workflow template (this file follows it)              | `C:\Users\transcend\.claude\WORKFLOW.md`                                                                                                                                                                                     |

**Hierarchy:** `docs/CODEMAPS/` is the primary navigation supplement (module map, CLI/web workflows, data flow, dependencies). ADRs and active sprint docs are source of truth for decisions. `SIDECAR_CONTRACT.md`, `MAINTENANCE.md`, `PROMPT_DESIGN.md`, and `SECURITY_AND_PERFORMANCE.md` remain as detailed reference docs for their respective domains. `.reports/` is an audit/report artifact area; do not treat it as product or architecture authority.

---

## 2. Progress — Phase Schedule

### 2.1 Roadmap Snapshot

Current status: **active phase defined in §2.3**.

| Sprint                                                    | Status           | Hasil utama                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| --------------------------------------------------------- | ---------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Foundation → v0.7.1 desktop track** (Audit Cleanup, Q2C–Q2F, Sprint N/O/P, Desktop Installer & Release Hardening) | ✅ Done | Hardened core → self-contained Windows desktop alpha → NSIS installer → **v0.7.1 released via tag-triggered CI**. Standing deferred: code-signing cert (ADR 017 — `WINDOWS_CERTIFICATE_THUMBPRINT` enables, no code change). Detail: [docs/SPRINT_HISTORY.md](docs/SPRINT_HISTORY.md) + ADR 016/017. |
| **v0.7.2 — Connection-First Routing + Enforcement Loop** | ✅ Done / tagged | ADR 018 (one `openai_chat`+`fake`, connection registry, per-segment routing/fallback, discovery cache, CLI parity) + ADR 019 (enforcement loop E1–E4, anti-slop). Post-release audit 2026-07-05: 3 High fixed, merged via PR #56; Medium/Low carry-forward absorbed into v0.7.3. Detail: git history, ADR 018/019, handoffs. |
| **v0.7.3 — Performance & Reliability**                    | 🔜 Active (planned) | Execution plan + ADR 020 draft (2026-07-05, Gate A) + **measured audit 2026-07-13** ([audit_weaver_073.md](audit_weaver_073.md): F/A findings verified on current code, N1–N8 added). M1 bench-baseline fix + storage/algorithmic quick wins → M2 reliability + input-safety carry-forward → M3 enforcement provenance + honest cost accounting (migration v14; M1.5 took v13 for the glossary-candidates index) → M4 opt-in bounded concurrency (ADR 020, default 1) → M5 validation/live checks/release gate. See §2.3/§2.4. |
| **Cross-Platform Desktop (macOS/Linux)**                  | 📋 Planned       | WKWebView (macOS) + WebKitGTK (Linux) session-header injection and POSIX graceful shutdown (SIGTERM), plus per-OS bundled sidecar. See §2.1.1.                                                                                                                                                                                                                                                                                                                                                                                                                               |
| **Desktop Optimization**                                  | 📋 Backlog       | onedir→onefile or payload trim and cold-start budget tuning, only after the installer ships and with evidence. See §2.1.1.                                                                                                                                                                                                                                                                                                                                                                                                                                                   |

Legend: ✅ complete · 🟡 pass-with-conditions · 🔜 next · 📋 planned/backlog · ⏭️ blocked · 🚫 deferred

Completed work is historical. Keep detailed evidence in git history, ADRs, sprint plans, validation notes, and handoff docs. This operating file should only preserve information needed to guide current and future work.

When starting a new sprint or phase:

- Update §2.1 with the current status.
- Define the active scope in §2.3.
- Define exit criteria in §2.4.
- Add only durable carry-forward lessons to §2.5.
- Do not continue old sprint scaffolding by default.

### 2.1.1 Deferred / Backlog (not yet scheduled)

Evidence-linked carry-forward. These are proposals, not active scope: each needs its own plan (and an ADR where it changes packaging shape, the stack, or a contract) before implementation. Do not scaffold ahead of a plan.

**Next planned sprint — Cross-Platform Desktop (macOS/Linux):** WKWebView/WebKitGTK session-header injection (`desktop/src/webview_session.rs` is a `#[cfg(not(windows))]` no-op today), POSIX graceful shutdown — SIGTERM before SIGKILL (`desktop/src/sidecar.rs`), per-OS bundled sidecar. Needs a fresh plan + ADR before any code. **Desktop Optimization** (onedir→onefile, payload/cold-start tuning) stays backlog behind it. Completed desktop-track history + durable desktop lessons: [docs/SPRINT_HISTORY.md](docs/SPRINT_HISTORY.md).

**Product / feature backlog (deferred by their ADRs, no owner schedule yet):**

| Item                                   | Source of truth                                      | Status                                            |
| -------------------------------------- | ---------------------------------------------------- | ------------------------------------------------- |
| OCR implementation beyond the contract | ADR 012 + `services/ocr_contract.py` (contract only) | Deferred feature; reopen with a plan              |
| Per-chapter QA tree badges             | ADR 008 (deferred to avoid full novel-scope scan)    | Deferred UX; gate on render-path budget (Gate B1) |
| QA `error` severity tier               | ADR 013 (**Rejected / Deferred**)                    | Do **not** plan unless explicitly reopened        |
| Provider-complete cost auditing        | ADR 014 (out of scope)                               | Reopen only with a migration + ADR                |
| Inline-markup preservation on EPUB export (audit N6: `_replace_text` flattens `<em>/<br/>` in translated blocks) | [audit_weaver_073.md](audit_weaver_073.md) §2 · `renderers/epub.py:234-237` | Deferred quality item; needs design + translation-quality eval, not a quick fix |
| Furigana reading as optional IR/prompt annotation (audit N8: `<rt>` dropped on import) | [audit_weaver_073.md](audit_weaver_073.md) §3 · `readers/epub.py:1429-1448` | Deferred; must pass §4.3 gate 1 (real pain evidenced) first |

**Permanently out of scope unless an ADR reopens (CLAUDE.md §3.4/§3.5):** new provider families, route rewrites, SPA migration, Node build pipeline, external queue/worker daemon, cloud sync, telemetry/phone-home, multi-user SaaS architecture.

### 2.2 Reusable Phase Gate

Before starting any new sprint, phase, or stage:

1. **Define scope** in §2.3, including acceptance criteria and explicit non-goals.
2. **List exit criteria** in §2.4 in plain language.
3. **Verify each criterion** with a concrete command, test, file check, or manual inspection.
4. **State user-facing status:** usable now, internal-only, not yet user-facing, or blocked.
5. **If all pass** — update §2.1 / §2.3 / §2.4 / §2.5 and write a handoff note.
6. **If any fails** — mark blocked, record missing proof, and stop.

> Required reminder: **Check exit criteria first. No next stage until evidence exists. Explain the detail for manual inspection.**

### 2.3 Active Phase — v0.7.3 Performance & Reliability Release (planned; audit-verified; implementation not started)

**Sprint focus:** measurable translation-pipeline performance (throughput, scalability, cockpit latency) + closure of the full audit ledger — v0.7.2 carry-forward **A1–A8** plus the 2026-07-13 measured-audit findings **N1–N8**. No feature ships unless it directly improves speed, accuracy, reliability, or maintainability.

**Sources of truth:** [`2026-07-05-v073-performance-execution-plan.md`](docs/superpowers/specs/2026-07-05-v073-performance-execution-plan.md) (F1–F8/A1–A8 anchors, per-milestone slices/acceptance) + [ADR 020](docs/decisions/020-bounded-translate-concurrency.md) (**Proposed** — must be Accepted before M4) + [`audit_weaver_073.md`](audit_weaver_073.md) (2026-07-13: measured evidence, N1–N8 anchors, reproducible probes). Do not re-derive findings; the anchors are in those documents.

**Measured baseline (2026-07-13, owner machine — the numbers the milestones must beat):**

- Rolling-window CTE (F2): 0.98 ms @1k → **48.1 ms @50k** translation rows per query; chapter-scoped variant **0.18 ms @50k** (−99.6%).
- Commit cost (F3): `synchronous=FULL` (today) **1.325 ms** vs `NORMAL` **0.031 ms** (43×); ≥2 commits/segment.
- Fresh 10k-segment fake run: **72.9 s** total; per-segment growth **1.96×** (first-100 6.89 ms → last-100 13.50 ms) — the "<20% delta" exit criterion currently fails at 96%.
- The bench harness cannot reproduce these numbers itself until N1 is fixed (audit probes are the interim reference).

**Milestones (one milestone = one branch = one PR, in order; audit N-findings are grouped into the milestone that already touches the same seam):**

| Milestone | Scope | Status |
| --- | --- | --- |
| **M1 — Bench baseline + storage/algorithmic quick wins** (P0, `perf/v073-storage-quick-wins`) | **Slice 1 = N1 (prerequisite for every baseline claim):** fix the broken bench harness — `_rewrite_project_for_fake` (`bench/run_performance_budgets.py:239`) string-replaces `type = "deepseek"` but v0.7.2 `weaver init` writes `[provider] type = ""`, so translate/export budgets no-op; write the fake provider block explicitly. Then: `PRAGMA synchronous=NORMAL` + read-only pragmas (F3); O(n²) rolling-window CTE scoped to chapter, **both** call sites incl. `list_export_segment_states` (F2); `list_connections`/secrets single-parse (F4); `discover_projects` render/queue-poll dedupe under the existing 5 s cache (F5); casefold hoists + `executemany` + `idx_glossary_candidates_project` + `table_info` cache (F7). Bench additions: flat-cost probe (target growth < 1.2×) + render budgets; delete the fictional "glossary LRU cache" doc claim. | ✅ **Done** (`ef3bbe3`/`fe4a1c2`/`eeb63ee`; not merged). N1 restored; flat-cost **1.009×**; queue poll 1 DB-open/project (warm). Two deviations: index took migration **v13** (M3→v14); `table_info` guard **retained** (pre-v9 read safety, not a hot loop) instead of cached; `workspace_index._CacheKey` unified onto the discovery key. |
| **M2 — Reliability + input-safety carry-forward** (P0, `fix/v073-audit-carryforward`) | Corrupt-TOML write-guard/backup + shared `_escape` incl. control chars (A2+A7); dead-primary → fallback-aware pre-flight (A1); legacy brand preserved in attempt history (A3); `weaver inspect` via routing resolution (A8). **Grouped input-safety (same reliability concern, small guards + tests):** apply `MAX_UPLOAD_BYTES` to `/projects/epub-preview` (N3, `api/routers/projects.py:95-100`); zip-decompression ceiling via manifest `file_size` sum before `read_epub` (N4 — `_archive_info` already reads it); per-chapter import degradation for malformed XHTML (N5 — Gate B decision: broken chapter = validation issue, not whole-book failure). | ✅ **Done** (`631ce46`…`da1dd02`; not merged — branch stacks on M1). Gate-B decisions settled: A2+A7 = **move-aside backup + ConfigError naming the backup** (retry writes fresh); A1 warning carried on plan/result/summary + CLI echo + job terminal events; N5 skip fires only for content unparseable even after ebooklib/lxml repair. Found + folded a **4th** `_escape` copy (`services/project.py`). Handoff: [2026-07-14](docs/superpowers/handoffs/2026-07-14-v073-m2-audit-carryforward.md). |
| **M3 — Enforcement provenance + honest cost accounting** (P1, `feat/v073-enforcement-provenance`) | Detection ungated from `enforce_repair` (A4a); verdicts/repair outcomes persisted (migration v14 — M1.5 shipped v13 for `idx_glossary_candidates_project`, `SCHEMA_VERSION` already 13; columns on `translations`) + row/summary token reconciliation (A4b+A5); explicit `max_retries` on the OpenAI client **and** resolve the dead `[translation] max_retries` init key — wire it or delete it (F6+N2, `services/project.py:350`); repair/JSON-repair call counts in the run summary. **Grouped accounting accuracy:** CJK-aware token estimator (N7 — `chars//4` undercounts JP ~3×; two-class heuristic, no new dependency) + recalibrate `MAX_CONTEXT_TOKENS` afterwards. | ✅ **Done** (`a898753`…`f735406`; not merged — stacks on M2). Gate-B decisions settled: provenance = **columns on `translations`** (violations JSON with NULL="not evaluated", `repair_attempted`/`repair_outcome`/repair token columns); row tokens = **primary call only**, repair spend split out ⇒ `sum(rows) == summary` exact, test-pinned; N2 = **delete** `[translation]` key **and** pin `[provider] max_retries` (default 2, explicit); N7 `MAX_CONTEXT_TOKENS` 600→**1000** honest tokens (typical 5-pair window preserved, worst-case halved). JSON-parse repair now sums usage across both calls + is counted. Handoff: [2026-07-18](docs/superpowers/handoffs/2026-07-18-v073-m3-enforcement-provenance.md). |
| **M4 — Bounded translate concurrency** (P1, `feat/v073-bounded-concurrency`) | Opt-in `[translation] max_concurrent = 1..4` (default 1 = today bit-for-bit); FakeProvider latency knob first; per-worker connections; locked cold-mark. **Blocked on ADR 020 Accepted.** | ⏭️ |
| **M5 — Validation & release gate** (P0, `chore/v073-release-gate`) | Bench + acceptance gate with before/after evidence vs the measured baseline above; live Gemini (`…/v1beta/openai`, current model — `gemini-1.5-flash` retired) + first `requires_ollama` test; E2 repair token-cost delta; concurrency live spot-check; manual `epubcheck` on export artifacts (audit rec — dev-tooling, no runtime dependency); optional py-spy session on `weaver serve` during a batch run (memory-leak evidence gap); CHANGELOG/version/tag `v0.7.3`. | 📋 |

**Non-goals (fenced):** streaming responses (strict-JSON makes it perceived-latency-only — owner-confirmed defer); circuit breaker/health scores/presets/ledger (D9); fuzzy TM; asyncio outside web; external queue; new provider families; speculative cache layers (fix the callers instead); Aho-Corasick glossary matching (no evidence of >5k-term glossaries; cap-20 early-exit bounds today's cost); inline-markup export preservation (N6) + furigana annotation (N8) — deferred to §2.1.1; deferred memory items (upload full-buffering beyond the N3/N4 guards, EPUB zip re-opens, DOCX in-memory build — no scaffolding).

**Next:** M1+M2+M3 done — **M3 exit reached: owner decides whether M4 (bounded concurrency) ships in v0.7.3 or slips to v0.7.4.** M4 requires ADR 020 **Accepted** first; either way M5 (`chore/v073-release-gate`) closes the release.

### 2.4 Exit Criteria

#### v0.7.3 Performance & Reliability exit — 📋 OPEN (defined 2026-07-05; tightened by the 2026-07-13 audit)

v0.7.3 ships only when every criterion below has concrete evidence (bench output, test run, or owner-confirmed live check) recorded in the milestone handoffs:

- [x] **Baseline restored (N1)** — M1: bench runs end-to-end; both harnesses fixed. Full suite 1624 passed; all budgets PASS; acceptance gate AC-1…AC-9 PASS.
- [ ] **Throughput:** `max_concurrent = 3` ⇒ ≥ 2.4× chapter wall-clock vs sequential on the latency-simulating FakeProvider bench; live spot-check confirms ≥ 2×. _(Waived if M4 slips to v0.7.4 by explicit owner decision at M3 exit.)_
- [x] **Scalability** — M1.2: rolling-window flat cost **1.009×** on the 10k fixture (was 1.96×), bench flat-cost probe green.
- [x] **Cockpit latency** — M1.3/M1.4: ≤ 1 `connections.toml`/`secrets.toml` parse per render; queue poll ≤ 1 DB open per project (warm), both asserted via counting-seam tests.
- [x] **Reliability** — ~~corrupt `connections.toml`/`secrets.toml` is never silently destroyed (backup-before-rewrite tested)~~ ✅ M2.1; ~~dead primary with a healthy fallback completes the run~~ ✅ M2.2 (e2e-tested); ~~enforcement verdicts/repair outcomes persisted + surfaced~~ ✅ M3 (migration v14; CLI/job JSON/history partial + `/translations` endpoint; old rows render "not evaluated").
- [x] **Input safety (N3/N4/N5)** — M2: preview upload cap (422 + shared `ensure_upload_within_limit`); declared-uncompressed ceiling 1 GiB before parse (`MAX_UNCOMPRESSED_BYTES`); per-chapter degradation via `DocumentIR.read_issues` surfaced by CLI/API/runtime log — each with regression tests.
- [x] **Accuracy accounting** — ~~per-segment row tokens reconcile exactly with the run summary incl. repair~~ ✅ M3 (`sum(rows) == summary` test-pinned; row = primary call, repair split into its own columns; JSON-repair usage summed, both call kinds counted in the summary); ~~legacy brand recorded in attempt history again~~ ✅ M2.3; ~~`weaver inspect` routing-aware~~ ✅ M2.4; ~~`[translation] max_retries` wired-or-deleted (N2)~~ ✅ M3 (deleted from init; `[provider] max_retries` explicit, default 2); ~~token estimator CJK-aware + `MAX_CONTEXT_TOKENS` recalibrated (N7)~~ ✅ M3 (two-class estimator; 600→1000 honest tokens).
- [ ] **No regressions:** existing `bench/run_performance_budgets.py` budgets + `bench/run_acceptance_gate.py` green; full pytest suite green; Gate-B1 checks intact; ~~migration v14 forward-tested + idempotent~~ ✅ M3. _(Full re-run at M5 release gate; M3 exit evidence: 1683 passed / budgets PASS incl. flat cost 0.97× / AC-1…AC-9 PASS.)_
- [ ] **Live validations:** Gemini over `…/v1beta/openai` (current default model chosen — `gemini-1.5-flash` retired) and Ollama over `:11434/v1` pass their gated tests on the owner machine; E2 repair token-cost delta recorded → `enforce_repair` default decision confirmed.

> Completed sprint exits (v0.7.2 routing + enforcement, Desktop Installer & Release Hardening, Q2F, Sprint N, Sprint P) are historical — ✅ MET, evidence in git history, ADR 016–019, and `docs/superpowers/handoffs/`. Do not re-verify or extend them here. Standing deferred non-blocker from ADR 017: released installers stay **unsigned** until a code-signing cert exists (`WINDOWS_CERTIFICATE_THUMBPRINT` enables it, no code change).

### 2.5 Phase Log

Deep detail lives in git history, ADRs, sprint plans, and handoff notes. This section preserves only operational lessons still useful for future work.

| Area                          | Source of truth                                                                                                                                                                                                         | Carry-forward rule                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| ----------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Architecture baseline         | Current architecture docs + ADRs                                                                                                                                                                                        | Prefer existing architecture over new layers. Do not introduce abstractions unless they remove real duplication or protect a proven boundary.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| CLI / API / UI workflow       | Current workflow docs + tests                                                                                                                                                                                           | Preserve existing entry points and user workflows. Any route, command, selector, or schema rename requires tests and migration notes.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| Desktop / sidecar boundary    | Current desktop docs + sidecar contract, if present                                                                                                                                                                     | Keep desktop integration isolated from core services. Do not let desktop code become a second source of business logic.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| Provider layer                | Current provider ADR/spec + provider tests                                                                                                                                                                              | Keep provider primitives domain-agnostic. Put workflow validation in services, not provider adapters.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| Workspace/read models         | Current workspace services + tests                                                                                                                                                                                      | Read paths should stay cheap, deterministic, and side-effect-free. Avoid expensive scanning, hashing, provider calls, or QA work on render paths.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| Cleanup/audit work            | Current audit plan + handoff notes                                                                                                                                                                                      | Treat audit findings as hypotheses until manually verified. Delete only when references, runtime paths, tests, and fallback behavior are understood.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| Connection/routing security (v0.7.2) | `docs/superpowers/handoffs/2026-06-16-connection-routing-security-review.md` | Connection/routing/enforcement routes audited for webUI + desktop. All behind the `X-Weaver-Session` boundary (only `_PUBLIC_PATHS = /healthz,/health,/version,/static` are open) + same-origin CORS; Gate B1 held (provider calls are explicit-POST only); secrets validated (`^[A-Za-z_][A-Za-z0-9_]*$`) + `0o600` + never echoed; HTMX hooks are **relative** (no host hardcoding). **Two fixes:** `find_project` rejects `/`,`\\`,`.`,`..` names (Windows `\\`-traversal — desktop target); inline error fallbacks now `html.escape` the `name` param (reflected-XSS). Rule: untrusted route params reflected outside Jinja **must** be `html.escape`d; never join a route `name` into a filesystem path without the separator/`..` guard. |
| Provider keys & transaction shape (v0.7.2 audit) | `docs/superpowers/handoffs/2026-07-05-v072-audit-and-blocker-fixes.md` · commits `019834a`/`dee710f` | The provider factory resolves key values **shell env → secret store** at build time (`providers/registry._resolve_key_value`) — never assume `apply_secrets_to_env` re-runs mid-session; keep the Test-probe and build-time resolution paths consistent. Never hold a SQLite write transaction across a provider network call: one segment **result** = one atomic commit (row + memory + candidates + status); the `in_progress` marker is its own short txn and `reset_in_progress_segments` is the crash net. The gemini legacy shim endpoint is `…/v1beta/openai` (bare `…/v1beta` has no `/chat/completions`). |
| Perf & bench (v0.7.3 M1) | `docs/superpowers/handoffs/2026-07-13-v073-m1-storage-quick-wins.md` · commits `ef3bbe3`/`fe4a1c2`/`eeb63ee` | **mtime cache keys must NOT include the `-wal` mtime** — a read-only WAL read creates/touches `-wal`, so a wal-sensitive key spuriously misses on the absent→present transition; key on `(project.toml, weaver.db)` mtime + TTL only (both `project_discovery._CacheKey` and `workspace_index._CacheKey`). Prove cache/N+1 wins with **counting-seam tests** (spy `connect_readonly_database` / the parse fn), not weak `state=="ready"` assertions. Scope O(n²) rolling-window CTEs to the chapter — a segment maps to one chapter so `MAX(attempt)` is byte-identical (pin with an inline old-SQL oracle). **`weaver validate` exits 1 when `critical`>0**, so the bench fake pattern must be pure-English (no `{source}`, no JP) or validate fails. Never trust a bench "exit 0" read through a `\| tee`/`\| tail` pipe — the pipe's exit code masks the real one. |

| Enforcement provenance & cost honesty (v0.7.3 M3) | `docs/superpowers/handoffs/2026-07-18-v073-m3-enforcement-provenance.md` · commits `a898753`…`f735406` | Provenance belongs **on the attempt row** (columns on `translations`, no side table): NULL violations = "not evaluated" is a distinct, honest state from `'[]'` = "evaluated clean" — never collapse them. Token reconciliation must hold **by construction**: the row stores the primary call's usage, repair spend goes in its own columns, and the summary is the sum — never store "whichever response was committed" (that was the A5 bug). Every hidden provider round-trip (SDK retries, JSON-parse repair, enforcement re-ask) must be either explicitly bounded (`OpenAI(max_retries=...)`) or counted in the run summary (§4.3 gate 6). Token estimators for JP must be CJK-aware (~1 tok/char, not chars//4); when an estimator changes, **recalibrate the budgets that consume it** in the same change or window behavior silently shifts. |
| Reliability & input-safety (v0.7.3 M2) | `docs/superpowers/handoffs/2026-07-14-v073-m2-audit-carryforward.md` · commits `631ce46`…`da1dd02` | Tolerant TOML reads (`{}` on corrupt) **must** pair with a write guard — otherwise the next save rebuilds from the empty view and silently destroys data; the shared pattern is `core/toml_write.guard_unparseable_toml` (move-aside backup + `ConfigError` naming the backup) and `escape_toml_string` for **every** hand-serialized TOML value (4 private `_escape` copies existed, all incomplete). Provider pre-flight goes through `translation.preflight_provider_chain` — abort only when *no* chain candidate is healthy; surface the warning, never swallow it. ebooklib/lxml **repairs** mildly broken chapter XHTML — only content unparseable after repair hits `DocumentIR.read_issues`, so test degradation with binary garbage, not unclosed tags. Zip-bomb bound = sum central-directory `file_size` before parse (zipfile enforces declared sizes on extraction, so the declared total is a sound ceiling). |

> Historical test counts are evidence only at the time they were recorded. Re-run relevant verification for the current phase; do not assume old counts still apply.

---

## 3. Stack

This section describes the default project stack. Treat `pyproject.toml`, current ADRs, and lockfiles as the final source of truth.

### 3.1 Core

**Runtime and tooling:** Python 3.11+ · uv · `pyproject.toml` · ruff · pyright basic · pytest

**CLI and app foundation:** typer · rich · pydantic v2 · tomllib · pathlib · sqlite3

**Storage:** SQLite in WAL mode, no ORM by default

**Import/export and document handling:** ebook/document libraries currently declared in `pyproject.toml`

**Provider integration:** provider SDKs currently declared in `pyproject.toml`; do not add or replace provider dependencies without an ADR or explicit sprint scope

### 3.2 Web Cockpit

**Default web stack:** FastAPI · server-rendered Jinja2 · HTMX

Rules:

- Web cockpit is optional and isolated behind the web extra.
- Keep the UI server-rendered.
- No SPA by default.
- No Node/build pipeline by default.
- Vendor browser assets locally when practical; avoid CDN dependency for core UI behavior.
- `asyncio` is allowed only where the FastAPI/web boundary requires it.
- Routes/templates must stay thin. Business logic belongs in services.

### 3.3 Desktop Shell

**Default desktop boundary:** Tauri in `desktop/`, isolated from Python core.

Rules:

- Desktop code is not a Python dependency.
- Desktop shell launches or connects to the local FastAPI sidecar according to the current sidecar contract.
- Desktop must not duplicate business logic from CLI, API, services, or storage.
- Desktop-specific behavior stays inside `desktop/` unless an ADR explicitly expands the boundary.

### 3.4 Deferred / Out of Scope Unless Planned

The following are not part of the default stack and must not be scaffolded casually:

- OCR implementation
- New provider families
- Route rewrites
- SPA migration
- Node build pipeline
- External queue
- Cloud sync
- Telemetry
- Multi-user SaaS architecture

### 3.5 Banned Unless Explicitly Approved

The following require an ADR or explicit orchestrator approval before use:

- Flask
- Django
- SQLAlchemy or another ORM
- Celery, RQ, or external worker queues
- Docker as a required local runtime
- React/Vue/Svelte/SPA framework
- Required Node build pipeline
- OpenTelemetry
- Sentry or external error tracking
- External job queue, worker daemon, or multi-process worker pool
- Global mutable cross-project store
- `asyncio` outside the web layer without a documented reason

### 3.6 Stack Change Rule

A stack change is allowed only when it satisfies all of these:

1. Solves a current, documented project problem.
2. Has an ADR or explicit sprint scope.
3. Includes migration impact.
4. Includes rollback strategy.
5. Keeps CLI, API, desktop, storage, and tests coherent.

---

## 4. AI Instructions

### 4.1 Before Coding

1. Read this file first, then the relevant current doc/ADR from §1.
2. Check the active stage in §2.3 before starting any work. If no sprint/stage is active, do not continue old scaffolding by default; open a new execution plan first.
3. Respect the active execution plan, stage order, and gate rules defined for the current sprint.
4. Run `rtk git status --short --branch`. If WIP overlaps the relevant area, tell the orchestrator before editing.
5. Confirm scaffolding is actually requested. Docs/strategy request ≠ build code.
6. Check the file tree before creating new files or folders. Use exact names/values from the current docs for types, schemas, exit codes, selectors, and routes. Do not improvise.
7. Before committing: scan the diff for AI attribution trailers, bot author metadata, leaked credentials, and unrelated changes.

### 4.2 Code Rules

Follow the current engineering ADR/source-of-truth listed in §1.

- **Types:** Type hints on every public function. Pyright basic must pass.
- **Modularity:** One concept per file. Split if >400 lines or >5 public functions. Functions >50 lines or >4 params need justification.
- **Naming:** Forbidden filenames: `utils.py`, `helpers.py`, `manager.py`. Avoid class names ending `Manager`/`Helper`/`Handler` unless they truly are that pattern. Name modules for purpose.
- **Public APIs:** No `**kwargs` in public APIs. No bare `except:` or `except Exception:` outside CLI/web boundaries. Never use `except: pass`.
- **Errors:** All domain errors go through the `WeaverError` hierarchy. User-facing errors must state what failed, likely cause, and next action.
- **State discipline:** State writes go through services. CLI/web must not touch SQLite directly. One segment result = one atomic commit (translation row + memory + status together); provider network calls never run inside an open transaction. Status transitions live in the same transaction as the data they describe.
- **Layer boundaries:** Shared/core code is framework-agnostic. No web `Request`/`Response`, DI wiring, template output, or CLI formatting in core services. Pydantic belongs at the web/API boundary. UI templates/routes carry no business logic.
- **API keys:** Env vars or local secrets file only. Never store keys in config, logs, rendered HTML, SSE events, tests, or fixtures. Shell env wins.
- **Value types:** Use `@dataclass(frozen=True)` for value objects. Use `pathlib.Path` for paths. Use atomic writes for valuable state.
- **Cockpit UI hooks:** Do not rename/remove existing route, template, CSS, HTMX, or DOM hooks unless the active plan explicitly requires it and tests are updated.
- **Tests:** Mirror the source tree. Use `FakeProvider`; never live LLMs in CI. Fixtures must be public-domain or synthetic. Mock external boundaries only, not internal code.
- **Security for I/O changes:** Parse input through typed schemas/models, not raw dict chains. Never pass user strings to `os.system`, `subprocess(shell=True)`, `eval`, or `exec`. Malformed input must fail safely.
- **Performance:** Preserve documented runtime budgets. Any regression over 20% needs evidence and justification.
- **Tech-debt prevention:** No stub functions “for later”, no commented-out code, no single-caller abstractions, no config flag to defer a decision. Dead code is deleted on sight. TODO/FIXME must include an issue and cleanup plan.
- **Git/PR:** Conventional Commits with scope, for example `feat(translate): ...`. Branches use `feat|fix|docs|chore/<name>`. One PR = one concern. No force-push to `main`.
- **Githooks:** `.githooks/` are mandatory. Keep `git config core.hooksPath .githooks` enabled.

### 4.3 Anti-Slop

The LLM must be load-bearing infrastructure, never decoration.

- No “smart”, “AI-powered”, “magical”, or “intelligent” feature names.
- No chat UIs, avatars, sparkles, fortune-cookie loaders, marketing language, telemetry, or phone-home behavior.
- No prompt-wrapper features. A new “mode” that only changes the system prompt is not a feature.
- A feature ships only if all six gates pass:
  1. Real pain: evidenced, not “would be cool”.
  2. Falsifiable spec.
  3. Deterministic where possible.
  4. User can override every AI artifact.
  5. Failure is visible and never silently substituted.
  6. Cost is visible.

- No config flags for unbuilt features. No stub functions. No commented-out code. No abstractions with one caller.

### 4.4 Scope Discipline

Build vertically, not horizontally. One polished slice beats several half-finished ones. When in doubt between spectacle and correctness, prioritize correctness.

- Build only what the active stage lists.
- Deferred items get no scaffolding “for later”.
- One PR = one concern. Do not bundle refactor + feature.
- One implementation stage should map to one branch + one PR unless the active execution plan says otherwise.
- Add a **Non-Goals** line per stage to fence scope.
- No global mutable store without an ADR.
- No cross-project write behavior without an ADR.
- No expensive file hashing, scanning, or source inspection on render paths unless explicitly budgeted and tested.
- When no sprint is active, open a new scope by writing a sprint execution plan and updating §2.3 / §2.4 before implementation.

Default build order:

1. Validate prior carry-over.
2. Implement stages in execution-plan order.
3. Update docs and handoff notes.
4. Run final gate validation.

### 4.5 Communication

- Terse, technical. No filler, no apology, no marketing language.
- Reference files as `[name](path/file.md)` or `src/weaver/foo.py:42`.
- State decisions directly.
- Use concise Indonesian when the user writes in Indonesian.
- When uncertain, present 2–3 concrete options with trade-offs.
- Flag conflicts early: locked-stack changes, phase jumps, scope creep, direction regressions.
- During debugging: state what is happening, what was expected, and what evidence supports the conclusion.

### 4.6 Contribution Identity

> **Copy this section verbatim into every project CLAUDE.md. Do not modify.**

AI is a ghostwriter. Repository accountability remains with the human owner.

- Do not add `Co-Authored-By: Claude` or any AI/model co-author trailer to commits.
- Do not add “Generated with Claude Code” or equivalent tags to commit messages or PR bodies.
- Do not push commits with AI or bot author identity.
- Do not make AI appear in the GitHub contributor graph.
- Author and committer identity must be the repo owner’s human identity configured for the project.
- If AI assistance needs to be disclosed, mention it only in normal prose in a PR description or changelog, never in git metadata.

---

## 5. Implementation Agent Team

Weaver is built by the repo owner with Claude as Lead Technical Orchestrator, who splits work across specialist roles. Each role maps to a Weaver layer and is **realized** either by the orchestrator working inline or by a named Claude subagent/skill (spawn only when the owner asks, per the harness rule).

| #   | Role                                   | Weaver domain                                                           | Must not do                                                                             | Realized by                                                              |
| --- | -------------------------------------- | ----------------------------------------------------------------------- | --------------------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| 1   | **Lead Orchestrator**                  | Stage sequencing, scope control, merge readiness, final gate            | Skip final validation; assign ambiguous work; build a hub on the un-hardened foundation | Orchestrator (inline) · `Plan`                                           |
| 2   | **Product / Workflow Architect**       | User journey, page hierarchy, workflow coherence (cockpit)              | Add pages without a user-journey path; design features that bypass the core pipeline    | Orchestrator · `feature-dev:code-architect`                              |
| 3   | **Frontend Engineer**                  | Jinja2 + HTMX templates, partials, navigation, a11y, 390px+ states      | Add a frontend build step; rename HTMX hooks (§4.2); noisy UI outside the design system | Orchestrator · `frontend-design`                                         |
| 4   | **Backend Engineer**                   | API routers, `services/`, CLI commands, provider boundaries, validation | Put business logic in routers; touch SQLite from CLI/web; bypass services               | Orchestrator · `feature-dev:code-architect`/`code-explorer`              |
| 5   | **Data / Storage Engineer**            | `storage/migrations.py`, `schema.sql`, persistence, backward compat     | Schema churn without approval; break compat without ADR; mutate on a read path          | Orchestrator · `pr-review-toolkit:type-design-analyzer`                  |
| 6   | **QA / Validation Engineer**           | pytest suite, regression, edge cases, acceptance                        | Validate unit-only; skip user-facing workflow paths                                     | `pr-review-toolkit:pr-test-analyzer` · `verify`                          |
| 7   | **Security / Safety Engineer**         | I/O surfaces, secrets, path traversal, EPUB/image handling              | Unsafe file/subprocess patterns; secrets in config/logs/render; cross-project path leak | `security-review` · `pr-review-toolkit:silent-failure-hunter`            |
| 8   | **Performance / Reliability Engineer** | Render-path cost (Gate B1), job recovery, budgets                       | Ship blocking UX; hide errors with silent retries; hash source files on render          | Orchestrator (budget checks) · `pr-review-toolkit:silent-failure-hunter` |
| 9   | **Documentation / Handoff Writer**     | CLAUDE.md, sprint notes, ADR drafts, §8 handoff                         | Duplicate source-of-truth docs; write verbose non-operational prose                     | Orchestrator · `pr-review-toolkit:comment-analyzer`                      |
| 10  | **Critic / Devil's Advocate**          | Challenge assumptions, overengineering, hidden bugs, sequencing         | Block without an actionable alternative; complain without evidence                      | `pr-review-toolkit:code-reviewer` · `feature-dev:code-reviewer`          |
| 11  | **Release Captain**                    | Stage/sprint final gate, "done/not-done", known-gap doc                 | Mark done without evidence; merge incomplete work                                       | Orchestrator · `code-review`                                             |

**Rule:** No role overrides the orchestrator's scope without documenting reason, risk, and a proposed alternative. **The same agent should not be the sole reviewer of its own work** — builder (Backend/Frontend) → reviewer (Critic/QA/Security). Spawn subagents only when the owner asks (harness rule); otherwise the orchestrator fills the role inline.

---

## 6. Implementation Tracks

A track is owned by exactly one role. Supporting roles review or provide input but do not override the owner.

| Track | Name                           | Owner             | Weaver entry → exit                                                                                                      |
| ----- | ------------------------------ | ----------------- | ------------------------------------------------------------------------------------------------------------------------ |
| T0    | **Docs & Source of Truth**     | Doc Writer        | Stage scope defined → CLAUDE.md/§2 + handoff (§8) updated; ADRs current                                                  |
| T1    | **Product Workflow & UX**      | Product Architect | Stage defines/modifies a flow → journey documented; no orphan pages/states                                               |
| T2    | **Frontend (Jinja2 + HTMX)**   | Frontend Eng      | T1 defines UI; tokens exist → renders at 390px+; keyboard nav; loading/empty/error states; hooks intact                  |
| T3    | **Backend / API & Services**   | Backend Eng       | Contracts defined; storage exists → endpoints correct; input validated; services own writes; routers SQL-free            |
| T4    | **Data, Storage & Migration**  | Storage Eng       | Schema/migration required → forward + idempotency tested; existing data preserved; no silent loss                        |
| T5    | **Provider / Job Integration** | Backend Eng       | New provider/model config required → retry/fallback works; secrets confirmed; cost visible; ADR `010` intact             |
| T6    | **QA, Testing & Regression**   | QA Eng            | Implementation complete → full suite passes; regressions + edge cases documented; acceptance verified                    |
| T7    | **Security & Reliability**     | Security Eng      | Feature touches I/O/secrets/fs/subprocess/network → surfaces enumerated; risks + mitigations documented                  |
| T8    | **Performance & Runtime**      | Perf Eng          | Feature complete → budget met or regression justified; **zero render-path hashing**; no blocking UX; job recovery tested |
| T9    | **Release & Final Gate**       | Release Captain   | All tracks done; T6/T7/T8 passed → checklist signed; known gaps + next step clear                                        |

---

## 7. Orchestrator Operating Model

1. Read §1 docs governing the current stage; identify the stage from §2.3.
2. Confirm §3 locked-stack constraints — no new dependency or architecture shift without an ADR/owner approval.
3. Split the stage into tracks (§6); give each track an owner, scope, **acceptance criteria, and explicit non-goals** before implementation.
4. Require a handoff note (§8) at the end of each track.
5. Run Critic review (role #10) before the final gate; run QA + Security + Perf (T6+T7+T8) before merging.
6. Produce a per-track status: **Done** (implemented + validated + documented + handed off) · **Partial** (known gaps documented) · **Blocked** (external dependency) · **Deferred** (reason + trigger) · **Risk Accepted** (mitigation + rollback documented).

**Operating rule:** optimize for sequence, coherence, and risk reduction — not maximum parallel work.

---

## 8. Agent Handoff Protocol

Every track ends with a handoff note. Without it, the work is incomplete by definition.

```
## Handoff: [Role]
**Track:** [T0-T9]
**Scope:** [what this track was asked to do]
**Files/Areas Touched:** [created/modified]
**What Changed:** [summary]
**What Was Intentionally Not Changed:** [scope boundaries respected]
**Validation Performed:** [tests run, manual checks, evidence — paste commands/output]
**Known Risks:** [incomplete, fragile, or uncertain]
**Recommended Next Role / Next Step:** [single next action]
```

**Rule:** a handoff must leave enough context to continue **without re-auditing the repo**. Update §2.3/§2.5 at each stage gate. The "next step" line is mandatory.

---

## 9. Review Gates

| Gate               | Stage                | Checks                                                                                                                         | Skippable?   |
| ------------------ | -------------------- | ------------------------------------------------------------------------------------------------------------------------------ | ------------ |
| **A — Scope**      | Before work          | Aligned with active stage (§2.3)? Owner clear? Non-goals stated? Acceptance defined?                                           | No           |
| **B — Readiness**  | Before coding        | Affected files known? §3 constraints respected? Matches existing patterns? **Gate B1: no QA/provider/hashing on render path.** | No for T2–T5 |
| **C — Validation** | After implementation | Tests/manual checks documented? Regressions + edge cases listed? Handoff written?                                              | No for T2–T8 |
| **D — Release**    | Before merge         | Work complete? Known gaps documented? Critic review done? §2.4 stage criteria green?                                           | No           |

**Gate-skip rule:** fewer gates for small changes (single file, <50 lines, no schema change), but **never skip Gate C**. Document any skip in the handoff.

---

## 10. Decision Rules

| #   | Rule                                                                                                                                         |
| --- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Prefer **existing architecture** over new patterns. The cross-project read layer is `workspace_index`; do not invent a parallel store.       |
| 2   | Prefer **small, sequenced changes** over broad rewrites. One stage, one branch, one PR.                                                      |
| 3   | Prefer **user workflow completion** over isolated polish. A working end-to-end cockpit path beats a perfectly refactored unused component.   |
| 4   | **Explicit ownership** — every track has a named owner role (§5).                                                                            |
| 5   | **No new runtime dependency** without an ADR. A new import is an architecture decision.                                                      |
| 6   | **No "complete" without validation evidence.** "It compiles" / "tests should pass" is not validation — run them.                             |
| 7   | **Do not modify roadmap/architecture/stack silently.** Propose changes in a handoff or ADR draft.                                            |
| 8   | **When in doubt, document the uncertainty** and propose the smallest safe next step. A documented question beats an undocumented assumption. |

---

_This file is the operating manual for Weaver. It follows the global template `@WORKFLOW.md`. Read it before any code change. The roadmap (§2.1) is the plan; the active phase (§2.3) is the status — do not conflate them._
