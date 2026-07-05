# Handoff — v0.7.2 Release Audit + Blocker Fixes (2026-07-05)

**Role:** Lead Orchestrator (audit) + Backend Engineer (fixes)
**Track:** T6/T7/T8 (audit) → T3 (fixes) → T0 (doc de-stale)
**Scope:** Full release-readiness audit of the shipped v0.7.2 tag; fix the three High findings before opening v0.7.3; de-stale all progress docs.

## Audit verdict

v0.7.2 (tag on `main`) is structurally healthy: ruff / format / pyright clean, suite **1609 passed** at audit time, versions consistent, no TODO/FIXME debt, June security hardening intact, D9 lean-backing fence held. **No Critical findings.** 3 High / 5 Medium / 5 Low.

## High findings — fixed on `fix/v072-audit-blockers`

| # | Finding | Fix | Commit |
| --- | --- | --- | --- |
| H1 | Key saved from a running cockpit lands in `secrets.toml` only; `apply_secrets_to_env` runs once at startup and `OpenAIChatProvider` read `os.environ` only → Test ✓ but the next translate raised `WEAVER_CONN_<NAME> is not set` until restart (rotation likewise stale). | Provider factory resolves the key **shell env → secret store** at build time (`providers/registry._resolve_key_value`), matching the Test-probe path. Shell env still wins. | `019834a` |
| H2 | Legacy gemini D6 shim pointed at `…/v1beta`, which has no `/chat/completions`; ADR 018 §5.3 specifies `…/v1beta/openai`. Every pre-0.7.2 `type=gemini` project broke live. | Endpoint corrected in `_LEGACY_DEFAULTS`. | `019834a` |
| H3 | `translate_one_segment` held the WAL write lock across the provider network call (up to minutes × fallback chain × repair re-ask); with `busy_timeout=10s`, concurrent cockpit writes failed "database is locked" (symptom previously patched around in `e2aec0f`). | Provider calls run outside any transaction. Three short txns: mark `in_progress` → provider + enforcement (no txn) → result + memory + candidates + status in **one atomic commit**. Unexpected in-flight exception restores prior status; `reset_in_progress_segments` stays the crash net. State rule updated in CLAUDE.md/AGENTS.md §4.2 + `docs/CODEMAPS/data.md`. | `dee710f` |

## Medium/Low — carried into v0.7.3 planning (CLAUDE.md §2.3)

Medium: fallback-blind healthcheck; corrupt `connections.toml`/`secrets.toml` silently rewritten as empty on next write; legacy brand projects record `provider="custom"`; enforcement violations/repair outcomes not persisted (detection also gated by `enforce_repair`, contradicting its docstring); per-segment token-cost split (row vs run summary).
Low: `list_connections` N+1 TOML parse; `_escape` misses control chars; `weaver inspect` last direct `[provider]` reader (`services/project.py:244`).
Pending: live Gemini/Ollama validation (`requires_cloud`/`requires_ollama`); E2 repair token-cost delta on a live run; gemini shim default model `gemini-1.5-flash` retired upstream.
Speed candidate (needs ADR): bounded in-process translate concurrency, unlocked by H3.

## Validation Performed

`uv run ruff check .` clean · `uv run ruff format --check .` clean (385 files) · `uv run pyright src` 0 errors · `uv run pytest -q -m "not requires_cloud and not requires_ollama"` → **1614 passed, 1 skipped** (baseline 1609 + 5 new regression tests: secret-store fallback, shell-env-wins, gemini endpoint, provider-outside-transaction probe, prior-status restore).

## Known Risks

- H2 verified against ADR 018's decision text; live Gemini validation still pending on a real key.
- H3 changes crash-window semantics: a hard kill between the `in_progress` marker and the result commit leaves the segment `in_progress` until the next run's `reset_in_progress_segments` (previously the rollback was immediate). Covered by an explicit prior-status-restore test for the exception path.

## Recommended Next Role / Next Step

Owner: merge `fix/v072-audit-blockers` into `main`. Then Lead Orchestrator: write the v0.7.3 execution plan (Gate A) from the carry-forward list before any implementation.
