"""Pydantic response schemas for the FastAPI cockpit (web-boundary DTOs).

Stage 2A defines only the system schemas. Project / Novel / Volume / Chapter and
import DTOs arrive in Stage 2B/2C alongside their endpoints.
"""

from __future__ import annotations

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Liveness probe payload."""

    status: str


class VersionResponse(BaseModel):
    """Application identity and version payload."""

    name: str
    version: str
