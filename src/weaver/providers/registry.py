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
from weaver.providers.deepseek import DeepSeekConfig, DeepSeekProvider
from weaver.providers.fake import FakeProvider
from weaver.providers.gemini import GeminiConfig, GeminiProvider
from weaver.providers.ollama import OllamaConfig, OllamaProvider

ProviderFactory = Callable[[Mapping[str, Any]], LLMProvider]

_REGISTRY: dict[str, ProviderFactory] = {}


def register_provider(name: str, factory: ProviderFactory) -> None:
    """Register a provider factory under `name`. Last writer wins."""

    _REGISTRY[name] = factory


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
    fail_rate = float(config.get("fail_rate", 0.0))
    seed = int(config.get("seed", 0))
    return FakeProvider(pattern=pattern, fail_rate=fail_rate, seed=seed, model=model)


def _build_deepseek(config: Mapping[str, Any]) -> LLMProvider:
    return DeepSeekProvider(
        config=DeepSeekConfig(
            model=str(config.get("model", DeepSeekConfig.model)),
            base_url=str(config.get("base_url", DeepSeekConfig.base_url)),
            temperature=float(config.get("temperature", DeepSeekConfig.temperature)),
            timeout_seconds=float(config.get("timeout_seconds", DeepSeekConfig.timeout_seconds)),
        )
    )


def _build_gemini(config: Mapping[str, Any]) -> LLMProvider:
    return GeminiProvider(
        config=GeminiConfig(
            model=str(config.get("model", GeminiConfig.model)),
            temperature=float(config.get("temperature", GeminiConfig.temperature)),
            timeout_seconds=float(config.get("timeout_seconds", GeminiConfig.timeout_seconds)),
        )
    )


def _build_ollama(config: Mapping[str, Any]) -> LLMProvider:
    return OllamaProvider(
        config=OllamaConfig(
            model=str(config.get("model", OllamaConfig.model)),
            base_url=str(config.get("base_url", OllamaConfig.base_url)),
            temperature=float(config.get("temperature", OllamaConfig.temperature)),
            top_p=float(config.get("top_p", OllamaConfig.top_p)),
            timeout_seconds=float(config.get("timeout_seconds", OllamaConfig.timeout_seconds)),
        )
    )


register_provider("fake", _build_fake)
register_provider("deepseek", _build_deepseek)
register_provider("gemini", _build_gemini)
register_provider("ollama", _build_ollama)
