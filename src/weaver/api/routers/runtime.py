"""Runtime endpoints: sidecar-contract health and runtime introspection.

Distinct from ``routers/system.py`` so the older ``/health`` + ``/version``
payloads stay bit-identical with the soak script and existing tests. ``/healthz``
is the sidecar-contract liveness path (Sprint G3) used by the Tauri shell's
boot poll; ``/runtime/status`` is the post-handshake introspection endpoint.

Tokens, secrets, and API keys are never exposed by anything in this module
(CLAUDE.md §4.2).
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Request

from weaver.api.schemas import HealthZResponse, RuntimeStatusResponse
from weaver.services.app_paths import BOOKS_DIR_ENV, AppPaths

ENV_VAR = "WEAVER_ENV"
HOST_VAR = "WEAVER_HOST"
PORT_VAR = "WEAVER_PORT"
DEFAULT_ENV = "dev"

router = APIRouter(tags=["runtime"])


@router.get("/healthz", response_model=HealthZResponse)
def healthz() -> HealthZResponse:
    """Sidecar liveness probe."""
    return HealthZResponse(ok=True, ts=datetime.now(UTC).isoformat())


@router.get("/runtime/status", response_model=RuntimeStatusResponse)
def runtime_status(request: Request) -> RuntimeStatusResponse:
    """Report env mode, bind, and the runtime's resolved directories.

    Host and port are read from env vars when set so the sidecar can verify
    its own assignment after binding to a random port. They are ``None`` when
    the runtime is hosted in-process (e.g. TestClient) — that is informative,
    not an error.
    """
    app_paths: AppPaths = request.app.state.app_paths
    base_dir: Path = request.app.state.base_dir
    host = os.environ.get(HOST_VAR) or None
    port_raw = os.environ.get(PORT_VAR)
    try:
        port = int(port_raw) if port_raw is not None and port_raw.strip() else None
    except ValueError:
        port = None
    books_dir = os.environ.get(BOOKS_DIR_ENV) or str(base_dir)
    return RuntimeStatusResponse(
        env=os.environ.get(ENV_VAR, DEFAULT_ENV),
        host=host,
        port=port,
        app_data_dir=str(app_paths.root),
        logs_dir=str(app_paths.logs_dir),
        books_dir=books_dir,
    )
