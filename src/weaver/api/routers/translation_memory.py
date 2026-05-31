"""Translation memory endpoints: project-scoped read overview + delete (Stage 6B).

Thin adapter over ``weaver.services.translation_memory``. Domain logic and storage
stay framework-agnostic; this module maps results to Pydantic DTOs and exceptions
to HTTP status codes. Deleting an entry removes only its ``translation_memory``
row — translation history, manual edits, glossary, and character data are untouched.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response

from weaver.api.schemas import MemoryEntryResponse, MemoryOverviewResponse
from weaver.errors import TranslationMemoryNotFoundError, WeaverError
from weaver.services.project_discovery import find_project
from weaver.services.translation_memory import delete_entry, get_memory_overview
from weaver.storage.translation_memory import TranslationMemoryRecord

router = APIRouter(prefix="/projects", tags=["translation-memory"])


def _base_dir(request: Request) -> Path:
    return request.app.state.base_dir  # type: ignore[no-any-return]


def _project_toml(request: Request, name: str) -> Path:
    dp = find_project(_base_dir(request), name)
    if dp is None:
        raise HTTPException(status_code=404, detail=f"Project '{name}' not found.")
    if dp.error:
        raise HTTPException(status_code=422, detail=dp.error)
    return dp.project_toml


def _to_entry(record: TranslationMemoryRecord) -> MemoryEntryResponse:
    return MemoryEntryResponse(
        source_text=record.source_text,
        source_hash=record.source_hash,
        target_text=record.target_text,
        provider=record.provider,
        model=record.model,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@router.get("/{name}/memory", response_model=MemoryOverviewResponse)
def get_memory(name: str, request: Request) -> MemoryOverviewResponse:
    """Return a project's translation-memory entries plus reuse statistics."""
    project_toml = _project_toml(request, name)
    try:
        overview = get_memory_overview(project_toml, cwd=_base_dir(request))
    except WeaverError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return MemoryOverviewResponse(
        total_entries=overview.total_entries,
        exact_hits=overview.exact_hits,
        reused_from_memory=overview.reused_from_memory,
        entries=[_to_entry(record) for record in overview.entries],
    )


@router.delete("/{name}/memory/{source_hash}", status_code=204)
def remove_memory_entry(name: str, source_hash: str, request: Request) -> Response:
    """Delete one translation-memory entry by source hash (TM row only)."""
    project_toml = _project_toml(request, name)
    try:
        delete_entry(project_toml, source_hash=source_hash, cwd=_base_dir(request))
    except TranslationMemoryNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except WeaverError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return Response(status_code=204)
