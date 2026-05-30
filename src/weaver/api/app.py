"""ASGI application factory for the FastAPI cockpit.

Runs in parallel with the Flask cockpit baseline (ADR 004). This module must not
import Flask; it wires routers and consumes shared services only.
"""

from __future__ import annotations

from fastapi import FastAPI

from weaver import __version__
from weaver.api.routers.system import router as system_router


def create_api_app() -> FastAPI:
    """Build and configure the FastAPI cockpit application."""
    app = FastAPI(
        title="Weaver Cockpit API",
        summary="Local API for the Weaver JP->EN light-novel translation cockpit.",
        version=__version__,
    )
    app.include_router(system_router)
    return app
