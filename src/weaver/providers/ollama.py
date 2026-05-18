"""Local Ollama provider via HTTP `/api/generate`."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

import httpx

from weaver.errors import (
    ProviderResponseError,
    ProviderTimeout,
    ProviderUnavailable,
)
from weaver.providers.base import LLMProvider, ProviderStatus
from weaver.providers.parser import parse_response
from weaver.providers.prompts import load_repair_prompt, load_system_prompt, render_user_message
from weaver.providers.types import TranslationRequest, TranslationResponse

DEFAULT_BASE_URL = "http://localhost:11434"
DEFAULT_MODEL = "qwen3:14b"
DEFAULT_TEMPERATURE = 0.3
DEFAULT_TOP_P = 0.9


@dataclass(frozen=True)
class OllamaConfig:
    """Configuration for `OllamaProvider`."""

    model: str = DEFAULT_MODEL
    base_url: str = DEFAULT_BASE_URL
    temperature: float = DEFAULT_TEMPERATURE
    top_p: float = DEFAULT_TOP_P
    timeout_seconds: float = 180.0


class OllamaProvider(LLMProvider):
    """HTTP client for a locally-hosted Ollama daemon."""

    name = "ollama"

    def __init__(
        self,
        *,
        config: OllamaConfig | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._config = config or OllamaConfig()
        self._client = client or httpx.Client(timeout=self._config.timeout_seconds)
        self._owns_client = client is None

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
                input_tokens=_usage(first, "prompt_eval_count"),
                output_tokens=_usage(first, "eval_count"),
            )
        except Exception:
            repair_prompt = f"{prompt}\n\n{first_text}\n\n{load_repair_prompt()}"
            repair = self._generate(repair_prompt)
            repair_text = _extract_text(repair)
            return parse_response(
                repair_text,
                input_tokens=_usage(repair, "prompt_eval_count"),
                output_tokens=_usage(repair, "eval_count"),
            )

    def healthcheck(self) -> ProviderStatus:
        start = time.perf_counter()
        url = f"{self._config.base_url.rstrip('/')}/api/tags"
        try:
            response = self._client.get(url)
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            return self._status(False, f"timeout: {exc}", start)
        except httpx.HTTPStatusError as exc:
            return self._status(
                False,
                f"HTTP {exc.response.status_code} from {url}",
                start,
            )
        except httpx.HTTPError as exc:
            return self._status(False, f"unreachable: {exc}", start)
        return self._status(True, None, start)

    def close(self) -> None:
        """Close the underlying HTTP client if we created it."""

        if self._owns_client:
            self._client.close()

    def _generate(self, prompt: str) -> dict[str, Any]:
        url = f"{self._config.base_url.rstrip('/')}/api/generate"
        payload = {
            "model": self._config.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": self._config.temperature,
                "top_p": self._config.top_p,
            },
        }
        try:
            response = self._client.post(url, json=payload)
            response.raise_for_status()
            return response.json()
        except httpx.TimeoutException as exc:
            raise ProviderTimeout(
                f"Ollama request timed out: {exc}. "
                "Likely cause: model loading or generation exceeded timeout. "
                "Next command: raise `translation.timeout_seconds` or use a smaller model."
            ) from exc
        except httpx.ConnectError as exc:
            raise ProviderUnavailable(
                f"Cannot reach Ollama at {self._config.base_url}: {exc}. "
                "Likely cause: Ollama daemon is not running. "
                "Next command: start Ollama (`ollama serve`), then rerun."
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise ProviderResponseError(
                f"Ollama returned HTTP {exc.response.status_code}: {exc.response.text}. "
                "Likely cause: model name unknown or request malformed. "
                "Next command: run `ollama list` and confirm the model is pulled."
            ) from exc
        except json.JSONDecodeError as exc:
            raise ProviderResponseError(
                f"Ollama response was not valid JSON: {exc}. "
                "Likely cause: streaming was enabled or upstream crashed mid-response. "
                "Next command: rerun translation."
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(
                f"Ollama HTTP error: {exc}. "
                "Likely cause: network or daemon error. "
                "Next command: check `ollama serve` logs, then rerun."
            ) from exc

    def _status(self, healthy: bool, message: str | None, start: float) -> ProviderStatus:
        latency_ms = int((time.perf_counter() - start) * 1000)
        return ProviderStatus(
            healthy=healthy,
            provider_name=self.name,
            model=self._config.model,
            message=message,
            latency_ms=latency_ms,
        )


def _extract_text(payload: dict[str, Any]) -> str:
    value = payload.get("response")
    if not isinstance(value, str) or not value:
        raise ProviderResponseError(
            "Ollama response is missing a non-empty `response` field. "
            "Likely cause: model produced empty output. "
            "Next command: rerun translation."
        )
    return value


def _usage(payload: dict[str, Any], key: str) -> int | None:
    value = payload.get(key)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
