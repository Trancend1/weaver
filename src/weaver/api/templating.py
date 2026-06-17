"""Jinja2 templating + static-asset wiring for the FastAPI cockpit UI (ADR ``007``).

Single place that builds the ``Jinja2Templates`` instance and mounts the vendored
static dir (HTMX 1.9.12 + minimal CSS — no CDN, no Node build). Keeps ``app.py`` a
thin factory. The UI layer is presentation only: templates render context dicts
built by ``routers/ui.py`` from the shared services (CLAUDE.md §4.2).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from weaver.api.status_labels import (
    badge_class_for_job,
    badge_class_for_review,
    badge_class_for_translation,
    job_status_label,
    review_status_label,
    translation_status_label,
)

_PACKAGE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = _PACKAGE_DIR / "templates"
STATIC_DIR = _PACKAGE_DIR / "static"


def _asset_version() -> str:
    """Cache-busting token for ``/static/app.css``.

    Computed once at import from the stylesheet's mtime so a CSS change is
    picked up on the next server start (browsers otherwise serve a stale copy
    of the un-versioned ``app.css``). No render-path filesystem cost.
    """

    try:
        return str(int(STATIC_DIR.joinpath("app.css").stat().st_mtime))
    except OSError:
        return "0"


templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.globals["asset_version"] = _asset_version()
templates.env.globals["translation_status_label"] = translation_status_label
templates.env.globals["job_status_label"] = job_status_label
templates.env.globals["review_status_label"] = review_status_label
templates.env.globals["badge_class_for_translation"] = badge_class_for_translation
templates.env.globals["badge_class_for_job"] = badge_class_for_job
templates.env.globals["badge_class_for_review"] = badge_class_for_review


def mount_static(app: FastAPI) -> None:
    """Mount the vendored static assets at ``/static`` (idempotent per app)."""

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
