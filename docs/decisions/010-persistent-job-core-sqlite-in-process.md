# ADR 010 — Persistent Job Core (SQLite-backed, single-process)

## Status

Accepted (maintainer, 2026-06-08). Locked **before** Sprint I begins. Companion to ADR `009`.

## Context

`src/weaver/api/jobs.py` (Sprints 4A/4B) holds translate, batch-translate, and export progress in memory:

```python
# JobRegistry is temporary infrastructure.
# Do not build Celery, Redis, RabbitMQ, Kafka, Dramatiq, RQ, or distributed workers.
# Single-process thread worker only.
```

Three job types (`TranslationJob`, `BatchJob`, `ExportJob`) share a status state machine (`running → done | failed | cancelled`), an SSE event queue, a `threading.Event` cancel flag, and per-id lookup. Two consequences in practice:

1. **Refresh loses live progress.** The HTMX cockpit re-renders the job panel from in-memory state; a browser refresh, a navigation away, or a process restart drops the live counters.
2. **No job history.** Once a worker thread finishes, the registry entry remains in memory only — there is no way to ask "what jobs ran today?" after a restart.

Sprint I in [weaver_next_plan.md](../weaver_next_plan.md) needs persistence to: survive refresh, survive process restart, list active and historical jobs, and let later sprints (parse-as-job in J, export-as-job in K, OCR-as-job in M) plug in without re-inventing progress storage.

The temptation, when adding persistence, is to introduce a queue broker (Celery / Redis / RQ). CLAUDE.md §3 rejects all of them, and the comment in `jobs.py` predates SQLite persistence and still applies.

## Decision

**Persist job state to SQLite. Keep the worker model strictly single-process and in-thread.**

### Allowed

```text
FastAPI process
  └── in-process JobRegistry (api/jobs.py)
       └── threading.Thread workers (existing)
            └── SQLite persistence for:
                 status · progress counters · current_label · errors ·
                 started_at / finished_at · history · cancel-flag mirror
```

### Forbidden (unchanged from CLAUDE.md §3 + `api/jobs.py:8-10`)

```text
Celery · Redis · RabbitMQ · Kafka · Dramatiq · RQ
External worker daemon
Multi-process queue
Multi-node scheduler
Cron / scheduled background jobs without an ADR
```

### Schema (additive, v4 → v5; full DDL in Sprint I scope)

```text
jobs                      — one row per job (chapter / batch / export / parse / ocr)
job_events                — already exists; add nullable job_id; backfill = NULL
job_progress_snapshots    — sampled progress for resume / history graphs
```

`jobs.status` reuses the existing state machine plus three new transitional states (`queued`, `processed`, `finalizing`) reserved for downstream sprints (export staging, OCR batch finalize). Adding them now avoids a second migration later.

### Cold-start recovery

On FastAPI startup the registry runs **exactly one** recovery pass: any `jobs.status = 'running'` row gets `status = 'failed'`, `error_summary = 'process restart'`, `finished_at = now()`. **No auto-resume** — the single-process invariant means a previous worker thread cannot be revived.

### Write cadence

- Status transitions (`running → done | failed | cancelled`): synchronous SQLite write inside the worker before the terminal SSE event.
- Per-segment / per-snapshot progress: persisted on a **1-second snapshot interval**, not per event. The in-process queue stays the source of truth for live SSE; SQLite is the read-back on refresh.
- Cancel: persisted immediately so a refresh after cancel does not show `running`.

### SSE resume

`GET /jobs/{job_id}/stream` includes the last persisted event id as `Last-Event-Id`; reconnects skip already-delivered events.

## Consequences

**Improves.**

- Refresh-safe progress without changing the stack.
- One job model used by every long-running workflow (Sprint I wires `import_source`, `translation`, `batch_translate`, `export_book`; J wires parse; M wires OCR).
- Boundary is explicit: SQLite is the durability layer, not a queue. Future contributors cannot read "persistent jobs" as "ok to add Celery".

**Tradeoffs.**

- No multi-process parallelism. Multiple translate jobs still serialize on the GIL-bound worker pool; this matches current behavior and is acceptable for a local cockpit. Lifting this restriction needs its own ADR.
- SQLite write contention is possible under fast SSE updates. Mitigated by the 1 s snapshot interval and by keeping per-event writes off the hot path.
- Cold-start recovery is destructive (running jobs become failed). The single-process invariant makes any other recovery dishonest; users see the failure in history and can re-submit.

## Related Files

- `src/weaver/api/jobs.py` — registry to extend (do not rewrite); the existing `JobRunner`, `BatchJobRunner`, `ExportJobRunner` types are preserved.
- `src/weaver/storage/schema.sql` — adds `jobs`, `job_progress_snapshots`; `job_events` gains `job_id`.
- `src/weaver/storage/migrations.py` — v4 → v5 migration with idempotency test.
- `src/weaver/services/{import_source,translation,batch_translate,export_book}.py` — call sites that submit jobs.
- ADR [`004`](004-fastapi-cockpit-technical-direction.md), ADR [`009`](009-htmx-first-fastapi-stable-tauri-sidecar-ready.md).
- [docs/weaver_next_plan.md](../weaver_next_plan.md) Sprint I — full schema + acceptance criteria.
