"""Flask app factory for the local web cockpit (ADR ``0016`` / ``0017``).

Binds ``127.0.0.1`` only — never ``0.0.0.0`` (ADR ``0017``). Single-user local
tool, no auth. The dev server runs with ``threaded=True`` so SSE streaming and
ordinary requests coexist (ADR ``0016`` D1). Web dependencies live behind the
optional ``weaver[web]`` extra.
"""

from __future__ import annotations

import webbrowser
from pathlib import Path

from flask import Flask

from weaver.web.job_manager import JobManager
from weaver.web.routes_config import config_bp
from weaver.web.routes_export import export_bp
from weaver.web.routes_glossary import glossary_bp
from weaver.web.routes_new import new_bp
from weaver.web.routes_projects import projects_bp
from weaver.web.routes_translate import translate_bp

# Loopback only. Bind address is never user-configurable (security: ADR 0017).
HOST = "127.0.0.1"
DEFAULT_PORT = 8765

# Upload cap for EPUB file input (ADR 0017). EPUBs are small; 64 MiB is generous.
MAX_UPLOAD_BYTES = 64 * 1024 * 1024


def create_app(books_dir: Path, *, job_manager: JobManager | None = None) -> Flask:
    """Build the cockpit Flask app.

    Args:
        books_dir: Root directory to discover projects under and (in 12b) to
            sandbox the file browser to.
        job_manager: Optional injected registry (tests pass a fresh one). A new
            :class:`JobManager` is created when omitted.

    Returns:
        A configured Flask app with project and translate blueprints registered.
    """

    from weaver.core.secret_store import apply_secrets_to_env

    apply_secrets_to_env()

    app = Flask(__name__)
    app.config["BOOKS_DIR"] = books_dir.resolve()
    app.config["JOB_MANAGER"] = job_manager or JobManager()
    app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES
    app.register_blueprint(projects_bp)
    app.register_blueprint(translate_bp)
    app.register_blueprint(new_bp)
    app.register_blueprint(config_bp)
    app.register_blueprint(export_bp)
    app.register_blueprint(glossary_bp)
    return app


def run_server(
    *,
    books_dir: Path,
    port: int = DEFAULT_PORT,
    open_browser: bool = True,
) -> None:
    """Run the cockpit dev server on loopback.

    Args:
        books_dir: Root directory to discover projects under.
        port: TCP port on ``127.0.0.1``. Host is fixed to loopback.
        open_browser: When True, open the default browser at the cockpit URL.
    """

    app = create_app(books_dir)
    url = f"http://{HOST}:{port}"
    if open_browser:
        webbrowser.open(url)
    app.run(host=HOST, port=port, threaded=True)
