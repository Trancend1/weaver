"""New-project routes: sandboxed file browser, upload, and init (Phase 12b).

GET ``/new`` renders the new-project page.
GET ``/api/browse?dir=`` returns a JSON directory listing (sandboxed, ADR ``0017``).
POST ``/new/init`` initializes a project from a browsed path or an uploaded EPUB.

Uploads are copied to ``<books-dir>/.weaver/_uploads/`` (blueprint plan D2) before
init. Only ``.epub`` files are accepted; size is capped by ``MAX_CONTENT_LENGTH``.
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
from weaver.services.project import initialize_project
from weaver.web.file_browser import EPUB_SUFFIX, list_directory, resolve_epub

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
    """Initialize a project from a browsed path or an uploaded EPUB."""

    books_dir = _books_dir()
    provider = request.form.get("provider") or None
    template = request.form.get("template") or None

    try:
        epub_path = _select_epub(books_dir)
        result = initialize_project(
            epub_path,
            cwd=books_dir,
            template=template,
            provider=provider,
        )
    except WeaverError as exc:
        return render_template("new.html", books_dir=str(books_dir), error=str(exc))

    return redirect(url_for("projects.cockpit", name=result.project_name))


def _select_epub(books_dir: Path) -> Path:
    """Return the EPUB to init: an uploaded file (preferred) or a browsed path."""

    upload = request.files.get("epub_file")
    if upload is not None and upload.filename:
        return _save_upload(books_dir, upload.filename, upload)

    browsed = request.form.get("epub_path", "").strip()
    if browsed:
        return resolve_epub(books_dir, browsed)

    raise WeaverError(
        "No EPUB selected. "
        "Likely cause: neither an uploaded file nor a browsed path was provided. "
        "Next command: upload a .epub or pick one from the browser."
    )


def _save_upload(books_dir: Path, filename: str, file_storage: object) -> Path:
    safe_name = secure_filename(filename)
    if not safe_name.lower().endswith(EPUB_SUFFIX):
        raise WeaverError(
            f"Uploaded file is not an EPUB: {filename}. "
            "Likely cause: only .epub uploads are accepted. "
            "Next command: choose a .epub file."
        )
    uploads_dir = books_dir / ".weaver" / UPLOADS_DIRNAME
    uploads_dir.mkdir(parents=True, exist_ok=True)
    target = uploads_dir / safe_name
    file_storage.save(target)  # type: ignore[attr-defined]
    return target
