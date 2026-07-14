"""Provider registry and factory.

``build_provider()`` is the single entry point CLI/services use to instantiate
an ``LLMProvider`` from the parsed ``[provider]`` block (ADR 018 D1).

There is **one real transport** in Weaver: ``openai_chat``, the OpenAI-compatible
``/chat/completions`` client in :mod:`weaver.providers.openai_chat`. The
``fake`` engine exists for tests. The legacy brand ``type`` labels
(``deepseek``, ``gemini``, ``ollama``) survive only as a migration shim that
maps a pre-0.7.2 ``[provider]`` block onto the protocol-first config (D6). No
new project uses those labels — new configs speak in protocol + connection.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from typing import Any

from weaver.core.secret_store import load_secrets
from weaver.errors import ConfigError
from weaver.providers.base import LLMProvider
from weaver.providers.config_values import read_float, read_int
from weaver.providers.fake import FakeProvider
from weaver.providers.openai_chat import (
    OpenAIChatConfig,
    OpenAIChatProvider,
)

ProviderFactory = Callable[[Mapping[str, Any]], LLMProvider]

PROTOCOL_OPENAI_CHAT = "openai_chat"
PROTOCOL_FAKE = "fake"

# Legacy brand `type` → openai_chat defaults (ADR 018 D6). ``gemini`` and
# ``ollama`` are routed through their OpenAI-compatible endpoints (see ADR 018
# §5.3); the native ``google-generativeai`` / ``/api/generate`` clients are
# gone. No new project uses these labels.
_LEGACY_DEFAULTS: dict[str, dict[str, str]] = {
    "deepseek": {
        "protocol": PROTOCOL_OPENAI_CHAT,
        "model": "deepseek-chat",
        "base_url": "https://api.deepseek.com",
        "api_key_env": "DEEPSEEK_API_KEY",
    },
    "gemini": {
        "protocol": PROTOCOL_OPENAI_CHAT,
        "model": "gemini-1.5-flash",
        # Google's OpenAI-compatible surface lives under /v1beta/openai
        # (ADR 018 §5.3); bare /v1beta has no /chat/completions route.
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "api_key_env": "GEMINI_API_KEY",
    },
    "ollama": {
        "protocol": PROTOCOL_OPENAI_CHAT,
        "model": "qwen3:14b",
        "base_url": "http://localhost:11434/v1",
        "api_key_env": "",
    },
    "fake": {
        "protocol": PROTOCOL_FAKE,
        "model": "fake-1",
    },
}

_REGISTRY: dict[str, ProviderFactory] = {}


def register_provider(name: str, factory: ProviderFactory) -> None:
    """Register a provider factory under ``name``. Last writer wins."""

    _REGISTRY[name] = factory


def known_provider_types() -> list[str]:
    """Return the set of brand ``type`` names the registry accepts.

    Includes the legacy brand aliases (so existing ``[provider] type = ...``
    rows still render in the cockpit) plus the modern engine names. The
    underlying transport is always ``openai_chat`` for non-fake projects.
    """

    return sorted(set(_REGISTRY) | set(_LEGACY_DEFAULTS) | {"custom"})


def known_protocols() -> list[str]:
    """Return supported provider transport protocol ids."""

    return [PROTOCOL_OPENAI_CHAT, PROTOCOL_FAKE]


def normalize_provider_config(config: Mapping[str, Any]) -> dict[str, Any]:
    """Return config normalized to free-form ``type`` + explicit ``protocol``.

    Legacy built-in provider types are projected to ``openai_chat`` with
    their default endpoint/model/key-env. User-supplied fields always win
    over defaults. The original ``type`` is preserved as the engine name
    (ADR 018 D6), so a legacy-brand project keeps recording its real brand
    (``deepseek``/``gemini``/``ollama``) in attempt history (audit A3).
    """

    provider_type = _clean(config.get("type"))
    legacy = _LEGACY_DEFAULTS.get(provider_type or "")
    normalized: dict[str, Any] = dict(legacy or {})
    for key, value in config.items():
        if _clean(value) is not None:
            normalized[key] = value
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


def _build_openai_chat(config: Mapping[str, Any]) -> LLMProvider:
    base_url = _required(config, "base_url", protocol=PROTOCOL_OPENAI_CHAT)
    model = _required(config, "model", protocol=PROTOCOL_OPENAI_CHAT)
    # ``api_key_env`` is optional — empty string means the endpoint is keyless
    # (e.g. local Ollama on :11434/v1). A non-empty name still requires a
    # value to be set in the shell env / secret store, which the provider
    # itself enforces at __init__ time.
    api_key_env = _clean(config.get("api_key_env")) or ""
    return OpenAIChatProvider(
        config=OpenAIChatConfig(
            model=model,
            base_url=base_url,
            temperature=read_float(
                config, "temperature", OpenAIChatConfig.temperature, minimum=0.0
            ),
            timeout_seconds=read_float(
                config, "timeout_seconds", OpenAIChatConfig.timeout_seconds, exclusive_minimum=0.0
            ),
            api_key_env=api_key_env,
            name=_clean(config.get("type")) or "openai_chat",
        ),
        api_key=_resolve_key_value(api_key_env),
    )


def _resolve_key_value(api_key_env: str) -> str | None:
    """Resolve the key value for ``api_key_env``: shell env first, secret store second.

    ``apply_secrets_to_env`` only runs at process startup, so a key saved to the
    secret store from a running cockpit (Add connection / Secrets page) would be
    invisible to ``os.environ`` until restart. Reading the store here — exactly like
    the Test-connection probe does — makes a freshly saved or rotated key take
    effect on the next provider build. Shell env always wins; ``None`` lets the
    provider fall through to its own missing-key guard (clear error, never silent).
    """

    if not api_key_env:
        return None
    return os.environ.get(api_key_env) or load_secrets().get(api_key_env) or None


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
register_provider("custom", _build_custom)
