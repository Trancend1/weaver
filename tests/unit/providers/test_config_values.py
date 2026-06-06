"""Numeric [provider] config readers (Phase D provider hardening)."""

from __future__ import annotations

import pytest

from weaver.errors import ConfigError
from weaver.providers.config_values import read_float, read_int


def test_read_float_absent_returns_default() -> None:
    assert read_float({}, "temperature", 0.3) == 0.3


def test_read_float_accepts_int_and_float() -> None:
    assert read_float({"temperature": 1}, "temperature", 0.3) == 1.0
    assert read_float({"temperature": 0.7}, "temperature", 0.3) == 0.7


@pytest.mark.parametrize("bad", ["hot", True, [0.5], None])
def test_read_float_rejects_non_numbers(bad: object) -> None:
    with pytest.raises(ConfigError, match="must be a number"):
        read_float({"temperature": bad}, "temperature", 0.3)


def test_read_float_enforces_inclusive_bounds() -> None:
    assert read_float({"top_p": 0.0}, "top_p", 0.9, minimum=0.0, maximum=1.0) == 0.0
    assert read_float({"top_p": 1.0}, "top_p", 0.9, minimum=0.0, maximum=1.0) == 1.0
    with pytest.raises(ConfigError, match="out of range"):
        read_float({"top_p": 1.5}, "top_p", 0.9, minimum=0.0, maximum=1.0)
    with pytest.raises(ConfigError, match="out of range"):
        read_float({"top_p": -0.1}, "top_p", 0.9, minimum=0.0, maximum=1.0)


def test_read_float_exclusive_minimum_rejects_zero() -> None:
    ok = read_float({"timeout_seconds": 0.5}, "timeout_seconds", 180.0, exclusive_minimum=0.0)
    assert ok == 0.5
    with pytest.raises(ConfigError, match="out of range"):
        read_float({"timeout_seconds": 0.0}, "timeout_seconds", 180.0, exclusive_minimum=0.0)
    with pytest.raises(ConfigError, match="out of range"):
        read_float({"timeout_seconds": -5}, "timeout_seconds", 180.0, exclusive_minimum=0.0)


def test_read_int_absent_returns_default() -> None:
    assert read_int({}, "seed", 0) == 0


@pytest.mark.parametrize("bad", [1.5, "5", True, None])
def test_read_int_rejects_non_int(bad: object) -> None:
    with pytest.raises(ConfigError, match="must be an integer"):
        read_int({"seed": bad}, "seed", 0)


def test_read_int_enforces_minimum() -> None:
    assert read_int({"n": 1}, "n", 5, minimum=1) == 1
    with pytest.raises(ConfigError, match=">= 1"):
        read_int({"n": 0}, "n", 5, minimum=1)
