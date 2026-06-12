"""OllamaProvider unit tests via httpx MockTransport."""

from __future__ import annotations

import json

import httpx
import pytest

from weaver.errors import ProviderResponseError, ProviderTimeout, ProviderUnavailable
from weaver.providers.ollama import OllamaConfig, OllamaProvider
from weaver.providers.types import Completion, TranslationContext, TranslationRequest


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
        provider_model="qwen3:14b",
    )


def _client(handler):
    transport = httpx.MockTransport(handler)
    return httpx.Client(transport=transport)


def test_ollama_translate_happy_path_returns_translation_and_tokens() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/generate"
        body = json.loads(request.content)
        assert body["stream"] is False
        assert "format" not in body
        return httpx.Response(
            200,
            json={
                "response": '{"translation": "Test", "notes": [], "uncertain_terms": []}',
                "prompt_eval_count": 100,
                "eval_count": 25,
            },
        )

    provider = OllamaProvider(
        config=OllamaConfig(base_url="http://localhost:11434"),
        client=_client(handler),
    )

    response = provider.translate(_request())

    assert response.translation == "Test"
    assert response.input_tokens == 100
    assert response.output_tokens == 25


def test_ollama_translate_recovers_via_repair_prompt() -> None:
    responses = iter(
        [
            httpx.Response(200, json={"response": "not json"}),
            httpx.Response(
                200,
                json={
                    "response": '{"translation": "Repaired", "notes": [], "uncertain_terms": []}'
                },
            ),
        ]
    )

    def handler(_: httpx.Request) -> httpx.Response:
        return next(responses)

    provider = OllamaProvider(client=_client(handler))

    response = provider.translate(_request())

    assert response.translation == "Repaired"


def test_ollama_translate_maps_connection_error_to_unavailable() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    provider = OllamaProvider(client=_client(handler))

    with pytest.raises(ProviderUnavailable):
        provider.translate(_request())


def test_ollama_translate_maps_timeout_to_provider_timeout() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("read timeout")

    provider = OllamaProvider(client=_client(handler))

    with pytest.raises(ProviderTimeout):
        provider.translate(_request())


def test_ollama_translate_maps_http_500_to_response_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "internal"})

    provider = OllamaProvider(client=_client(handler))

    with pytest.raises(ProviderResponseError):
        provider.translate(_request())


def test_ollama_healthcheck_uses_tags_endpoint() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(200, json={"models": []})

    provider = OllamaProvider(client=_client(handler))

    status = provider.healthcheck()

    assert status.healthy is True
    assert calls == ["/api/tags"]


def test_ollama_healthcheck_reports_unhealthy_on_connection_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("daemon down")

    provider = OllamaProvider(client=_client(handler))

    status = provider.healthcheck()

    assert status.healthy is False
    assert status.message is not None


def test_ollama_complete_returns_text_and_usage() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"response": '{"target": "cat"}', "prompt_eval_count": 7, "eval_count": 2},
        )

    provider = OllamaProvider(config=OllamaConfig(), client=_client(handler))

    out = provider.complete("p json", system="SYS", max_output_tokens=16)

    assert isinstance(out, Completion)
    assert out.text == '{"target": "cat"}'
    assert (out.input_tokens, out.output_tokens) == (7, 2)
    payload = seen["payload"]
    assert isinstance(payload, dict)
    assert payload["prompt"] == "SYS\n\np json"
    assert payload["options"]["num_predict"] == 16
