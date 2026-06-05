"""ASGI application factory for the FastAPI cockpit.

The FastAPI cockpit is the only web surface (ADR 004; Flask removed in Sprint
13B). This module wires routers and consumes shared services only.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from weaver import __version__
from weaver.api.jobs import JobRegistry
from weaver.api.routers.batch import router as batch_router
from weaver.api.routers.characters import router as characters_router
from weaver.api.routers.config import router as config_router
from weaver.api.routers.export import router as export_router
from weaver.api.routers.glossary import router as glossary_router
from weaver.api.routers.glossary_review import router as glossary_review_router
from weaver.api.routers.projects import router as projects_router
from weaver.api.routers.qa import router as qa_router
from weaver.api.routers.system import router as system_router
from weaver.api.routers.translate import router as translate_router
from weaver.api.routers.translation_memory import router as translation_memory_router
from weaver.api.routers.ui import router as ui_router
from weaver.api.routers.ui_admin import router as ui_admin_router
from weaver.api.templating import mount_static
from weaver.core.secret_store import apply_secrets_to_env


def create_api_app(base_dir: Path | None = None) -> FastAPI:
    """Build and configure the FastAPI cockpit application.

    Args:
        base_dir: Root directory to scan for projects. Defaults to cwd.
    """
    # Load API keys from the local secret store into the environment (shell env
    # wins) so configured providers can authenticate. Keys are never logged.
    apply_secrets_to_env()

    app = FastAPI(
        title="Weaver Cockpit API",
        summary="Local API for the Weaver JP->EN light-novel translation cockpit.",
        version=__version__,
    )
    app.state.base_dir = (base_dir or Path.cwd()).resolve()
    app.state.jobs = JobRegistry()
    app.include_router(system_router)
    app.include_router(projects_router)
    app.include_router(translate_router)
    app.include_router(batch_router)
    app.include_router(export_router)
    app.include_router(glossary_router)
    app.include_router(glossary_review_router)
    app.include_router(characters_router)
    app.include_router(translation_memory_router)
    app.include_router(config_router)
    app.include_router(qa_router)

    # Browser UI (ADR 007): server-rendered Jinja2 + HTMX under /ui, vendored
    # static assets at /static. JSON API above is unchanged. This UI is the
    # default `weaver serve` cockpit (Flask removed in Sprint 13B).
    mount_static(app)
    app.include_router(ui_router)
    app.include_router(ui_admin_router)

    @app.get("/", include_in_schema=False)
    def _root_redirect() -> RedirectResponse:
        return RedirectResponse(url="/ui")

    return app
