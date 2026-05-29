"""Translate-job start + SSE progress stream + cooperative stop (Phase 12b).

POST ``/project/<name>/translate`` starts one job (rejected when another runs).
GET ``/project/<name>/events`` streams live progress as ``text/event-stream``.
POST ``/project/<name>/translate/stop`` requests a cooperative cancel.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    redirect,
    request,
    url_for,
)
from flask.typing import ResponseReturnValue

from weaver.services.project_discovery import find_project
from weaver.services.translation import ProgressCallback, translate_project
from weaver.web.job_manager import JobManager, ShouldCancel, format_sse

translate_bp = Blueprint("translate", __name__)


def _books_dir() -> Path:
    return current_app.config["BOOKS_DIR"]


def _job_manager() -> JobManager:
    return current_app.config["JOB_MANAGER"]


@translate_bp.route("/project/<name>/translate", methods=["POST"])
def start(name: str) -> ResponseReturnValue:
    """Start a translate job for one project, then redirect to its cockpit.

    A second start while a job runs is rejected (one job at a time, ADR
    ``0019``) — the redirect carries a ``busy`` flag the cockpit surfaces.
    """

    project = find_project(_books_dir(), name)
    if project is None:
        abort(404, description=f"No project named {name!r}")

    project_toml = project.project_toml
    books_dir = _books_dir()
    retry_failed = request.form.get("retry_failed") == "on"
    first_n = _parse_first_n(request.form.get("first_n"))

    def runner(progress_callback: ProgressCallback, should_cancel: ShouldCancel):
        return translate_project(
            project_toml,
            cwd=books_dir,
            retry_failed=retry_failed,
            first_n=first_n,
            progress_callback=progress_callback,
            should_cancel=should_cancel,
        )

    job = _job_manager().start(name, runner)
    if job is None:
        return redirect(url_for("projects.cockpit", name=name, busy=1))
    return redirect(url_for("projects.cockpit", name=name))


@translate_bp.route("/project/<name>/translate/stop", methods=["POST"])
def stop(name: str) -> ResponseReturnValue:
    """Request a cooperative cancel of the running job for ``name``.

    The worker stops after the current segment (ADR ``0019``); already-translated
    segments stay committed. Redirects back to the cockpit either way.
    """

    _job_manager().request_cancel(name)
    return redirect(url_for("projects.cockpit", name=name))


@translate_bp.route("/project/<name>/events")
def events(name: str) -> ResponseReturnValue:
    """Stream the running job's progress for ``name`` as Server-Sent Events."""

    job_manager = _job_manager()
    job = job_manager.current
    if job is None or job.project_name != name:
        abort(404, description=f"No active job for project {name!r}")

    def stream() -> Iterator[str]:
        while True:
            event = job.queue.get()
            if event is None:  # stream-end sentinel
                break
            yield format_sse(event)

    response = Response(stream(), mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"
    return response


def _parse_first_n(raw: str | None) -> int | None:
    if raw is None or not raw.strip():
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value > 0 else None
