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


# ---------------------------------------------------------------------------
# Import (Stage 2C)
# ---------------------------------------------------------------------------


class ImportVolumeResponse(BaseModel):
    """Result of importing a source file as a new volume."""

    volume_id: int
    volume_title: str
    chapter_count: int
    segment_count: int
    glossary_candidate_count: int


# ---------------------------------------------------------------------------
# Translation workspace (Stage 3A — read only)
# ---------------------------------------------------------------------------


class WorkspaceSegmentResponse(BaseModel):
    """One source segment paired with its latest translation, if any."""

    id: str
    block_order: int
    kind: str
    source_text: str
    status: str
    translated_text: str | None


class ChapterWorkspaceResponse(BaseModel):
    """JP/EN workspace payload for one chapter (read-only)."""

    project_name: str
    volume_id: int
    volume_title: str
    chapter_id: str
    chapter_title: str | None
    segment_count: int
    translated_count: int
    segments: list[WorkspaceSegmentResponse]


# ---------------------------------------------------------------------------
# Translation workspace (Stage 3B — save one segment)
# ---------------------------------------------------------------------------


class SegmentTranslationUpdate(BaseModel):
    """Request body for saving one segment's translation."""

    translated_text: str


class SegmentTranslationResponse(BaseModel):
    """Result of saving one segment's translation (status becomes ``manual``)."""

    segment_id: str
    status: str
    translated_text: str
    saved_at: str


# ---------------------------------------------------------------------------
# Translation workspace (Stage 3C — revision history)
# ---------------------------------------------------------------------------


class TranslationAttemptResponse(BaseModel):
    """One recorded translation attempt for a segment."""

    attempt: int
    translated_text: str
    provider: str
    model: str
    created_at: str


class SegmentTranslationHistoryResponse(BaseModel):
    """A segment's current translation plus its full attempt history."""

    segment_id: str
    chapter_id: str
    status: str
    current_translation: str | None
    attempts: list[TranslationAttemptResponse]


# ---------------------------------------------------------------------------
# AI translation (Stage 4A — provider/model selection + background jobs)
# ---------------------------------------------------------------------------


class ChapterTranslateRequest(BaseModel):
    """Request to translate a whole chapter. Provider/model are optional overrides
    of the project's configured provider; omit to use the project default."""

    provider: str | None = None
    model: str | None = None


class SegmentSelectionTranslateRequest(BaseModel):
    """Request to translate a chosen set of segments within one chapter."""

    segment_ids: list[str]
    provider: str | None = None
    model: str | None = None


class TranslationJobResponse(BaseModel):
    """Acknowledgement that a background translate job was started (202)."""

    job_id: str
    status: str
    chapter_id: str
    mode: str


class TranslationJobResultResponse(BaseModel):
    """Per-run counts for a finished translate job."""

    chapter_id: str
    selected: int
    translated: int
    failed: int
    skipped: int
    input_tokens: int
    output_tokens: int
    cancelled: bool


class TranslationJobProgressResponse(BaseModel):
    """Live per-segment progress for a running (or finished) translate job."""

    current: int
    total: int
    translated: int
    failed: int


class TranslationJobStatusResponse(BaseModel):
    """A translate job's current state; ``result`` is set once it finishes."""

    job_id: str
    status: str
    chapter_id: str
    mode: str
    progress: TranslationJobProgressResponse
    result: TranslationJobResultResponse | None
    error: str | None
