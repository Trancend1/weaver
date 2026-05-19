"""Project TOML loading with ConfigError-mapped failure modes.

Single entry point for parsing `project.toml`. Wraps `tomllib` and required-key
checks so every CLI surface receives a `ConfigError` (CLI exit code 7 per
PRD_v2.md §10 AC-9) instead of a bare `TOMLDecodeError` or `KeyError`.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from weaver.errors import ConfigError

REQUIRED_TOP_LEVEL_TABLES = ("project", "provider", "translation")


def load_project_config(path: Path) -> dict[str, Any]:
    """Parse and validate a project.toml file.

    Args:
        path: Path to the project.toml file.

    Returns:
        Parsed TOML as a nested dict.

    Raises:
        ConfigError: When the file is missing, unparseable, or missing a
            required top-level table.
    """

    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ConfigError(
            f"Project config not found at {path}. "
            "Likely cause: incorrect path or project was never initialized. "
            "Next command: run `weaver init <input.epub>`."
        ) from exc
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(
            f"Could not parse {path}: {exc} (expected: valid TOML). "
            "Likely cause: file was edited with a tool that added a UTF-8 BOM, "
            "or a syntax error was introduced. "
            "Next command: open the file in a UTF-8 editor and remove any BOM."
        ) from exc
    for table in REQUIRED_TOP_LEVEL_TABLES:
        if table not in data:
            raise ConfigError(
                f"Missing required `[{table}]` table in {path} (expected type: table). "
                "Likely cause: project.toml was hand-edited. "
                "Next command: regenerate the project with `weaver init <input.epub>`."
            )
    return data
