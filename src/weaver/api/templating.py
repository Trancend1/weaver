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
    badge_class_for_translation,
    job_status_label,
    translation_status_label,
)

_PACKAGE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = _PACKAGE_DIR / "templates"
STATIC_DIR = _PACKAGE_DIR / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.globals["translation_status_label"] = translation_status_label
templates.env.globals["job_status_label"] = job_status_label
templates.env.globals["badge_class_for_translation"] = badge_class_for_translation
templates.env.globals["badge_class_for_job"] = badge_class_for_job


def mount_static(app: FastAPI) -> None:
    """Mount the vendored static assets at ``/static`` (idempotent per app)."""

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
