"""QA threshold config parsing (`[qa]` table) — Phase D."""

from __future__ import annotations

import pytest

from weaver.errors import ConfigError
from weaver.qa.thresholds import (
    DEFAULT_FALLBACK_HEAVY_MIN_SEGMENTS,
    DEFAULT_FALLBACK_HEAVY_RATIO,
    DEFAULT_REPEATED_MIN_CHARS,
    QAThresholds,
    load_qa_thresholds,
)


def _base() -> dict:
    return {"project": {}, "provider": {}, "translation": {}}


def test_absent_table_yields_defaults() -> None:
    result = load_qa_thresholds(_base())
    assert result == QAThresholds(
        fallback_heavy_ratio=DEFAULT_FALLBACK_HEAVY_RATIO,
        fallback_heavy_min_segments=DEFAULT_FALLBACK_HEAVY_MIN_SEGMENTS,
        repeated_min_chars=DEFAULT_REPEATED_MIN_CHARS,
    )


def test_partial_table_overrides_only_given_keys() -> None:
    config = _base() | {"qa": {"min_segments": 2}}
    result = load_qa_thresholds(config)
    assert result.fallback_heavy_min_segments == 2
    assert result.fallback_heavy_ratio == DEFAULT_FALLBACK_HEAVY_RATIO
    assert result.repeated_min_chars == DEFAULT_REPEATED_MIN_CHARS


def test_full_override() -> None:
    config = _base() | {
        "qa": {"fallback_heavy_ratio": 0.8, "min_segments": 3, "repeated_min_chars": 12}
    }
    result = load_qa_thresholds(config)
    assert result == QAThresholds(
        fallback_heavy_ratio=0.8, fallback_heavy_min_segments=3, repeated_min_chars=12
    )


def test_integer_ratio_is_accepted() -> None:
    # TOML may parse `1` as an int; it is a valid ratio (1.0).
    result = load_qa_thresholds(_base() | {"qa": {"fallback_heavy_ratio": 1}})
    assert result.fallback_heavy_ratio == 1.0


def test_ratio_bounds_are_inclusive() -> None:
    low = load_qa_thresholds(_base() | {"qa": {"fallback_heavy_ratio": 0.0}})
    high = load_qa_thresholds(_base() | {"qa": {"fallback_heavy_ratio": 1.0}})
    assert low.fallback_heavy_ratio == 0.0
    assert high.fallback_heavy_ratio == 1.0


def test_qa_not_a_table_raises() -> None:
    with pytest.raises(ConfigError, match="must be a table"):
        load_qa_thresholds(_base() | {"qa": 5})


def test_foreign_keys_are_ignored() -> None:
    # The `[qa]` table is shared with the per-segment QA flags (weaver.services.qa);
    # keys this module does not own must be ignored, not rejected.
    config = _base() | {
        "qa": {
            "detect_empty_output": True,
            "minimum_length_ratio": 0.3,
            "min_segments": 2,
        }
    }
    result = load_qa_thresholds(config)
    assert result.fallback_heavy_min_segments == 2
    assert result.fallback_heavy_ratio == DEFAULT_FALLBACK_HEAVY_RATIO


@pytest.mark.parametrize("bad", [-0.1, 1.1, 2])
def test_ratio_out_of_range_raises(bad: float) -> None:
    with pytest.raises(ConfigError, match="between 0.0 and 1.0"):
        load_qa_thresholds(_base() | {"qa": {"fallback_heavy_ratio": bad}})


@pytest.mark.parametrize("bad", ["0.5", True, [1]])
def test_ratio_wrong_type_raises(bad: object) -> None:
    with pytest.raises(ConfigError, match="must be a number"):
        load_qa_thresholds(_base() | {"qa": {"fallback_heavy_ratio": bad}})


@pytest.mark.parametrize("key", ["min_segments", "repeated_min_chars"])
def test_positive_int_rejects_zero_and_negative(key: str) -> None:
    with pytest.raises(ConfigError, match=">= 1"):
        load_qa_thresholds(_base() | {"qa": {key: 0}})


@pytest.mark.parametrize("key", ["min_segments", "repeated_min_chars"])
@pytest.mark.parametrize("bad", [1.5, "5", True])
def test_positive_int_rejects_non_int(key: str, bad: object) -> None:
    with pytest.raises(ConfigError, match="positive integer"):
        load_qa_thresholds(_base() | {"qa": {key: bad}})
