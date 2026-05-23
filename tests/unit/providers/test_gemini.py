"""GeminiProvider unit tests with a mocked GenerativeModel."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from weaver.errors import ProviderResponseError, ProviderTimeout, ProviderUnavailable
from weaver.providers import gemini as gemini_module
from weaver.providers.gemini import GeminiConfig, GeminiProvider
from weaver.providers.types import TranslationContext, TranslationRequest


def _request() -> TranslationRequest:
    return TranslationRequest(
        segment_id="seg-1",
        source_text="テスト",
        normalized_source_text="テスト",
        source_language="ja",
        target_language="en",
        context=TranslationContext(
            previous_segments=(),
            glossary_terms=(),
            honorific_policy="preserve",
        ),
        provider_model="gemini-1.5-flash",
    )


def _gemini_response(text: str, *, prompt_tokens: int = 30, output_tokens: int = 12) -> object:
    return SimpleNamespace(
        text=text,
        usage_metadata=SimpleNamespace(
            prompt_token_count=prompt_tokens,
            candidates_token_count=output_tokens,
        ),
    )


class _StubModel:
    def __init__(self, responses: list[object]) -> None:
        self._responses = list(responses)
        self.calls: list[str] = []

    def generate_content(self, prompt: str) -> object:
        self.calls.append(prompt)
        result = self._responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def test_gemini_translate_returns_translation_with_tokens() -> None:
    model = _StubModel(
        [_gemini_response('{"translation": "Hi", "notes": [], "uncertain_terms": []}')]
    )
    provider = GeminiProvider(client=model)

    response = provider.translate(_request())

    assert response.translation == "Hi"
    assert response.input_tokens == 30
    assert response.output_tokens == 12


def test_gemini_translate_recovers_via_repair_prompt() -> None:
    model = _StubModel(
        [
            _gemini_response("not json"),
            _gemini_response('{"translation": "Hi", "notes": [], "uncertain_terms": []}'),
        ]
    )
    provider = GeminiProvider(client=model)

    response = provider.translate(_request())

    assert response.translation == "Hi"
    assert len(model.calls) == 2


def test_gemini_translate_maps_rate_limit_to_timeout() -> None:
    class ResourceExhausted(Exception):
        pass

    model = _StubModel([ResourceExhausted("429")])
    provider = GeminiProvider(client=model)

    with pytest.raises(ProviderTimeout):
        provider.translate(_request())


def test_gemini_translate_maps_permission_denied_to_unavailable() -> None:
    class PermissionDenied(Exception):
        pass

    model = _StubModel([PermissionDenied("forbidden")])
    provider = GeminiProvider(client=model)

    with pytest.raises(ProviderUnavailable):
        provider.translate(_request())


def test_gemini_translate_maps_unknown_error_to_response_error() -> None:
    class WeirdError(Exception):
        pass

    model = _StubModel([WeirdError("weird")])
    provider = GeminiProvider(client=model)

    with pytest.raises(ProviderResponseError):
        provider.translate(_request())


def test_gemini_healthcheck_returns_healthy_status() -> None:
    model = _StubModel([_gemini_response('{"translation": "ok"}')])
    provider = GeminiProvider(client=model)

    status = provider.healthcheck()

    assert status.healthy is True
    assert status.provider_name == "gemini"


def test_gemini_constructor_without_client_or_env_raises(monkeypatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with pytest.raises(ProviderUnavailable):
        GeminiProvider(config=GeminiConfig())


def test_gemini_env_api_key_constant_is_the_env_var_name_not_a_literal_key() -> None:
    # Regression guard: ENV_API_KEY must hold the *name* of the env var
    # (e.g. "GEMINI_API_KEY"), never a literal API key value. A literal key
    # in source breaks `os.environ.get(ENV_API_KEY)` and leaks the credential
    # on any commit.
    assert gemini_module.ENV_API_KEY == "GEMINI_API_KEY"
