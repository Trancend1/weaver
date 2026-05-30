"""Pydantic response schemas for the FastAPI cockpit (web-boundary DTOs).

All types are read-only response models. Domain logic stays in
``weaver.services``; these are pure serialisation shapes.
"""

from __future__ import annotations

from pydantic import BaseModel

# ---------------------------------------------------------------------------
# System (Stage 2A)
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    """Liveness probe payload."""

    status: str


class VersionResponse(BaseModel):
    """Application identity and version payload."""

    name: str
    version: str


# ---------------------------------------------------------------------------
# Projects (Stage 2B)
# ---------------------------------------------------------------------------


class ProjectSummaryResponse(BaseModel):
    """Flat summary of one project (mirrors InspectSummary, no ProviderStatus)."""

    name: str
    project_toml: str
    source_file: str
    provider: str
    model: str
    volume_count: int
    chapter_count: int
    segment_count: int
    pending_count: int
    translated_count: int
    failed_count: int
    stale_count: int
    glossary_candidate_count: int
    glossary_term_count: int
    output_dir: str
    error: str | None


class ProjectListResponse(BaseModel):
    """Ordered list of projects discovered under base_dir."""

    projects: list[ProjectSummaryResponse]


class ChapterResponse(BaseModel):
    """One chapter in the novel tree."""

    id: str
    title: str | None
    segment_count: int
    translated_count: int


class VolumeResponse(BaseModel):
    """One volume with its chapters."""

    id: int
    title: str
    source_format: str
    volume_order: int
    chapter_count: int
    segment_count: int
    chapters: list[ChapterResponse]


class NovelTreeResponse(BaseModel):
    """Novel → Volume → Chapter tree for one project."""

    project_name: str
    volumes: list[VolumeResponse]


class ErrorResponse(BaseModel):
    """Generic error envelope."""

    detail: str
