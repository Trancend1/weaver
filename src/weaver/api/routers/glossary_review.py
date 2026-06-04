"""Glossary candidate-review endpoints (Stage 10D).

Thin adapter over the existing candidate-review services (`services/glossary_review`,
`services/glossary_diff`) — the same flow the CLI `glossary review` surface uses.
Approve/edit write into the project `glossary_terms`
table (the one `build_context` injects); there is **no second glossary store**.
Direct glossary CRUD (`routers/glossary.py`) is unchanged.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request

from weaver.api.schemas import (
    GlossaryCandidateActionResponse,
    GlossaryCandidateEditRequest,
    GlossaryCandidateListResponse,
    GlossaryCandidateResponse,
    GlossaryConflictResponse,
    GlossaryConflictsResponse,
    GlossaryDiffResponse,
    GlossaryReviewCountsResponse,
)
from weaver.errors import GlossaryCandidateNotFoundError, WeaverError
from weaver.services.glossary_diff import glossary_diff
from weaver.services.glossary_review import (
    GlossaryReviewState,
    act_on_candidate,
    list_pending,
    list_project_glossary_conflicts,
)
from weaver.services.project_discovery import find_project

router = APIRouter(prefix="/projects", tags=["glossary-review"])


def _base_dir(request: Request) -> Path:
    return request.app.state.base_dir  # type: ignore[no-any-return]


def _project_toml(request: Request, name: str) -> Path:
    dp = find_project(_base_dir(request), name)
    if dp is None:
        raise HTTPException(status_code=404, detail=f"Project '{name}' not found.")
    if dp.error:
        raise HTTPException(status_code=422, detail=dp.error)
    return dp.project_toml


def _counts_response(state: GlossaryReviewState) -> GlossaryReviewCountsResponse:
    return GlossaryReviewCountsResponse(
        pending=state.pending, approved=state.approved, rejected=state.rejected
    )


def _refresh_counts(project_toml: Path, base: Path) -> GlossaryReviewCountsResponse:
    return _counts_response(list_pending(project_toml, cwd=base, limit=1).counts)


def _do_action(
    request: Request,
    name: str,
    candidate_id: int,
    action: str,
    *,
    target: str | None = None,
    notes: str | None = None,
) -> GlossaryCandidateActionResponse:
    base = _base_dir(request)
    project_toml = _project_toml(request, name)
    try:
        act_on_candidate(project_toml, candidate_id, action, cwd=base, target=target, notes=notes)
    except GlossaryCandidateNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except WeaverError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return GlossaryCandidateActionResponse(
        candidate_id=candidate_id,
        action=action,
        counts=_refresh_counts(project_toml, base),
    )


@router.get("/{name}/glossary/candidates", response_model=GlossaryCandidateListResponse)
def list_candidates(
    name: str,
    request: Request,
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=200),
    find: str | None = None,
) -> GlossaryCandidateListResponse:
    """Return one page of pending glossary candidates plus queue counts."""
    base = _base_dir(request)
    project_toml = _project_toml(request, name)
    try:
        page = list_pending(project_toml, cwd=base, offset=offset, limit=limit, find=find)
    except WeaverError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return GlossaryCandidateListResponse(
        candidates=[
            GlossaryCandidateResponse(
                id=c.id,
                source=c.source,
                target=c.target,
                category=c.category,
                notes=c.notes,
                status=c.status,
                frequency=c.frequency,
            )
            for c in page.items
        ],
        total_pending=page.total_pending,
        offset=page.offset,
        limit=page.limit,
        find=page.find,
        counts=_counts_response(page.counts),
    )


@router.post(
    "/{name}/glossary/candidates/{candidate_id}/approve",
    response_model=GlossaryCandidateActionResponse,
)
def approve_candidate(
    name: str, candidate_id: int, request: Request
) -> GlossaryCandidateActionResponse:
    """Approve one candidate (writes it into the project `glossary_terms` table)."""
    return _do_action(request, name, candidate_id, "approve")


@router.post(
    "/{name}/glossary/candidates/{candidate_id}/edit",
    response_model=GlossaryCandidateActionResponse,
)
def edit_candidate(
    name: str, candidate_id: int, request: Request, body: GlossaryCandidateEditRequest
) -> GlossaryCandidateActionResponse:
    """Edit a candidate's target (and notes), then approve it. Empty target → 422."""
    return _do_action(request, name, candidate_id, "edit", target=body.target, notes=body.notes)


@router.post(
    "/{name}/glossary/candidates/{candidate_id}/reject",
    response_model=GlossaryCandidateActionResponse,
)
def reject_candidate(
    name: str, candidate_id: int, request: Request
) -> GlossaryCandidateActionResponse:
    """Reject one candidate (no glossary term is written)."""
    return _do_action(request, name, candidate_id, "reject")


@router.get("/{name}/glossary/conflicts", response_model=GlossaryConflictsResponse)
def list_conflicts(name: str, request: Request) -> GlossaryConflictsResponse:
    """Return approved-term conflicts (a source mapped to multiple targets)."""
    base = _base_dir(request)
    project_toml = _project_toml(request, name)
    try:
        conflicts = list_project_glossary_conflicts(project_toml, cwd=base)
    except WeaverError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return GlossaryConflictsResponse(
        conflicts=[
            GlossaryConflictResponse(source=source, targets=list(targets))
            for source, targets in conflicts
        ]
    )


@router.get("/{name}/glossary/diff", response_model=GlossaryDiffResponse)
def coverage_diff(
    name: str,
    request: Request,
    a: int = Query(..., ge=1, description="First chapter number (1-indexed)."),
    b: int = Query(..., ge=1, description="Second chapter number (1-indexed)."),
) -> GlossaryDiffResponse:
    """Return approved-term coverage diff between chapters ``a`` and ``b``."""
    base = _base_dir(request)
    project_toml = _project_toml(request, name)
    try:
        result = glossary_diff(project_toml, a, b, cwd=base)
    except WeaverError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return GlossaryDiffResponse(
        chapter_a=result.chapter_a,
        chapter_b=result.chapter_b,
        only_in_a=list(result.only_in_a),
        only_in_b=list(result.only_in_b),
        in_both=list(result.in_both),
    )
