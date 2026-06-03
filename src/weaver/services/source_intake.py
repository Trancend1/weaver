"""Resolve the source file for create/import from an upload or a browsed path.

Framework-agnostic glue shared by the FastAPI JSON endpoints and the browser UI
(Sprint 11B): given either uploaded bytes **or** a sandbox-relative browsed path,
return the on-disk source path. Upload is preferred when both are present. Reuses
``services/source_browser`` for sandboxing/storage — no new sandbox logic here.
"""

from __future__ import annotations

from pathlib import Path

from weaver.errors import ConfigError
from weaver.services.source_browser import resolve_source, store_uploaded_source


def resolve_intake_source(
    base_dir: Path,
    *,
    uploaded: tuple[str, bytes] | None = None,
    source_path: str | None = None,
) -> Path:
    """Return the source path to create/import from.

    Args:
        base_dir: Sandbox root (cockpit base dir).
        uploaded: ``(filename, data)`` for an uploaded source, or None.
        source_path: A sandbox-relative path to a browsed source, or None.

    Returns:
        The absolute, sandbox-confirmed source path (upload stored under the
        sandbox uploads dir, preserving the original stem).

    Raises:
        ConfigError: When neither input is provided, or the supplied source is
            outside the sandbox / an unsupported format.
    """

    if uploaded is not None:
        filename, data = uploaded
        return store_uploaded_source(base_dir, filename, data)
    if source_path and source_path.strip():
        return resolve_source(base_dir, source_path.strip())
    raise ConfigError(
        "No source selected. "
        "Likely cause: neither an uploaded file nor a browsed source path was given. "
        "Next command: upload or pick an EPUB, TXT, or HTML source."
    )
