"""Glossary review routes (Phase 12c).

GET ``/project/<name>/glossary`` — paginated pending candidates, queue counts,
approved-term conflicts, and an optional per-chapter coverage diff (all read via
stateless service ops).
POST ``/project/<name>/glossary/<id>`` — approve / edit / reject one candidate.

The CLI interactive review loop is untouched; the browser reuses the same store
through the stateless helpers in ``services/glossary_review.py``.
"""

from __future__ import annotations

from pathlib import Path

from flask import Blueprint, abort, current_app, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue

from weaver.errors import WeaverError
from weaver.services.glossary_diff import glossary_diff
from weaver.services.glossary_review import (
    act_on_candidate,
    list_pending,
    list_project_glossary_conflicts,
)
from weaver.services.project_discovery import find_project

glossary_bp = Blueprint("glossary", __name__)

PAGE_SIZE = 20


def _books_dir() -> Path:
    return current_app.config["BOOKS_DIR"]


@glossary_bp.route("/project/<name>/glossary")
def review(name: str) -> str:
    """Render the paginated glossary review page for one project."""

    books_dir = _books_dir()
    project = find_project(books_dir, name)
    if project is None:
        abort(404, description=f"No project named {name!r}")

    offset = _parse_int(request.args.get("offset"), default=0, minimum=0)
    find = (request.args.get("find") or "").strip() or None
    page = list_pending(
        project.project_toml, cwd=books_dir, offset=offset, limit=PAGE_SIZE, find=find
    )
    conflicts = list_project_glossary_conflicts(project.project_toml, cwd=books_dir)
    diff, diff_error = _maybe_diff(project.project_toml, books_dir)

    return render_template(
        "glossary.html",
        project=project,
        page=page,
        conflicts=conflicts,
        diff=diff,
        diff_error=diff_error,
        find=find or "",
        prev_offset=max(offset - PAGE_SIZE, 0) if offset > 0 else None,
        next_offset=offset + PAGE_SIZE if offset + PAGE_SIZE < page.total_pending else None,
    )


@glossary_bp.route("/project/<name>/glossary/<int:candidate_id>", methods=["POST"])
def act(name: str, candidate_id: int) -> ResponseReturnValue:
    """Apply approve / edit / reject to one candidate, then reload the page."""

    books_dir = _books_dir()
    project = find_project(books_dir, name)
    if project is None:
        abort(404, description=f"No project named {name!r}")

    action = request.form.get("action", "")
    offset = _parse_int(request.form.get("offset"), default=0, minimum=0)
    try:
        act_on_candidate(
            project.project_toml,
            candidate_id,
            action,
            cwd=books_dir,
            target=request.form.get("target"),
            notes=request.form.get("notes") or None,
        )
    except WeaverError as exc:
        return redirect(url_for("glossary.review", name=name, offset=offset, error=str(exc)))
    return redirect(url_for("glossary.review", name=name, offset=offset))


def _maybe_diff(project_toml: Path, books_dir: Path):
    raw_a = request.args.get("diff_a")
    raw_b = request.args.get("diff_b")
    if not raw_a or not raw_b:
        return None, None
    a = _parse_int(raw_a, default=0, minimum=1)
    b = _parse_int(raw_b, default=0, minimum=1)
    if a < 1 or b < 1:
        return None, "Chapter numbers must be 1 or greater."
    try:
        return glossary_diff(project_toml, a, b, cwd=books_dir), None
    except WeaverError as exc:
        return None, str(exc)


def _parse_int(raw: str | None, *, default: int, minimum: int) -> int:
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value >= minimum else default
