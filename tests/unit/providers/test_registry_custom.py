"""Tests for the generic custom OpenAI-compatible provider (ADR 018 D1/D6)."""

from __future__ import annotations

from pathlib import Path

import pytest

from weaver.core.secret_store import set_secret
from weaver.errors import ConfigError, ProviderUnavailable
from weaver.providers.openai_chat import OpenAIChatProvider
from weaver.providers.registry import (
    build_provider,
    known_protocols,
    known_provider_types,
    normalize_provider_config,
)


def test_known_provider_types_and_protocols_include_compatibility_values() -> None:
    types = known_provider_types()
    assert {"deepseek", "gemini", "ollama", "fake", "custom"} <= set(types)
    # One real transport + the test engine; the native protocols are gone
    # (ADR 018 D1). Legacy brand names survive as type aliases only.
    assert set(known_protocols()) == {"openai_chat", "fake"}


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


def test_build_custom_with_named_but_missing_key_value_is_unavailable(monkeypatch) -> None:
    # ``api_key_env`` is now optional (keyless endpoints). When the user does
    # name an env var, a missing value must still surface as a clear provider
    # error at __init__ time, never as a silent success.
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


def test_legacy_gemini_type_routes_through_openai_chat(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "sk-gemini")
    provider = build_provider({"type": "gemini"})
    # Transport is the unified openai_chat; the brand survives as the engine
    # name so attempt history records the real provider (audit A3).
    assert provider.name == "gemini"


@pytest.mark.parametrize("brand", ["deepseek", "gemini"])
def test_legacy_brand_is_preserved_as_engine_name(monkeypatch, brand: str) -> None:
    # Audit A3: normalize_provider_config must not clobber the legacy brand to
    # "custom" — new attempts on a legacy project record provider=<brand>.
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-x")
    monkeypatch.setenv("GEMINI_API_KEY", "sk-x")
    normalized = normalize_provider_config({"type": brand})
    assert normalized["type"] == brand
    assert build_provider({"type": brand}).name == brand


def test_legacy_gemini_shim_targets_openai_compatible_endpoint() -> None:
    # Google's OpenAI-compatible surface is /v1beta/openai (ADR 018 §5.3) —
    # bare /v1beta has no /chat/completions route, so the D6 shim must not
    # point there (v0.7.2 audit finding H2).
    normalized = normalize_provider_config({"type": "gemini"})
    assert normalized["base_url"] == "https://generativelanguage.googleapis.com/v1beta/openai"


def test_key_saved_only_in_secret_store_is_found_at_build_time(monkeypatch, tmp_path: Path) -> None:
    # A key saved from a *running* cockpit lands in secrets.toml but not in
    # os.environ (apply_secrets_to_env runs only at startup). The factory must
    # fall back to the store so the very next translate works without a
    # restart (v0.7.2 audit finding H1).
    monkeypatch.delenv("WEAVER_CONN_STOREONLY", raising=False)
    monkeypatch.setenv("WEAVER_SECRETS_PATH", str(tmp_path / "secrets.toml"))
    set_secret("WEAVER_CONN_STOREONLY", "sk-stored")

    provider = build_provider(
        {
            "type": "custom",
            "base_url": "https://api.example.com/v1",
            "model": "m",
            "api_key_env": "WEAVER_CONN_STOREONLY",
        }
    )

    assert provider.name == "custom"  # built — no ProviderUnavailable


def test_shell_env_wins_over_secret_store_at_build_time(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("WEAVER_SECRETS_PATH", str(tmp_path / "secrets.toml"))
    set_secret("WEAVER_CONN_BOTH", "sk-stored")
    monkeypatch.setenv("WEAVER_CONN_BOTH", "sk-shell")

    provider = build_provider(
        {
            "type": "custom",
            "base_url": "https://api.example.com/v1",
            "model": "m",
            "api_key_env": "WEAVER_CONN_BOTH",
        }
    )

    assert isinstance(provider, OpenAIChatProvider)
    assert provider._client.api_key == "sk-shell"  # noqa: SLF001 — asserting key precedence


def test_legacy_ollama_type_routes_to_local_keyless_openai_chat(monkeypatch) -> None:
    # Local Ollama has no key — the shim must pass an empty ``api_key_env``
    # and not raise at __init__ time. The OpenAI client is fed a dummy key
    # internally; the upstream is expected to ignore it.
    monkeypatch.delenv("WEAVER_TEST_OLLAMA_KEY", raising=False)
    provider = build_provider({"type": "ollama"})
    assert provider.name == "ollama"
