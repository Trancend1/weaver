"""Character endpoints: project-scoped CRUD keyed by Japanese name (Stage 5B).

Thin adapter over ``weaver.services.characters``. Domain logic and storage stay
framework-agnostic; this module maps results to Pydantic DTOs and exceptions to
HTTP status codes. Prompt injection of character context lands in Stage 5C.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response

from weaver.api.schemas import (
    CharacterCreateRequest,
    CharacterListResponse,
    CharacterResponse,
    CharacterUpdateRequest,
)
from weaver.errors import CharacterNotFoundError, WeaverError
from weaver.services.characters import add_character, delete, list_all, update_character
from weaver.services.project_discovery import find_project
from weaver.storage.characters import CharacterRecord

router = APIRouter(prefix="/projects", tags=["characters"])


def _base_dir(request: Request) -> Path:
    return request.app.state.base_dir  # type: ignore[no-any-return]


def _project_toml(request: Request, name: str) -> Path:
    dp = find_project(_base_dir(request), name)
    if dp is None:
        raise HTTPException(status_code=404, detail=f"Project '{name}' not found.")
    if dp.error:
        raise HTTPException(status_code=422, detail=dp.error)
    return dp.project_toml


def _to_response(character: CharacterRecord) -> CharacterResponse:
    return CharacterResponse(
        jp_name=character.jp_name,
        en_name=character.en_name,
        gender=character.gender,
        role=character.role,
        notes=character.notes,
    )


@router.get("/{name}/characters", response_model=CharacterListResponse)
def list_characters_endpoint(name: str, request: Request) -> CharacterListResponse:
    """Return all characters for one project."""
    project_toml = _project_toml(request, name)
    try:
        characters = list_all(project_toml, cwd=_base_dir(request))
    except WeaverError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    items = [_to_response(c) for c in characters]
    return CharacterListResponse(characters=items, count=len(items))


@router.post("/{name}/characters", response_model=CharacterResponse, status_code=201)
def create_character(
    name: str, body: CharacterCreateRequest, request: Request
) -> CharacterResponse:
    """Add or upsert one character (keyed by jp_name within the project)."""
    project_toml = _project_toml(request, name)
    try:
        character = add_character(
            project_toml,
            jp_name=body.jp_name,
            en_name=body.en_name,
            gender=body.gender,
            role=body.role,
            notes=body.notes,
            cwd=_base_dir(request),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except WeaverError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _to_response(character)


@router.patch("/{name}/characters/{jp_name}", response_model=CharacterResponse)
def update_character_endpoint(
    name: str, jp_name: str, body: CharacterUpdateRequest, request: Request
) -> CharacterResponse:
    """Update an existing character identified by its Japanese name."""
    project_toml = _project_toml(request, name)
    try:
        character = update_character(
            project_toml,
            jp_name=jp_name,
            en_name=body.en_name,
            gender=body.gender,
            role=body.role,
            notes=body.notes,
            cwd=_base_dir(request),
        )
    except CharacterNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except WeaverError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _to_response(character)


@router.delete("/{name}/characters/{jp_name}", status_code=204)
def remove_character(name: str, jp_name: str, request: Request) -> Response:
    """Delete one character identified by its Japanese name."""
    project_toml = _project_toml(request, name)
    try:
        delete(project_toml, jp_name=jp_name, cwd=_base_dir(request))
    except CharacterNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except WeaverError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return Response(status_code=204)
