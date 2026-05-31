"""Glossary endpoints: direct project-scoped term CRUD (Stage 5A).

Thin adapter over ``weaver.services.glossary_terms``. Domain logic and storage
stay framework-agnostic; this module maps results to Pydantic DTOs and exceptions
to HTTP status codes. The terms read/written here are the same project
``glossary_terms`` rows the candidate review flow populates and that
``services/translation.build_context`` injects into the prompt.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response

from weaver.api.schemas import (
    GlossaryListResponse,
    GlossaryTermCreateRequest,
    GlossaryTermResponse,
    GlossaryTermUpdateRequest,
)
from weaver.errors import GlossaryTermNotFoundError, WeaverError
from weaver.providers.types import GlossaryTerm
from weaver.services.glossary_terms import add_term, delete_term, list_terms, update_term
from weaver.services.project_discovery import find_project

router = APIRouter(prefix="/projects", tags=["glossary"])


def _base_dir(request: Request) -> Path:
    return request.app.state.base_dir  # type: ignore[no-any-return]


def _project_toml(request: Request, name: str) -> Path:
    dp = find_project(_base_dir(request), name)
    if dp is None:
        raise HTTPException(status_code=404, detail=f"Project '{name}' not found.")
    if dp.error:
        raise HTTPException(status_code=422, detail=dp.error)
    return dp.project_toml


def _to_response(term: GlossaryTerm) -> GlossaryTermResponse:
    return GlossaryTermResponse(
        source=term.source,
        target=term.target,
        category=term.category,
        notes=term.notes,
        case_sensitive=term.case_sensitive,
    )


@router.get("/{name}/glossary", response_model=GlossaryListResponse)
def list_glossary(name: str, request: Request) -> GlossaryListResponse:
    """Return all approved glossary terms for one project."""
    project_toml = _project_toml(request, name)
    try:
        terms = list_terms(project_toml, cwd=_base_dir(request))
    except WeaverError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    items = [_to_response(t) for t in terms]
    return GlossaryListResponse(terms=items, count=len(items))


@router.post("/{name}/glossary", response_model=GlossaryTermResponse, status_code=201)
def create_glossary_term(
    name: str, body: GlossaryTermCreateRequest, request: Request
) -> GlossaryTermResponse:
    """Add or upsert one glossary term (keyed by source within the project)."""
    project_toml = _project_toml(request, name)
    try:
        term = add_term(
            project_toml,
            source=body.source,
            target=body.target,
            category=body.category,
            notes=body.notes,
            case_sensitive=body.case_sensitive,
            cwd=_base_dir(request),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except WeaverError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _to_response(term)


@router.patch("/{name}/glossary/{source}", response_model=GlossaryTermResponse)
def update_glossary_term(
    name: str, source: str, body: GlossaryTermUpdateRequest, request: Request
) -> GlossaryTermResponse:
    """Update an existing glossary term identified by its source."""
    project_toml = _project_toml(request, name)
    try:
        term = update_term(
            project_toml,
            source=source,
            target=body.target,
            category=body.category,
            notes=body.notes,
            case_sensitive=body.case_sensitive,
            cwd=_base_dir(request),
        )
    except GlossaryTermNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except WeaverError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _to_response(term)


@router.delete("/{name}/glossary/{source}", status_code=204)
def remove_glossary_term(name: str, source: str, request: Request) -> Response:
    """Delete one glossary term identified by its source."""
    project_toml = _project_toml(request, name)
    try:
        delete_term(project_toml, source=source, cwd=_base_dir(request))
    except GlossaryTermNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except WeaverError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return Response(status_code=204)
