"""Live Ollama integration test (skipped in CI)."""

from __future__ import annotations

import pytest

from weaver.providers.ollama import OllamaProvider
from weaver.providers.types import TranslationContext, TranslationRequest

pytestmark = pytest.mark.requires_ollama


def test_ollama_translate_against_local_daemon() -> None:
    provider = OllamaProvider()
    try:
        status = provider.healthcheck()
        if not status.healthy:
            pytest.skip(f"Ollama not available: {status.message}")

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
            provider_model="qwen3:14b",
        )
        response = provider.translate(request)
        assert response.translation
    finally:
        provider.close()
