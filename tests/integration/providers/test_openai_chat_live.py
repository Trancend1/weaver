"""Live openai_chat integration test against DeepSeek (skipped without API key)."""

from __future__ import annotations

import os

import pytest

from weaver.providers.openai_chat import OpenAIChatConfig, OpenAIChatProvider
from weaver.providers.types import TranslationContext, TranslationRequest

pytestmark = pytest.mark.requires_cloud


def test_openai_chat_translate_with_real_api_key() -> None:
    if not os.environ.get("DEEPSEEK_API_KEY"):
        pytest.skip("DEEPSEEK_API_KEY not set")

    provider = OpenAIChatProvider(
        config=OpenAIChatConfig(
            model="deepseek-chat",
            base_url="https://api.deepseek.com",
            api_key_env="DEEPSEEK_API_KEY",
            name="deepseek",
        )
    )
    status = provider.healthcheck()
    if not status.healthy:
        pytest.skip(f"endpoint not available: {status.message}")

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
        provider_model="deepseek-chat",
    )
    response = provider.translate(request)

    assert response.translation
