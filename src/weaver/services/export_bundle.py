"""Bundle per-volume export artifacts into a single ZIP (Phase D).

A volume-aware export renders one artifact per volume under ``output/<target>/``.
An optional bundle step packages those already-written artifacts into a single
``.zip`` for easy download. Pure file packaging: it reads the rendered artifacts
and writes a ZIP — no database access, no provider call, no re-rendering. The
bundle holds the per-volume files of one target (e.g. every ``.docx``); a
multi-target bundle is out of scope.

Framework-agnostic: no web/CLI/job types here (ADR 002/004).
"""

from __future__ import annotations

import zipfile
from collections.abc import Sequence
from pathlib import Path

from weaver.errors import ExportError


def bundle_filename(target: str) -> str:
    """The deterministic ZIP name for a target's bundle (e.g. ``bundle-docx.zip``)."""

    return f"bundle-{target}.zip"


def write_export_bundle(*, output_path: Path, artifact_paths: Sequence[Path]) -> Path:
    """Zip the given export artifacts into a single ``.zip`` (stored by basename).

    Args:
        output_path: Destination path for the ``.zip``.
        artifact_paths: Already-written per-volume artifact files to include. Names
            are collision-safe within a target (each carries its volume id), so
            each entry is stored under its basename.

    Returns:
        The written bundle path.

    Raises:
        ExportError: If an artifact is missing or the ZIP cannot be written.
    """

    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in artifact_paths:
                archive.write(path, arcname=path.name)
    except OSError as exc:
        raise ExportError(
            f"Failed to write export bundle to '{output_path}'. "
            "Likely cause: an artifact was moved/deleted, the target directory is "
            "not writable, or the disk is full. "
            "Next command: re-run the export, then check filesystem permissions or space."
        ) from exc
    return output_path
