"""Tests for the generic custom OpenAI-compatible provider (ADR ``0020``)."""

from __future__ import annotations

import pytest

from weaver.errors import ConfigError
from weaver.providers.registry import build_provider, known_provider_types


def test_known_provider_types_includes_builtins_and_custom() -> None:
    types = known_provider_types()
    assert {"deepseek", "gemini", "ollama", "fake", "custom"} <= set(types)


def test_build_custom_success(monkeypatch) -> None:
    monkeypatch.setenv("MY_CUSTOM_KEY", "sk-x")
    provider = build_provider(
        {
            "type": "custom",
            "base_url": "https://api.example.com/v1",
            "model": "some-model",
            "api_key_env": "MY_CUSTOM_KEY",
        }
    )
    assert provider.name == "custom"


def test_build_custom_requires_base_url(monkeypatch) -> None:
    monkeypatch.setenv("MY_CUSTOM_KEY", "sk-x")
    with pytest.raises(ConfigError):
        build_provider({"type": "custom", "model": "m", "api_key_env": "MY_CUSTOM_KEY"})


def test_build_custom_requires_model(monkeypatch) -> None:
    monkeypatch.setenv("MY_CUSTOM_KEY", "sk-x")
    with pytest.raises(ConfigError):
        build_provider({"type": "custom", "base_url": "https://x", "api_key_env": "MY_CUSTOM_KEY"})


def test_build_custom_requires_api_key_env() -> None:
    with pytest.raises(ConfigError):
        build_provider({"type": "custom", "base_url": "https://x", "model": "m"})


def test_build_custom_missing_key_value_is_unavailable(monkeypatch) -> None:
    from weaver.errors import ProviderUnavailable

    monkeypatch.delenv("ABSENT_KEY", raising=False)
    with pytest.raises(ProviderUnavailable):
        build_provider(
            {
                "type": "custom",
                "base_url": "https://x",
                "model": "m",
                "api_key_env": "ABSENT_KEY",
            }
        )
