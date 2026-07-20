"""Deterministic provider for development and CI."""

from __future__ import annotations

import json
import random
import time

from weaver.errors import ProviderResponseError
from weaver.providers.base import LLMProvider, ProviderStatus
from weaver.providers.types import Completion, TranslationRequest, TranslationResponse


class FakeProvider(LLMProvider):
    """Zero-network provider that returns deterministic translations.

    `pattern` is formatted with `{source}` (the segment's normalized source
    text); the default mirrors PROMPT_DESIGN.md §Model-Specific Notes.
    `fail_rate` injects synthetic failures for retry-path testing; a fixed
    `seed` keeps failure sampling deterministic across runs.
    `latency_seconds` simulates provider round-trip time (sleeps before every
    `translate`/`complete` call) so concurrency benchmarks can demonstrate
    real overlap between workers instead of measuring near-zero no-op calls.
    `report_token_usage` returns a deterministic character-based token
    estimate instead of `None`, so cost-accounting paths can be exercised
    without a live provider.
    """

    name = "fake"

    def __init__(
        self,
        *,
        pattern: str = "[FAKE] {source}",
        fail_rate: float = 0.0,
        seed: int = 0,
        model: str = "fake-1",
        completion: str = '{"target": "[FAKE]"}',
        latency_seconds: float = 0.0,
        report_token_usage: bool = False,
    ) -> None:
        if not 0.0 <= fail_rate <= 1.0:
            raise ValueError("fail_rate must be in [0.0, 1.0]")
        if latency_seconds < 0.0:
            raise ValueError("latency_seconds must be >= 0.0")
        self._pattern = pattern
        self._fail_rate = fail_rate
        self._random = random.Random(seed)
        self._model = model
        self._completion = completion
        self._latency_seconds = latency_seconds
        self._report_token_usage = report_token_usage

    def translate(self, request: TranslationRequest) -> TranslationResponse:
        if self._latency_seconds > 0.0:
            time.sleep(self._latency_seconds)
        if self._fail_rate > 0.0 and self._random.random() < self._fail_rate:
            raise ProviderResponseError(
                "FakeProvider synthetic failure. "
                "Likely cause: fail_rate>0 sampled this segment. "
                "Next command: rerun with FakeProvider(fail_rate=0) to disable injection."
            )

        translation = self._pattern.format(source=request.normalized_source_text)
        raw = json.dumps(
            {
                "translation": translation,
                "notes": [],
                "uncertain_terms": [],
            },
            ensure_ascii=False,
        )
        input_tokens = output_tokens = None
        if self._report_token_usage:
            # Synthetic fixture approximating a JP-input/EN-output length ratio;
            # deliberately not an accurate estimator and never used in production
            # cost accounting (see services/translation.py for the real one).
            input_tokens = max(1, len(request.normalized_source_text))
            output_tokens = max(1, len(translation) // 4)
        return TranslationResponse(
            translation=translation,
            notes=(),
            uncertain_terms=(),
            raw_response=raw,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    def complete(
        self, prompt: str, *, system: str | None = None, max_output_tokens: int
    ) -> Completion:
        if self._latency_seconds > 0.0:
            time.sleep(self._latency_seconds)
        if self._fail_rate > 0.0 and self._random.random() < self._fail_rate:
            raise ProviderResponseError(
                "FakeProvider synthetic failure. "
                "Likely cause: fail_rate>0 sampled this call. "
                "Next command: rerun with FakeProvider(fail_rate=0)."
            )
        return Completion(
            text=self._completion,
            input_tokens=None,
            output_tokens=None,
            raw_response=self._completion,
        )

    def healthcheck(self) -> ProviderStatus:
        start = time.perf_counter()
        latency_ms = int((time.perf_counter() - start) * 1000)
        return ProviderStatus(
            healthy=True,
            provider_name=self.name,
            model=self._model,
            message=None,
            latency_ms=latency_ms,
        )
