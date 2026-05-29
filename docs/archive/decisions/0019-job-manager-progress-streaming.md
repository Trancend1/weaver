# 0019: Job Manager and Progress Streaming

Date: 2026-05-29
Status: accepted

## Context

The cockpit (ADR `0016`) must run translate jobs (long-running, many provider calls) and stream live progress to the browser (PP3). The CLI runs translate synchronously in the foreground with a Rich progress bar; a web request cannot block for minutes. The locked stack rejects asyncio and queue/worker frameworks (Celery/RQ). `translate_project` currently has no cancel path, so a "stop" button is impossible without a code change.

The maintainer chose **one translate job at a time** (decision: concurrency model) — no parallel jobs, no job queue, in v1.

## Decision

Add `src/weaver/web/job_manager.py`: an in-memory, threaded, single-job registry.

- **One job at a time.** A global lock guards the single active job. A second `POST .../translate` while a job runs is rejected with a clear message + a link to the running job. No queue.
- **Background thread.** The worker runs `translate_project` in one `threading.Thread`. No asyncio, no process pool, no external worker.
- **Progress transport.** The worker pushes progress events onto a thread-safe `queue.Queue`. The SSE route (`GET /project/<name>/events`, `text/event-stream`) drains the queue to the client. Events:
  - `event: progress` → `{current, total, segment_id, status, input_tokens, output_tokens}`
  - `event: done` → `{selected, translated, failed, pending, stale, input_tokens, output_tokens}`
  - `event: error` → `{message}`
- **Cooperative cancel.** `translate_project` gains an optional `should_cancel: Callable[[], bool] | None`, checked between segments. The CLI passes `None` (no behavior change). The JobManager passes a flag set by `POST .../translate/stop`. No thread kill — the worker stops cleanly between segments, leaving state consistent (one segment = one transaction, unchanged).
- **State after restart.** The registry is in-memory only; a server restart loses live-job tracking, but all translated segments are already persisted in SQLite. A reopened cockpit reflects true DB state via `inspect_project`.

## Consequences

Easier: live monitoring with no asyncio and no broker; SQLite WAL allows the dashboard to read status while the worker writes; cancel is safe because it is cooperative and transactional.

Harder: single-job means a second project must wait — acceptable for a single-user tool; a job queue is deferred to a future ADR. The cancel hook adds one optional parameter to `translate_project` (additive, wire-compatible). SSE under the Flask dev server requires `threaded=True` (ADR `0016`, D1).
