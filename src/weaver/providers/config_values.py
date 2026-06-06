"""Typed readers for numeric ``[provider]`` config values (Phase D hardening).

Provider numeric settings (``temperature``, ``timeout_seconds``, ``top_p``, …)
arrive from the parsed ``[provider]`` TOML block as arbitrary values. A bare
``float(config[...])`` turns a typo like ``temperature = "hot"`` into an opaque
``ValueError`` that escapes as a crash. These readers coerce with a clear
:class:`~weaver.errors.ConfigError` (what failed / likely cause / next command)
and enforce the obvious valid ranges instead.

Pure: no I/O, no DB, no secrets — they never read or echo an API key.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from weaver.errors import ConfigError


def read_float(
    config: Mapping[str, Any],
    key: str,
    default: float,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
    exclusive_minimum: float | None = None,
) -> float:
    """Read a numeric ``[provider]`` value as a float, or return ``default``.

    Args:
        config: The parsed ``[provider]`` mapping.
        key: The setting name.
        default: Value used when ``key`` is absent.
        minimum: Inclusive lower bound, if any.
        maximum: Inclusive upper bound, if any.
        exclusive_minimum: Strict lower bound, if any (value must be greater).

    Raises:
        ConfigError: If the value is not a number or is out of range.
    """

    if key not in config:
        return default
    value = config[key]
    # bool is a subclass of int; reject it so `temperature = true` doesn't pass.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(
            f"`[provider].{key}` must be a number (got: {value!r}). "
            "Likely cause: the value was quoted or set to a non-number in project.toml. "
            f"Next command: set `{key}` to a number (e.g. {default})."
        )
    number = float(value)
    too_low = (minimum is not None and number < minimum) or (
        exclusive_minimum is not None and number <= exclusive_minimum
    )
    too_high = maximum is not None and number > maximum
    if too_low or too_high:
        raise ConfigError(
            f"`[provider].{key}` is out of range (got: {number}; allowed: "
            f"{_range_text(minimum, maximum, exclusive_minimum)}). "
            "Likely cause: an invalid threshold in project.toml. "
            f"Next command: set `{key}` within range (e.g. {default})."
        )
    return number


def read_int(
    config: Mapping[str, Any],
    key: str,
    default: int,
    *,
    minimum: int | None = None,
) -> int:
    """Read a numeric ``[provider]`` value as an int, or return ``default``.

    Raises:
        ConfigError: If the value is not an integer or is below ``minimum``.
    """

    if key not in config:
        return default
    value = config[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(
            f"`[provider].{key}` must be an integer (got: {value!r}). "
            "Likely cause: the value was a float, string, or boolean in project.toml. "
            f"Next command: set `{key}` to a whole number (e.g. {default})."
        )
    if minimum is not None and value < minimum:
        raise ConfigError(
            f"`[provider].{key}` must be >= {minimum} (got: {value}). "
            "Likely cause: a negative or too-small value in project.toml. "
            f"Next command: set `{key}` to {minimum} or more."
        )
    return value


def _range_text(
    minimum: float | None, maximum: float | None, exclusive_minimum: float | None
) -> str:
    if exclusive_minimum is not None and maximum is not None:
        return f"> {exclusive_minimum} and <= {maximum}"
    if exclusive_minimum is not None:
        return f"> {exclusive_minimum}"
    if minimum is not None and maximum is not None:
        return f"{minimum}–{maximum}"
    if minimum is not None:
        return f">= {minimum}"
    if maximum is not None:
        return f"<= {maximum}"
    return "any"
