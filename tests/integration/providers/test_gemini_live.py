"""Live Gemini test over Google's OpenAI-compatible surface (skipped without a key).

The `…/v1beta/openai` base_url landed as an unverified fix in the v0.7.2
post-release audit (ADR 018 §5.3) — bare `…/v1beta` has no `/chat/completions`
route. This test is the first thing that exercises it against a live key, so it
drives everything from `normalize_provider_config` rather than test-local
constants: a pass proves the *shipped* legacy-shim endpoint and default model,
not a guess.
"""

from __future__ import annotations

import os

import pytest

from weaver.providers.openai_chat import OpenAIChatConfig, OpenAIChatProvider
from weaver.providers.registry import normalize_provider_config
from weaver.providers.types import TranslationContext, TranslationRequest

pytestmark = pytest.mark.requires_cloud

GEMINI_OPENAI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"


def test_gemini_legacy_shim_translates_over_v1beta_openai() -> None:
    if not os.environ.get("GEMINI_API_KEY"):
        pytest.skip("GEMINI_API_KEY not set")

    normalized = normalize_provider_config({"type": "gemini"})
    assert normalized["base_url"] == GEMINI_OPENAI_BASE_URL
    assert normalized["api_key_env"] == "GEMINI_API_KEY"

    provider = OpenAIChatProvider(
        config=OpenAIChatConfig(
            model=str(normalized["model"]),
            base_url=str(normalized["base_url"]),
            api_key_env=str(normalized["api_key_env"]),
            name="gemini",
        )
    )

    # Unhealthy here is a failure, not a skip: the key is present, so the run was
    # opted into. A retired default model or a wrong base_url must be visible
    # (CLAUDE.md §4.3 gate 5), not silently swallowed as "environment missing".
    status = provider.healthcheck()
    assert status.healthy, f"gemini healthcheck failed for {normalized['model']}: {status.message}"

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
        provider_model=str(normalized["model"]),
    )
    response = provider.translate(request)

    assert response.translation
    # Gemini reports usage, so this also proves the M3 token-accounting path on a
    # real cloud response rather than only on the fake provider.
    assert response.input_tokens is not None
    assert response.output_tokens is not None
