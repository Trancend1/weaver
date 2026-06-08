"""Project endpoints: list, tree, and import.

All endpoints are scoped to a ``base_dir`` stored in ``app.state`` at startup.
Domain logic stays in ``weaver.services``; this module is a thin adapter layer.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, Response, UploadFile

from weaver.api.jobs import ParseResult
from weaver.api.schemas import (
    BrowseEntryResponse,
    BrowseListingResponse,
    ChapterResponse,
    ChapterWorkspaceResponse,
    CreateNovelResponse,
    ImportVolumeResponse,
    NovelTreeResponse,
    ProjectListResponse,
    ProjectSummaryResponse,
    ReparseJobResponse,
    SegmentTranslationHistoryResponse,
    SegmentTranslationResponse,
    SegmentTranslationUpdate,
    SnapshotStatusResponse,
    TranslationAttemptResponse,
    VolumeResponse,
    WorkspaceSegmentResponse,
)
from weaver.errors import (
    ChapterNotFoundError,
    ProjectNotFoundError,
    SegmentNotFoundError,
    VolumeNotFoundError,
    WeaverError,
)
from weaver.services.chapter_workspace import chapter_workspace
from weaver.services.epub_reparse import (
    reparse_volume,
    status_for_volume,
)
from weaver.services.epub_structure_preview import preview_epub_structure
from weaver.services.import_source import import_volume
from weaver.services.project import delete_project, initialize_project, project_exists
from weaver.services.project_discovery import discover_projects, find_project
from weaver.services.project_tree import project_tree
from weaver.services.segment_history import segment_translation_history
from weaver.services.source_browser import list_directory, resolve_source
from weaver.services.source_intake import resolve_intake_source
from weaver.services.volume import delete_volume_from_project
from weaver.services.workspace_edit import save_segment_translation

router = APIRouter(prefix="/projects", tags=["projects"])


def _base_dir(request: Request) -> Path:
    return request.app.state.base_dir  # type: ignore[no-any-return]


def _jobs(request: Request):
    """Optional in-memory JobRegistry (None outside the live app)."""
    return getattr(request.app.state, "jobs", None)


@router.post("/epub-preview")
async def preview_epub_endpoint(
    request: Request,
    file: UploadFile | None = File(None, description="EPUB file to preview."),
    source_path: str | None = Form(
        None, description="Sandbox-relative EPUB path selected from browse."
    ),
) -> dict[str, object]:
    """Return a read-only ParsedEpub preview without importing or persisting it."""

    base = _base_dir(request)
    if file is None and not source_path:
        raise HTTPException(status_code=422, detail="Upload or source_path is required.")

    tmp_path: Path | None = None
    try:
        if file is not None:
            suffix = Path(file.filename or "preview.epub").suffix or ".epub"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp_path = Path(tmp.name)
                tmp.write(await file.read())
            preview_path = tmp_path
        else:
            preview_path = resolve_source(base, source_path or "")
        return preview_epub_structure(preview_path)
    except WeaverError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)


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


@router.get("/browse", response_model=BrowseListingResponse)
def browse_sources(
    request: Request, rel_dir: str = Query("", alias="dir")
) -> BrowseListingResponse:
    """List sub-directories and importable source files under the base dir.

    Sandboxed to ``base_dir`` (ADR ``0017``): ``..`` traversal and absolute paths
    are rejected. The ``dir`` query is a path relative to the base dir; ``""`` is
    the root.
    """
    base = _base_dir(request)
    try:
        listing = list_directory(base, rel_dir)
    except WeaverError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return BrowseListingResponse(
        rel_dir=listing.rel_dir,
        parent=listing.parent,
        entries=[
            BrowseEntryResponse(name=e.name, kind=e.kind, rel_path=e.rel_path)
            for e in listing.entries
        ],
    )


@router.post("/create", response_model=CreateNovelResponse, status_code=201)
async def create_novel(
    request: Request,
    file: UploadFile | None = File(
        None, description="Source file to create the novel from (EPUB, TXT, or HTML)."
    ),
    source_path: str | None = Form(
        None, description="Path to a browsed source, relative to the base dir."
    ),
    provider: str | None = Form(None, description="Provider type for the generated config."),
    template: str | None = Form(None, description="Template preset for the generated config."),
) -> CreateNovelResponse:
    """Create a new novel project from an uploaded or browsed source file.

    Exactly one source is required: an uploaded ``file`` (preferred) or a browsed
    ``source_path``. The project name derives from the source filename stem.
    Creating over an existing project of the same name is refused (409).
    Sourceless creation is unsupported — the source defines the project name and
    initial volume.
    """
    base = _base_dir(request)
    uploaded = (file.filename, await file.read()) if file is not None and file.filename else None

    try:
        source = resolve_intake_source(base, uploaded=uploaded, source_path=source_path)
        if project_exists(source, cwd=base):
            raise HTTPException(
                status_code=409,
                detail=(
                    f"A project named {source.stem!r} already exists. "
                    "Likely cause: this source was already created. "
                    "Next command: open the existing project or import as a volume."
                ),
            )
        result = initialize_project(source, cwd=base, template=template, provider=provider)
    except WeaverError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return CreateNovelResponse(
        project_name=result.project_name,
        chapter_count=result.chapter_count,
        segment_count=result.segment_count,
        glossary_candidate_count=result.glossary_candidate_count,
    )


@router.get("/{name}/tree", response_model=NovelTreeResponse)
def get_project_tree(name: str, request: Request) -> NovelTreeResponse:
    """Return the Project → Volume → Chapter tree for one project."""
    base = _base_dir(request)
    dp = find_project(base, name)
    if dp is None:
        raise HTTPException(status_code=404, detail=f"Project '{name}' not found.")
    if dp.error:
        raise HTTPException(status_code=422, detail=dp.error)

    try:
        tree = project_tree(dp.project_toml, cwd=base, jobs=_jobs(request))
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
                status=v.status,
                status_label=v.status_label,
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


@router.get(
    "/{name}/chapters/{chapter_id}/workspace",
    response_model=ChapterWorkspaceResponse,
)
def get_chapter_workspace(name: str, chapter_id: str, request: Request) -> ChapterWorkspaceResponse:
    """Return the read-only JP/EN workspace for one chapter.

    The payload carries the chapter's source segments in block order plus the
    latest translation text per segment (``None`` when untranslated). Navigation
    (Novel -> Volume -> Chapter) is served by ``GET /projects/{name}/tree``.
    """
    base = _base_dir(request)
    dp = find_project(base, name)
    if dp is None:
        raise HTTPException(status_code=404, detail=f"Project '{name}' not found.")
    if dp.error:
        raise HTTPException(status_code=422, detail=dp.error)

    try:
        workspace = chapter_workspace(dp.project_toml, chapter_id, cwd=base)
    except ChapterNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except WeaverError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return ChapterWorkspaceResponse(
        project_name=workspace.project_name,
        volume_id=workspace.volume_id,
        volume_title=workspace.volume_title,
        chapter_id=workspace.chapter_id,
        chapter_title=workspace.chapter_title,
        segment_count=workspace.segment_count,
        translated_count=workspace.translated_count,
        segments=[
            WorkspaceSegmentResponse(
                id=s.id,
                block_order=s.block_order,
                kind=s.kind,
                source_text=s.source_text,
                status=s.status,
                translated_text=s.translated_text,
            )
            for s in workspace.segments
        ],
    )


@router.get(
    "/{name}/chapters/{chapter_id}/segments/{segment_id}/translations",
    response_model=SegmentTranslationHistoryResponse,
)
def get_segment_translation_history(
    name: str,
    chapter_id: str,
    segment_id: str,
    request: Request,
) -> SegmentTranslationHistoryResponse:
    """Return one segment's translation revision history (all attempts).

    Attempts are oldest-first; ``current_translation`` is the latest attempt's
    text. Rejects unknown project (404), chapter (404), and segment / wrong
    chapter (404).
    """
    base = _base_dir(request)
    dp = find_project(base, name)
    if dp is None:
        raise HTTPException(status_code=404, detail=f"Project '{name}' not found.")
    if dp.error:
        raise HTTPException(status_code=422, detail=dp.error)

    try:
        history = segment_translation_history(dp.project_toml, chapter_id, segment_id, cwd=base)
    except (ChapterNotFoundError, SegmentNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except WeaverError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return SegmentTranslationHistoryResponse(
        segment_id=history.segment_id,
        chapter_id=history.chapter_id,
        status=history.status,
        current_translation=history.current_translation,
        attempts=[
            TranslationAttemptResponse(
                attempt=a.attempt,
                translated_text=a.text,
                provider=a.provider,
                model=a.model,
                created_at=a.created_at,
            )
            for a in history.attempts
        ],
    )


@router.patch(
    "/{name}/chapters/{chapter_id}/segments/{segment_id}/translation",
    response_model=SegmentTranslationResponse,
)
def update_segment_translation(
    name: str,
    chapter_id: str,
    segment_id: str,
    body: SegmentTranslationUpdate,
    request: Request,
) -> SegmentTranslationResponse:
    """Save one segment's translation; sets its status to ``manual``.

    The source text is preserved; only a new translation attempt is recorded.
    Rejects unknown project (404), chapter (404), segment / wrong chapter (404),
    and empty text (422).
    """
    base = _base_dir(request)
    dp = find_project(base, name)
    if dp is None:
        raise HTTPException(status_code=404, detail=f"Project '{name}' not found.")
    if dp.error:
        raise HTTPException(status_code=422, detail=dp.error)

    try:
        result = save_segment_translation(
            dp.project_toml, chapter_id, segment_id, body.translated_text, cwd=base
        )
    except (ChapterNotFoundError, SegmentNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except WeaverError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return SegmentTranslationResponse(
        segment_id=result.segment_id,
        status=result.status,
        translated_text=result.translated_text,
        saved_at=result.saved_at,
    )


@router.post("/{name}/import", response_model=ImportVolumeResponse, status_code=201)
async def import_volume_endpoint(
    name: str,
    request: Request,
    file: UploadFile = File(..., description="Source file to import (EPUB, TXT, or HTML)."),
) -> ImportVolumeResponse:
    """Import a source file as a new volume in an existing project.

    The file is streamed to a temporary path preserving its original suffix so
    that format detection works correctly. The temp file is removed on completion
    regardless of success or failure.
    """
    base = _base_dir(request)

    dp = find_project(base, name)
    if dp is None:
        raise HTTPException(status_code=404, detail=f"Project '{name}' not found.")
    if dp.error:
        raise HTTPException(status_code=422, detail=dp.error)

    filename = file.filename or "upload.bin"
    suffix = Path(filename).suffix or ".bin"

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp_path = Path(tmp.name)
        try:
            content = await file.read()
            tmp.write(content)
        except Exception as exc:
            tmp_path.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail="Failed to read uploaded file.") from exc

    try:
        result = import_volume(dp.project_toml, tmp_path, cwd=base)
    except WeaverError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        tmp_path.unlink(missing_ok=True)

    return ImportVolumeResponse(
        volume_id=result.volume_id,
        volume_title=result.volume_title,
        chapter_count=result.chapter_count,
        segment_count=result.segment_count,
        glossary_candidate_count=result.glossary_candidate_count,
    )


# --- lifecycle deletes (Sprint H3) -----------------------------------------


@router.delete("/{name}", status_code=204)
def delete_project_endpoint(name: str, request: Request) -> Response:
    """Permanently delete a project and every artefact under ``.weaver/<name>``.

    The original source file is **not** touched (it lives outside the project
    directory). Returns 204 on success, 404 when the project is unknown.
    """
    base = _base_dir(request)
    dp = find_project(base, name)
    if dp is None:
        raise HTTPException(status_code=404, detail=f"Project '{name}' not found.")
    try:
        delete_project(dp.project_toml)
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except WeaverError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return Response(status_code=204)


@router.delete("/{name}/volumes/{volume_id}", status_code=204)
def delete_volume_endpoint(name: str, volume_id: int, request: Request) -> Response:
    """Permanently delete one volume and every row that depends on it.

    Project-scoped data (glossary, characters, translation memory) survives —
    use ``DELETE /projects/{name}`` to remove the whole project.
    """
    base = _base_dir(request)
    dp = find_project(base, name)
    if dp is None:
        raise HTTPException(status_code=404, detail=f"Project '{name}' not found.")
    if dp.error:
        raise HTTPException(status_code=422, detail=dp.error)
    try:
        delete_volume_from_project(dp.project_toml, volume_id, cwd=base)
    except VolumeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except WeaverError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return Response(status_code=204)


# --- EPUB preservation snapshot (Sprint J4) --------------------------------


def _require_project(request: Request, name: str):
    base = _base_dir(request)
    dp = find_project(base, name)
    if dp is None:
        raise HTTPException(status_code=404, detail=f"Project '{name}' not found.")
    if dp.error:
        raise HTTPException(status_code=422, detail=dp.error)
    return base, dp


@router.get(
    "/{name}/volumes/{volume_id}/snapshot",
    response_model=SnapshotStatusResponse,
)
def get_volume_snapshot_status(
    name: str, volume_id: int, request: Request
) -> SnapshotStatusResponse:
    """Report whether the volume's EPUB snapshot is missing/fresh/stale."""
    base, dp = _require_project(request, name)
    try:
        status = status_for_volume(dp.project_toml, volume_id, cwd=base)
    except VolumeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except WeaverError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return SnapshotStatusResponse(
        volume_id=status.volume_id,
        state=status.state,
        source_hash=status.source_hash,
        parser_version=status.parser_version,
        created_at=status.created_at,
        updated_at=status.updated_at,
    )


@router.post(
    "/{name}/volumes/{volume_id}/reparse",
    response_model=ReparseJobResponse,
    status_code=202,
)
def submit_volume_reparse(name: str, volume_id: int, request: Request) -> ReparseJobResponse:
    """Submit a Sprint I persistent parse job that refreshes the snapshot."""
    base, dp = _require_project(request, name)
    jobs = _jobs(request)
    if jobs is None:
        raise HTTPException(status_code=503, detail="Job registry is not available.")

    project_toml = dp.project_toml

    def runner(should_cancel) -> ParseResult:  # noqa: ARG001 — single-unit parse
        status = reparse_volume(project_toml, volume_id, cwd=base)
        # Bring back enough counters to feed the result_json contract.
        from contextlib import closing

        from weaver.services.epub_snapshot import read_snapshot

        parsed = read_snapshot((base / ".weaver" / name / "weaver.db").resolve(), volume_id)
        _ = closing  # silence unused (closing used inside read_snapshot)
        return ParseResult(
            volume_id=volume_id,
            source_hash=status.source_hash or "",
            parser_version=status.parser_version or 0,
            manifest_count=len(parsed.manifest) if parsed else 0,
            spine_count=len(parsed.spine) if parsed else 0,
            nav_count=len(parsed.navigation) if parsed else 0,
            image_count=len(parsed.images) if parsed else 0,
            validation_count=len(parsed.validation_issues) if parsed else 0,
        )

    try:
        job = jobs.submit_parse(project_name=name, volume_id=volume_id, runner=runner)
    except WeaverError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ReparseJobResponse(job_id=job.id, volume_id=volume_id)
