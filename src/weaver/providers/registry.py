"""Provider registry and factory.

`build_provider()` is the single entry point CLI/services use to instantiate
a concrete `LLMProvider` from the parsed `[provider]` block of
`project.toml`. Provider names map 1:1 to docs/PRD_v2.md §provider.type.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from weaver.errors import ConfigError
from weaver.providers.base import LLMProvider
from weaver.providers.config_values import read_float, read_int
from weaver.providers.deepseek import DeepSeekConfig, DeepSeekProvider
from weaver.providers.fake import FakeProvider
from weaver.providers.gemini import GeminiConfig, GeminiProvider
from weaver.providers.ollama import OllamaConfig, OllamaProvider

ProviderFactory = Callable[[Mapping[str, Any]], LLMProvider]

_REGISTRY: dict[str, ProviderFactory] = {}


def register_provider(name: str, factory: ProviderFactory) -> None:
    """Register a provider factory under `name`. Last writer wins."""

    _REGISTRY[name] = factory


def known_provider_types() -> list[str]:
    """Return registered provider type names, sorted (registry-driven validation)."""

    return sorted(_REGISTRY)


def build_provider(config: Mapping[str, Any]) -> LLMProvider:
    """Instantiate a provider from a parsed `[provider]` TOML block.

    Args:
        config: Mapping with at minimum a `type` key. Additional keys
            (`model`, `base_url`, etc.) are passed through to the
            provider-specific factory.

    Returns:
        Concrete `LLMProvider` instance ready for `translate()`/`healthcheck()`.

    Raises:
        ConfigError: If `type` is missing or names an unknown provider.
    """

    provider_type = config.get("type")
    if not isinstance(provider_type, str) or not provider_type:
        raise ConfigError(
            "Provider configuration is missing `provider.type`. "
            "Likely cause: project.toml has no `[provider]` block or `type` field. "
            'Next command: edit project.toml and set `provider.type = "deepseek"` '
            "(or fake/gemini/ollama)."
        )
    factory = _REGISTRY.get(provider_type)
    if factory is None:
        known = ", ".join(sorted(_REGISTRY)) or "<none registered>"
        raise ConfigError(
            f"Unknown provider type `{provider_type}`. "
            f"Likely cause: typo in project.toml. Known providers: {known}. "
            "Next command: edit project.toml `[provider] type` to a known provider."
        )
    return factory(config)


def _build_fake(config: Mapping[str, Any]) -> LLMProvider:
    model = str(config.get("model", "fake-1"))
    pattern = str(config.get("pattern", "[FAKE] {source}"))
    fail_rate = read_float(config, "fail_rate", 0.0, minimum=0.0, maximum=1.0)
    seed = read_int(config, "seed", 0)
    return FakeProvider(pattern=pattern, fail_rate=fail_rate, seed=seed, model=model)


def _build_deepseek(config: Mapping[str, Any]) -> LLMProvider:
    return DeepSeekProvider(
        config=DeepSeekConfig(
            model=str(config.get("model", DeepSeekConfig.model)),
            base_url=str(config.get("base_url", DeepSeekConfig.base_url)),
            temperature=read_float(config, "temperature", DeepSeekConfig.temperature, minimum=0.0),
            timeout_seconds=read_float(
                config, "timeout_seconds", DeepSeekConfig.timeout_seconds, exclusive_minimum=0.0
            ),
        )
    )


def _build_gemini(config: Mapping[str, Any]) -> LLMProvider:
    return GeminiProvider(
        config=GeminiConfig(
            model=str(config.get("model", GeminiConfig.model)),
            temperature=read_float(config, "temperature", GeminiConfig.temperature, minimum=0.0),
            timeout_seconds=read_float(
                config, "timeout_seconds", GeminiConfig.timeout_seconds, exclusive_minimum=0.0
            ),
        )
    )


def _build_ollama(config: Mapping[str, Any]) -> LLMProvider:
    return OllamaProvider(
        config=OllamaConfig(
            model=str(config.get("model", OllamaConfig.model)),
            base_url=str(config.get("base_url", OllamaConfig.base_url)),
            temperature=read_float(config, "temperature", OllamaConfig.temperature, minimum=0.0),
            top_p=read_float(config, "top_p", OllamaConfig.top_p, minimum=0.0, maximum=1.0),
            timeout_seconds=read_float(
                config, "timeout_seconds", OllamaConfig.timeout_seconds, exclusive_minimum=0.0
            ),
        )
    )


def _build_custom(config: Mapping[str, Any]) -> LLMProvider:
    """Generic OpenAI-compatible endpoint (ADR `0020`).

    Reuses the OpenAI-compatible `DeepSeekProvider` engine but takes a
    user-supplied `base_url`, `model`, and `api_key_env` (the env var / secret
    name holding the key). The key value itself is never read from config.
    """

    base_url = str(config.get("base_url", "")).strip()
    if not base_url:
        raise ConfigError(
            "Custom provider requires `base_url`. "
            'Likely cause: [provider] base_url is missing for type = "custom". '
            "Next command: set the endpoint URL in project.toml or the cockpit."
        )
    api_key_env = str(config.get("api_key_env", "")).strip()
    if not api_key_env:
        raise ConfigError(
            "Custom provider requires `api_key_env`. "
            'Likely cause: [provider] api_key_env is missing for type = "custom". '
            "Next command: set the env-var name that holds the key (e.g. MY_API_KEY)."
        )
    model = str(config.get("model", "")).strip()
    if not model:
        raise ConfigError(
            "Custom provider requires `model`. "
            'Likely cause: [provider] model is missing for type = "custom". '
            "Next command: set the model id in project.toml or the cockpit."
        )
    return DeepSeekProvider(
        config=DeepSeekConfig(
            model=model,
            base_url=base_url,
            temperature=read_float(config, "temperature", DeepSeekConfig.temperature, minimum=0.0),
            timeout_seconds=read_float(
                config, "timeout_seconds", DeepSeekConfig.timeout_seconds, exclusive_minimum=0.0
            ),
            api_key_env=api_key_env,
            name="custom",
        )
    )


register_provider("fake", _build_fake)
register_provider("deepseek", _build_deepseek)
register_provider("gemini", _build_gemini)
register_provider("ollama", _build_ollama)
register_provider("custom", _build_custom)
