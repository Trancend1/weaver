"""Live Gemini integration test (skipped without API key)."""

from __future__ import annotations

import os

import pytest

from weaver.providers.gemini import GeminiProvider
from weaver.providers.types import TranslationContext, TranslationRequest

pytestmark = pytest.mark.requires_cloud


def test_gemini_translate_with_real_api_key() -> None:
    if not os.environ.get("GEMINI_API_KEY"):
        pytest.skip("GEMINI_API_KEY not set")

    provider = GeminiProvider()
    status = provider.healthcheck()
    if not status.healthy:
        pytest.skip(f"Gemini not available: {status.message}")

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
        provider_model="gemini-1.5-flash",
    )
    response = provider.translate(request)

    assert response.translation
