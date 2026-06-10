"""UI router: candidates + character drafts (Sprint Q2a split).

Split from the monolithic `ui.py` router.  Zero behaviour change.
"""

from __future__ import annotations

from contextlib import closing
from html import escape
from typing import Any

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse

from weaver.api.routers.candidates import (
    apply_candidate_endpoint,
    approve_candidate_endpoint,
    reject_candidate_endpoint,
)
from weaver.api.routers.ui import _base_dir, _resolve_project_toml
from weaver.api.templating import templates
from weaver.api.ui_context import project_layout
from weaver.errors import (
    WeaverError,
)
from weaver.services.project_paths import resolve_database_path
from weaver.storage.db import connect_readonly_database
from weaver.storage.projects import get_first_project_id

router = APIRouter(tags=["ui"], include_in_schema=False)


# --- candidate review UI (Sprint L3 — HTMX surfaces) ------------------------


@router.get("/ui/projects/{name}/candidates", response_class=HTMLResponse)
def ui_candidates_page(name: str, request: Request) -> HTMLResponse:
    """Translation candidates review page."""
    return templates.TemplateResponse(
        request,
        "candidates.html",
        {**project_layout(request, name, active_nav="candidates"), "name": name},
    )


@router.get("/ui/projects/{name}/candidates/list", response_class=HTMLResponse)
def ui_candidates_list(name: str, request: Request) -> HTMLResponse:
    """HTMX fragment: list of candidates for a project."""
    from weaver.storage.candidates import list_candidates_for_project

    project_toml = _resolve_project_toml(request, name)
    db_path = resolve_database_path(project_toml, cwd=_base_dir(request))
    candidates: list[dict] = []
    total = 0
    error: str | None = None
    try:
        with closing(connect_readonly_database(db_path)) as conn:
            pid = get_first_project_id(conn)
            if pid is not None:
                rows = list_candidates_for_project(conn, project_id=pid, limit=200)
                total = len(rows)
                candidates = [_candidate_to_ui_json(r) for r in rows]
    except WeaverError as exc:
        error = str(exc)
    return templates.TemplateResponse(
        request,
        "partials/_candidates_list.html",
        {"candidates": candidates, "total_count": total, "name": name, "error": error},
    )


@router.post("/ui/projects/{name}/candidates/{candidate_id}/approve", response_class=HTMLResponse)
def ui_candidate_approve(name: str, candidate_id: str, request: Request) -> HTMLResponse:
    """Approve a candidate (HTMX). Re-renders the candidate card."""
    try:
        approve_candidate_endpoint(name, candidate_id, request)
    except HTTPException as exc:
        return HTMLResponse(
            f'<div class="error" role="alert" id="candidate-{candidate_id}">'
            f"Could not approve: {escape(str(exc.detail))}</div>"
        )
    return ui_candidates_rerender_card(request, name, candidate_id)


@router.post("/ui/projects/{name}/candidates/{candidate_id}/reject", response_class=HTMLResponse)
def ui_candidate_reject(name: str, candidate_id: str, request: Request) -> HTMLResponse:
    """Reject a candidate (HTMX). Re-renders the candidate card."""
    try:
        reject_candidate_endpoint(name, candidate_id, request)
    except HTTPException as exc:
        return HTMLResponse(
            f'<div class="error" role="alert" id="candidate-{candidate_id}">'
            f"Could not reject: {escape(str(exc.detail))}</div>"
        )
    return ui_candidates_rerender_card(request, name, candidate_id)


@router.post("/ui/projects/{name}/candidates/{candidate_id}/apply", response_class=HTMLResponse)
def ui_candidate_apply(name: str, candidate_id: str, request: Request) -> HTMLResponse:
    """Apply a candidate to its segment (HTMX). Re-renders the candidate card."""
    try:
        apply_candidate_endpoint(name, candidate_id, request)
    except HTTPException as exc:
        return HTMLResponse(
            f'<div class="error" role="alert" id="candidate-{candidate_id}">'
            f"Could not apply: {escape(str(exc.detail))}</div>"
        )
    return ui_candidates_rerender_card(request, name, candidate_id)


@router.post(
    "/ui/projects/{name}/chapters/{chapter_id}/segments/{segment_id}/candidates/generate",
    response_class=HTMLResponse,
)
def ui_candidate_generate(
    name: str, chapter_id: str, segment_id: str, request: Request
) -> HTMLResponse:
    """Generate one AI candidate for a segment (HTMX); render the new card.

    Thin adapter over ``generate_candidate``: the service stores a ``pending``
    candidate grounded in glossary/character/chapter context and **never**
    mutates the live translation. A provider call that fails mid-translate is
    captured by the service as an empty candidate (rendered as a failed card);
    an unavailable provider or a bad segment raises a ``WeaverError``, which we
    surface as a safe inline fragment — never a 500.
    """
    from weaver.services.candidate_generation import generate_candidate

    project_toml = _resolve_project_toml(request, name)
    try:
        record = generate_candidate(
            project_toml,
            chapter_id,
            segment_id,
            cwd=_base_dir(request),
        )
    except WeaverError as exc:
        return HTMLResponse(
            f'<div class="error" role="alert">Could not generate a candidate: '
            f"{escape(str(exc))}</div>"
        )
    return templates.TemplateResponse(
        request,
        "partials/_candidates_list.html",
        {"candidates": [_candidate_to_ui_json(record)], "total_count": 1, "name": name},
    )


def ui_candidates_rerender_card(request: Request, name: str, candidate_id: str) -> HTMLResponse:
    """Re-render one candidate card after a status transition."""
    from weaver.storage.candidates import get_candidate

    project_toml = _resolve_project_toml(request, name)
    db_path = resolve_database_path(project_toml, cwd=_base_dir(request))
    c = None
    try:
        with closing(connect_readonly_database(db_path)) as conn:
            c = get_candidate(conn, candidate_id=candidate_id)
    except (LookupError, WeaverError):
        return HTMLResponse(
            f'<div class="error" id="candidate-{candidate_id}">Candidate not found.</div>'
        )
    candidate = _candidate_to_ui_json(c)
    return templates.TemplateResponse(
        request,
        "partials/_candidates_list.html",
        {
            "candidates": [candidate],
            "total_count": 1,
            "name": name,
        },
    )


def _candidate_to_ui_json(c: Any) -> dict:
    import json

    prov = c.provenance_json
    return {
        "id": c.id,
        "project_id": c.project_id,
        "volume_id": c.volume_id,
        "chapter_id": c.chapter_id,
        "segment_id": c.segment_id,
        "source_text": c.source_text,
        "candidate_text": c.candidate_text,
        "provider": c.provider,
        "model": c.model,
        "status": c.status,
        "provenance": json.loads(prov) if isinstance(prov, str) else prov,
        "created_at": c.created_at,
        "updated_at": c.updated_at,
    }


# --- character drafts UI (Sprint L4 — HTMX surfaces) ------------------------


@router.get("/ui/projects/{name}/character-drafts", response_class=HTMLResponse)
def ui_drafts_page(name: str, request: Request) -> HTMLResponse:
    """Character page drafts review page."""
    return templates.TemplateResponse(
        request,
        "character_drafts.html",
        {**project_layout(request, name, active_nav="drafts"), "name": name},
    )


@router.get("/ui/projects/{name}/drafts/list", response_class=HTMLResponse)
def ui_drafts_list(name: str, request: Request) -> HTMLResponse:
    """HTMX fragment: list of character drafts for a project."""
    from weaver.storage.character_drafts import list_drafts_for_project

    project_toml = _resolve_project_toml(request, name)
    db_path = resolve_database_path(project_toml, cwd=_base_dir(request))
    drafts: list[dict] = []
    total = 0
    error: str | None = None
    try:
        with closing(connect_readonly_database(db_path)) as conn:
            pid = get_first_project_id(conn)
            if pid is not None:
                rows = list_drafts_for_project(conn, project_id=pid, limit=200)
                total = len(rows)
                for r in rows:
                    drafts.append(_draft_to_ui_json(r))
    except WeaverError as exc:
        error = str(exc)
    return templates.TemplateResponse(
        request,
        "partials/_drafts_list.html",
        {"drafts": drafts, "total_count": total, "name": name, "error": error},
    )


@router.post("/ui/projects/{name}/drafts/generate", response_class=HTMLResponse)
def ui_draft_generate(name: str, request: Request, chapter_id: str = Form(...)) -> HTMLResponse:
    """Generate a character-page draft for a chapter (HTMX); render the card.

    Thin adapter over ``generate_character_draft`` (deterministic XHTML text
    extraction — no OCR, no provider call). Renders the new draft card, a calm
    "no character content" notice when the chapter has none, or a safe inline
    error fragment — never a 500. Non-destructive: a new ``draft`` row is added;
    existing reviewed drafts are untouched.
    """
    from weaver.services.character_draft import generate_character_draft

    project_toml = _resolve_project_toml(request, name)
    try:
        draft = generate_character_draft(project_toml, chapter_id, cwd=_base_dir(request))
    except WeaverError as exc:
        return HTMLResponse(
            f'<div class="error" role="alert">Could not generate a draft: {escape(str(exc))}</div>'
        )
    if draft is None:
        return HTMLResponse(
            '<div class="empty empty-state" role="status">No character page content '
            "detected in this chapter.</div>"
        )
    return templates.TemplateResponse(
        request,
        "partials/_drafts_list.html",
        {"drafts": [_draft_to_ui_json(draft)], "total_count": 1, "name": name},
    )


@router.post("/ui/projects/{name}/drafts/{draft_id}/approve", response_class=HTMLResponse)
def ui_draft_approve(name: str, draft_id: str, request: Request) -> HTMLResponse:
    """Approve a character draft (HTMX). Re-renders the draft card."""
    from weaver.api.routers.candidates import approve_draft_endpoint

    try:
        approve_draft_endpoint(name, draft_id, request)
    except HTTPException as exc:
        return HTMLResponse(
            f'<div class="error" role="alert" id="draft-{draft_id}">'
            f"Could not approve: {escape(str(exc.detail))}</div>"
        )
    return ui_drafts_rerender_card(request, name, draft_id)


@router.post("/ui/projects/{name}/drafts/{draft_id}/reject", response_class=HTMLResponse)
def ui_draft_reject(name: str, draft_id: str, request: Request) -> HTMLResponse:
    """Reject a character draft (HTMX). Re-renders the draft card."""
    from weaver.api.routers.candidates import reject_draft_endpoint

    try:
        reject_draft_endpoint(name, draft_id, request)
    except HTTPException as exc:
        return HTMLResponse(
            f'<div class="error" role="alert" id="draft-{draft_id}">'
            f"Could not reject: {escape(str(exc.detail))}</div>"
        )
    return ui_drafts_rerender_card(request, name, draft_id)


def ui_drafts_rerender_card(request: Request, name: str, draft_id: str) -> HTMLResponse:
    """Re-render one draft card after a status transition."""
    from weaver.storage.character_drafts import get_draft

    project_toml = _resolve_project_toml(request, name)
    db_path = resolve_database_path(project_toml, cwd=_base_dir(request))
    d = None
    try:
        with closing(connect_readonly_database(db_path)) as conn:
            d = get_draft(conn, draft_id=draft_id)
    except (LookupError, WeaverError):
        return HTMLResponse(f'<div class="error" id="draft-{draft_id}">Draft not found.</div>')
    draft = _draft_to_ui_json(d)
    return templates.TemplateResponse(
        request,
        "partials/_drafts_list.html",
        {
            "drafts": [draft],
            "total_count": 1,
            "name": name,
        },
    )


def _draft_to_ui_json(d: Any) -> dict:
    import json

    prov = d.provenance_json
    return {
        "id": d.id,
        "project_id": d.project_id,
        "volume_id": d.volume_id,
        "chapter_id": d.chapter_id,
        "segment_id": d.segment_id,
        "source_text": d.source_text,
        "draft_text": d.draft_text,
        "heading": d.heading,
        "page_identifier": d.page_identifier,
        "status": d.status,
        "provenance": json.loads(prov) if isinstance(prov, str) else prov,
        "created_at": d.created_at,
        "updated_at": d.updated_at,
    }
