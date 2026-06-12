"""LLMProvider abstract base class and ProviderStatus type."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from weaver.providers.types import Completion, TranslationRequest, TranslationResponse


@dataclass(frozen=True)
class ProviderStatus:
    """Result of `LLMProvider.healthcheck()` for `weaver inspect --healthcheck`."""

    healthy: bool
    provider_name: str
    model: str
    message: str | None
    latency_ms: int | None


class LLMProvider(ABC):
    """Translation provider contract.

    All concrete providers must subclass this and set `name` to the
    canonical provider identifier (`fake`, `deepseek`, `gemini`, `ollama`).
    Implementations may raise any subclass of `weaver.errors.ProviderError`
    from `translate()`; `healthcheck()` must not raise — failures are
    reported via `ProviderStatus(healthy=False, message=...)`.
    """

    name: str

    @abstractmethod
    def translate(self, request: TranslationRequest) -> TranslationResponse:
        """Translate one segment via the upstream model."""

    @abstractmethod
    def healthcheck(self) -> ProviderStatus:
        """Probe upstream availability without translating real content."""

    @abstractmethod
    def complete(
        self, prompt: str, *, system: str | None = None, max_output_tokens: int
    ) -> Completion:
        """Return a raw text completion + token usage for an opaque prompt.

        Transport primitive only — it carries no domain knowledge. Callers build
        their own prompt and parse/validate the result in a service. Implementations
        may raise any `weaver.errors.ProviderError` subclass on failure.
        """
