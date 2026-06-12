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
    Completion,
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


def test_deepseek_complete_returns_text_and_usage() -> None:
    completions = _StubChatCompletions(
        [_completion('{"target": "Demon King"}', prompt_tokens=11, completion_tokens=3)]
    )
    provider = DeepSeekProvider(client=_StubClient(completions))

    out = provider.complete("return json target", system="sys", max_output_tokens=64)

    assert isinstance(out, Completion)
    assert out.text == '{"target": "Demon King"}'
    assert (out.input_tokens, out.output_tokens) == (11, 3)
    sent = completions.calls[0]
    assert sent["max_tokens"] == 64
    messages = sent["messages"]
    assert isinstance(messages, list)
    assert messages[0] == {"role": "system", "content": "sys"}
    assert messages[-1]["content"] == "return json target"


def test_deepseek_complete_jsonmode_rejection_is_visible_not_silent() -> None:
    # A custom/OpenAI-compatible endpoint that rejects response_format=json_object
    # must surface as a provider error — never a silent fallback/empty success.
    class BadRequestError(Exception):
        pass

    completions = _StubChatCompletions(
        [BadRequestError("response_format json_object unsupported")]
    )
    provider = DeepSeekProvider(client=_StubClient(completions))

    with pytest.raises(ProviderResponseError):
        provider.complete("p mentioning json", max_output_tokens=8)


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


def test_deepseek_healthcheck_probe_mentions_json_for_json_mode() -> None:
    # The engine always requests response_format=json_object. json-mode-strict
    # OpenAI-compatible endpoints (e.g. Groq) reject prompts lacking the word
    # "json", so the healthcheck probe must include it.
    completions = _StubChatCompletions([_completion('{"status": "ok"}')])
    provider = DeepSeekProvider(client=_StubClient(completions))

    provider.healthcheck()

    assert len(completions.calls) == 1
    call = completions.calls[0]
    assert call["response_format"] == {"type": "json_object"}
    blob = " ".join(str(m["content"]) for m in call["messages"]).lower()  # type: ignore[union-attr]
    assert "json" in blob


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


def test_deepseek_maps_model_not_found_to_clear_error() -> None:
    class NotFoundError(Exception):
        pass

    completions = _StubChatCompletions([NotFoundError("model 'wrong-model' does not exist")])
    provider = DeepSeekProvider(client=_StubClient(completions))

    with pytest.raises(ProviderResponseError, match="model not found"):
        provider.translate(_request())


def test_deepseek_error_never_leaks_api_key() -> None:
    class AuthenticationError(Exception):
        pass

    secret = "sk-SUPER-SECRET-DO-NOT-LEAK"
    completions = _StubChatCompletions([AuthenticationError("invalid api key")])
    provider = DeepSeekProvider(
        config=DeepSeekConfig(), api_key=secret, client=_StubClient(completions)
    )

    status = provider.healthcheck()

    assert status.healthy is False
    assert secret not in (status.message or "")
