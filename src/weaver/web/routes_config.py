"""Provider/model config route (Phase 12b, ADR ``0018``).

POST ``/project/<name>/config`` writes provider/model to project scope
(``project.toml [provider]``) or global scope (``~/.weaver/config.toml``).

API keys are never accepted, written, or rendered (CLAUDE.md §4.2, ADR ``0017``)
— this route only touches ``type`` / ``model`` / ``base_url``.
"""

from __future__ import annotations

from pathlib import Path

from flask import Blueprint, abort, current_app, redirect, request, url_for
from flask.typing import ResponseReturnValue

from weaver.core.global_config import default_global_config_path
from weaver.core.secret_store import set_secret
from weaver.errors import WeaverError
from weaver.services.config_writer import set_provider
from weaver.services.project_discovery import find_project

config_bp = Blueprint("config", __name__)


def _books_dir() -> Path:
    return current_app.config["BOOKS_DIR"]


@config_bp.route("/project/<name>/config", methods=["POST"])
def update(name: str) -> ResponseReturnValue:
    """Set provider/model for a project (scope=project) or globally.

    Provider fields (``type``/``model``/``base_url``/``api_key_env``) go to config
    via ``config_writer``. An optional ``api_key`` value is written **only** to the
    secret store under ``api_key_env`` (ADR ``0020``) — never to ``project.toml``,
    never echoed back.
    """

    project = find_project(_books_dir(), name)
    if project is None:
        abort(404, description=f"No project named {name!r}")

    scope = request.form.get("scope", "project")
    provider_type = request.form.get("provider_type") or None
    model = request.form.get("model") or None
    base_url = request.form.get("base_url") or None
    api_key_env = (request.form.get("api_key_env") or "").strip() or None
    api_key = request.form.get("api_key") or None  # value — never persisted to config

    target = default_global_config_path() if scope == "global" else project.project_toml
    try:
        set_provider(
            target,
            provider_type=provider_type,
            model=model,
            base_url=base_url if scope != "global" else None,
            api_key_env=api_key_env if scope != "global" else None,
        )
        if api_key and api_key_env:
            set_secret(api_key_env, api_key)
    except WeaverError as exc:
        return redirect(url_for("projects.cockpit", name=name, config_error=str(exc)))

    return redirect(url_for("projects.cockpit", name=name, config_saved=scope))
