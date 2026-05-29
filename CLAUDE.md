# Weaver

Offline-capable, glossary-aware **JP→EN** novel translation workbench. CLI tool for amateur fan-translators. Single maintainer.

**Outputs:** translated EPUB + Markdown review file. Nothing else.
**Not:** GUI, SaaS, consumer product, web app.

---

## 1. Documentation Map

User-facing docs live in [README.md](README.md). Internal specs live in [docs/](docs/). Read before non-trivial work.

| Doc | Purpose |
|-----|---------|
| [README.md](README.md) | User-facing: install, quickstart, commands, providers, exit codes |
| [PRD_v2.md](docs/PRD_v2.md) | MVP-0 scope, commands, acceptance criteria, `project.toml` schema |
| [SYSTEM_ARCHITECTURE.md](docs/SYSTEM_ARCHITECTURE.md) | Module layout, IR types, SQLite schema, provider interface |
| [BLUEPRINT_EXECUTION_PLAN.md](docs/BLUEPRINT_EXECUTION_PLAN.md) | 10-phase build order |
| [ENGINEERING_STANDARDS.md](docs/ENGINEERING_STANDARDS.md) | Coding rules, naming, testing |
| [AI_SLOP_PREVENTION.md](docs/AI_SLOP_PREVENTION.md) | Feature gates, anti-patterns |
| [PROMPT_DESIGN.md](docs/PROMPT_DESIGN.md) | Prompt templates (read before Phase 3) |
| [DESIGN_SYSTEM.md](docs/DESIGN_SYSTEM.md) | CLI/UX surface rules |
| [BRAND_DIRECTION.md](docs/BRAND_DIRECTION.md) | Voice and tone |
| [SECURITY_AND_PERFORMANCE.md](docs/SECURITY_AND_PERFORMANCE.md) | Budgets, threat model |
| [FUTURE_ROADMAP.md](docs/FUTURE_ROADMAP.md) | Deferred features |
| [FEATURE_PRIORITY_MATRIX.md](docs/FEATURE_PRIORITY_MATRIX.md) | What ships when |
| [GO_TO_MARKET.md](docs/GO_TO_MARKET.md) | Launch plan |
| [FINAL_STARTUP_VERDICT.md](docs/FINAL_STARTUP_VERDICT.md) | Strategic context |
| [quickstart.md](docs/quickstart.md) | Detailed walkthrough (supplements README) |
| [decisions/](docs/decisions/) | ADRs: provider interface, IR shape, segment ID, glossary algorithm, EPUB roundtrip, Sprint 11b |
| [api/](docs/api/) | Stable JSON API shapes (`qa_json_schema.md`) |
| [benchmarks.md](docs/benchmarks.md) | Phase 10 performance budget evidence |
| [release_acceptance.md](docs/release_acceptance.md) | Phase 10.5 AC-1 through AC-9 evidence |
| [feature_plan/](docs/feature_plan/) | Phase 12 Web Cockpit planning: [feature plan](docs/feature_plan/web-feature-plan.md), [architecture](docs/feature_plan/web-architecture.md), [execution blueprint](docs/feature_plan/web-execution-blueprint.md), [master plan](docs/feature_plan/2026-05-29-web-cockpit-phase-12.md) |

**Rule:** docs are the spec. Code follows docs. If code contradicts docs, ask first.

---

## 2. Progress

Single source of truth for build status. Update at end of every phase/sprint. Roadmap, exit criteria, and ordering sourced from [BLUEPRINT_EXECUTION_PLAN.md](docs/BLUEPRINT_EXECUTION_PLAN.md) and the CLI UX plan at `plans/semua-phase-log-1-10-hazy-lovelace.md`. No calendar estimates — phase order and dependencies are what matters; ship when exit criteria pass.

### 2.1 Roadmap

| #   | Phase                                                                                              | Depends on | Status         |
| --- | -------------------------------------------------------------------------------------------------- | ---------- | -------------- |
| 0   | Foundations — repo, tooling, CI, `weaver --version`                                                | —          | ✅ Complete     |
| 1   | Source Reader & IR — EPUB → `DocumentIR`, segment IDs                                              | 0          | ✅ Complete     |
| 2   | State Store — SQLite (WAL), migrations, repository fns                                             | 1          | ✅ Complete     |
| 3   | Providers — `FakeProvider`, `DeepSeekProvider`, `GeminiProvider`, `OllamaProvider`                 | 2          | ✅ Complete     |
| 4   | Translation Orchestrator — context builder, resumable loop                                         | 3          | ✅ Complete     |
| 5   | Glossary Workflow — candidate extraction, interactive review                                       | 4          | ✅ Complete     |
| 6   | Markdown Export — per-chapter review files                                                         | 4          | ✅ Complete     |
| 7   | Manual Edit — `weaver edit <segment>` via `$EDITOR`                                                | 4          | ✅ Complete     |
| 8   | EPUB Renderer — translated EPUB roundtrip                                                          | 1 + 6      | ✅ Complete     |
| 9   | QA Engine — `weaver validate` deterministic checks                                                 | 4          | ✅ Complete     |
| 10  | Hardening, Docs, Release — v0.1.0 (PyPI publish credential-gated)                                  | all        | ✅ Complete     |
| 11a | CLI UX Sprint A — flags, completion, doctor, aliases (0.2.x)                                       | 10         | ✅ Complete     |
| 11b | CLI UX Sprint B — global config, templates, preview, sampled translate, JSON schema (0.3.0)        | 11a        | ✅ Complete     |
| 11c | CLI UX Sprint C — `weaver new` wizard, TUI dashboard, glossary diff, EPUBCheck, honorific modes    | 11b        | ✅ Complete     |
| 12a | Web Cockpit A — `weaver serve`, project discovery, read-only monitor + SSE (0.5.0)                 | 11c        | ⏳ Planned      |
| 12b | Web Cockpit B — file input (browse/upload), provider/model config, translate controls, export      | 12a        | ⬜ Pending      |
| 12c | Web Cockpit C — glossary review UI                                                                 | 12b        | ⬜ Pending      |

Legend: ✅ complete · 🟡 in progress · ⏳ next · ⬜ pending · 🚫 blocked.

Critical path: Phases 1→4 strict. Phases 5/6/7/9 may overlap once 4 ships. CLI UX 11a→11b→11c is strict: B layers global config, C consumes both. Web Cockpit 12a→12b→12c is strict: A lays Flask app + discovery + JobManager, B layers write actions, C moves glossary review into the browser. Phase 12 is planned (not scheduled) — see [docs/feature_plan/web-feature-plan.md](docs/feature_plan/web-feature-plan.md), [web-architecture.md](docs/feature_plan/web-architecture.md), [web-execution-blueprint.md](docs/feature_plan/web-execution-blueprint.md). ADRs `0016`–`0019` author first.

### 2.2 Reusable Phase Gate

Before starting any next phase/sprint, always run this gate:

1. Read the current active sprint in §2.3 and its source section in [BLUEPRINT_EXECUTION_PLAN.md](docs/BLUEPRINT_EXECUTION_PLAN.md) (Phases 0–10) or `plans/semua-phase-log-1-10-hazy-lovelace.md` (Phase 11 sprints).
2. List the active sprint's exit criteria in plain language.
3. Verify each exit criterion with a concrete command, test, file check, or manual inspection.
4. State what is usable now, what is internal-only, and what is still not user-facing.
5. If every exit criterion passes, update §2.1 Roadmap, §2.3 Active Phase, §2.4 Exit Criteria, and §2.5 Phase Log.
6. If any exit criterion fails or is unverified, do not proceed. Mark the row blocked or keep it active, then record the missing proof.

Required reminder before phase transition: **"Check exit criteria first. No next phase until evidence exists. Explain the detail for manual inspection."**

### 2.3 Active Sprint — Phase 12a: Web Cockpit A (Monitor + Project Discovery)

**Goal:** stand up the local web cockpit foundation — `weaver serve` (Flask, `127.0.0.1`, `threaded=True`), project discovery (no more typed paths, PP1), a read-only project cockpit mirroring `weaver inspect`, and live translate progress via a `JobManager` + SSE (PP3 starts). Every change is additive — CLI stays wire-compatible. Plan source: [docs/feature_plan/web-execution-blueprint.md](docs/feature_plan/web-execution-blueprint.md) §3.

**Gate:** no Flask or cockpit code enters the codebase until ADR `0016` is merged.

**Sub-sprint deliverables** (ADRs land before matching implementation):

| Row | ADR | Implementation |
| --- | --- | -------------- |
| A1  | `0016-web-cockpit-framework.md`          | `weaver serve [--port 8765] [--books-dir PATH] [--no-browser]`; Flask app factory; `127.0.0.1` bind; vendored `htmx.min.js`; `weaver[web]` extra |
| A2  | *(none — uses 0016)*                     | `services/project_discovery.py` + Dashboard listing discovered `.weaver/*` projects (PP1) |
| A3  | `0017-localhost-security-model.md`       | loopback bind, no auth, no secret rendering (foundation for 12b file browser) |
| A4  | `0019-job-manager-progress-streaming.md` | `web/job_manager.py` skeleton (one-job lock) + SSE endpoint streaming a read-only translate run (PP3) |
| A5  | *(none — uses 0019)*                     | read-only project cockpit view mirroring `weaver inspect` |

**Exit criteria:** see §2.4 → "Phase 12a". Mirrors [web-execution-blueprint.md](docs/feature_plan/web-execution-blueprint.md) §5 (global) + §3 (12a exit).

**Blockers / open questions:** none. ADRs `0016`/`0017`/`0019` authored (accepted); merge `0016` before code. `0018` defers to 12b.

**Update protocol when sprint closes:** flip §2.1 row `12a` to ✅; log outcome in §2.5; set §2.3 Active Sprint to 12b.

### 2.4 Exit Criteria

Compact evidence ledger. Inspection notes for completed phases live in this section; deep-dive detail for legacy phases lives in git history and `plans/`. Active sprint keeps full detail.

#### Phase 12a — Web Cockpit A (Monitor + Project Discovery)

Status: `⏳ Planned`

Plain-language criteria (mirror of [web-execution-blueprint.md](docs/feature_plan/web-execution-blueprint.md) §5 global exit + §3 12a exit):

1. ADR `0016` lands and is merged **before** any Flask/cockpit code enters the codebase (gate rule). ADRs `0017`–`0019` land in `docs/decisions/` per ENGINEERING_STANDARDS format.
2. All implementation PRs land green; one PR = one concern (no bundled refactor + feature).
3. AC-1..AC-9 acceptance gate stays PASS.
4. Ruff lint + format clean. Pyright `0 errors`.
5. Existing CLI stays wire-compatible — every Phase 11 command + flag works unchanged. `translate_project` gains only the additive optional `should_cancel` hook (CLI passes `None`).
6. README + `docs/quickstart.md` document `weaver serve` (loopback bind, `--port`, `--books-dir`, `weaver[web]` install).
7. All web dependencies sit behind the `weaver[web]` optional extra; core install pulls no Flask.
8. **12a usable surface:** browse to `http://127.0.0.1:8765`, see all discovered projects with no path typing; start a translate job from the cockpit and watch live SSE progress stream to completion (or clean cancel).

Evidence: *(pending — fill as PRs land)*

| Criterion | Proof | Status |
| --------- | ----- | ------ |
| ADRs `0016`–`0019` | `docs/decisions/` | ✅ authored |
| `weaver serve` + Flask app factory + vendored htmx + `weaver[web]` | *(A1, pending)* | ⏳ |
| `services/project_discovery.py` + dashboard project list | *(A2, pending)* | ⏳ |
| Loopback `127.0.0.1` bind, no auth (ADR `0017`) | *(A3, pending)* | ⏳ |
| `web/job_manager.py` single-job registry + SSE stream (ADR `0019`) | *(A4, pending)* | ⏳ |
| Read-only cockpit view mirroring `weaver inspect` | *(A5, pending)* | ⏳ |
| Acceptance gate | `bench/run_acceptance_gate.py` → AC-1..AC-9 PASS | ⏳ |

#### Phases 0–10 — All Passed

| Phase                    | Key surface                                                                                          | Verified by                                                                                            | Tests |
| ------------------------ | ---------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ | ----- |
| 0 Foundations            | `weaver --version`, `WeaverError` hierarchy, typer skeleton                                          | local ruff/format/pyright/pytest                                                                       | n/a   |
| 1 Source Reader & IR     | `DocumentIR`, deterministic segment IDs, source-hash stale detection                                 | `tests/unit/core`, `tests/integration/readers`                                                         | 7     |
| 2 State Store            | SQLite WAL schema, `weaver init`, `weaver inspect`, 10k-segment resume <5s                           | `tests/unit/storage`, `tests/integration/test_cli_state_store.py`                                      | 18    |
| 3 Providers              | 4-provider registry, JSON parse+repair, `--healthcheck` flag, v1→v2 token-column migration           | `tests/unit/providers`, `tests/integration/providers/test_fake_end_to_end.py`                          | 82    |
| 4 Translation Orchestrator | resumable translate loop, retry-failed, stale detection, Rich progress                             | `tests/unit/services/test_translation_orchestrator.py`, `tests/integration/test_cli_translate.py`      | 89    |
| 5 Glossary Workflow      | candidate extraction (regex + optional fugashi), review/edit/conflicts, conflict exit 6              | `tests/unit/services/test_glossary.py`, `tests/integration/test_cli_glossary.py`                       | 98    |
| 6 Markdown Export        | `weaver export --mode markdown`, failed/stale/missing markers, `--translation-only`                  | `tests/integration/test_cli_export_markdown.py`                                                        | 101   |
| 7 Manual Edit            | `weaver edit` via `$EDITOR`, manual status survives `--retry-failed`, exit 5 on missing id           | `tests/unit/services/test_manual_edit.py`, `tests/integration/test_cli_edit.py`                        | 109   |
| 8 EPUB Renderer          | `weaver export --mode epub`, xpath-based block rewrite, `EpubNcx` fallback for source EPUB           | `tests/unit/renderers/test_epub.py`, `tests/integration/test_cli_export_epub.py`                       | 115   |
| 9 QA Engine              | 6 deterministic checks, `--json` stable shape, critical=exit 1                                       | `tests/unit/qa/test_checks.py`, `tests/integration/test_cli_validate.py`                               | 136   |
| 10 Hardening + Release   | benchmarks (200ch synthetic), docs build, AC-1..AC-9 PASS, 0.1.0 dist built; post-release P0 patch (Gemini key revert, `services/glossary_review.py` extraction, `.githooks/pre-commit` secret-scan) | `bench/run_performance_budgets.py`, `bench/run_acceptance_gate.py`, `tests/unit/services/test_glossary_review.py` | 152   |

**Verification rerun** for any of the above:

```powershell
.\.venv\Scripts\python.exe -m pytest -m "not requires_ollama and not requires_cloud"
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m ruff format --check src tests
.\.venv\Scripts\pyright.exe --pythonpath .\.venv\Scripts\python.exe
.\.venv\Scripts\python.exe bench\run_acceptance_gate.py
```

#### Phase 11a — CLI UX Sprint A

Status: `✅ Passed`

Plain-language criteria (from plan §5 Phase A):

1. Every existing command + flag keeps working unchanged (wire-compatible).
2. Tab completion installable via `weaver --install-completion <shell>`.
3. `weaver translate` accepts `--provider`, `--model`, `--dry-run`, `--verbose`, and multiple project paths.
4. `weaver edit` resolves segments via `--first-failed`, `--next-stale`, `--recent` without copy-pasting hex ids.
5. `weaver glossary review` prefixes prompts with `Reviewed N of M`; implements `[f]ind` hotkey and `--find <substring>`.
6. `weaver doctor` surfaces missing env vars, DB integrity, and provider env config; `--healthcheck` adds reachability probe.
7. `weaver validate --schema` prints stable JSON shape; no project required.
8. `weaver inspect` table shows `N (P%)` for segments and `N (P% of candidates)` for glossary terms.
9. Hidden aliases `tx`, `ins`, `gl` route to `translate`, `inspect`, `glossary`.
10. Global `--debug` flag prints Python tracebacks instead of three-line user errors.
11. AC-1..AC-9 acceptance gate stays PASS.

Evidence:

| Criterion                                | Proof                                                                                                                                                                 | Status     |
| ---------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- |
| Wire-compatible existing CLI tests       | `tests/integration/test_cli_translate.py`, `test_cli_edit.py`, `test_cli_glossary.py`, `test_cli_validate.py` all green                                               | ✅ Passed   |
| `--provider`/`--model`/`--dry-run`/`--verbose` | `tests/integration/test_cli_translate_phase_a.py` (4 tests)                                                                                                   | ✅ Passed   |
| Edit selector flags                      | `tests/unit/services/test_resolve_segment_id.py` (5 tests), `tests/integration/test_cli_edit_phase_a.py` (4 tests)                                                    | ✅ Passed   |
| Glossary `[f]ind` + `--find` + counter   | `tests/integration/test_cli_glossary_phase_a.py` (5 tests)                                                                                                            | ✅ Passed   |
| `weaver doctor`                          | `tests/unit/services/test_doctor.py` (5 tests), `tests/integration/test_cli_doctor.py` (3 tests)                                                                      | ✅ Passed   |
| `validate --schema`                      | `tests/integration/test_cli_validate_schema.py` (2 tests)                                                                                                             | ✅ Passed   |
| Batch translate                          | `tests/integration/test_cli_translate_batch.py` (2 tests)                                                                                                             | ✅ Passed   |
| Aliases + `--debug`                      | `tests/integration/test_cli_aliases_and_debug.py` (6 tests)                                                                                                           | ✅ Passed   |
| Inspect percentages                      | `tests/integration/test_cli_inspect_percentages.py` (3 tests)                                                                                                         | ✅ Passed   |
| Help epilogs on every command            | `tests/integration/test_cli_help_epilogs.py` (10 parametrized)                                                                                                        | ✅ Passed   |
| Acceptance gate                          | `bench/run_acceptance_gate.py` → AC-1..AC-9 PASS                                                                                                                      | ✅ Passed   |

Latest observed result: `201 passed, 3 deselected`; Ruff lint+format clean; Pyright `0 errors`; AC-1..AC-9 PASS.

Manual inspection:

- `src/weaver/cli/main.py` flips `add_completion=True`, registers hidden aliases (`tx`/`ins`/`gl`), threads `--debug` through `_exit_with_error`, adds `--provider`/`--model`/`--dry-run`/`--verbose` on translate, multi-project translate, `--first-failed`/`--next-stale`/`--recent` on edit, `--find` on glossary review, `weaver doctor` command, `--schema` on validate, percentages on inspect, `epilog=` examples on all 10 commands.
- `src/weaver/services/translation.py` adds `dry_run`, `provider_override`, and a widened `ProgressCallback` signature.
- `src/weaver/services/manual_edit.py` adds `resolve_segment_id(selector)` for `first-failed` / `next-stale` / `recent` lookups.
- `src/weaver/services/glossary_review.py` adds `find(substring)` returning the first matching pending candidate.
- `src/weaver/services/qa.py` adds `qa_report_schema()`.
- New `src/weaver/services/doctor.py` runs 5 checks: python version, EDITOR, config schema, DB WAL mode, provider env var; optional provider healthcheck.
- `pyproject.toml` adds `[tool.ruff.lint.flake8-bugbear] extend-immutable-calls = ["typer.Argument"]`.
- `README.md` and `docs/quickstart.md` document shortcuts, completion install, and `weaver doctor`.

Usability:

- Usable now: every Phase A change ships behind opt-in flags or new commands. Power users get `--dry-run`, `--verbose`, batch translate, edit shortcuts, aliases. Beginners get `weaver doctor`, better `--help`, completion.
- Internal-only: `qa_report_schema()` dict, `resolve_segment_id` SQL helpers, `DoctorReport` dataclass.
- Not user-facing yet: global config file, project templates, `weaver preview`, `weaver new` wizard, `weaver dashboard` TUI — land in 11b / 11c.

#### Phase 11b — CLI UX Sprint B

Status: `✅ Passed`

Plain-language criteria (from plan §5 Phase B):

1. `~/.weaver/config.toml` resolves through precedence chain `CLI flag > project.toml > global > built-in default`.
2. `WEAVER_DEFAULT_PROVIDER`, `WEAVER_DEFAULT_MODEL`, `WEAVER_OUTPUT_DIR` honored on the same chain.
3. `weaver init --from-template <name>` writes prebaked `[glossary]` / `[qa]` knobs for `light-novel`, `web-novel`, `aozora-classic`.
4. `weaver preview <project.toml> [--segment ID] [--chapter K]` renders matching block(s) inline (paged via `--pager auto`).
5. `weaver translate --first-N 10` samples N segments and stops, leaving state consistent.
6. `weaver validate --json` payload carries `schema_version: 1`; documented at `docs/api/qa_json_schema.md`.
7. `weaver init` (overwrite) and `weaver glossary edit` (lossy TSV diff) prompt for confirm before destructive action.
8. AC-1..AC-9 stays PASS. 30 new tests across 7 new test files (231 total).

Evidence:

| Criterion | Proof | Status |
| --------- | ----- | ------ |
| 6 ADRs (`0006`–`0011`) | `docs/decisions/` | ✅ |
| `global_config.py` + precedence chain | `tests/unit/core/test_global_config.py` (5 tests) | ✅ |
| Templates (`light-novel`, `web-novel`, `aozora-classic`) | `tests/unit/core/test_templates.py` (3 tests), `tests/integration/test_cli_init_template.py` (2 tests) | ✅ |
| `weaver preview` | `tests/unit/services/test_preview.py` (3 tests), `tests/integration/test_cli_preview.py` (2 tests) | ✅ |
| `--first-N` on translate | `tests/integration/test_cli_translate_sampled.py` (3 tests) | ✅ |
| `schema_version: 1` in `--json` | `tests/unit/services/test_qa_schema_version.py` (2 tests), `test_cli_validate_schema.py` updated | ✅ |
| Destructive confirm (init overwrite, glossary edit) | `tests/integration/test_cli_destructive_confirm.py` (3 tests) | ✅ |
| Acceptance gate | `bench/run_acceptance_gate.py` → AC-1..AC-9 PASS | ✅ |

Latest observed result: `231 passed, 3 deselected`; Ruff lint+format clean; Pyright `0 errors`; AC-1..AC-9 PASS.

New modules: `src/weaver/core/global_config.py`, `src/weaver/core/templates.py`, `src/weaver/services/preview.py`.
New docs: `docs/api/qa_json_schema.md`, six ADRs `0006`–`0011`.
Version bumped to `0.3.0`.

#### Phase 11c — CLI UX Sprint C

Status: `✅ Passed`

Plain-language criteria (from plan §5 Phase C):

1. `weaver new` interactive wizard authors a project end-to-end (provider pick → template pick → output pick → init). Uses `questionary` dep gated by ADR `0014`.
2. `weaver dashboard` read-only TUI mirror of `weaver inspect`. Uses `textual` dep gated by ADR `0012`; aesthetic policy gated by ADR `0015`. `--no-color` honored.
3. `weaver glossary diff <chapter-A> <chapter-B>` read-only per-chapter term diff.
4. `weaver validate --epub` invokes EPUBCheck (optional Java dep, ADR `0013-epubcheck-optional-dep.md`).
5. `[translation] honorifics` accepts `localize` and `hybrid` in addition to `preserve`.
6. AC-1..AC-9 stays PASS.

Evidence:

| Criterion | Proof | Status |
| --------- | ----- | ------ |
| 4 ADRs (`0012`–`0015`) | `docs/decisions/` | ✅ |
| `weaver new` wizard | `tests/unit/services/test_wizard.py` (3), `tests/integration/test_cli_new.py` (3) | ✅ |
| `weaver dashboard` TUI | `tests/unit/services/test_dashboard.py` (3), `tests/integration/test_cli_dashboard.py` (2) | ✅ |
| `weaver glossary diff` | `tests/unit/services/test_glossary_diff.py` (4), `tests/integration/test_cli_glossary_diff.py` (2) | ✅ |
| `weaver validate --epub` | `tests/unit/services/test_epubcheck.py` (4), `tests/integration/test_cli_validate_epub.py` (3) | ✅ |
| Honorifics `localize`/`hybrid` | `tests/integration/test_cli_honorifics.py` (3) | ✅ |
| Acceptance gate | `bench/run_acceptance_gate.py` → AC-1..AC-9 PASS | ✅ |

Latest observed result: `258 passed, 3 deselected`; Ruff lint+format clean; Pyright `0 errors`.

New modules: `src/weaver/services/epubcheck.py`, `src/weaver/services/wizard.py`, `src/weaver/services/glossary_diff.py`, `src/weaver/tui/__init__.py`, `src/weaver/tui/dashboard_app.py`.
New docs: 4 ADRs `0012`–`0015`; quickstart updated; README updated.
Optional extras: `weaver[tui]` (textual), `weaver[wizard]` (questionary), `weaver[all]`.
Version bumped to `0.4.0`.

### 2.5 Phase Log

| #   | Phase                       | Source                                                                  | Outcome                                                                                                                                                                                                                                                                                                                                                |
| --- | --------------------------- | ----------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 0   | Foundations                 | [#1](https://github.com/Trancend1/weaver-translate/pull/1)              | MIT license, `pyproject.toml` (uv + hatchling), `weaver --version`, `WeaverError` hierarchy, typer CLI skeleton.                                                                                                                                                                                                                                       |
| 1   | Source Reader & IR          | Local sprint                                                            | `DocumentIR` dataclasses, ebooklib EPUB reader, deterministic segment IDs/source hashes, fixture EPUB.                                                                                                                                                                                                                                                 |
| 2   | State Store                 | Local sprint                                                            | SQLite WAL schema, `weaver init`, `weaver inspect`, stale/reset behavior, 10k-segment resume <5s.                                                                                                                                                                                                                                                      |
| 3   | Providers                   | Local sprint                                                            | 4-provider factory, JSON parse+repair, prompt templates, `--healthcheck` flag, v1→v2 token-column migration.                                                                                                                                                                                                                                           |
| 4   | Translation Orchestrator    | Local sprint                                                            | `weaver translate` with rolling context, resume, retry-failed, stale detection, Rich progress.                                                                                                                                                                                                                                                         |
| 5   | Glossary Workflow           | Local sprint                                                            | candidate extraction, `weaver glossary review/edit/conflicts`, approved-term injection, conflict exit 6.                                                                                                                                                                                                                                               |
| 6   | Markdown Export             | Local sprint                                                            | `weaver export --mode markdown` with `--translation-only`, failed/stale/missing markers.                                                                                                                                                                                                                                                                |
| 7   | Manual Edit                 | Local sprint                                                            | `weaver edit <segment-id>` via `$EDITOR`, manual status survives `--retry-failed`.                                                                                                                                                                                                                                                                     |
| 8   | EPUB Renderer               | Local sprint                                                            | `weaver export --mode epub` with xpath block rewrite, navigation fallback.                                                                                                                                                                                                                                                                              |
| 9   | QA Engine                   | Local sprint                                                            | `weaver validate` with 6 deterministic checks, `--json`, critical-exit-1.                                                                                                                                                                                                                                                                              |
| 10  | Hardening, Docs, Release    | Local sprint                                                            | benchmarks, docs build, AC-1..AC-9 gate, 0.1.0 dist built. Post-release P0 patch: Gemini API key revert + `tests/unit/providers/test_gemini.py` regression guard + `.githooks/pre-commit` secret-scan hook + `src/weaver/services/glossary_review.py` extracted to honor CLAUDE.md §4.2 layering rule. 152 tests. PyPI publish/tag credential-gated. |
| 11a | CLI UX Sprint A             | Local sprint, plan `plans/semua-phase-log-1-10-hazy-lovelace.md` §5 A   | 14 wire-compatible changes: shell completion, `--help` examples, `--provider`/`--model`/`--dry-run`/`--verbose`/batch on translate, `--first-failed`/`--next-stale`/`--recent` on edit, `Reviewed N of M` + `[f]ind` + `--find` on glossary review, `weaver doctor`, `weaver validate --schema`, hidden `tx`/`ins`/`gl` aliases, global `--debug`, inspect percentages. 201 tests, 0 lint/type errors, AC-1..AC-9 PASS. |
| 11b | CLI UX Sprint B             | Local sprint, plan `plans/semua-phase-log-1-10-hazy-lovelace.md` §5 B   | 7 additive features: `~/.weaver/config.toml` precedence chain + env vars, `weaver init --from-template` (3 presets), `weaver preview` with `--segment`/`--chapter`/`--pager`, `weaver translate --first-N`, `schema_version: 1` in `--json` payload + `docs/api/qa_json_schema.md`, destructive-confirm on init overwrite + glossary edit. 6 ADRs (`0006`–`0011`). 231 tests (+30), 0 lint/type errors, AC-1..AC-9 PASS. Version `0.3.0`. |
| 11c | CLI UX Sprint C             | Local sprint, plan `plans/semua-phase-log-1-10-hazy-lovelace.md` §5 C   | 5 additive features: `weaver new` questionary wizard, `weaver dashboard` Textual TUI, `weaver glossary diff`, `weaver validate --epub` (EPUBCheck, graceful degradation), `honorifics = localize\|hybrid` validation. 4 ADRs (`0012`–`0015`). Optional extras `[tui]`/`[wizard]`/`[all]`. 258 tests (+27), 0 lint/type errors, AC-1..AC-9 PASS. Version `0.4.0`. |

---

## 3. Stack (Locked)

**Use:** Python 3.11+ · uv · pyproject.toml · ruff · pyright (basic) · pytest · typer · rich · pydantic v2 · tomllib · sqlite3 (WAL, no ORM) · ebooklib · fugashi + ipadic-neologd · openai SDK · google-generativeai · Jinja2.

**Rejected (no reintroduction without ADR):** Django · FastAPI · SQLAlchemy · Celery · RQ · Docker · asyncio · Sentry · OpenTelemetry.

**Conditionally reopened:** **Flask (sync only)** + HTMX for the Phase 12 local web cockpit — *pending ADR `0016`*. Until `0016` lands, Flask stays out of the codebase. Behind optional extra `weaver[web]`. asyncio / FastAPI / React-Node build remain rejected. See [docs/feature_plan/web-architecture.md](docs/feature_plan/web-architecture.md).

**Providers (MVP-0):**

| Provider | Role | Auth |
|----------|------|------|
| `deepseek` | Default cloud | `DEEPSEEK_API_KEY` |
| `gemini` | Free-tier cloud | `GEMINI_API_KEY` |
| `ollama` | Local, optional | None (local) |
| `fake` | CI/dev default | None |

---

## 4. AI Instructions

### 4.1 Before Coding
- Read relevant doc section. Docs are authoritative.
- Match phase order. No jumping ahead.
- Before starting a new phase, run the reusable phase gate in §2.2 and check exit criteria first.
- Use exact names/values from docs for types, schemas, exit codes. No improvisation.
- When unsure: ask. Do not invent fields, prompts, commands, exit codes.

### 4.2 Code Rules (Non-Negotiable)

Source: [ENGINEERING_STANDARDS.md](docs/ENGINEERING_STANDARDS.md).

- Type hints on every public function. Pyright basic must pass.
- One concept per file. Split if >400 lines or >5 public functions.
- Forbidden filenames: `utils.py`, `helpers.py`, `manager.py`. Name modules for what they do.
- No `**kwargs` in public APIs.
- No `except: pass`. No `except Exception: pass` outside CLI boundary.
- All errors via `WeaverError` hierarchy in `src/weaver/errors.py`.
- User-facing errors: **what failed / likely cause / next command**.
- State writes go through services. CLI never touches SQLite directly.
- One segment translation = one transaction.
- API keys via env vars only, never config files. Never log keys.
- `@dataclass(frozen=True)` for value types. Mutability only for state machines.
- File paths via `pathlib.Path`. Atomic writes (`tempfile` + `replace`) for valuable state.
- Tests mirror source tree. Use `FakeProvider`, never live LLMs in CI. Fixtures = public domain only.

### 4.3 Anti-Slop

Source: [AI_SLOP_PREVENTION.md](docs/AI_SLOP_PREVENTION.md).

- No "smart" / "AI-powered" / "magical" / "intelligent" feature names.
- No chat UIs, assistant avatars, sparkle animations, fortune-cookie loaders.
- Deterministic by default. LLM only when determinism impossible AND output is verifiable AND user can override.
- No config flags for unbuilt features.
- No stub functions, no commented-out code, no abstractions with one caller.

### 4.4 Scope Discipline

- MVP-0 ships only what [PRD_v2.md](docs/PRD_v2.md) §6 lists.
- Deferred items (PRD §7) get no scaffolding "for later".
- Not in acceptance criteria (PRD §10) → do not build.
- One PR = one concern. No bundled refactor + feature.

### 4.5 Communication

- Terse, technical. No filler, no apology, no marketing language.
- Reference files as `[name](path/file.md)` or `src/weaver/foo.py:42`.
- State decisions directly.

### 4.6 Contribution Identity

- Agentic AI must not appear as a GitHub contributor, author, committer, co-author, or bot identity.
- Do not add `Co-Authored-By`, `Generated-By`, `Assisted-By`, or similar trailers for Claude, Codex, ChatGPT, Anthropic, OpenAI, or other agentic AI tools.
- Commit author and committer identity must stay on the maintainer/user account only.
- Before any commit or PR, scan the pending commit message and recent history for `Co-Authored-By`, `Claude`, `Anthropic`, `Codex`, `ChatGPT`, `OpenAI`, and AI no-reply emails.
- The repo hook in `.githooks/commit-msg` is mandatory local guardrail. Keep `git config core.hooksPath .githooks` enabled.
- If an AI attribution trailer or bot author is found after commit, stop phase work and clean history before opening or updating PRs.
