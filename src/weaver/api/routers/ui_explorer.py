"""UI router: per-volume Content Explorer (Sprint Q9).

Promotes the structure surface to a tabbed Content Explorer:
Structure · Segments · Assets · Metadata · Warnings.

Read-only and snapshot-fed: structure/assets/metadata/warnings render from the
persisted EPUB snapshot (``read_snapshot``, readonly); segments render from the
project DB via ``services/segment_listing``. **No reparse, no source-file
hashing, no archive access, no QA scan, no provider call on render** — snapshot
freshness checks stay behind the explicit snapshot-status button, and the
Assets tab links only to the ADR 012 gated image endpoint (manifest-id keyed).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from weaver.api.templating import templates
from weaver.api.ui_context import project_layout
from weaver.errors import VolumeNotFoundError, WeaverError
from weaver.services.epub_snapshot import read_snapshot, snapshot_info
from weaver.services.epub_structure_preview import serialize_parsed_epub
from weaver.services.project_discovery import find_project
from weaver.services.project_paths import resolve_database_path
from weaver.services.segment_listing import list_volume_segments

router = APIRouter(tags=["ui"], include_in_schema=False)

EXPLORER_TABS = ("structure", "segments", "assets", "metadata", "warnings")
_SNAPSHOT_TABS = frozenset({"structure", "assets", "metadata", "warnings"})


def _base_dir(request: Request) -> Path:
    return request.app.state.base_dir  # type: ignore[no-any-return]


@router.get("/ui/projects/{name}/volumes/{volume_id}/structure", response_class=HTMLResponse)
def content_explorer(
    name: str,
    volume_id: int,
    request: Request,
    tab: str = Query("structure"),
    chapter: str = Query(""),
    status: str = Query(""),
    review_status: str = Query(""),
    kind: str = Query(""),
    page: int = Query(1),
) -> HTMLResponse:
    """Content Explorer for one imported volume (tabbed, read-only)."""
    base = _base_dir(request)
    dp = find_project(base, name)
    if dp is None:
        raise HTTPException(status_code=404, detail=f"No project named {name!r}.")
    if dp.error:
        return templates.TemplateResponse(
            request, "error.html", {"message": dp.error}, status_code=422
        )
    return render_content_explorer(
        request,
        name,
        volume_id,
        dp.project_toml,
        tab=tab,
        chapter=chapter,
        status=status,
        review_status=review_status,
        kind=kind,
        page=page,
    )


def render_content_explorer(
    request: Request,
    name: str,
    volume_id: int,
    project_toml: Path,
    *,
    tab: str = "structure",
    chapter: str = "",
    status: str = "",
    review_status: str = "",
    kind: str = "",
    page: int = 1,
) -> HTMLResponse:
    """Render the Content Explorer page (also the legacy ``volume:`` target).

    Snapshot tabs read the persisted snapshot only; the Segments tab reads the
    project DB only. Neither path touches the source archive.
    """

    active_tab = tab if tab in EXPLORER_TABS else "structure"
    base = _base_dir(request)
    db_path = resolve_database_path(project_toml, cwd=base)

    preview: dict[str, Any] | None = None
    snapshot_missing = False
    if active_tab in _SNAPSHOT_TABS:
        try:
            parsed = read_snapshot(db_path, volume_id)
        except WeaverError as exc:
            return templates.TemplateResponse(
                request, "error.html", {"message": str(exc)}, status_code=422
            )
        if parsed is None:
            snapshot_missing = True
        else:
            try:
                preview = serialize_parsed_epub(
                    parsed,
                    project_name=name,
                    volume_id=volume_id,
                    include_excerpts=False,  # snapshot render never opens the archive
                )
            except WeaverError as exc:
                return templates.TemplateResponse(
                    request, "error.html", {"message": str(exc)}, status_code=422
                )

    listing = None
    if active_tab == "segments":
        try:
            listing = list_volume_segments(
                project_toml,
                volume_id,
                chapter_id=chapter or None,
                status=status,
                review_status=review_status,
                kind=kind,
                page=page,
                cwd=base,
            )
        except VolumeNotFoundError as exc:
            return templates.TemplateResponse(
                request, "not_found.html", {"message": str(exc)}, status_code=404
            )
        except WeaverError as exc:
            return templates.TemplateResponse(
                request, "error.html", {"message": str(exc)}, status_code=422
            )

    try:
        snap_info = snapshot_info(db_path, volume_id)
    except WeaverError:
        snap_info = None

    return templates.TemplateResponse(
        request,
        "epub_preview.html",
        {
            **project_layout(request, name, active_nav="project"),
            "source_path": f"volume:{volume_id}",
            "volume_preview": True,
            "explorer_tab": active_tab,
            "explorer_tabs": EXPLORER_TABS,
            "project_name": name,
            "volume_id": volume_id,
            "preview": preview,
            "snapshot_missing": snapshot_missing,
            "snapshot_info": snap_info,
            "listing": listing,
            "error": (
                "Snapshot missing — open Inspect status and reparse the volume."
                if snapshot_missing and active_tab in _SNAPSHOT_TABS
                else None
            ),
        },
    )
