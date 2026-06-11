"""ASGI application factory for the FastAPI cockpit.

The FastAPI cockpit is the only web surface (ADR 004; Flask removed in Sprint
13B). This module wires routers and consumes shared services only.

Sprint G2: ``base_dir`` resolves from (in priority order) the explicit factory
arg, ``$WEAVER_BOOKS_DIR``, then ``Path.cwd()``. The app-data root resolves via
``services.app_paths.resolve_app_paths`` and is attached to ``app.state``.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

from weaver import __version__
from weaver.api.jobs import JobRegistry
from weaver.api.routers.batch import router as batch_router
from weaver.api.routers.candidates import router as candidates_router
from weaver.api.routers.characters import router as characters_router
from weaver.api.routers.config import router as config_router
from weaver.api.routers.export import router as export_router
from weaver.api.routers.glossary import router as glossary_router
from weaver.api.routers.glossary_review import router as glossary_review_router
from weaver.api.routers.jobs import router as jobs_router
from weaver.api.routers.projects import router as projects_router
from weaver.api.routers.qa import router as qa_router
from weaver.api.routers.runtime import router as runtime_router
from weaver.api.routers.system import router as system_router
from weaver.api.routers.translate import router as translate_router
from weaver.api.routers.translation_memory import router as translation_memory_router
from weaver.api.routers.ui import router as ui_router
from weaver.api.routers.ui_admin import router as ui_admin_router
from weaver.api.routers.ui_candidates import router as ui_candidates_router
from weaver.api.routers.ui_exports import router as ui_exports_router
from weaver.api.routers.ui_jobs import router as ui_jobs_router
from weaver.api.routers.ui_providers import router as ui_providers_router
from weaver.api.routers.ui_qa import router as ui_qa_router
from weaver.api.routers.ui_queue import router as ui_queue_router
from weaver.api.routers.ui_resources import router as ui_resources_router
from weaver.api.routers.ui_review import router as ui_review_router
from weaver.api.routers.ui_workspace import router as ui_workspace_router
from weaver.api.templating import mount_static
from weaver.core.secret_store import apply_secrets_to_env
from weaver.services.app_paths import BOOKS_DIR_ENV, resolve_app_paths
from weaver.services.job_store import recover_all_projects
from weaver.services.logging_setup import install_logging, log_runtime_event
from weaver.services.runtime_env import (
    current_env,
    docs_enabled,
    session_token,
)

SESSION_HEADER = "X-Weaver-Session"
_PUBLIC_PATHS = frozenset({"/healthz", "/health", "/version", "/static"})


def create_api_app(base_dir: Path | None = None) -> FastAPI:
    """Build and configure the FastAPI cockpit application.

    Args:
        base_dir: Root directory to scan for projects. When ``None``, falls
            back to ``$WEAVER_BOOKS_DIR`` then ``Path.cwd()``. The env-var
            fallback lets ``weaver serve`` pass the books-dir through Uvicorn's
            ``factory=True`` invocation without ``os.chdir`` side effects.
    """
    # Load API keys from the local secret store into the environment (shell env
    # wins) so configured providers can authenticate. Keys are never logged.
    apply_secrets_to_env()

    env_mode = current_env()
    show_docs = docs_enabled()
    docs_url = "/docs" if show_docs else None
    redoc_url = "/redoc" if show_docs else None

    app = FastAPI(
        title="Weaver Cockpit API",
        summary="Local API for the Weaver JP->EN light-novel translation cockpit.",
        version=__version__,
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url="/openapi.json" if show_docs else None,
    )
    if base_dir is None:
        env_books_dir = os.environ.get(BOOKS_DIR_ENV, "").strip()
        base_dir = Path(env_books_dir) if env_books_dir else Path.cwd()
    app.state.base_dir = base_dir.resolve()
    app.state.app_paths = resolve_app_paths()
    app.state.jobs = JobRegistry(base_dir=app.state.base_dir)
    app.state.workspace_cache = {}
    app.state.env_mode = env_mode

    # Cold-start recovery (Sprint I3, ADR 010): mark every `running` job in any
    # project DB as `failed` with a stable reason. Single-process invariant means
    # a previous worker thread cannot be revived. Idempotent.
    recovered = recover_all_projects(app.state.base_dir)
    if recovered:
        log_runtime_event(
            "jobs.cold_start_recovered",
            base_dir=str(app.state.base_dir),
            projects=recovered,
        )

    # Test mode skips the file-handler install so the test suite does not
    # write to the user's real app-data directory. Set WEAVER_ENV=test to
    # opt out, or WEAVER_DATA_DIR to redirect.
    if env_mode != "test":
        install_logging(app.state.app_paths)
        log_runtime_event(
            "runtime.start",
            env=env_mode,
            base_dir=str(app.state.base_dir),
            app_data_dir=str(app.state.app_paths.root),
            version=__version__,
        )

    if env_mode == "desktop":
        # Same-origin only. The shell webview shares scheme+host+port with the
        # sidecar, so cross-origin requests are by definition off-platform.
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[],
            allow_credentials=False,
            allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=[SESSION_HEADER, "Content-Type", "HX-Request", "HX-Target"],
        )

    expected_token = session_token()
    if expected_token is not None:

        @app.middleware("http")
        async def _enforce_session_token(request: Request, call_next):  # type: ignore[no-untyped-def]
            path = request.url.path
            if any(path == p or path.startswith(p + "/") for p in _PUBLIC_PATHS):
                return await call_next(request)
            received = request.headers.get(SESSION_HEADER)
            if received != expected_token:
                return JSONResponse(status_code=401, content={"detail": "Invalid session token."})
            return await call_next(request)

    app.include_router(system_router)
    app.include_router(runtime_router)
    app.include_router(projects_router)
    app.include_router(jobs_router)
    app.include_router(translate_router)
    app.include_router(batch_router)
    app.include_router(export_router)
    app.include_router(glossary_router)
    app.include_router(glossary_review_router)
    app.include_router(candidates_router)
    app.include_router(characters_router)
    app.include_router(translation_memory_router)
    app.include_router(config_router)
    app.include_router(qa_router)

    # Browser UI (ADR 007): server-rendered Jinja2 + HTMX under /ui, vendored
    # static assets at /static. JSON API above is unchanged. This UI is the
    # default `weaver serve` cockpit (Flask removed in Sprint 13B).
    mount_static(app)
    app.include_router(ui_router)
    app.include_router(ui_workspace_router)
    app.include_router(ui_jobs_router)
    app.include_router(ui_queue_router)
    app.include_router(ui_resources_router)
    app.include_router(ui_providers_router)
    app.include_router(ui_exports_router)
    app.include_router(ui_candidates_router)
    app.include_router(ui_review_router)
    app.include_router(ui_admin_router)
    app.include_router(ui_qa_router)

    @app.get("/", include_in_schema=False)
    def _root_redirect() -> RedirectResponse:
        return RedirectResponse(url="/ui")

    return app
