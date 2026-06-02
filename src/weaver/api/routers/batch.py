"""Batch AI-translation endpoints: start chapter/volume/novel jobs + read status.

Stage 7B. POST endpoints validate the request synchronously (project, scope,
provider health) then background the multi-chapter translation on a worker
thread, returning ``202`` with a job id. The status/cancel/events endpoints live
under a distinct ``/batch/jobs/`` prefix so they never collide with the
start routes.

Thin adapter layer: domain logic stays in ``weaver.services.batch_translate``;
the job registry lives in ``weaver.api.jobs``. The per-chapter translate /
retranslate endpoints (``weaver.api.routers.translate``) are untouched.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from weaver.api.jobs import BatchJob, JobRegistry, format_sse
from weaver.api.schemas import (
    BatchChapterOutcomeResponse,
    BatchJobProgressResponse,
    BatchJobResponse,
    BatchJobResultResponse,
    BatchJobStatusResponse,
    BatchTranslateRequest,
)
from weaver.errors import (
    ChapterNotFoundError,
    ProviderError,
    VolumeNotFoundError,
    WeaverError,
)
from weaver.services.batch_translate import (
    BatchPlan,
    prepare_batch_translation,
    run_batch_translation,
)
from weaver.services.project_discovery import find_project

router = APIRouter(prefix="/projects", tags=["batch"])


def _base_dir(request: Request) -> Path:
    return request.app.state.base_dir  # type: ignore[no-any-return]


def _jobs(request: Request) -> JobRegistry:
    return request.app.state.jobs  # type: ignore[no-any-return]


def _provider_override(provider: str | None, model: str | None) -> dict[str, str] | None:
    override = {k: v for k, v in {"type": provider, "model": model}.items() if v is not None}
    return override or None


def _start_batch(
    request: Request,
    name: str,
    *,
    scope: str,
    target_id: str | None,
    body: BatchTranslateRequest,
) -> BatchJobResponse:
    base = _base_dir(request)
    dp = find_project(base, name)
    if dp is None:
        raise HTTPException(status_code=404, detail=f"Project '{name}' not found.")
    if dp.error:
        raise HTTPException(status_code=422, detail=dp.error)

    try:
        plan = prepare_batch_translation(
            dp.project_toml,
            scope=scope,
            target_id=target_id,
            mode=body.mode,
            cwd=base,
            provider_override=_provider_override(body.provider, body.model),
        )
    except (ChapterNotFoundError, VolumeNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except WeaverError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    def runner(should_cancel, progress, plan: BatchPlan = plan):  # bind plan per job
        return run_batch_translation(plan, should_cancel=should_cancel, progress_callback=progress)

    job = _jobs(request).submit_batch(
        project_name=name,
        scope=plan.scope,
        scope_id=plan.scope_id,
        mode=plan.mode,
        runner=runner,
    )
    return BatchJobResponse(
        job_id=job.id,
        status=job.status,
        scope=job.scope,
        scope_id=job.scope_id,
        mode=job.mode,
    )


@router.post("/{name}/batch/novel", response_model=BatchJobResponse, status_code=202)
def batch_translate_novel(
    name: str, body: BatchTranslateRequest, request: Request
) -> BatchJobResponse:
    """Start a background job translating every chapter in the novel.

    Chapters run in reading order across volumes. ``mode`` governs overwrite
    (``skip_existing`` default). Rejects unknown project (404), bad config/mode
    (422), and unhealthy provider (502). An empty novel returns 202 and a job
    that finishes immediately with zero counts."""
    return _start_batch(request, name, scope="novel", target_id=None, body=body)


@router.post("/{name}/batch/volumes/{volume_id}", response_model=BatchJobResponse, status_code=202)
def batch_translate_volume(
    name: str, volume_id: str, body: BatchTranslateRequest, request: Request
) -> BatchJobResponse:
    """Start a background job translating every chapter in one volume.

    Rejects unknown project (404), unknown volume (404), bad config/mode (422),
    and unhealthy provider (502)."""
    return _start_batch(request, name, scope="volume", target_id=volume_id, body=body)


@router.post(
    "/{name}/batch/chapters/{chapter_id}", response_model=BatchJobResponse, status_code=202
)
def batch_translate_chapter(
    name: str, chapter_id: str, body: BatchTranslateRequest, request: Request
) -> BatchJobResponse:
    """Start a background batch job scoped to one chapter.

    Same overwrite semantics as the novel/volume routes; useful for a uniform
    batch-progress shape over a single chapter. Rejects unknown project (404),
    unknown chapter (404), bad config/mode (422), and unhealthy provider (502)."""
    return _start_batch(request, name, scope="chapter", target_id=chapter_id, body=body)


@router.get("/{name}/batch/jobs/{job_id}", response_model=BatchJobStatusResponse)
def get_batch_job(name: str, job_id: str, request: Request) -> BatchJobStatusResponse:
    """Return a batch job's live aggregate progress, status, and (once done) result."""
    return _batch_status(_require_batch_job(request, name, job_id))


@router.post("/{name}/batch/jobs/{job_id}/cancel", response_model=BatchJobStatusResponse)
def cancel_batch_job(name: str, job_id: str, request: Request) -> BatchJobStatusResponse:
    """Request a cooperative cancel of a running batch job.

    The worker stops after the current segment (and before the next chapter);
    already-translated segments stay committed. Idempotent and safe on a finished
    job (no-op). Returns the job's current status."""
    job = _require_batch_job(request, name, job_id)
    job.request_cancel()
    return _batch_status(job)


@router.get("/{name}/batch/jobs/{job_id}/events")
def stream_batch_job(name: str, job_id: str, request: Request) -> StreamingResponse:
    """Stream a batch job's aggregate progress as Server-Sent Events until done.

    Single-consumer: events are drained from the job's queue. A late subscriber
    still sees the buffered progress events followed by the terminal event."""
    job = _require_batch_job(request, name, job_id)

    def stream() -> Iterator[str]:
        while True:
            event = job.queue.get()
            if event is None:  # stream-end sentinel
                break
            yield format_sse(event)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _require_batch_job(request: Request, name: str, job_id: str) -> BatchJob:
    job = _jobs(request).get_batch(job_id)
    if job is None or job.project_name != name:
        raise HTTPException(
            status_code=404, detail=f"Batch job '{job_id}' not found for project '{name}'."
        )
    return job


def _batch_status(job: BatchJob) -> BatchJobStatusResponse:
    progress = job.snapshot()
    result = None
    if job.result is not None:
        r = job.result
        result = BatchJobResultResponse(
            scope=r.scope,
            scope_id=r.scope_id,
            mode=r.mode,
            provider=r.provider,
            model=r.model,
            chapters_total=r.chapters_total,
            chapters_done=r.chapters_done,
            segments_total=r.segments_total,
            translated=r.translated,
            reused_from_memory=r.reused_from_memory,
            skipped=r.skipped,
            failed=r.failed,
            input_tokens=r.input_tokens,
            output_tokens=r.output_tokens,
            cancelled=r.cancelled,
            started_at=r.started_at,
            finished_at=r.finished_at,
            duration_seconds=r.duration_seconds,
            chapters=[
                BatchChapterOutcomeResponse(
                    chapter_id=c.chapter_id,
                    selected=c.selected,
                    translated=c.translated,
                    reused_from_memory=c.reused_from_memory,
                    failed=c.failed,
                    skipped=c.skipped,
                    input_tokens=c.input_tokens,
                    output_tokens=c.output_tokens,
                    cancelled=c.cancelled,
                )
                for c in r.chapters
            ],
        )
    return BatchJobStatusResponse(
        job_id=job.id,
        status=job.status,
        scope=job.scope,
        scope_id=job.scope_id,
        mode=job.mode,
        progress=BatchJobProgressResponse(
            scope=progress.scope,
            scope_id=progress.scope_id,
            mode=progress.mode,
            provider=progress.provider,
            model=progress.model,
            chapters_total=progress.chapters_total,
            chapters_done=progress.chapters_done,
            current_chapter_id=progress.current_chapter_id,
            segments_total=progress.segments_total,
            segments_done=progress.segments_done,
            translated=progress.translated,
            reused_from_memory=progress.reused_from_memory,
            skipped=progress.skipped,
            failed=progress.failed,
        ),
        result=result,
        error=job.error,
    )
