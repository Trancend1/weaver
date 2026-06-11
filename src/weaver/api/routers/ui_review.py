"""UI router: review + reading preview (Sprint Q2a split).

Split from the monolithic `ui.py` router.  Zero behaviour change.
"""

from __future__ import annotations

from contextlib import closing

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from weaver.api.routers.ui import _base_dir, _import_error
from weaver.api.templating import templates
from weaver.api.ui_context import project_layout
from weaver.errors import (
    ChapterNotFoundError,
    SegmentNotFoundError,
    VolumeNotFoundError,
    WeaverError,
)
from weaver.services.project_discovery import find_project
from weaver.services.project_paths import resolve_database_path
from weaver.services.reading_preview import (
    reading_preview_for_chapter,
    reading_preview_for_volume,
)
from weaver.services.segment_review import (
    list_review_queue,
    set_segment_review_status,
)
from weaver.storage.db import connect_readonly_database

router = APIRouter(tags=["ui"], include_in_schema=False)


# --- reading preview (Sprint P2 — WV-002) ------------------------------------


@router.get("/ui/projects/{name}/volumes/{volume_id}/preview", response_class=HTMLResponse)
def ui_volume_reading_preview(
    name: str,
    volume_id: int,
    request: Request,
    mode: str = Query("reading"),
) -> HTMLResponse:
    """Read-only reading preview for one volume."""

    base = _base_dir(request)
    dp = find_project(base, name)
    if dp is None:
        return templates.TemplateResponse(
            request,
            "not_found.html",
            {"message": f"No project named {name!r} under {base}."},
            status_code=404,
        )
    if dp.error:
        return templates.TemplateResponse(
            request, "error.html", {"message": dp.error}, status_code=422
        )
    try:
        chapters = reading_preview_for_volume(dp.project_toml, volume_id, cwd=base)
    except VolumeNotFoundError as exc:
        return templates.TemplateResponse(
            request, "not_found.html", {"message": str(exc)}, status_code=404
        )
    except WeaverError as exc:
        return templates.TemplateResponse(
            request, "error.html", {"message": str(exc)}, status_code=422
        )
    return templates.TemplateResponse(
        request,
        "reading_preview.html",
        {
            **project_layout(request, name, active_nav="project"),
            "project_name": name,
            "volume_id": volume_id,
            "chapter_id": None,
            "mode": mode,
            "base_url": request.url.path,
            "chapters": chapters,
        },
    )


@router.get("/ui/projects/{name}/chapters/{chapter_id}/preview", response_class=HTMLResponse)
def ui_chapter_reading_preview(
    name: str,
    chapter_id: str,
    request: Request,
    mode: str = Query("reading"),
) -> HTMLResponse:
    """Read-only reading preview for one chapter."""

    base = _base_dir(request)
    dp = find_project(base, name)
    if dp is None:
        return templates.TemplateResponse(
            request,
            "not_found.html",
            {"message": f"No project named {name!r} under {base}."},
            status_code=404,
        )
    if dp.error:
        return templates.TemplateResponse(
            request, "error.html", {"message": dp.error}, status_code=422
        )
    try:
        chapter = reading_preview_for_chapter(dp.project_toml, chapter_id, cwd=base)
    except ChapterNotFoundError as exc:
        return templates.TemplateResponse(
            request, "not_found.html", {"message": str(exc)}, status_code=404
        )
    except WeaverError as exc:
        return templates.TemplateResponse(
            request, "error.html", {"message": str(exc)}, status_code=422
        )
    return templates.TemplateResponse(
        request,
        "reading_preview.html",
        {
            **project_layout(request, name, active_nav="project"),
            "project_name": name,
            "volume_id": None,
            "chapter_id": chapter_id,
            "mode": mode,
            "base_url": request.url.path,
            "chapters": [chapter],
        },
    )


# --- review status (Sprint P3 — WV-003) ------------------------------------


@router.post("/ui/projects/{name}/segments/{segment_id}/review", response_class=HTMLResponse)
def ui_segment_review(
    name: str,
    segment_id: str,
    request: Request,
    review_status: str = Query(...),
) -> HTMLResponse:
    """Set a segment's review status and re-render the segment row (HTMX)."""
    base = _base_dir(request)
    dp = find_project(base, name)
    if dp is None:
        raise HTTPException(status_code=404, detail=f"No project named {name!r}.")
    if dp.error:
        return _import_error(request, dp.error)
    try:
        set_segment_review_status(dp.project_toml, segment_id, review_status, cwd=base)
    except SegmentNotFoundError as exc:
        return templates.TemplateResponse(
            request,
            "not_found.html",
            {"message": str(exc)},
            status_code=404,
        )
    except WeaverError as exc:
        return _import_error(request, str(exc))
    # Return only the statusline fragment — not the full segment row.
    from weaver.storage.segments import get_segment

    seg_status = "pending"
    try:
        with closing(
            connect_readonly_database(resolve_database_path(dp.project_toml, cwd=base))
        ) as conn:
            seg_record = get_segment(conn, segment_id)
            if seg_record is not None:
                seg_status = seg_record.status
    except Exception:
        pass
    return templates.TemplateResponse(
        request,
        "partials/_segment_statusline.html",
        {
            "seg_id": segment_id,
            "status": seg_status,
            "review_status": review_status,
        },
    )


@router.get("/ui/projects/{name}/volumes/{volume_id}/review", response_class=HTMLResponse)
def ui_review_queue(
    name: str,
    volume_id: int,
    request: Request,
    status_filter: str = Query(""),
) -> HTMLResponse:
    """Review queue for one volume."""
    base = _base_dir(request)
    dp = find_project(base, name)
    if dp is None:
        return templates.TemplateResponse(
            request,
            "not_found.html",
            {"message": f"No project named {name!r} under {base}."},
            status_code=404,
        )
    if dp.error:
        return _import_error(request, dp.error)
    from weaver.errors import VolumeNotFoundError

    try:
        queue = list_review_queue(
            dp.project_toml,
            volume_id,
            status_filter=status_filter or None,
            cwd=base,
        )
    except VolumeNotFoundError as exc:
        return templates.TemplateResponse(
            request, "not_found.html", {"message": str(exc)}, status_code=404
        )
    except WeaverError as exc:
        return _import_error(request, str(exc))
    return templates.TemplateResponse(
        request,
        "review_queue.html",
        {
            **project_layout(request, name, active_nav="project"),
            "project_name": name,
            "volume_id": volume_id,
            "status_filter": status_filter,
            "queue": queue,
        },
    )
