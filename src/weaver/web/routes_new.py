"""New-project + volume-import routes: file browser, upload, init, import.

GET ``/new`` renders the new-project page.
GET ``/api/browse?dir=`` returns a JSON directory listing (sandboxed, ADR ``0017``).
POST ``/new/init`` creates a novel from a browsed/uploaded source (EPUB/TXT/HTML).
POST ``/project/<name>/import`` adds another volume to an existing novel.

Uploads are copied to ``<books-dir>/.weaver/_uploads/`` before init; only
supported source suffixes are accepted; size is capped by ``MAX_CONTENT_LENGTH``.
"""

from __future__ import annotations

from pathlib import Path

from flask import (
    Blueprint,
    abort,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask.typing import ResponseReturnValue
from werkzeug.utils import secure_filename

from weaver.errors import WeaverError
from weaver.services.import_source import import_volume
from weaver.services.project import initialize_project
from weaver.services.project_discovery import find_project
from weaver.web.file_browser import SOURCE_SUFFIXES, list_directory, resolve_source

new_bp = Blueprint("new", __name__)

UPLOADS_DIRNAME = "_uploads"


def _books_dir() -> Path:
    return current_app.config["BOOKS_DIR"]


@new_bp.route("/new")
def new_page() -> str:
    """Render the new-project page (file browser + upload form)."""

    return render_template("new.html", books_dir=str(_books_dir()), error=None)


@new_bp.route("/api/browse")
def browse() -> ResponseReturnValue:
    """Return a JSON directory listing under the books-dir sandbox."""

    rel_dir = request.args.get("dir", "")
    try:
        listing = list_directory(_books_dir(), rel_dir)
    except WeaverError as exc:
        abort(400, description=str(exc))
    return jsonify(
        {
            "rel_dir": listing.rel_dir,
            "parent": listing.parent,
            "entries": [
                {"name": e.name, "kind": e.kind, "rel_path": e.rel_path} for e in listing.entries
            ],
        }
    )


@new_bp.route("/new/init", methods=["POST"])
def init() -> ResponseReturnValue:
    """Create a novel from a browsed path or an uploaded source (EPUB/TXT/HTML)."""

    books_dir = _books_dir()
    provider = request.form.get("provider") or None
    template = request.form.get("template") or None

    try:
        source_path = _select_source(books_dir)
        result = initialize_project(
            source_path,
            cwd=books_dir,
            template=template,
            provider=provider,
        )
    except WeaverError as exc:
        return render_template("new.html", books_dir=str(books_dir), error=str(exc))

    return redirect(url_for("projects.cockpit", name=result.project_name))


@new_bp.route("/project/<name>/import", methods=["POST"])
def import_volume_route(name: str) -> ResponseReturnValue:
    """Import another source file as a new volume in an existing novel."""

    books_dir = _books_dir()
    project = find_project(books_dir, name)
    if project is None:
        abort(404, description=f"No project named {name!r} under {books_dir}")

    try:
        source_path = _select_source(books_dir)
        import_volume(project.project_toml, source_path, cwd=books_dir)
    except WeaverError as exc:
        return redirect(url_for("projects.cockpit", name=name, import_error=str(exc)))

    return redirect(url_for("projects.cockpit", name=name, imported=source_path.name))


def _select_source(books_dir: Path) -> Path:
    """Return the source to import: an uploaded file (preferred) or a browsed path."""

    upload = request.files.get("epub_file")
    if upload is not None and upload.filename:
        return _save_upload(books_dir, upload.filename, upload)

    browsed = request.form.get("epub_path", "").strip()
    if browsed:
        return resolve_source(books_dir, browsed)

    supported = ", ".join(sorted(SOURCE_SUFFIXES))
    raise WeaverError(
        "No source file selected. "
        "Likely cause: neither an uploaded file nor a browsed path was provided. "
        f"Next command: upload or pick one of: {supported}."
    )


def _save_upload(books_dir: Path, filename: str, file_storage: object) -> Path:
    safe_name = secure_filename(filename)
    if Path(safe_name).suffix.lower() not in SOURCE_SUFFIXES:
        supported = ", ".join(sorted(SOURCE_SUFFIXES))
        raise WeaverError(
            f"Unsupported upload: {filename}. "
            f"Likely cause: only these source formats are accepted: {supported}. "
            "Next command: choose a supported source file."
        )
    uploads_dir = books_dir / ".weaver" / UPLOADS_DIRNAME
    uploads_dir.mkdir(parents=True, exist_ok=True)
    target = uploads_dir / safe_name
    file_storage.save(target)  # type: ignore[attr-defined]
    return target
