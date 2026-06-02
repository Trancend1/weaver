"""Export endpoints: start novel/volume/chapter EPUB export + read status/SSE.

Stage 8B. POST endpoints validate the request synchronously (project, scope,
target) via :func:`weaver.services.export_book.prepare_export`, then background
the per-volume render on a worker thread, returning ``202`` with a job id. The
status/cancel/events endpoints live under a distinct ``/export/jobs/`` prefix so
they never collide with the start routes or the batch/chapter job namespaces.

Thin adapter layer: domain logic stays in ``weaver.services.export_book``; the job
registry lives in ``weaver.api.jobs``. Translation, translation-memory, and
provider paths are untouched.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from weaver.api.jobs import ExportJob, JobRegistry, format_sse
from weaver.api.schemas import (
    ExportArtifactResponse,
    ExportFallbackByStatusResponse,
    ExportJobProgressResponse,
    ExportJobResponse,
    ExportJobResultResponse,
    ExportJobStatusResponse,
    ExportRequest,
)
from weaver.errors import ChapterNotFoundError, VolumeNotFoundError, WeaverError
from weaver.services.export_book import ExportPlan, prepare_export, run_export
from weaver.services.project_discovery import find_project

router = APIRouter(prefix="/projects", tags=["export"])


def _base_dir(request: Request) -> Path:
    return request.app.state.base_dir  # type: ignore[no-any-return]


def _jobs(request: Request) -> JobRegistry:
    return request.app.state.jobs  # type: ignore[no-any-return]


def _start_export(
    request: Request,
    name: str,
    *,
    scope: str,
    target_id: str | None,
    body: ExportRequest | None,
) -> ExportJobResponse:
    options = body or ExportRequest()
    base = _base_dir(request)
    dp = find_project(base, name)
    if dp is None:
        raise HTTPException(status_code=404, detail=f"Project '{name}' not found.")
    if dp.error:
        raise HTTPException(status_code=422, detail=dp.error)

    try:
        plan = prepare_export(
            dp.project_toml,
            scope=scope,
            target_id=target_id,
            target=options.target,
            cwd=base,
        )
    except (ChapterNotFoundError, VolumeNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except WeaverError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    def runner(should_cancel, progress, plan: ExportPlan = plan):  # bind plan per job
        return run_export(plan, should_cancel=should_cancel, progress_callback=progress)

    job = _jobs(request).submit_export(
        project_name=name,
        scope=plan.scope,
        scope_id=plan.scope_id,
        target=plan.target,
        runner=runner,
    )
    return ExportJobResponse(
        job_id=job.id,
        status=job.status,
        scope=job.scope,
        scope_id=job.scope_id,
        target=job.target,
    )


@router.post("/{name}/export/novel", response_model=ExportJobResponse, status_code=202)
def export_novel(
    name: str, request: Request, body: ExportRequest | None = None
) -> ExportJobResponse:
    """Start a background job exporting every volume to its own EPUB.

    One artifact per volume (no cross-EPUB merge). Rejects unknown project (404),
    unsupported target (422). An empty novel returns 202 and a job that finishes
    immediately with zero artifacts."""
    return _start_export(request, name, scope="novel", target_id=None, body=body)


@router.post(
    "/{name}/export/volumes/{volume_id}", response_model=ExportJobResponse, status_code=202
)
def export_volume(
    name: str, volume_id: str, request: Request, body: ExportRequest | None = None
) -> ExportJobResponse:
    """Start a background job exporting one volume to its own EPUB.

    Rejects unknown project (404), unknown volume (404), unsupported target (422)."""
    return _start_export(request, name, scope="volume", target_id=volume_id, body=body)


@router.post(
    "/{name}/export/chapters/{chapter_id}", response_model=ExportJobResponse, status_code=202
)
def export_chapter(
    name: str, chapter_id: str, request: Request, body: ExportRequest | None = None
) -> ExportJobResponse:
    """Start a background job exporting one chapter to its own EPUB.

    Rejects unknown project (404), unknown chapter (404), unsupported target (422)."""
    return _start_export(request, name, scope="chapter", target_id=chapter_id, body=body)


@router.get("/{name}/export/jobs/{job_id}", response_model=ExportJobStatusResponse)
def get_export_job(name: str, job_id: str, request: Request) -> ExportJobStatusResponse:
    """Return an export job's live progress, status, and (once done) result."""
    return _export_status(_require_export_job(request, name, job_id))


@router.post("/{name}/export/jobs/{job_id}/cancel", response_model=ExportJobStatusResponse)
def cancel_export_job(name: str, job_id: str, request: Request) -> ExportJobStatusResponse:
    """Request a cooperative cancel of a running export job.

    The worker stops before the next volume; already-written artifacts stay.
    Idempotent and safe on a finished job (no-op). Returns the current status."""
    job = _require_export_job(request, name, job_id)
    job.request_cancel()
    return _export_status(job)


@router.get("/{name}/export/jobs/{job_id}/events")
def stream_export_job(name: str, job_id: str, request: Request) -> StreamingResponse:
    """Stream an export job's per-volume progress as Server-Sent Events until done.

    Single-consumer: events are drained from the job's queue. A late subscriber
    still sees the buffered progress events followed by the terminal event."""
    job = _require_export_job(request, name, job_id)

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


def _require_export_job(request: Request, name: str, job_id: str) -> ExportJob:
    job = _jobs(request).get_export(job_id)
    if job is None or job.project_name != name:
        raise HTTPException(
            status_code=404, detail=f"Export job '{job_id}' not found for project '{name}'."
        )
    return job


def _export_status(job: ExportJob) -> ExportJobStatusResponse:
    progress = job.snapshot()
    result = None
    if job.result is not None:
        r = job.result
        result = ExportJobResultResponse(
            target=r.target,
            scope=r.scope,
            scope_id=r.scope_id,
            output_dir=str(r.output_dir),
            volumes_total=r.volumes_total,
            volumes_exported=r.volumes_exported,
            chapters_exported=r.chapters_exported,
            translated_segments=r.translated_segments,
            fallback_segments=r.fallback_segments,
            generated_at=r.generated_at,
            cancelled=r.cancelled,
            artifacts=[
                ExportArtifactResponse(
                    volume_id=a.volume_id,
                    volume_title=a.volume_title,
                    source_format=a.source_format,
                    output_path=str(a.output_path),
                    chapters_exported=a.chapters_exported,
                    translated_segments=a.translated_segments,
                    fallback_segments=a.fallback_segments,
                    fallback_by_status=ExportFallbackByStatusResponse(
                        pending=a.fallback_by_status.pending,
                        in_progress=a.fallback_by_status.in_progress,
                        failed=a.fallback_by_status.failed,
                        stale=a.fallback_by_status.stale,
                        skipped=a.fallback_by_status.skipped,
                        untranslated=a.fallback_by_status.untranslated,
                    ),
                )
                for a in r.artifacts
            ],
        )
    return ExportJobStatusResponse(
        job_id=job.id,
        status=job.status,
        scope=job.scope,
        scope_id=job.scope_id,
        target=job.target,
        progress=ExportJobProgressResponse(
            target=progress.target,
            scope=progress.scope,
            scope_id=progress.scope_id,
            volumes_total=progress.volumes_total,
            volumes_done=progress.volumes_done,
            current_volume_id=progress.current_volume_id,
            current_volume_title=progress.current_volume_title,
            translated_segments=progress.translated_segments,
            fallback_segments=progress.fallback_segments,
        ),
        result=result,
        error=job.error,
    )
