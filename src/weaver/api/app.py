"""ASGI application factory for the FastAPI cockpit.

Runs in parallel with the Flask cockpit baseline (ADR 004). This module must not
import Flask; it wires routers and consumes shared services only.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from weaver import __version__
from weaver.api.routers.projects import router as projects_router
from weaver.api.routers.system import router as system_router


def create_api_app(base_dir: Path | None = None) -> FastAPI:
    """Build and configure the FastAPI cockpit application.

    Args:
        base_dir: Root directory to scan for projects. Defaults to cwd.
    """
    app = FastAPI(
        title="Weaver Cockpit API",
        summary="Local API for the Weaver JP->EN light-novel translation cockpit.",
        version=__version__,
    )
    app.state.base_dir = (base_dir or Path.cwd()).resolve()
    app.include_router(system_router)
    app.include_router(projects_router)
    return app
