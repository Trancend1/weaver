"""Project read endpoints: list projects and fetch the novel tree.

Reuses ``weaver.services.project_discovery`` and ``weaver.services.project_tree``
without duplicating domain logic. ``base_dir`` is resolved from ``app.state``
which the factory sets at startup.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from weaver.api.schemas import (
    ChapterResponse,
    NovelTreeResponse,
    ProjectListResponse,
    ProjectSummaryResponse,
    VolumeResponse,
)
from weaver.errors import WeaverError
from weaver.services.project_discovery import discover_projects, find_project
from weaver.services.project_tree import project_tree

router = APIRouter(prefix="/projects", tags=["projects"])


def _base_dir(request: Request) -> Path:
    return request.app.state.base_dir  # type: ignore[no-any-return]


@router.get("", response_model=ProjectListResponse)
def list_projects(request: Request) -> ProjectListResponse:
    """Return all projects discovered under base_dir."""
    discovered = discover_projects(_base_dir(request))
    projects = []
    for dp in discovered:
        s = dp.summary
        projects.append(
            ProjectSummaryResponse(
                name=dp.name,
                project_toml=str(dp.project_toml),
                source_file=s.source_file if s else "",
                provider=s.provider if s else "",
                model=s.model if s else "",
                volume_count=s.volume_count if s else 0,
                chapter_count=s.chapter_count if s else 0,
                segment_count=s.segment_count if s else 0,
                pending_count=s.pending_count if s else 0,
                translated_count=s.translated_count if s else 0,
                failed_count=s.failed_count if s else 0,
                stale_count=s.stale_count if s else 0,
                glossary_candidate_count=s.glossary_candidate_count if s else 0,
                glossary_term_count=s.glossary_term_count if s else 0,
                output_dir=s.output_dir if s else "",
                error=dp.error,
            )
        )
    return ProjectListResponse(projects=projects)


@router.get("/{name}/tree", response_model=NovelTreeResponse)
def get_project_tree(name: str, request: Request) -> NovelTreeResponse:
    """Return the Novel → Volume → Chapter tree for one project."""
    base = _base_dir(request)
    dp = find_project(base, name)
    if dp is None:
        raise HTTPException(status_code=404, detail=f"Project '{name}' not found.")
    if dp.error:
        raise HTTPException(status_code=422, detail=dp.error)

    try:
        tree = project_tree(dp.project_toml, cwd=base)
    except WeaverError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return NovelTreeResponse(
        project_name=tree.project_name,
        volumes=[
            VolumeResponse(
                id=v.id,
                title=v.title,
                source_format=v.source_format,
                volume_order=v.volume_order,
                chapter_count=v.chapter_count,
                segment_count=v.segment_count,
                chapters=[
                    ChapterResponse(
                        id=c.id,
                        title=c.title,
                        segment_count=c.segment_count,
                        translated_count=c.translated_count,
                    )
                    for c in v.chapters
                ],
            )
            for v in tree.volumes
        ],
    )
