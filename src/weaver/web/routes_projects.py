"""Dashboard and read-only project cockpit routes (Phase 12a).

GET ``/`` lists every discovered project (no path typing — kills PP1).
GET ``/project/<name>`` renders a read-only cockpit mirroring ``weaver inspect``.
All write actions (config, translate controls, export, glossary) land in 12b/12c.
"""

from __future__ import annotations

from pathlib import Path

from flask import Blueprint, abort, current_app, render_template

from weaver.core.global_config import load_global_config, resolve_config_value
from weaver.core.secret_store import list_secret_names
from weaver.providers.registry import known_provider_types
from weaver.services.project_discovery import discover_projects, find_project

projects_bp = Blueprint("projects", __name__)


def _books_dir() -> Path:
    return current_app.config["BOOKS_DIR"]


@projects_bp.route("/")
def dashboard() -> str:
    """List discovered projects and the resolved global provider default."""

    global_config = load_global_config()
    default_provider = resolve_config_value(
        "default_provider",
        env_var="WEAVER_DEFAULT_PROVIDER",
        global_config=global_config,
        default="deepseek",
    )
    default_model = resolve_config_value(
        "default_model",
        env_var="WEAVER_DEFAULT_MODEL",
        global_config=global_config,
        default="—",
    )
    projects = discover_projects(_books_dir())
    return render_template(
        "dashboard.html",
        projects=projects,
        books_dir=str(_books_dir()),
        default_provider=default_provider,
        default_model=default_model,
    )


@projects_bp.route("/project/<name>")
def cockpit(name: str) -> str:
    """Render the read-only cockpit for one project (mirrors ``inspect``)."""

    project = find_project(_books_dir(), name)
    if project is None:
        abort(404, description=f"No project named {name!r} under {_books_dir()}")
    job_manager = current_app.config["JOB_MANAGER"]
    running_here = (
        job_manager.is_running()
        and job_manager.current is not None
        and job_manager.current.project_name == name
    )
    return render_template(
        "cockpit.html",
        project=project,
        running_here=running_here,
        provider_types=known_provider_types(),
        secret_names=list_secret_names(),
    )
