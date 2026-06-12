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
    ) -> None:
        if not 0.0 <= fail_rate <= 1.0:
            raise ValueError("fail_rate must be in [0.0, 1.0]")
        self._pattern = pattern
        self._fail_rate = fail_rate
        self._random = random.Random(seed)
        self._model = model
        self._completion = completion

    def translate(self, request: TranslationRequest) -> TranslationResponse:
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
        return TranslationResponse(
            translation=translation,
            notes=(),
            uncertain_terms=(),
            raw_response=raw,
            input_tokens=None,
            output_tokens=None,
        )

    def complete(
        self, prompt: str, *, system: str | None = None, max_output_tokens: int
    ) -> Completion:
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
