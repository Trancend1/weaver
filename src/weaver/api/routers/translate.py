"""AI translation endpoints: start chapter/selection jobs and read job status.

Stage 4A. POST endpoints validate the request synchronously (project, chapter,
selection, provider health) then background the per-segment translation on a worker
thread, returning ``202`` with a job id. ``GET .../jobs/{job_id}`` reads the job's
terminal state and result. Live progress, an SSE stream, and cancellation are 4B.

Thin adapter layer: domain logic stays in ``weaver.services.workspace_translate``;
the job registry lives in ``weaver.api.jobs``.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from weaver.api.jobs import (
    JobRegistry,
    TranslationJob,
    format_sse,
    parse_last_event_id,
    replay_persisted_events,
)
from weaver.api.schemas import (
    ChapterRetranslateRequest,
    ChapterTranslateRequest,
    SegmentSelectionRetranslateRequest,
    SegmentSelectionTranslateRequest,
    TranslationJobProgressResponse,
    TranslationJobResponse,
    TranslationJobResultResponse,
    TranslationJobStatusResponse,
)
from weaver.errors import (
    ChapterNotFoundError,
    ProviderError,
    SegmentNotFoundError,
    WeaverError,
)
from weaver.services.project_discovery import find_project
from weaver.services.workspace_translate import (
    TranslationPlan,
    prepare_chapter_translation,
    run_translation,
)

router = APIRouter(prefix="/projects", tags=["translate"])


def _base_dir(request: Request) -> Path:
    return request.app.state.base_dir  # type: ignore[no-any-return]


def _jobs(request: Request) -> JobRegistry:
    return request.app.state.jobs  # type: ignore[no-any-return]


def _provider_override(provider: str | None, model: str | None) -> dict[str, str] | None:
    override = {k: v for k, v in {"type": provider, "model": model}.items() if v is not None}
    return override or None


def _start_job(
    request: Request,
    name: str,
    chapter_id: str,
    *,
    segment_ids: list[str] | None,
    mode: str = "skip_existing",
    provider: str | None,
    model: str | None,
) -> TranslationJobResponse:
    base = _base_dir(request)
    dp = find_project(base, name)
    if dp is None:
        raise HTTPException(status_code=404, detail=f"Project '{name}' not found.")
    if dp.error:
        raise HTTPException(status_code=422, detail=dp.error)

    try:
        plan = prepare_chapter_translation(
            dp.project_toml,
            chapter_id,
            segment_ids=segment_ids,
            mode=mode,
            cwd=base,
            provider_override=_provider_override(provider, model),
        )
    except (ChapterNotFoundError, SegmentNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except WeaverError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    def runner(should_cancel, progress, plan: TranslationPlan = plan):  # bind plan per job
        return run_translation(plan, should_cancel=should_cancel, progress_callback=progress)

    job = _jobs(request).submit(
        project_name=name,
        chapter_id=chapter_id,
        mode=plan.mode,
        total=len(plan.target_segment_ids),
        runner=runner,
    )
    return TranslationJobResponse(
        job_id=job.id,
        status=job.status,
        chapter_id=job.chapter_id,
        mode=job.mode,
    )


@router.post(
    "/{name}/chapters/{chapter_id}/translate",
    response_model=TranslationJobResponse,
    status_code=202,
)
def translate_chapter(
    name: str,
    chapter_id: str,
    body: ChapterTranslateRequest,
    request: Request,
) -> TranslationJobResponse:
    """Start a background job translating one chapter's untranslated segments.

    Already ``translated`` / ``manual`` segments are skipped. ``provider`` / ``model``
    override the project's configured provider for this run only. Rejects unknown
    project (404), chapter (404), bad config/glossary (422), and unhealthy
    provider (502).
    """
    return _start_job(
        request,
        name,
        chapter_id,
        segment_ids=None,
        provider=body.provider,
        model=body.model,
    )


@router.post(
    "/{name}/chapters/{chapter_id}/translate-segments",
    response_model=TranslationJobResponse,
    status_code=202,
)
def translate_segments(
    name: str,
    chapter_id: str,
    body: SegmentSelectionTranslateRequest,
    request: Request,
) -> TranslationJobResponse:
    """Start a background job translating a chosen set of segments in one chapter.

    Each id must belong to ``chapter_id``; already-translated segments among the
    selection are skipped. Rejects unknown project (404), chapter (404), unknown /
    wrong-chapter segment (404), empty selection (422), and unhealthy provider (502).
    """
    return _start_job(
        request,
        name,
        chapter_id,
        segment_ids=body.segment_ids,
        provider=body.provider,
        model=body.model,
    )


@router.post(
    "/{name}/chapters/{chapter_id}/retranslate",
    response_model=TranslationJobResponse,
    status_code=202,
)
def retranslate_chapter(
    name: str,
    chapter_id: str,
    body: ChapterRetranslateRequest,
    request: Request,
) -> TranslationJobResponse:
    """Start a background job re-translating a chapter under an explicit mode.

    ``mode`` controls overwrite: ``skip_existing`` (default, never overwrites),
    ``retranslate_non_manual`` (re-translates ``translated`` but protects
    ``manual``), or ``force_selected`` (overwrites everything, including
    ``manual``). Each retranslated segment appends a new attempt; prior attempts
    stay as immutable history.
    """
    return _start_job(
        request,
        name,
        chapter_id,
        segment_ids=None,
        mode=body.mode,
        provider=body.provider,
        model=body.model,
    )


@router.post(
    "/{name}/chapters/{chapter_id}/retranslate-segments",
    response_model=TranslationJobResponse,
    status_code=202,
)
def retranslate_segments(
    name: str,
    chapter_id: str,
    body: SegmentSelectionRetranslateRequest,
    request: Request,
) -> TranslationJobResponse:
    """Start a background job re-translating a chosen set of segments under a mode.

    Same overwrite semantics as :func:`retranslate_chapter`; ``manual`` segments in
    the selection are only overwritten when ``mode`` is ``force_selected``.
    """
    return _start_job(
        request,
        name,
        chapter_id,
        segment_ids=body.segment_ids,
        mode=body.mode,
        provider=body.provider,
        model=body.model,
    )


@router.get(
    "/{name}/jobs/{job_id}",
    response_model=TranslationJobStatusResponse,
)
def get_translation_job(name: str, job_id: str, request: Request) -> TranslationJobStatusResponse:
    """Return a translate job's live progress, status, and (once finished) result."""
    return _job_status(_require_job(request, name, job_id))


@router.post(
    "/{name}/jobs/{job_id}/cancel",
    response_model=TranslationJobStatusResponse,
)
def cancel_translation_job(
    name: str, job_id: str, request: Request
) -> TranslationJobStatusResponse:
    """Request a cooperative cancel of a running job.

    The worker stops after the current segment; already-translated segments stay
    committed. Idempotent and safe to call on a finished job (no-op). Returns the
    job's current status.
    """
    job = _require_job(request, name, job_id)
    job.request_cancel()
    return _job_status(job)


@router.get("/{name}/jobs/{job_id}/events")
def stream_translation_job(name: str, job_id: str, request: Request) -> StreamingResponse:
    """Stream a job's progress as Server-Sent Events until it finishes.

    Single-consumer for the live tail: events are drained from the job's queue,
    so one client reads one stream. Reconnecting clients pass ``Last-Event-Id``
    (header or ``?last_event_id=`` query) and receive every persisted event
    strictly newer than that id before the live tail resumes (Sprint I4 / ADR
    010). A finished job's full event log is served from SQLite alone.
    """
    job = _require_job(request, name, job_id)
    last_event_id = parse_last_event_id(
        request.headers.get("Last-Event-Id") or request.query_params.get("last_event_id")
    )
    db_path = job.storage.db_path if job.storage is not None else None
    terminal_at_open = job.status in {"done", "failed", "cancelled"}

    def stream() -> Iterator[str]:
        seen: set[int] = set()
        for envelope in replay_persisted_events(db_path, job_id, after_id=last_event_id):
            seen.add(int(envelope["id"]))
            yield format_sse(envelope)
        if terminal_at_open:
            # The job already finished. The queue's stream-end sentinel has
            # almost certainly been drained by an earlier subscriber; replay
            # alone is the authoritative event log (Sprint I4 / ADR 010).
            return
        while True:
            event = job.queue.get()
            if event is None:  # stream-end sentinel
                break
            if isinstance(event.get("id"), int) and event["id"] in seen:
                continue
            yield format_sse(event)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _require_job(request: Request, name: str, job_id: str) -> TranslationJob:
    job = _jobs(request).get(job_id)
    if job is None or job.project_name != name:
        raise HTTPException(
            status_code=404, detail=f"Translation job '{job_id}' not found for project '{name}'."
        )
    return job


def _job_status(job: TranslationJob) -> TranslationJobStatusResponse:
    progress = job.snapshot()
    result = None
    if job.result is not None:
        r = job.result
        result = TranslationJobResultResponse(
            chapter_id=r.chapter_id,
            selected=r.selected,
            translated=r.translated,
            reused_from_memory=r.reused_from_memory,
            failed=r.failed,
            skipped=r.skipped,
            input_tokens=r.input_tokens,
            output_tokens=r.output_tokens,
            cancelled=r.cancelled,
        )
    return TranslationJobStatusResponse(
        job_id=job.id,
        status=job.status,
        chapter_id=job.chapter_id,
        mode=job.mode,
        progress=TranslationJobProgressResponse(
            current=progress.current,
            total=progress.total,
            translated=progress.translated,
            failed=progress.failed,
        ),
        result=result,
        error=job.error,
    )
