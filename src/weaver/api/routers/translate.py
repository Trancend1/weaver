"""AI translation endpoints: start chapter/selection jobs and read job status.

Stage 4A. POST endpoints validate the request synchronously (project, chapter,
selection, provider health) then background the per-segment translation on a worker
thread, returning ``202`` with a job id. ``GET .../jobs/{job_id}`` reads the job's
terminal state and result. Live progress, an SSE stream, and cancellation are 4B.

Thin adapter layer: domain logic stays in ``weaver.services.workspace_translate``;
the job registry lives in ``weaver.api.jobs``.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from weaver.api.jobs import JobRegistry, TranslationJob
from weaver.api.schemas import (
    ChapterTranslateRequest,
    SegmentSelectionTranslateRequest,
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

    def runner(plan: TranslationPlan = plan):  # bind plan per job
        return run_translation(plan)

    job = _jobs(request).submit(
        project_name=name,
        chapter_id=chapter_id,
        mode=plan.mode,
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


@router.get(
    "/{name}/jobs/{job_id}",
    response_model=TranslationJobStatusResponse,
)
def get_translation_job(name: str, job_id: str, request: Request) -> TranslationJobStatusResponse:
    """Return a translate job's current status and (once finished) its result."""
    job = _jobs(request).get(job_id)
    if job is None or job.project_name != name:
        raise HTTPException(
            status_code=404, detail=f"Translation job '{job_id}' not found for project '{name}'."
        )
    return _job_status(job)


def _job_status(job: TranslationJob) -> TranslationJobStatusResponse:
    result = None
    if job.result is not None:
        r = job.result
        result = TranslationJobResultResponse(
            chapter_id=r.chapter_id,
            selected=r.selected,
            translated=r.translated,
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
        result=result,
        error=job.error,
    )
