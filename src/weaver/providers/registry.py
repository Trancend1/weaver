"""Provider registry and factory.

``build_provider()`` is the single entry point CLI/services use to instantiate
an ``LLMProvider`` from the parsed ``[provider]`` block. New config prefers a
free-form ``type`` label plus an explicit transport ``protocol``; legacy
built-in types are normalized for backward compatibility.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from weaver.errors import ConfigError
from weaver.providers.base import LLMProvider
from weaver.providers.config_values import read_float, read_int
from weaver.providers.deepseek import (
    DEFAULT_BASE_URL as DEEPSEEK_BASE_URL,
)
from weaver.providers.deepseek import (
    DEFAULT_MODEL as DEEPSEEK_MODEL,
)
from weaver.providers.deepseek import (
    ENV_API_KEY as DEEPSEEK_ENV,
)
from weaver.providers.deepseek import (
    DeepSeekConfig,
    DeepSeekProvider,
)
from weaver.providers.fake import FakeProvider
from weaver.providers.gemini import (
    DEFAULT_MODEL as GEMINI_MODEL,
)
from weaver.providers.gemini import (
    ENV_API_KEY as GEMINI_ENV,
)
from weaver.providers.gemini import (
    GeminiConfig,
    GeminiProvider,
)
from weaver.providers.ollama import (
    DEFAULT_BASE_URL as OLLAMA_BASE_URL,
)
from weaver.providers.ollama import (
    DEFAULT_MODEL as OLLAMA_MODEL,
)
from weaver.providers.ollama import (
    OllamaConfig,
    OllamaProvider,
)

ProviderFactory = Callable[[Mapping[str, Any]], LLMProvider]

PROTOCOL_OPENAI_CHAT = "openai_chat"
PROTOCOL_GEMINI_GENERATE = "gemini_generate"
PROTOCOL_OLLAMA_GENERATE = "ollama_generate"
PROTOCOL_FAKE = "fake"

_REGISTRY: dict[str, ProviderFactory] = {}


_LEGACY_DEFAULTS: dict[str, dict[str, str]] = {
    "deepseek": {
        "type": "custom",
        "protocol": PROTOCOL_OPENAI_CHAT,
        "model": DEEPSEEK_MODEL,
        "base_url": DEEPSEEK_BASE_URL,
        "api_key_env": DEEPSEEK_ENV,
    },
    "gemini": {
        "type": "custom",
        "protocol": PROTOCOL_GEMINI_GENERATE,
        "model": GEMINI_MODEL,
        "api_key_env": GEMINI_ENV,
    },
    "ollama": {
        "type": "custom",
        "protocol": PROTOCOL_OLLAMA_GENERATE,
        "model": OLLAMA_MODEL,
        "base_url": OLLAMA_BASE_URL,
    },
    "fake": {
        "type": "custom",
        "protocol": PROTOCOL_FAKE,
        "model": "fake-1",
    },
}


def register_provider(name: str, factory: ProviderFactory) -> None:
    """Register a provider factory under ``name``. Last writer wins."""

    _REGISTRY[name] = factory


def known_provider_types() -> list[str]:
    """Return legacy/runtime provider type names, sorted."""

    return sorted(_REGISTRY)


def known_protocols() -> list[str]:
    """Return supported provider transport protocol ids."""

    return [PROTOCOL_OPENAI_CHAT, PROTOCOL_GEMINI_GENERATE, PROTOCOL_OLLAMA_GENERATE, PROTOCOL_FAKE]


def normalize_provider_config(config: Mapping[str, Any]) -> dict[str, Any]:
    """Return config normalized to free-form ``type`` + explicit ``protocol``.

    Legacy built-in provider types are projected to ``type = custom`` with a
    protocol and defaults. User-supplied fields always win over defaults.
    """

    provider_type = _clean(config.get("type"))
    legacy = _LEGACY_DEFAULTS.get(provider_type or "")
    normalized: dict[str, Any] = dict(legacy or {})
    for key, value in config.items():
        if _clean(value) is not None:
            normalized[key] = value
    if legacy is not None:
        normalized["type"] = "custom"
    return normalized


def build_provider(config: Mapping[str, Any]) -> LLMProvider:
    """Instantiate a provider from a parsed ``[provider]`` TOML block."""

    normalized = normalize_provider_config(config)
    protocol = _clean(normalized.get("protocol"))
    provider_type = _clean(normalized.get("type"))

    if not protocol:
        factory = _REGISTRY.get(provider_type or "")
        if factory is not None:
            return factory(normalized)
        raise ConfigError(
            "Provider configuration is incomplete. "
            "Likely cause: [provider] type/protocol/model/base_url/api_key_env "
            "have not been set. "
            "Next command: open Config and set provider type, protocol, endpoint, "
            "model, and key env."
        )

    if protocol == PROTOCOL_OPENAI_CHAT:
        return _build_openai_chat(normalized)
    if protocol == PROTOCOL_GEMINI_GENERATE:
        return _build_gemini(normalized)
    if protocol == PROTOCOL_OLLAMA_GENERATE:
        return _build_ollama(normalized)
    if protocol == PROTOCOL_FAKE:
        return _build_fake(normalized)

    known = ", ".join(known_protocols())
    raise ConfigError(
        f"Unknown provider protocol `{protocol}`. "
        f"Likely cause: typo in project.toml. Known protocols: {known}. "
        "Next command: edit [provider] protocol to a supported value."
    )


def _build_fake(config: Mapping[str, Any]) -> LLMProvider:
    model = str(config.get("model", "fake-1"))
    pattern = str(config.get("pattern", "[FAKE] {source}"))
    completion = str(config.get("completion", '{"target": "[FAKE]"}'))
    fail_rate = read_float(config, "fail_rate", 0.0, minimum=0.0, maximum=1.0)
    seed = read_int(config, "seed", 0)
    return FakeProvider(
        pattern=pattern, fail_rate=fail_rate, seed=seed, model=model, completion=completion
    )


def _build_deepseek(config: Mapping[str, Any]) -> LLMProvider:
    legacy = normalize_provider_config({**config, "type": "deepseek"})
    return _build_openai_chat(legacy)


def _build_openai_chat(config: Mapping[str, Any]) -> LLMProvider:
    base_url = _required(config, "base_url", protocol=PROTOCOL_OPENAI_CHAT)
    api_key_env = _required(config, "api_key_env", protocol=PROTOCOL_OPENAI_CHAT)
    model = _required(config, "model", protocol=PROTOCOL_OPENAI_CHAT)
    return DeepSeekProvider(
        config=DeepSeekConfig(
            model=model,
            base_url=base_url,
            temperature=read_float(config, "temperature", DeepSeekConfig.temperature, minimum=0.0),
            timeout_seconds=read_float(
                config, "timeout_seconds", DeepSeekConfig.timeout_seconds, exclusive_minimum=0.0
            ),
            api_key_env=api_key_env,
            name=_clean(config.get("type")) or "custom",
        )
    )


def _build_gemini(config: Mapping[str, Any]) -> LLMProvider:
    return GeminiProvider(
        config=GeminiConfig(
            model=str(config.get("model") or GeminiConfig.model),
            temperature=read_float(config, "temperature", GeminiConfig.temperature, minimum=0.0),
            timeout_seconds=read_float(
                config, "timeout_seconds", GeminiConfig.timeout_seconds, exclusive_minimum=0.0
            ),
        )
    )


def _build_ollama(config: Mapping[str, Any]) -> LLMProvider:
    return OllamaProvider(
        config=OllamaConfig(
            model=str(config.get("model") or OllamaConfig.model),
            base_url=str(config.get("base_url") or OllamaConfig.base_url),
            temperature=read_float(config, "temperature", OllamaConfig.temperature, minimum=0.0),
            top_p=read_float(config, "top_p", OllamaConfig.top_p, minimum=0.0, maximum=1.0),
            timeout_seconds=read_float(
                config, "timeout_seconds", OllamaConfig.timeout_seconds, exclusive_minimum=0.0
            ),
        )
    )


def _build_custom(config: Mapping[str, Any]) -> LLMProvider:
    normalized = normalize_provider_config(
        {**config, "protocol": config.get("protocol") or PROTOCOL_OPENAI_CHAT}
    )
    return build_provider(normalized)


def _required(config: Mapping[str, Any], key: str, *, protocol: str) -> str:
    value = _clean(config.get(key))
    if value:
        return value
    raise ConfigError(
        f"Provider protocol `{protocol}` requires `{key}`. "
        f"Likely cause: [provider] {key} is missing. "
        "Next command: open Config and fill the provider endpoint settings."
    )


def _clean(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


register_provider("fake", _build_fake)
register_provider("deepseek", _build_deepseek)
register_provider("gemini", _build_gemini)
register_provider("ollama", _build_ollama)
register_provider("custom", _build_custom)
