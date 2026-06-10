"""Candidate-review and character-draft JSON API endpoints (Sprint L).

Thin adapter layer: domain logic stays in ``services/candidate_generation``,
``services/candidate_apply``, and ``services/character_draft``.
"""

from __future__ import annotations

import json
from contextlib import closing
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from weaver.api.schemas import (
    CandidateActionResponse,
    CandidateApplyRequest,
    CandidateGenerateRequest,
    CandidateGenerateResponse,
    CandidateListResponse,
    CandidateResponse,
    CharacterDraftActionResponse,
    CharacterDraftGenerateResponse,
    CharacterDraftListResponse,
    CharacterDraftResponse,
)
from weaver.errors import (
    CandidateNotFoundError,
    CharacterDraftNotFoundError,
    ProviderError,
    SegmentNotFoundError,
    WeaverError,
)
from weaver.services.candidate_apply import apply_candidate, approve_candidate, reject_candidate
from weaver.services.candidate_generation import generate_candidate
from weaver.services.character_draft import (
    approve_draft,
    generate_character_draft,
    reject_draft,
)
from weaver.services.project_discovery import find_project
from weaver.services.project_paths import resolve_database_path
from weaver.storage.candidates import (
    list_candidates_for_chapter,
    list_candidates_for_project,
    list_candidates_for_segment,
)
from weaver.storage.character_drafts import list_drafts_for_project
from weaver.storage.db import connect_readonly_database
from weaver.storage.projects import get_first_project_id

router = APIRouter(prefix="/projects", tags=["candidates"])


def _base_dir(request: Request) -> Path:
    return request.app.state.base_dir  # type: ignore[no-any-return]


def _resolve_project_toml(request: Request, name: str) -> Path:
    base = _base_dir(request)
    dp = find_project(base, name)
    if dp is None:
        raise HTTPException(status_code=404, detail=f"Project '{name}' not found.")
    if dp.error:
        raise HTTPException(status_code=422, detail=dp.error)
    return dp.project_toml


def _candidate_to_response(cand: Any) -> CandidateResponse:  # noqa: ANN401
    prov = cand.provenance_json
    parsed = json.loads(prov) if isinstance(prov, str) else prov
    return CandidateResponse(
        id=cand.id,
        project_id=cand.project_id,
        volume_id=cand.volume_id,
        chapter_id=cand.chapter_id,
        segment_id=cand.segment_id,
        source_text=cand.source_text,
        candidate_text=cand.candidate_text,
        provider=cand.provider,
        model=cand.model,
        status=cand.status,
        provenance=parsed,
        created_at=cand.created_at,
        updated_at=cand.updated_at,
    )


def _draft_to_response(d: Any) -> CharacterDraftResponse:  # noqa: ANN401
    prov = d.provenance_json
    parsed = json.loads(prov) if isinstance(prov, str) else prov
    return CharacterDraftResponse(
        id=d.id,
        project_id=d.project_id,
        volume_id=d.volume_id,
        chapter_id=d.chapter_id,
        segment_id=d.segment_id,
        source_text=d.source_text,
        draft_text=d.draft_text,
        heading=d.heading,
        page_identifier=d.page_identifier,
        status=d.status,
        provenance=parsed,
        created_at=d.created_at,
        updated_at=d.updated_at,
    )


# --- Translation Candidates --------------------------------------------------


@router.get("/{name}/candidates", response_model=CandidateListResponse)
def list_candidates(
    name: str,
    request: Request,
    chapter_id: str | None = None,
    segment_id: str | None = None,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> CandidateListResponse:
    """List translation candidates for a project, optionally filtered."""
    project_toml = _resolve_project_toml(request, name)
    db_path = resolve_database_path(project_toml, cwd=_base_dir(request))
    with closing(connect_readonly_database(db_path)) as connection:
        pid = get_first_project_id(connection)
        if pid is None:
            return CandidateListResponse(candidates=[], total_count=0)

        if segment_id is not None:
            rows = list_candidates_for_segment(connection, segment_id=segment_id, status=status)
        elif chapter_id is not None:
            rows = list_candidates_for_chapter(
                connection, chapter_id=chapter_id, status=status, limit=limit, offset=offset
            )
        else:
            rows = list_candidates_for_project(
                connection, project_id=pid, status=status, limit=limit, offset=offset
            )

    candidates = [_candidate_to_response(r) for r in rows]
    return CandidateListResponse(candidates=candidates, total_count=len(candidates))


@router.post("/{name}/candidates/generate", response_model=CandidateGenerateResponse)
def generate_candidate_endpoint(
    name: str,
    chapter_id: str,
    segment_id: str,
    request: Request,
    body: CandidateGenerateRequest | None = None,
) -> CandidateGenerateResponse:
    """Generate one translation candidate for a segment.

    The candidate is grounded in glossary, character DB, and chapter context.
    It is stored as ``pending`` — never auto-applied.
    """
    project_toml = _resolve_project_toml(request, name)
    override = None
    if body is not None and (body.provider or body.model):
        override = {}
        if body.provider:
            override["type"] = body.provider
        if body.model:
            override["model"] = body.model

    try:
        record = generate_candidate(
            project_toml,
            chapter_id,
            segment_id,
            cwd=_base_dir(request),
            provider_override=override,
        )
    except (SegmentNotFoundError, ProviderError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except WeaverError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return CandidateGenerateResponse(candidate=_candidate_to_response(record))


@router.post("/{name}/candidates/{candidate_id}/approve", response_model=CandidateActionResponse)
def approve_candidate_endpoint(
    name: str, candidate_id: str, request: Request
) -> CandidateActionResponse:
    """Approve a candidate (status → ``approved``). Does not apply it."""
    project_toml = _resolve_project_toml(request, name)
    try:
        record = approve_candidate(project_toml, candidate_id, cwd=_base_dir(request))
    except CandidateNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except WeaverError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return CandidateActionResponse(candidate=_candidate_to_response(record), action="approved")


@router.post("/{name}/candidates/{candidate_id}/reject", response_model=CandidateActionResponse)
def reject_candidate_endpoint(
    name: str, candidate_id: str, request: Request
) -> CandidateActionResponse:
    """Reject a candidate (status → ``rejected``). Retained for audit."""
    project_toml = _resolve_project_toml(request, name)
    try:
        record = reject_candidate(project_toml, candidate_id, cwd=_base_dir(request))
    except CandidateNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except WeaverError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return CandidateActionResponse(candidate=_candidate_to_response(record), action="rejected")


@router.post("/{name}/candidates/{candidate_id}/apply", response_model=CandidateActionResponse)
def apply_candidate_endpoint(
    name: str,
    candidate_id: str,
    request: Request,
    body: CandidateApplyRequest | None = None,
) -> CandidateActionResponse:
    """Apply a candidate to its segment (creates a translation history entry).

    When ``edited_text`` is provided, the segment status becomes ``manual``.
    Otherwise the candidate text is applied as-is and the segment becomes
    ``translated``.
    """
    project_toml = _resolve_project_toml(request, name)
    edited = body.edited_text if body is not None else None
    try:
        record = apply_candidate(
            project_toml, candidate_id, cwd=_base_dir(request), edited_text=edited
        )
    except (CandidateNotFoundError, SegmentNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except WeaverError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return CandidateActionResponse(candidate=_candidate_to_response(record), action="applied")


# --- Character Page Drafts ---------------------------------------------------


@router.get("/{name}/drafts", response_model=CharacterDraftListResponse)
def list_drafts(
    name: str,
    request: Request,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> CharacterDraftListResponse:
    """List character page drafts for a project."""
    project_toml = _resolve_project_toml(request, name)
    db_path = resolve_database_path(project_toml, cwd=_base_dir(request))
    with closing(connect_readonly_database(db_path)) as connection:
        pid = get_first_project_id(connection)
        if pid is None:
            return CharacterDraftListResponse(drafts=[], total_count=0)
        rows = list_drafts_for_project(
            connection, project_id=pid, status=status, limit=limit, offset=offset
        )

    drafts = [_draft_to_response(r) for r in rows]
    return CharacterDraftListResponse(drafts=drafts, total_count=len(drafts))


@router.post("/{name}/drafts/generate", response_model=CharacterDraftGenerateResponse)
def generate_draft_endpoint(
    name: str,
    chapter_id: str,
    request: Request,
) -> CharacterDraftGenerateResponse:
    """Generate a character page draft from a chapter's XHTML text.

    Only processes text content — no OCR, no image processing. Returns
    ``null`` draft when no character content is detected.
    """
    project_toml = _resolve_project_toml(request, name)
    try:
        draft = generate_character_draft(project_toml, chapter_id, cwd=_base_dir(request))
    except WeaverError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if draft is None:
        return CharacterDraftGenerateResponse(
            draft=None,
            message="No character page content detected in this chapter.",
        )
    return CharacterDraftGenerateResponse(
        draft=_draft_to_response(draft),
        message="Character page draft generated.",
    )


@router.post("/{name}/drafts/{draft_id}/approve", response_model=CharacterDraftActionResponse)
def approve_draft_endpoint(
    name: str, draft_id: str, request: Request
) -> CharacterDraftActionResponse:
    """Approve a character page draft."""
    project_toml = _resolve_project_toml(request, name)
    try:
        record = approve_draft(project_toml, draft_id, cwd=_base_dir(request))
    except CharacterDraftNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except WeaverError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return CharacterDraftActionResponse(draft=_draft_to_response(record), action="approved")


@router.post("/{name}/drafts/{draft_id}/reject", response_model=CharacterDraftActionResponse)
def reject_draft_endpoint(
    name: str, draft_id: str, request: Request
) -> CharacterDraftActionResponse:
    """Reject a character page draft."""
    project_toml = _resolve_project_toml(request, name)
    try:
        record = reject_draft(project_toml, draft_id, cwd=_base_dir(request))
    except CharacterDraftNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except WeaverError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return CharacterDraftActionResponse(draft=_draft_to_response(record), action="rejected")
