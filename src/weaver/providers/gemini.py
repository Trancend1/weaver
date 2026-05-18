"""Google Gemini Flash provider via `google-generativeai`."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

from weaver.errors import (
    ProviderResponseError,
    ProviderTimeout,
    ProviderUnavailable,
)
from weaver.providers.base import LLMProvider, ProviderStatus
from weaver.providers.parser import parse_response
from weaver.providers.prompts import load_repair_prompt, load_system_prompt, render_user_message
from weaver.providers.types import TranslationRequest, TranslationResponse

DEFAULT_MODEL = "gemini-1.5-flash"
DEFAULT_TEMPERATURE = 0.3
ENV_API_KEY = "GEMINI_API_KEY"


@dataclass(frozen=True)
class GeminiConfig:
    """Configuration for `GeminiProvider`."""

    model: str = DEFAULT_MODEL
    temperature: float = DEFAULT_TEMPERATURE
    timeout_seconds: float = 180.0


class GeminiProvider(LLMProvider):
    """`google-generativeai` client targeting Gemini Flash."""

    name = "gemini"

    def __init__(
        self,
        *,
        config: GeminiConfig | None = None,
        api_key: str | None = None,
        client: Any | None = None,
    ) -> None:
        self._config = config or GeminiConfig()
        resolved_key = api_key if api_key is not None else os.environ.get(ENV_API_KEY)
        if client is None and not resolved_key:
            raise ProviderUnavailable(
                f"{ENV_API_KEY} environment variable is not set. "
                "Likely cause: Gemini API key missing from the shell environment. "
                f"Next command: set ${ENV_API_KEY} before running `weaver translate`."
            )
        self._client = (
            client
            if client is not None
            else _build_gemini_client(
                api_key=resolved_key or "",
                model=self._config.model,
                temperature=self._config.temperature,
            )
        )

    def translate(self, request: TranslationRequest) -> TranslationResponse:
        system_prompt = load_system_prompt()
        user_message = render_user_message(
            request.context, source_text=request.normalized_source_text
        )
        prompt = f"{system_prompt}\n\n{user_message}"

        first = self._generate(prompt)
        first_text = _extract_text(first)
        try:
            return parse_response(
                first_text,
                input_tokens=_usage(first, "prompt_token_count"),
                output_tokens=_usage(first, "candidates_token_count"),
            )
        except Exception:
            repair_prompt = f"{prompt}\n\n{first_text}\n\n{load_repair_prompt()}"
            repair = self._generate(repair_prompt)
            repair_text = _extract_text(repair)
            return parse_response(
                repair_text,
                input_tokens=_usage(repair, "prompt_token_count"),
                output_tokens=_usage(repair, "candidates_token_count"),
            )

    def healthcheck(self) -> ProviderStatus:
        start = time.perf_counter()
        try:
            self._generate("ping")
        except ProviderUnavailable as exc:
            return self._status(False, str(exc), start)
        except ProviderTimeout as exc:
            return self._status(False, f"timeout: {exc}", start)
        except ProviderResponseError as exc:
            return self._status(False, f"response error: {exc}", start)
        return self._status(True, None, start)

    def _generate(self, prompt: str) -> Any:
        try:
            return self._client.generate_content(prompt)
        except Exception as exc:
            raise _translate_gemini_error(exc) from exc

    def _status(self, healthy: bool, message: str | None, start: float) -> ProviderStatus:
        latency_ms = int((time.perf_counter() - start) * 1000)
        return ProviderStatus(
            healthy=healthy,
            provider_name=self.name,
            model=self._config.model,
            message=message,
            latency_ms=latency_ms,
        )


def _build_gemini_client(*, api_key: str, model: str, temperature: float) -> Any:
    from typing import cast

    try:
        import google.generativeai as _genai  # pyright: ignore[reportMissingTypeStubs]
    except ImportError as exc:
        raise ProviderUnavailable(
            "`google-generativeai` package is not installed. "
            "Likely cause: provider dependencies were not installed. "
            "Next command: reinstall weaver to pull provider dependencies."
        ) from exc
    genai = cast(Any, _genai)
    genai.configure(api_key=api_key)
    return genai.GenerativeModel(
        model_name=model,
        generation_config={
            "temperature": temperature,
            "response_mime_type": "application/json",
        },
    )


def _extract_text(response: Any) -> str:
    text = getattr(response, "text", None)
    if isinstance(text, str) and text:
        return text
    candidates = getattr(response, "candidates", None) or []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        parts = getattr(content, "parts", None) or []
        for part in parts:
            part_text = getattr(part, "text", None)
            if isinstance(part_text, str) and part_text:
                return part_text
    raise ProviderResponseError(
        "Gemini response did not include any text content. "
        "Likely cause: safety filter blocked the response or upstream returned empty payload. "
        "Next command: rerun translation; if it persists, check the source for flagged content."
    )


def _usage(response: Any, key: str) -> int | None:
    metadata = getattr(response, "usage_metadata", None)
    if metadata is None:
        return None
    value = getattr(metadata, key, None)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _translate_gemini_error(exc: BaseException) -> Exception:
    name = type(exc).__name__
    message = str(exc) or name
    if name in {"DeadlineExceeded", "Timeout", "TimeoutError"}:
        return ProviderTimeout(
            f"Gemini request timed out: {message}. "
            "Likely cause: network slow or upstream overloaded. "
            "Next command: rerun translation or raise `translation.timeout_seconds`."
        )
    if name in {"PermissionDenied", "Unauthenticated"}:
        return ProviderUnavailable(
            f"Gemini auth failed: {message}. "
            f"Likely cause: invalid or revoked ${ENV_API_KEY}. "
            f"Next command: regenerate the Gemini API key and update ${ENV_API_KEY}."
        )
    if name in {"ResourceExhausted", "TooManyRequests"}:
        return ProviderTimeout(
            f"Gemini rate limit hit: {message}. "
            "Likely cause: free-tier 15 req/min or 1M tokens/day exceeded. "
            "Next command: wait 60 seconds and rerun."
        )
    if name in {"ServiceUnavailable", "Unavailable", "ConnectionError"}:
        return ProviderUnavailable(
            f"Gemini unreachable: {message}. "
            "Likely cause: DNS, network, or upstream outage. "
            "Next command: check network connectivity, then rerun."
        )
    return ProviderResponseError(
        f"Gemini call failed ({name}): {message}. "
        "Likely cause: upstream returned an unexpected error. "
        "Next command: rerun translation; check Gemini status if it persists."
    )
