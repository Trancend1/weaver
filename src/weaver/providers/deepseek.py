"""DeepSeek chat-completions provider (OpenAI-compatible API)."""

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

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"
DEFAULT_TEMPERATURE = 0.3
ENV_API_KEY = "DEEPSEEK_API_KEY"


@dataclass(frozen=True)
class DeepSeekConfig:
    """Configuration for `DeepSeekProvider`.

    The same provider class serves both the built-in ``deepseek`` endpoint and a
    generic ``custom`` OpenAI-compatible endpoint (ADR `0020`): ``base_url``,
    ``api_key_env`` (which env var holds the key), and ``name`` (for logs /
    status) are all configurable.
    """

    model: str = DEFAULT_MODEL
    base_url: str = DEFAULT_BASE_URL
    temperature: float = DEFAULT_TEMPERATURE
    timeout_seconds: float = 180.0
    api_key_env: str = ENV_API_KEY
    name: str = "deepseek"


class DeepSeekProvider(LLMProvider):
    """OpenAI-compatible chat-completions client (DeepSeek or custom endpoint)."""

    name = "deepseek"

    def __init__(
        self,
        *,
        config: DeepSeekConfig | None = None,
        api_key: str | None = None,
        client: Any | None = None,
    ) -> None:
        self._config = config or DeepSeekConfig()
        self.name = self._config.name
        api_key_env = self._config.api_key_env
        resolved_key = api_key if api_key is not None else os.environ.get(api_key_env)
        if client is None and not resolved_key:
            raise ProviderUnavailable(
                f"{api_key_env} environment variable is not set. "
                "Likely cause: API key missing from the environment / secret store. "
                f"Next command: set ${api_key_env} or run `weaver secrets set {api_key_env}`."
            )
        self._client = (
            client
            if client is not None
            else _build_openai_client(
                api_key=resolved_key or "",
                base_url=self._config.base_url,
                timeout_seconds=self._config.timeout_seconds,
            )
        )

    def translate(self, request: TranslationRequest) -> TranslationResponse:
        system_prompt = load_system_prompt()
        user_message = render_user_message(
            request.context, source_text=request.normalized_source_text
        )

        first = self._chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ]
        )
        first_content = _extract_content(first)
        try:
            return parse_response(
                first_content,
                input_tokens=_usage(first, "prompt_tokens"),
                output_tokens=_usage(first, "completion_tokens"),
            )
        except Exception:
            repair = self._chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                    {"role": "assistant", "content": first_content},
                    {"role": "user", "content": load_repair_prompt()},
                ]
            )
            repair_content = _extract_content(repair)
            return parse_response(
                repair_content,
                input_tokens=_usage(repair, "prompt_tokens"),
                output_tokens=_usage(repair, "completion_tokens"),
            )

    def healthcheck(self) -> ProviderStatus:
        start = time.perf_counter()
        try:
            self._chat_completion(
                messages=[
                    {"role": "system", "content": "ping"},
                    {"role": "user", "content": "ping"},
                ],
                max_tokens=1,
            )
        except ProviderUnavailable as exc:
            return self._status(False, str(exc), start)
        except ProviderTimeout as exc:
            return self._status(False, f"timeout: {exc}", start)
        except ProviderResponseError as exc:
            return self._status(False, f"response error: {exc}", start)
        return self._status(True, None, start)

    def _chat_completion(
        self,
        *,
        messages: list[dict[str, str]],
        max_tokens: int | None = None,
    ) -> Any:
        kwargs: dict[str, Any] = {
            "model": self._config.model,
            "messages": messages,
            "temperature": self._config.temperature,
            "response_format": {"type": "json_object"},
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        try:
            return self._client.chat.completions.create(**kwargs)
        except Exception as exc:
            raise _translate_openai_error(exc) from exc

    def _status(self, healthy: bool, message: str | None, start: float) -> ProviderStatus:
        latency_ms = int((time.perf_counter() - start) * 1000)
        return ProviderStatus(
            healthy=healthy,
            provider_name=self.name,
            model=self._config.model,
            message=message,
            latency_ms=latency_ms,
        )


def _build_openai_client(*, api_key: str, base_url: str, timeout_seconds: float) -> Any:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ProviderUnavailable(
            "`openai` package is not installed. "
            "Likely cause: provider dependencies were not installed. "
            "Next command: reinstall weaver to pull provider dependencies."
        ) from exc
    return OpenAI(api_key=api_key, base_url=base_url, timeout=timeout_seconds)


def _extract_content(completion: Any) -> str:
    try:
        choice = completion.choices[0]
        message = choice.message
        content = message.content
    except (AttributeError, IndexError) as exc:
        raise ProviderResponseError(
            "DeepSeek response is missing `choices[0].message.content`. "
            "Likely cause: upstream returned an unexpected payload shape. "
            "Next command: rerun translation; if it persists, check DeepSeek status."
        ) from exc
    if not isinstance(content, str):
        raise ProviderResponseError(
            "DeepSeek response content is not a string. "
            "Likely cause: upstream returned tool calls or null content. "
            "Next command: rerun translation."
        )
    return content


def _usage(completion: Any, key: str) -> int | None:
    usage = getattr(completion, "usage", None)
    if usage is None:
        return None
    value = getattr(usage, key, None)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _translate_openai_error(exc: BaseException) -> Exception:
    name = type(exc).__name__
    message = str(exc) or name
    if name in {"APITimeoutError", "Timeout"}:
        return ProviderTimeout(
            f"DeepSeek request timed out: {message}. "
            "Likely cause: network slow or upstream overloaded. "
            "Next command: rerun translation or raise `translation.timeout_seconds`."
        )
    if name in {"AuthenticationError", "PermissionDeniedError"}:
        return ProviderUnavailable(
            f"DeepSeek auth failed: {message}. "
            f"Likely cause: invalid or revoked ${ENV_API_KEY}. "
            f"Next command: regenerate the DeepSeek API key and update ${ENV_API_KEY}."
        )
    if name in {"APIConnectionError", "ConnectionError"}:
        return ProviderUnavailable(
            f"DeepSeek unreachable: {message}. "
            "Likely cause: DNS or network outage. "
            "Next command: check network connectivity, then rerun."
        )
    if name == "RateLimitError":
        return ProviderTimeout(
            f"DeepSeek rate limit hit: {message}. "
            "Likely cause: too many concurrent requests. "
            "Next command: wait and rerun; reduce concurrency in `project.toml`."
        )
    return ProviderResponseError(
        f"DeepSeek call failed ({name}): {message}. "
        "Likely cause: upstream returned an unexpected error. "
        "Next command: rerun translation; check DeepSeek status if it persists."
    )
