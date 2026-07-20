"""FakeProvider unit tests covering determinism, pattern, fail rate, healthcheck."""

from __future__ import annotations

import time

import pytest

from weaver.errors import ProviderResponseError
from weaver.providers.fake import FakeProvider
from weaver.providers.types import (
    Completion,
    TranslationContext,
    TranslationRequest,
)


def test_fake_complete_is_deterministic_and_parseable() -> None:
    provider = FakeProvider(completion='{"target": "[FAKE]"}')
    out = provider.complete("any prompt mentioning json", max_output_tokens=64)
    assert isinstance(out, Completion)
    assert out.text == '{"target": "[FAKE]"}'
    assert out.input_tokens is None and out.output_tokens is None
    # deterministic across calls
    assert provider.complete("other", max_output_tokens=8).text == '{"target": "[FAKE]"}'


def _request(source: str = "テスト") -> TranslationRequest:
    return TranslationRequest(
        segment_id="seg-1",
        source_text=source,
        normalized_source_text=source,
        source_language="ja",
        target_language="en",
        context=TranslationContext(
            previous_segments=(),
            glossary_terms=(),
            honorific_policy="preserve",
        ),
        provider_model="fake-1",
    )


def test_fake_provider_default_pattern_returns_marker_translation() -> None:
    provider = FakeProvider()

    response = provider.translate(_request("こんにちは"))

    assert response.translation == "[FAKE] こんにちは"
    assert response.notes == ()
    assert response.uncertain_terms == ()
    assert response.input_tokens is None
    assert response.output_tokens is None


def test_fake_provider_custom_pattern_applies_to_source() -> None:
    provider = FakeProvider(pattern="TRANSLATED: {source}")

    response = provider.translate(_request("foo"))

    assert response.translation == "TRANSLATED: foo"


def test_fake_provider_is_deterministic_for_same_seed() -> None:
    a = FakeProvider(fail_rate=0.5, seed=42)
    b = FakeProvider(fail_rate=0.5, seed=42)

    a_failures = _count_failures(a, attempts=20)
    b_failures = _count_failures(b, attempts=20)

    assert a_failures == b_failures


def test_fake_provider_fail_rate_zero_never_fails() -> None:
    provider = FakeProvider(fail_rate=0.0, seed=7)

    failures = _count_failures(provider, attempts=50)

    assert failures == 0


def test_fake_provider_rejects_invalid_fail_rate() -> None:
    with pytest.raises(ValueError):
        FakeProvider(fail_rate=1.5)


def test_fake_provider_healthcheck_reports_healthy() -> None:
    provider = FakeProvider()

    status = provider.healthcheck()

    assert status.healthy is True
    assert status.provider_name == "fake"
    assert status.message is None
    assert status.latency_ms is not None


def _count_failures(provider: FakeProvider, *, attempts: int) -> int:
    failures = 0
    for _ in range(attempts):
        try:
            provider.translate(_request())
        except ProviderResponseError:
            failures += 1
    return failures


def test_latency_seconds_delays_translate() -> None:
    provider = FakeProvider(latency_seconds=0.05)
    start = time.perf_counter()
    provider.translate(_request())
    assert time.perf_counter() - start >= 0.05


def test_latency_seconds_defaults_to_zero() -> None:
    provider = FakeProvider()
    start = time.perf_counter()
    provider.translate(_request())
    assert time.perf_counter() - start < 0.05


def test_negative_latency_rejected() -> None:
    with pytest.raises(ValueError, match="latency_seconds"):
        FakeProvider(latency_seconds=-1.0)


def test_synthetic_usage_reported_when_enabled() -> None:
    provider = FakeProvider(report_token_usage=True)
    response = provider.translate(_request())
    assert response.input_tokens is not None
    assert response.output_tokens is not None
    assert response.input_tokens > 0


def test_usage_is_none_by_default() -> None:
    response = FakeProvider().translate(_request())
    assert response.input_tokens is None
    assert response.output_tokens is None
