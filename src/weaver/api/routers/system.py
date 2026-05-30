"""System endpoints: health check and version/status."""

from __future__ import annotations

from fastapi import APIRouter

from weaver import __version__
from weaver.api.schemas import HealthResponse, VersionResponse

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Report liveness of the cockpit API."""
    return HealthResponse(status="ok")


@router.get("/version", response_model=VersionResponse)
def version() -> VersionResponse:
    """Report the application name and version."""
    return VersionResponse(name="weaver", version=__version__)
