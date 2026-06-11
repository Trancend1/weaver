"""Resolve the source file for create/import from an upload or a browsed path.

Framework-agnostic glue shared by the FastAPI JSON endpoints and the browser UI
(Sprint 11B): given either uploaded bytes **or** a sandbox-relative browsed path,
return the on-disk source path. Upload is preferred when both are present. Reuses
``services/source_browser`` for sandboxing/storage — no new sandbox logic here.
"""

from __future__ import annotations

from pathlib import Path

from weaver.errors import ConfigError, SourceTooLargeError
from weaver.services.source_browser import resolve_source, store_uploaded_source

# Hard cap on uploaded source bytes (QF-08). Light-novel EPUB/TXT/HTML sources
# are far smaller; this guards against an accidental or hostile oversized upload
# being buffered to disk. Browsed (on-disk) paths are not re-checked here — they
# already live inside the sandbox.
MAX_UPLOAD_BYTES = 256 * 1024 * 1024  # 256 MiB


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
        SourceTooLargeError: When the uploaded source exceeds
            :data:`MAX_UPLOAD_BYTES`.
    """

    if uploaded is not None:
        filename, data = uploaded
        if len(data) > MAX_UPLOAD_BYTES:
            limit_mib = MAX_UPLOAD_BYTES // (1024 * 1024)
            actual_mib = len(data) / (1024 * 1024)
            raise SourceTooLargeError(
                f"Uploaded source {filename!r} is {actual_mib:.0f} MiB, over the "
                f"{limit_mib} MiB limit. "
                "Likely cause: the wrong file was selected, or the source bundles "
                "large media. "
                "Next command: upload a smaller EPUB, TXT, or HTML source."
            )
        return store_uploaded_source(base_dir, filename, data)
    if source_path and source_path.strip():
        return resolve_source(base_dir, source_path.strip())
    raise ConfigError(
        "No source selected. "
        "Likely cause: neither an uploaded file nor a browsed source path was given. "
        "Next command: upload or pick an EPUB, TXT, or HTML source."
    )
