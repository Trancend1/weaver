"""Export trigger route (Phase 12b).

POST ``/project/<name>/export`` runs the markdown or epub export over the shared
service core (no logic in the web layer) and redirects back to the cockpit.
"""

from __future__ import annotations

from pathlib import Path

from flask import Blueprint, abort, current_app, redirect, request, url_for
from flask.typing import ResponseReturnValue

from weaver.errors import WeaverError
from weaver.services.export import export_epub_project, export_markdown_project
from weaver.services.project_discovery import find_project

export_bp = Blueprint("export", __name__)


def _books_dir() -> Path:
    return current_app.config["BOOKS_DIR"]


@export_bp.route("/project/<name>/export", methods=["POST"])
def run_export(name: str) -> ResponseReturnValue:
    """Export the project to markdown or epub, then redirect to the cockpit."""

    project = find_project(_books_dir(), name)
    if project is None:
        abort(404, description=f"No project named {name!r}")

    mode = request.form.get("mode", "markdown")
    books_dir = _books_dir()
    project_toml = project.project_toml

    try:
        if mode == "epub":
            result = export_epub_project(project_toml, cwd=books_dir)
            output = str(result.output_path)
        elif mode == "markdown":
            md = export_markdown_project(project_toml, cwd=books_dir)
            output = str(md.output_dir)
        else:
            abort(400, description=f"Unknown export mode {mode!r}")
    except WeaverError as exc:
        return redirect(url_for("projects.cockpit", name=name, export_error=str(exc)))

    return redirect(url_for("projects.cockpit", name=name, exported=mode, output=output))
