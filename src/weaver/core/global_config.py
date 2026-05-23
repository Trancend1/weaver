"""Global config file loading and multi-tier value resolution.

Reads ``~/.weaver/config.toml`` (optional) and implements the precedence chain:
CLI flag > env var > project.toml > global config > built-in default.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any


def default_global_config_path() -> Path:
    """Return the canonical path for the user-level config file."""

    return Path.home() / ".weaver" / "config.toml"


def load_global_config(path: Path | None = None) -> dict[str, Any]:
    """Load the global config file, tolerant of missing or empty files.

    Args:
        path: Override path for testing. Defaults to ``~/.weaver/config.toml``.

    Returns:
        Parsed TOML dict, or empty dict when the file does not exist or is
        empty.
    """

    config_path = path or default_global_config_path()
    if not config_path.is_file():
        return {}
    try:
        text = config_path.read_text(encoding="utf-8")
    except OSError:
        return {}
    if not text.strip():
        return {}
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return {}


def resolve_config_value(
    key: str,
    *,
    cli_value: str | None = None,
    env_var: str | None = None,
    project_config: dict[str, Any] | None = None,
    global_config: dict[str, Any] | None = None,
    default: str,
) -> str:
    """Resolve a configuration value through the four-tier precedence chain.

    Precedence (highest wins):
    1. ``cli_value`` — explicit CLI flag
    2. Environment variable named ``env_var``
    3. ``project_config[key]`` — project.toml section value
    4. ``global_config[key]`` — ~/.weaver/config.toml value
    5. ``default`` — built-in fallback

    Args:
        key: The config key name (used to look up in project and global dicts).
        cli_value: Value passed via CLI flag, or None.
        env_var: Name of the environment variable to check, or None.
        project_config: Relevant section from project.toml, or None.
        global_config: Parsed global config dict, or None.
        default: Built-in default when all other tiers are absent.

    Returns:
        Resolved string value.
    """

    if cli_value is not None:
        return cli_value

    if env_var is not None:
        env_value = os.environ.get(env_var)
        if env_value is not None and env_value.strip():
            return env_value.strip()

    if project_config is not None:
        project_value = project_config.get(key)
        if project_value is not None:
            return str(project_value)

    if global_config is not None:
        global_value = global_config.get(key)
        if global_value is not None:
            return str(global_value)

    return default
