"""Configurable thresholds for the deterministic scope-level QA checks (Phase D).

In Phase B the scope checks (``fallback_heavy``, ``repeated_identical_translation``)
used module-level constants. They are now overridable per project via an optional
``[qa]`` table in ``project.toml``:

```toml
[qa]
fallback_heavy_ratio = 0.5   # 0.0–1.0; flag a chapter when this share has no
                             # publishable translation
min_segments = 5             # only score fallback-heavy at/above this segment count
repeated_min_chars = 8       # ignore repeated translations shorter than this
```

Defaults are unchanged when the table (or a key) is absent, so existing projects
behave identically. The ``[qa]`` table is **shared** with the per-segment QA flags
read by :mod:`weaver.services.qa` (``detect_empty_output``, ``minimum_length_ratio``,
…), so foreign keys are ignored here rather than rejected. Only the three keys this
module owns are validated: a wrong type or out-of-range value raises
:class:`~weaver.errors.ConfigError`. Pure value type — no I/O, no DB,
framework-agnostic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from weaver.errors import ConfigError

DEFAULT_FALLBACK_HEAVY_RATIO = 0.5
DEFAULT_FALLBACK_HEAVY_MIN_SEGMENTS = 5
DEFAULT_REPEATED_MIN_CHARS = 8


@dataclass(frozen=True)
class QAThresholds:
    """Resolved QA thresholds; defaults reproduce Phase B behavior."""

    fallback_heavy_ratio: float = DEFAULT_FALLBACK_HEAVY_RATIO
    fallback_heavy_min_segments: int = DEFAULT_FALLBACK_HEAVY_MIN_SEGMENTS
    repeated_min_chars: int = DEFAULT_REPEATED_MIN_CHARS


def load_qa_thresholds(config: dict[str, Any]) -> QAThresholds:
    """Build :class:`QAThresholds` from a parsed ``project.toml`` dict.

    Reads the optional ``[qa]`` table. An absent table yields all defaults.
    Foreign keys (the per-segment QA flags owned by :mod:`weaver.services.qa`)
    are ignored; only this module's three keys are validated.

    Args:
        config: The full parsed ``project.toml`` mapping.

    Returns:
        Resolved thresholds.

    Raises:
        ConfigError: If ``[qa]`` is not a table, or one of this module's keys has
            the wrong type or is out of range.
    """

    table = config.get("qa")
    if table is None:
        return QAThresholds()
    if not isinstance(table, dict):
        raise ConfigError(
            "The `[qa]` entry in project.toml must be a table (expected type: table). "
            "Likely cause: `qa` was set to a scalar value. "
            "Next command: replace it with a `[qa]` table or remove it."
        )
    return QAThresholds(
        fallback_heavy_ratio=_read_ratio(table, "fallback_heavy_ratio"),
        fallback_heavy_min_segments=_read_positive_int(table, "min_segments"),
        repeated_min_chars=_read_positive_int(table, "repeated_min_chars"),
    )


def _read_ratio(table: dict[str, Any], key: str) -> float:
    if key not in table:
        return DEFAULT_FALLBACK_HEAVY_RATIO
    value = table[key]
    # bool is a subclass of int; reject it explicitly so `true`/`false` don't pass.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(
            f"`[qa].{key}` must be a number between 0.0 and 1.0 (got: {value!r}). "
            "Likely cause: the value is not a number. "
            "Next command: set it to a ratio such as 0.5."
        )
    ratio = float(value)
    if not 0.0 <= ratio <= 1.0:
        raise ConfigError(
            f"`[qa].{key}` must be between 0.0 and 1.0 (got: {ratio}). "
            "Likely cause: the ratio is outside the valid range. "
            "Next command: set it to a value such as 0.5."
        )
    return ratio


def _read_positive_int(table: dict[str, Any], key: str) -> int:
    default = (
        DEFAULT_FALLBACK_HEAVY_MIN_SEGMENTS if key == "min_segments" else DEFAULT_REPEATED_MIN_CHARS
    )
    if key not in table:
        return default
    value = table[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(
            f"`[qa].{key}` must be a positive integer (got: {value!r}). "
            "Likely cause: the value is a float, string, or boolean. "
            "Next command: set it to a whole number such as 5."
        )
    if value < 1:
        raise ConfigError(
            f"`[qa].{key}` must be >= 1 (got: {value}). "
            "Likely cause: a zero or negative threshold. "
            "Next command: set it to a positive whole number."
        )
    return value
