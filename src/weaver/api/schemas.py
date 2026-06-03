"""Pydantic response schemas for the FastAPI cockpit (web-boundary DTOs).

All types are read-only response models. Domain logic stays in
``weaver.services``; these are pure serialisation shapes.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

TranslateMode = Literal["skip_existing", "retranslate_non_manual", "force_selected"]

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
# Create novel + file browser (Stage 10B)
# ---------------------------------------------------------------------------


class BrowseEntryResponse(BaseModel):
    """One sandboxed listing item: a sub-directory or importable source file."""

    name: str
    kind: str  # "dir" | "epub" | "txt" | "html"
    rel_path: str


class BrowseListingResponse(BaseModel):
    """A sandboxed directory listing relative to the cockpit base dir."""

    rel_dir: str
    parent: str | None
    entries: list[BrowseEntryResponse]


class CreateNovelResponse(BaseModel):
    """Result of creating a new novel project from a source file."""

    project_name: str
    chapter_count: int
    segment_count: int
    glossary_candidate_count: int


# ---------------------------------------------------------------------------
# Provider / secret config (Stage 10C)
# ---------------------------------------------------------------------------


class ProviderConfigResponse(BaseModel):
    """Redacted provider/model config. Never carries an API-key value."""

    default_provider: str | None
    default_model: str | None
    project_name: str | None
    provider_type: str | None
    model: str | None
    base_url: str | None
    api_key_env: str | None
    api_key_set: bool
    secret_names: list[str]


class ConfigUpdateRequest(BaseModel):
    """Write provider/model config to ``project`` or ``global`` scope.

    Carries no key value — only ``api_key_env`` (the env-var *name*). Project
    scope requires ``project``.
    """

    scope: Literal["project", "global"] = "project"
    project: str | None = None
    provider_type: str | None = None
    model: str | None = None
    base_url: str | None = None
    api_key_env: str | None = None


class SecretUpdateRequest(BaseModel):
    """Set one API-key secret. The value is stored, never echoed back."""

    value: str


class SecretResponse(BaseModel):
    """Redacted secret state: a name and whether it is stored. No value."""

    name: str
    is_set: bool


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


class ChapterRetranslateRequest(BaseModel):
    """Request to retranslate a chapter under an explicit overwrite mode.

    ``mode`` defaults to ``skip_existing`` (safe). ``manual`` segments are only
    overwritten when ``mode`` is ``force_selected``."""

    mode: TranslateMode = "skip_existing"
    provider: str | None = None
    model: str | None = None


class SegmentSelectionRetranslateRequest(BaseModel):
    """Request to retranslate a chosen set of segments under an overwrite mode."""

    segment_ids: list[str]
    mode: TranslateMode = "skip_existing"
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
    reused_from_memory: int
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


# ---------------------------------------------------------------------------
# Glossary (Stage 5A — direct project-scoped term CRUD)
# ---------------------------------------------------------------------------


class GlossaryTermResponse(BaseModel):
    """One approved project glossary term."""

    source: str
    target: str
    category: str | None
    notes: str | None
    case_sensitive: bool


class GlossaryListResponse(BaseModel):
    """All approved glossary terms for a project."""

    terms: list[GlossaryTermResponse]
    count: int


class GlossaryTermCreateRequest(BaseModel):
    """Add or upsert one glossary term (keyed by ``source`` per project)."""

    source: str
    target: str
    category: str | None = None
    notes: str | None = None
    case_sensitive: bool = False


class GlossaryTermUpdateRequest(BaseModel):
    """Update an existing glossary term identified by its path ``source``."""

    target: str
    category: str | None = None
    notes: str | None = None
    case_sensitive: bool = False


# ---------------------------------------------------------------------------
# Character database (Stage 5B — project-scoped CRUD, keyed by jp_name)
# ---------------------------------------------------------------------------


class CharacterResponse(BaseModel):
    """One project character."""

    jp_name: str
    en_name: str
    gender: str | None
    role: str | None
    notes: str | None


class CharacterListResponse(BaseModel):
    """All characters for a project."""

    characters: list[CharacterResponse]
    count: int


class CharacterCreateRequest(BaseModel):
    """Add or upsert one character (keyed by ``jp_name`` per project)."""

    jp_name: str
    en_name: str
    gender: str | None = None
    role: str | None = None
    notes: str | None = None


class CharacterUpdateRequest(BaseModel):
    """Update an existing character identified by its path ``jp_name``."""

    en_name: str
    gender: str | None = None
    role: str | None = None
    notes: str | None = None


# ---------------------------------------------------------------------------
# Translation memory (Stage 6B — project-scoped read + delete)
# ---------------------------------------------------------------------------


class MemoryEntryResponse(BaseModel):
    """One stored translation-memory entry."""

    source_text: str
    source_hash: str
    target_text: str
    provider: str | None
    model: str | None
    created_at: str
    updated_at: str


class MemoryOverviewResponse(BaseModel):
    """A project's translation-memory entries plus reuse statistics."""

    total_entries: int
    exact_hits: int
    reused_from_memory: int
    entries: list[MemoryEntryResponse]


# ---------------------------------------------------------------------------
# Batch translation (Sprint 7B — chapter/volume/novel jobs + aggregate progress)
# ---------------------------------------------------------------------------


class BatchTranslateRequest(BaseModel):
    """Request to start a batch (chapter/volume/novel) translation.

    ``mode`` defaults to ``skip_existing`` (safe); ``retranslate_non_manual`` and
    ``force_selected`` apply only when explicitly sent. ``provider`` / ``model``
    override the project's configured provider for this run only."""

    mode: TranslateMode = "skip_existing"
    provider: str | None = None
    model: str | None = None


class BatchJobResponse(BaseModel):
    """Acknowledgement that a background batch job was started (202)."""

    job_id: str
    status: str
    scope: str
    scope_id: str | None
    mode: str


class BatchJobProgressResponse(BaseModel):
    """Live aggregate progress for a running (or finished) batch job."""

    scope: str
    scope_id: str | None
    mode: str
    provider: str
    model: str
    chapters_total: int
    chapters_done: int
    current_chapter_id: str | None
    segments_total: int
    segments_done: int
    translated: int
    reused_from_memory: int
    skipped: int
    failed: int


class BatchChapterOutcomeResponse(BaseModel):
    """Per-chapter result inside a finished batch job."""

    chapter_id: str
    selected: int
    translated: int
    reused_from_memory: int
    failed: int
    skipped: int
    input_tokens: int
    output_tokens: int
    cancelled: bool


class BatchJobResultResponse(BaseModel):
    """Aggregate counts, timing, and per-chapter outcomes for a finished batch."""

    scope: str
    scope_id: str | None
    mode: str
    provider: str
    model: str
    chapters_total: int
    chapters_done: int
    segments_total: int
    translated: int
    reused_from_memory: int
    skipped: int
    failed: int
    input_tokens: int
    output_tokens: int
    cancelled: bool
    started_at: str
    finished_at: str
    duration_seconds: float
    chapters: list[BatchChapterOutcomeResponse]


class BatchJobStatusResponse(BaseModel):
    """A batch job's current state; ``result`` is set once it finishes."""

    job_id: str
    status: str
    scope: str
    scope_id: str | None
    mode: str
    progress: BatchJobProgressResponse
    result: BatchJobResultResponse | None
    error: str | None


class ExportRequest(BaseModel):
    """Request to start a background export.

    ``target`` defaults to ``epub`` (the only implemented target). The body is
    optional; an empty POST uses the default."""

    target: str = "epub"


class ExportJobResponse(BaseModel):
    """Acknowledgement that a background export job was started (202)."""

    job_id: str
    status: str
    scope: str
    scope_id: str | None
    target: str


class ExportFallbackByStatusResponse(BaseModel):
    """Per-status counts of segments that fell back to source text."""

    pending: int
    in_progress: int
    failed: int
    stale: int
    skipped: int
    untranslated: int


class ExportArtifactResponse(BaseModel):
    """One exported file (one volume) in a finished export job."""

    volume_id: int
    volume_title: str
    source_format: str
    output_path: str
    chapters_exported: int
    translated_segments: int
    fallback_segments: int
    fallback_by_status: ExportFallbackByStatusResponse


class ExportJobProgressResponse(BaseModel):
    """Live per-volume progress for a running (or finished) export job."""

    target: str
    scope: str
    scope_id: str | None
    volumes_total: int
    volumes_done: int
    current_volume_id: int | None
    current_volume_title: str | None
    translated_segments: int
    fallback_segments: int


class ExportJobResultResponse(BaseModel):
    """Aggregate counts and per-volume artifacts for a finished export."""

    target: str
    scope: str
    scope_id: str | None
    output_dir: str
    volumes_total: int
    volumes_exported: int
    chapters_exported: int
    translated_segments: int
    fallback_segments: int
    generated_at: str
    cancelled: bool
    artifacts: list[ExportArtifactResponse]


class ExportJobStatusResponse(BaseModel):
    """An export job's current state; ``result`` is set once it finishes."""

    job_id: str
    status: str
    scope: str
    scope_id: str | None
    target: str
    progress: ExportJobProgressResponse
    result: ExportJobResultResponse | None
    error: str | None
