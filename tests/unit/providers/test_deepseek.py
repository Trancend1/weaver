"""DeepSeekProvider unit tests with a mocked OpenAI-compatible client."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from weaver.errors import (
    ProviderResponseError,
    ProviderTimeout,
    ProviderUnavailable,
)
from weaver.providers.deepseek import DeepSeekConfig, DeepSeekProvider
from weaver.providers.types import (
    TranslationContext,
    TranslationRequest,
)


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
        provider_model="deepseek-chat",
    )


def _completion(content: str, *, prompt_tokens: int = 50, completion_tokens: int = 20) -> object:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        ),
    )


class _StubChatCompletions:
    def __init__(self, responses: list[object]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        result = self._responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class _StubClient:
    def __init__(self, completions: _StubChatCompletions) -> None:
        self.chat = SimpleNamespace(completions=completions)


def test_deepseek_translate_happy_path_returns_translation_and_tokens() -> None:
    completions = _StubChatCompletions(
        [_completion('{"translation": "Test", "notes": [], "uncertain_terms": []}')]
    )
    provider = DeepSeekProvider(client=_StubClient(completions))

    response = provider.translate(_request())

    assert response.translation == "Test"
    assert response.input_tokens == 50
    assert response.output_tokens == 20
    assert len(completions.calls) == 1
    assert completions.calls[0]["response_format"] == {"type": "json_object"}


def test_deepseek_translate_issues_repair_on_invalid_json() -> None:
    completions = _StubChatCompletions(
        [
            _completion("not json"),
            _completion('{"translation": "Test", "notes": [], "uncertain_terms": []}'),
        ]
    )
    provider = DeepSeekProvider(client=_StubClient(completions))

    response = provider.translate(_request())

    assert response.translation == "Test"
    assert len(completions.calls) == 2


def test_deepseek_translate_propagates_parse_error_after_repair() -> None:
    from weaver.errors import ParserError

    completions = _StubChatCompletions([_completion("not json"), _completion("still not json")])
    provider = DeepSeekProvider(client=_StubClient(completions))

    with pytest.raises(ParserError):
        provider.translate(_request())


def test_deepseek_translate_maps_timeout_error() -> None:
    class APITimeoutError(Exception):
        pass

    completions = _StubChatCompletions([APITimeoutError("upstream slow")])
    provider = DeepSeekProvider(client=_StubClient(completions))

    with pytest.raises(ProviderTimeout):
        provider.translate(_request())


def test_deepseek_translate_maps_auth_error_to_unavailable() -> None:
    class AuthenticationError(Exception):
        pass

    completions = _StubChatCompletions([AuthenticationError("invalid key")])
    provider = DeepSeekProvider(client=_StubClient(completions))

    with pytest.raises(ProviderUnavailable):
        provider.translate(_request())


def test_deepseek_translate_maps_generic_error_to_response_error() -> None:
    class RuntimeOops(Exception):
        pass

    completions = _StubChatCompletions([RuntimeOops("boom")])
    provider = DeepSeekProvider(client=_StubClient(completions))

    with pytest.raises(ProviderResponseError):
        provider.translate(_request())


def test_deepseek_healthcheck_returns_healthy_status() -> None:
    completions = _StubChatCompletions([_completion('{"translation": "ok"}')])
    provider = DeepSeekProvider(client=_StubClient(completions))

    status = provider.healthcheck()

    assert status.healthy is True
    assert status.provider_name == "deepseek"
    assert status.latency_ms is not None


def test_deepseek_healthcheck_reports_unhealthy_on_auth_failure() -> None:
    class AuthenticationError(Exception):
        pass

    completions = _StubChatCompletions([AuthenticationError("invalid key")])
    provider = DeepSeekProvider(client=_StubClient(completions))

    status = provider.healthcheck()

    assert status.healthy is False
    assert status.message is not None


def test_deepseek_constructor_without_client_or_env_raises(monkeypatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    with pytest.raises(ProviderUnavailable):
        DeepSeekProvider(config=DeepSeekConfig())
