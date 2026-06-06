"""Provider registry tests."""

from __future__ import annotations

import pytest

from weaver.errors import ConfigError
from weaver.providers import build_provider
from weaver.providers.fake import FakeProvider


def test_build_provider_dispatches_to_fake() -> None:
    provider = build_provider({"type": "fake", "model": "fake-1"})

    assert isinstance(provider, FakeProvider)
    assert provider.name == "fake"


def test_build_provider_raises_for_missing_type() -> None:
    with pytest.raises(ConfigError):
        build_provider({"model": "deepseek-chat"})


def test_build_provider_raises_for_unknown_type() -> None:
    with pytest.raises(ConfigError):
        build_provider({"type": "imaginary"})


# --- numeric config validation (Phase D provider hardening) ----------------- #


def test_build_fake_rejects_bad_fail_rate() -> None:
    with pytest.raises(ConfigError, match="must be a number"):
        build_provider({"type": "fake", "fail_rate": "high"})
    with pytest.raises(ConfigError, match="out of range"):
        build_provider({"type": "fake", "fail_rate": 2.0})


def test_build_fake_rejects_non_int_seed() -> None:
    with pytest.raises(ConfigError, match="must be an integer"):
        build_provider({"type": "fake", "seed": 1.5})


def test_build_deepseek_rejects_bad_temperature() -> None:
    # read_float runs while building the config, before the API-key check, so this
    # is a clean ConfigError regardless of whether DEEPSEEK_API_KEY is set.
    with pytest.raises(ConfigError, match="must be a number"):
        build_provider({"type": "deepseek", "temperature": "hot"})


def test_build_deepseek_rejects_nonpositive_timeout() -> None:
    with pytest.raises(ConfigError, match="out of range"):
        build_provider({"type": "deepseek", "timeout_seconds": 0})


def test_build_ollama_rejects_top_p_out_of_range() -> None:
    with pytest.raises(ConfigError, match="out of range"):
        build_provider({"type": "ollama", "top_p": 2.0})


def test_build_provider_accepts_valid_numbers() -> None:
    # Ollama needs no API key, so a valid numeric config builds end to end.
    provider = build_provider(
        {"type": "ollama", "temperature": 0.7, "top_p": 0.9, "timeout_seconds": 30}
    )
    assert provider.name == "ollama"
