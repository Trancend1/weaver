"""OpenAI-compatible chat-completions provider (the `openai_chat` protocol).

A single, brand-free transport for any OpenAI-compatible `/chat/completions`
endpoint — DeepSeek, OpenRouter, Groq, Together, a local Ollama `/v1`, or any
other compatible server. The endpoint, key env-var name, and model are all
configured per connection (ADR 018); nothing here is tied to a vendor.
"""

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
from weaver.providers.types import Completion, TranslationRequest, TranslationResponse

DEFAULT_TEMPERATURE = 0.3
DEFAULT_TIMEOUT_SECONDS = 180.0


@dataclass(frozen=True)
class OpenAIChatConfig:
    """Configuration for `OpenAIChatProvider`.

    `base_url`, `api_key_env` (which env var holds the key), `model`, and `name`
    (for logs / status) are all required per connection — there is no vendor
    default. The same engine serves every OpenAI-compatible endpoint.
    """

    model: str = ""
    base_url: str = ""
    temperature: float = DEFAULT_TEMPERATURE
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    api_key_env: str = ""
    name: str = "openai_chat"


class OpenAIChatProvider(LLMProvider):
    """OpenAI-compatible chat-completions client for any configured endpoint."""

    name = "openai_chat"

    def __init__(
        self,
        *,
        config: OpenAIChatConfig | None = None,
        api_key: str | None = None,
        client: Any | None = None,
    ) -> None:
        self._config = config or OpenAIChatConfig()
        self.name = self._config.name
        api_key_env = self._config.api_key_env
        resolved_key = api_key if api_key is not None else os.environ.get(api_key_env or "")
        if client is None and not resolved_key:
            raise ProviderUnavailable(
                f"{api_key_env or 'API key env var'} is not set. "
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

    def complete(
        self, prompt: str, *, system: str | None = None, max_output_tokens: int
    ) -> Completion:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        response = self._chat_completion(messages=messages, max_tokens=max_output_tokens)
        content = _extract_content(response)
        return Completion(
            text=content,
            input_tokens=_usage(response, "prompt_tokens"),
            output_tokens=_usage(response, "completion_tokens"),
            raw_response=content,
        )

    def healthcheck(self) -> ProviderStatus:
        start = time.perf_counter()
        try:
            # This engine always requests response_format=json_object. json-mode-strict
            # OpenAI-compatible endpoints (e.g. Groq) reject any prompt that does not
            # contain the word "json", so the probe must mention it; otherwise the
            # healthcheck 400s and every such endpoint looks unhealthy.
            self._chat_completion(
                messages=[
                    {"role": "system", "content": "Health check. Reply with a small json object."},
                    {"role": "user", "content": 'Reply with {"status": "ok"} as json.'},
                ],
                max_tokens=16,
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
            raise _translate_openai_error(
                exc, provider_name=self.name, api_key_env=self._config.api_key_env
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
            "OpenAI-compatible response is missing `choices[0].message.content`. "
            "Likely cause: upstream returned an unexpected payload shape. "
            "Next command: rerun translation; if it persists, check the endpoint's status."
        ) from exc
    if not isinstance(content, str):
        raise ProviderResponseError(
            "OpenAI-compatible response content is not a string. "
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


def _translate_openai_error(
    exc: BaseException,
    *,
    provider_name: str = "openai_chat",
    api_key_env: str = "",
) -> Exception:
    display_name = provider_name or "OpenAI-compatible endpoint"
    env_hint = api_key_env or "the configured API key env var"
    name = type(exc).__name__
    message = str(exc) or name
    if name in {"APITimeoutError", "Timeout"}:
        return ProviderTimeout(
            f"{display_name} request timed out: {message}. "
            "Likely cause: network slow or upstream overloaded. "
            "Next command: rerun translation or raise `translation.timeout_seconds`."
        )
    if name in {"AuthenticationError", "PermissionDeniedError"}:
        return ProviderUnavailable(
            f"{display_name} auth failed: {message}. "
            f"Likely cause: invalid or revoked ${env_hint}. "
            f"Next command: regenerate the endpoint API key and update ${env_hint}."
        )
    if name in {"NotFoundError", "NotFound"}:
        return ProviderResponseError(
            f"{display_name} model not found: {message}. "
            "Likely cause: the configured `model` is misspelled or unavailable to this "
            "key/endpoint. "
            "Next command: check the connection's model against the endpoint's models."
        )
    if name in {"APIConnectionError", "ConnectionError"}:
        return ProviderUnavailable(
            f"{display_name} unreachable: {message}. "
            "Likely cause: DNS or network outage. "
            "Next command: check network connectivity, then rerun."
        )
    if name == "RateLimitError":
        return ProviderTimeout(
            f"{display_name} rate limit hit: {message}. "
            "Likely cause: too many concurrent requests. "
            "Next command: wait and rerun; reduce concurrency in `project.toml`."
        )
    return ProviderResponseError(
        f"{display_name} call failed ({name}): {message}. "
        "Likely cause: upstream returned an unexpected error. "
        "Next command: rerun translation; check endpoint status if it persists."
    )
