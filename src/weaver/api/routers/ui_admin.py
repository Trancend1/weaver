"""Consistency/admin browser UI (Stage 11C): glossary, characters, TM, config.

Server-rendered Jinja2 + HTMX (ADR ``007``), **presentation only** — every route
is a thin adapter over the existing services (`glossary_terms`, `glossary_review`,
`glossary_diff`, `characters`, `translation_memory`, `provider_config`). No
business logic, no storage access, no behavior change. API-key *values* are only
ever accepted by the secret-set form and are never rendered back. Lives under
``/ui``; the JSON API is untouched.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from weaver.api.templating import templates
from weaver.api.ui_context import global_layout, project_layout
from weaver.errors import (
    CharacterNotFoundError,
    GlossaryCandidateNotFoundError,
    GlossaryTermNotFoundError,
    SecretNotFoundError,
    TranslationMemoryNotFoundError,
    WeaverError,
)
from weaver.providers.registry import known_provider_types
from weaver.services import characters as characters_service
from weaver.services import glossary_terms as glossary_service
from weaver.services import provider_config as config_service
from weaver.services import translation_memory as tm_service
from weaver.services.glossary_diff import glossary_diff
from weaver.services.glossary_review import (
    act_on_candidate,
    list_pending,
    list_project_glossary_conflicts,
)
from weaver.services.project_discovery import discover_projects, find_project

router = APIRouter(tags=["ui"], include_in_schema=False)

CANDIDATE_PAGE = 20
MEMORY_PAGE = 50


def _base_dir(request: Request) -> Path:
    return request.app.state.base_dir  # type: ignore[no-any-return]


def _project_toml(request: Request, name: str) -> Path:
    dp = find_project(_base_dir(request), name)
    if dp is None:
        raise HTTPException(status_code=404, detail=f"No project named {name!r}.")
    if dp.error:
        raise HTTPException(status_code=422, detail=dp.error)
    return dp.project_toml


def _opt(value: str | None) -> str | None:
    return value.strip() if value and value.strip() else None


# --- glossary terms + candidate review --------------------------------------


def _glossary_terms_ctx(request: Request, name: str) -> dict[str, object]:
    base = _base_dir(request)
    return {
        "name": name,
        "terms": glossary_service.list_terms(_project_toml(request, name), cwd=base),
    }


def _candidates_ctx(
    request: Request, name: str, *, offset: int = 0, find: str | None = None
) -> dict[str, object]:
    base = _base_dir(request)
    page = list_pending(
        _project_toml(request, name), cwd=base, offset=offset, limit=CANDIDATE_PAGE, find=find
    )
    return {
        "name": name,
        "page": page,
        "find": find or "",
        "prev_offset": max(offset - CANDIDATE_PAGE, 0) if offset > 0 else None,
        "next_offset": offset + CANDIDATE_PAGE
        if offset + CANDIDATE_PAGE < page.total_pending
        else None,
    }


def _terms_fragment(request: Request, name: str, *, error: str | None = None) -> HTMLResponse:
    ctx = _glossary_terms_ctx(request, name)
    ctx["error"] = error
    return templates.TemplateResponse(request, "partials/_glossary_terms.html", ctx)


def _candidates_fragment(
    request: Request,
    name: str,
    *,
    offset: int = 0,
    find: str | None = None,
    error: str | None = None,
) -> HTMLResponse:
    ctx = _candidates_ctx(request, name, offset=offset, find=find)
    ctx["error"] = error
    return templates.TemplateResponse(request, "partials/_glossary_candidates.html", ctx)


@router.get("/ui/projects/{name}/glossary", response_class=HTMLResponse)
def glossary_page(name: str, request: Request) -> HTMLResponse:
    """Glossary admin: term CRUD, candidate review, conflicts, coverage diff."""
    base = _base_dir(request)
    try:
        project_toml = _project_toml(request, name)
        conflicts = list_project_glossary_conflicts(project_toml, cwd=base)
    except HTTPException:
        raise
    except WeaverError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    ctx: dict[str, object] = {
        **project_layout(request, name, active_nav="glossary"),
        **_glossary_terms_ctx(request, name),
        **_candidates_ctx(request, name),
        "conflicts": conflicts,
    }
    return templates.TemplateResponse(request, "glossary.html", ctx)


@router.post("/ui/projects/{name}/glossary/terms", response_class=HTMLResponse)
def glossary_add(
    name: str,
    request: Request,
    source: str = Form(...),
    target: str = Form(...),
    category: str | None = Form(None),
    notes: str | None = Form(None),
) -> HTMLResponse:
    """Add (upsert) one glossary term, then re-render the terms table."""
    base = _base_dir(request)
    try:
        glossary_service.add_term(
            _project_toml(request, name),
            source=source,
            target=target,
            category=_opt(category),
            notes=_opt(notes),
            cwd=base,
        )
    except (ValueError, WeaverError) as exc:
        return _terms_fragment(request, name, error=str(exc))
    return _terms_fragment(request, name)


@router.post("/ui/projects/{name}/glossary/terms/{source}/update", response_class=HTMLResponse)
def glossary_update(
    name: str,
    source: str,
    request: Request,
    target: str = Form(...),
    category: str | None = Form(None),
    notes: str | None = Form(None),
) -> HTMLResponse:
    """Update one glossary term, then re-render the terms table."""
    base = _base_dir(request)
    try:
        glossary_service.update_term(
            _project_toml(request, name),
            source=source,
            target=target,
            category=_opt(category),
            notes=_opt(notes),
            cwd=base,
        )
    except GlossaryTermNotFoundError as exc:
        return _terms_fragment(request, name, error=str(exc))
    except (ValueError, WeaverError) as exc:
        return _terms_fragment(request, name, error=str(exc))
    return _terms_fragment(request, name)


@router.post("/ui/projects/{name}/glossary/terms/{source}/delete", response_class=HTMLResponse)
def glossary_delete(name: str, source: str, request: Request) -> HTMLResponse:
    """Delete one glossary term, then re-render the terms table."""
    base = _base_dir(request)
    try:
        glossary_service.delete_term(_project_toml(request, name), source=source, cwd=base)
    except GlossaryTermNotFoundError as exc:
        return _terms_fragment(request, name, error=str(exc))
    return _terms_fragment(request, name)


@router.get("/ui/projects/{name}/glossary/candidates", response_class=HTMLResponse)
def glossary_candidates_fragment(
    name: str, request: Request, offset: int = Query(0, ge=0), find: str | None = None
) -> HTMLResponse:
    """Paged pending-candidate list, optionally filtered by ``find`` (HTMX fragment)."""
    return _candidates_fragment(request, name, offset=offset, find=find)


@router.post(
    "/ui/projects/{name}/glossary/candidates/{candidate_id}/{action}",
    response_class=HTMLResponse,
)
def glossary_candidate_action(
    name: str,
    candidate_id: int,
    action: str,
    request: Request,
    target: str | None = Form(None),
    notes: str | None = Form(None),
    offset: int = Form(0),
    find: str | None = Form(None),
) -> HTMLResponse:
    """Approve / edit / reject one candidate, then re-render the candidate list."""
    base = _base_dir(request)
    try:
        act_on_candidate(
            _project_toml(request, name),
            candidate_id,
            action,
            cwd=base,
            target=_opt(target),
            notes=_opt(notes),
        )
    except GlossaryCandidateNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, WeaverError) as exc:
        return _candidates_fragment(request, name, offset=offset, find=find, error=str(exc))
    return _candidates_fragment(request, name, offset=offset, find=find)


@router.get("/ui/projects/{name}/glossary/diff", response_class=HTMLResponse)
def glossary_diff_fragment(
    name: str, request: Request, a: int = Query(..., ge=1), b: int = Query(..., ge=1)
) -> HTMLResponse:
    """Render the approved-term coverage diff between two chapters (HTMX fragment)."""
    base = _base_dir(request)
    try:
        result = glossary_diff(_project_toml(request, name), a, b, cwd=base)
    except WeaverError as exc:
        return templates.TemplateResponse(
            request, "partials/_glossary_diff.html", {"error": str(exc)}
        )
    return templates.TemplateResponse(request, "partials/_glossary_diff.html", {"diff": result})


# --- characters -------------------------------------------------------------


def _characters_fragment(request: Request, name: str, *, error: str | None = None) -> HTMLResponse:
    base = _base_dir(request)
    return templates.TemplateResponse(
        request,
        "partials/_characters.html",
        {
            "name": name,
            "characters": characters_service.list_all(_project_toml(request, name), cwd=base),
            "error": error,
        },
    )


@router.get("/ui/projects/{name}/characters", response_class=HTMLResponse)
def characters_page(name: str, request: Request) -> HTMLResponse:
    """Character DB admin: add/edit/delete characters injected into prompts."""
    base = _base_dir(request)
    return templates.TemplateResponse(
        request,
        "characters.html",
        {
            **project_layout(request, name, active_nav="characters"),
            "name": name,
            "characters": characters_service.list_all(_project_toml(request, name), cwd=base),
        },
    )


@router.post("/ui/projects/{name}/characters", response_class=HTMLResponse)
def characters_add(
    name: str,
    request: Request,
    jp_name: str = Form(...),
    en_name: str = Form(...),
    gender: str | None = Form(None),
    role: str | None = Form(None),
    notes: str | None = Form(None),
) -> HTMLResponse:
    """Add (upsert) one character, then re-render the character table."""
    base = _base_dir(request)
    try:
        characters_service.add_character(
            _project_toml(request, name),
            jp_name=jp_name,
            en_name=en_name,
            gender=_opt(gender),
            role=_opt(role),
            notes=_opt(notes),
            cwd=base,
        )
    except (ValueError, WeaverError) as exc:
        return _characters_fragment(request, name, error=str(exc))
    return _characters_fragment(request, name)


@router.post("/ui/projects/{name}/characters/{jp_name}/update", response_class=HTMLResponse)
def characters_update(
    name: str,
    jp_name: str,
    request: Request,
    en_name: str = Form(...),
    gender: str | None = Form(None),
    role: str | None = Form(None),
    notes: str | None = Form(None),
) -> HTMLResponse:
    """Update one character, then re-render the character table."""
    base = _base_dir(request)
    try:
        characters_service.update_character(
            _project_toml(request, name),
            jp_name=jp_name,
            en_name=en_name,
            gender=_opt(gender),
            role=_opt(role),
            notes=_opt(notes),
            cwd=base,
        )
    except CharacterNotFoundError as exc:
        return _characters_fragment(request, name, error=str(exc))
    except (ValueError, WeaverError) as exc:
        return _characters_fragment(request, name, error=str(exc))
    return _characters_fragment(request, name)


@router.post("/ui/projects/{name}/characters/{jp_name}/delete", response_class=HTMLResponse)
def characters_delete(name: str, jp_name: str, request: Request) -> HTMLResponse:
    """Delete one character, then re-render the character table."""
    base = _base_dir(request)
    try:
        characters_service.delete(_project_toml(request, name), jp_name=jp_name, cwd=base)
    except CharacterNotFoundError as exc:
        return _characters_fragment(request, name, error=str(exc))
    return _characters_fragment(request, name)


# --- translation memory -----------------------------------------------------


def _memory_ctx(
    request: Request, name: str, *, offset: int = 0, find: str | None = None
) -> dict[str, object]:
    """Build the TM context, paginating + filtering the entries in the UI layer.

    The overview (and the JSON API) still returns every row; here we only render
    a page of them so a large novel's TM doesn't paint thousands of rows at once.
    """
    base = _base_dir(request)
    overview = tm_service.get_memory_overview(_project_toml(request, name), cwd=base)
    needle = (find or "").strip().lower()
    entries = list(overview.entries)
    if needle:
        entries = [
            e
            for e in entries
            if needle in (e.source_text or "").lower() or needle in (e.target_text or "").lower()
        ]
    total_matching = len(entries)
    return {
        "name": name,
        "overview": overview,
        "entries": entries[offset : offset + MEMORY_PAGE],
        "find": find or "",
        "offset": offset,
        "total_matching": total_matching,
        "prev_offset": max(offset - MEMORY_PAGE, 0) if offset > 0 else None,
        "next_offset": offset + MEMORY_PAGE if offset + MEMORY_PAGE < total_matching else None,
    }


def _memory_fragment(
    request: Request,
    name: str,
    *,
    offset: int = 0,
    find: str | None = None,
    error: str | None = None,
) -> HTMLResponse:
    ctx = _memory_ctx(request, name, offset=offset, find=find)
    ctx["error"] = error
    return templates.TemplateResponse(request, "partials/_memory.html", ctx)


@router.get("/ui/projects/{name}/memory", response_class=HTMLResponse)
def memory_page(
    name: str, request: Request, offset: int = Query(0, ge=0), find: str | None = None
) -> HTMLResponse:
    """Translation-memory admin: read entries + reuse stats, delete one entry."""
    ctx = {
        **project_layout(request, name, active_nav="memory"),
        **_memory_ctx(request, name, offset=offset, find=find),
    }
    return templates.TemplateResponse(request, "memory.html", ctx)


@router.get("/ui/projects/{name}/memory/entries", response_class=HTMLResponse)
def memory_entries_fragment(
    name: str, request: Request, offset: int = Query(0, ge=0), find: str | None = None
) -> HTMLResponse:
    """Paged + filtered TM entries (HTMX fragment)."""
    return _memory_fragment(request, name, offset=offset, find=find)


@router.post("/ui/projects/{name}/memory/{source_hash}/delete", response_class=HTMLResponse)
def memory_delete(
    name: str,
    source_hash: str,
    request: Request,
    offset: int = Form(0),
    find: str | None = Form(None),
) -> HTMLResponse:
    """Delete one TM entry (TM-row only), then re-render the current page."""
    base = _base_dir(request)
    try:
        tm_service.delete_entry(_project_toml(request, name), source_hash=source_hash, cwd=base)
    except TranslationMemoryNotFoundError as exc:
        return _memory_fragment(request, name, offset=offset, find=find, error=str(exc))
    return _memory_fragment(request, name, offset=offset, find=find)


# --- provider / secret config -----------------------------------------------


def _config_ctx(request: Request, project: str | None) -> dict[str, object]:
    base = _base_dir(request)
    view = config_service.read_config(base, project=_opt(project))
    return {
        **global_layout("config"),
        "view": view,
        "project": _opt(project),
        "projects": [dp.name for dp in discover_projects(base)],
        "provider_types": known_provider_types(),
    }


@router.get("/ui/config", response_class=HTMLResponse)
def config_page(request: Request, project: str | None = None) -> HTMLResponse:
    """Provider/model + secret config admin (key values never rendered)."""
    try:
        ctx = _config_ctx(request, project)
    except WeaverError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return templates.TemplateResponse(request, "config.html", ctx)


@router.post("/ui/config", response_class=HTMLResponse)
def config_save(
    request: Request,
    scope: str = Form("project"),
    project: str | None = Form(None),
    provider_type: str | None = Form(None),
    model: str | None = Form(None),
    base_url: str | None = Form(None),
    api_key_env: str | None = Form(None),
) -> HTMLResponse:
    """Persist provider/model config (no key value accepted), then re-render."""
    base = _base_dir(request)
    error: str | None = None
    try:
        config_service.write_config(
            base,
            scope=scope,
            project=_opt(project),
            provider_type=_opt(provider_type),
            model=_opt(model),
            base_url=_opt(base_url),
            api_key_env=_opt(api_key_env),
        )
    except WeaverError as exc:
        error = str(exc)
    ctx = _config_ctx(request, project)
    ctx["error"] = error
    ctx["saved"] = error is None
    return templates.TemplateResponse(request, "partials/_config_form.html", ctx)


@router.post("/ui/config/secrets", response_class=HTMLResponse)
def config_secret_set(
    request: Request,
    project: str | None = Form(None),
    env_name: str = Form(...),
    value: str = Form(...),
) -> HTMLResponse:
    """Store an API-key secret under an env-var name (value never echoed back)."""
    error: str | None = None
    try:
        config_service.store_secret(env_name, value)
    except WeaverError as exc:
        error = str(exc)
    ctx = _config_ctx(request, project)
    ctx["secret_error"] = error
    ctx["secret_saved"] = error is None
    return templates.TemplateResponse(request, "partials/_secrets.html", ctx)


@router.post("/ui/config/secrets/{env_name}/delete", response_class=HTMLResponse)
def config_secret_delete(
    env_name: str, request: Request, project: str | None = Form(None)
) -> HTMLResponse:
    """Remove a stored secret, then re-render the secret list."""
    error: str | None = None
    try:
        config_service.remove_secret(env_name)
    except SecretNotFoundError as exc:
        error = str(exc)
    ctx = _config_ctx(request, project)
    ctx["secret_error"] = error
    return templates.TemplateResponse(request, "partials/_secrets.html", ctx)
