"""Live Ollama test over the local `:11434/v1` surface (skipped without a daemon).

First user of the `requires_ollama` marker (declared since v0.7.2 with zero
usages). Like the Gemini live test it drives the shipped legacy-shim defaults so
a pass proves the keyless `openai_chat` path an offline suite cannot reach: no
`api_key_env`, so the provider must fall back to its dummy key instead of
raising `ProviderUnavailable`.
"""

from __future__ import annotations

import pytest

from weaver.providers.openai_chat import OpenAIChatConfig, OpenAIChatProvider
from weaver.providers.registry import normalize_provider_config
from weaver.providers.types import TranslationContext, TranslationRequest

pytestmark = pytest.mark.requires_ollama

OLLAMA_BASE_URL = "http://localhost:11434/v1"


def test_ollama_legacy_shim_translates_keyless_over_local_v1() -> None:
    normalized = normalize_provider_config({"type": "ollama"})
    assert normalized["base_url"] == OLLAMA_BASE_URL
    assert normalized["api_key_env"] == ""

    model = str(normalized["model"])
    provider = OpenAIChatProvider(
        config=OpenAIChatConfig(
            model=model,
            base_url=str(normalized["base_url"]),
            api_key_env="",
            name="ollama",
        )
    )

    # Opting into `-m requires_ollama` asserts the daemon is up and the default
    # model is pulled, so an unhealthy endpoint is a failure with the fix in the
    # message — not a skip that would let the exit criterion pass on nothing.
    status = provider.healthcheck()
    assert status.healthy, (
        f"ollama healthcheck failed for {model}: {status.message}. "
        f"Likely cause: daemon not running or model not pulled. "
        f"Next command: `ollama serve` then `ollama pull {model}`."
    )

    request = TranslationRequest(
        segment_id="seg-1",
        source_text="こんにちは。",
        normalized_source_text="こんにちは。",
        source_language="ja",
        target_language="en",
        context=TranslationContext(
            previous_segments=(),
            glossary_terms=(),
            honorific_policy="preserve",
        ),
        provider_model=model,
    )
    response = provider.translate(request)

    assert response.translation
    assert response.raw_response
    # Token usage is intentionally not asserted: local Ollama may report none
    # (`TranslationResponse.input_tokens` is documented as None for it).
