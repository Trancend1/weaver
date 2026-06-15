"""On-demand model discovery for OpenAI-compatible endpoints (ADR 018 D3).

Probes ``GET /v1/models`` for a connection. This doubles as the **Test
Connection** check: a successful list proves connectivity + auth without needing a
model id, and yields the model count shown on the connection card. Discovery is
**always on demand** (explicit Test/Refresh POST) — never on render, never on a
background thread (Gate B1).

Discovery only ever *suggests*; the model field stays a free-form string
everywhere (ADR 018 D3). An endpoint that exposes no ``/models`` simply yields an
empty list — the user can still type any id.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from weaver.errors import ProviderResponseError, ProviderTimeout, ProviderUnavailable


@dataclass(frozen=True)
class DiscoveryResult:
    """Outcome of one model-discovery probe."""

    models: tuple[str, ...]
    latency_ms: int

    @property
    def count(self) -> int:
        return len(self.models)


def list_models(
    *,
    base_url: str,
    api_key: str,
    timeout_seconds: float = 60.0,
    client: Any | None = None,
) -> DiscoveryResult:
    """Probe an OpenAI-compatible endpoint for its model list.

    Args:
        base_url: The endpoint base URL (e.g. ``https://openrouter.ai/api/v1``).
        api_key: The raw key value (used only for this probe, never stored here).
        timeout_seconds: Per-request timeout.
        client: Optional pre-built client for testing.

    Returns:
        A :class:`DiscoveryResult` with sorted model ids and the probe latency.

    Raises:
        ProviderUnavailable / ProviderTimeout / ProviderResponseError: mapped from
        the upstream failure so the caller can render an inline status fragment.
    """

    probe_client = (
        client if client is not None else _build_client(base_url, api_key, timeout_seconds)
    )
    start = time.perf_counter()
    try:
        page = probe_client.models.list()
    except Exception as exc:  # noqa: BLE001 — mapped to a typed ProviderError below
        raise _map_error(exc) from exc
    latency_ms = int((time.perf_counter() - start) * 1000)
    return DiscoveryResult(models=_extract_ids(page), latency_ms=latency_ms)


def _extract_ids(page: Any) -> tuple[str, ...]:
    data = getattr(page, "data", page)
    ids: list[str] = []
    try:
        for item in data:
            model_id = getattr(item, "id", None)
            if model_id is None and isinstance(item, dict):
                model_id = item.get("id")
            if model_id:
                ids.append(str(model_id))
    except TypeError:
        return ()
    return tuple(sorted(set(ids)))


def _build_client(base_url: str, api_key: str, timeout_seconds: float) -> Any:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ProviderUnavailable(
            "`openai` package is not installed. "
            "Likely cause: provider dependencies were not installed. "
            "Next command: reinstall weaver to pull provider dependencies."
        ) from exc
    return OpenAI(api_key=api_key or "", base_url=base_url, timeout=timeout_seconds)


def _map_error(exc: BaseException) -> Exception:
    name = type(exc).__name__
    message = str(exc) or name
    if name in {"APITimeoutError", "Timeout"}:
        return ProviderTimeout(
            f"Model discovery timed out: {message}. "
            "Likely cause: network slow or endpoint overloaded. "
            "Next command: retry, or raise the connection timeout."
        )
    if name in {"AuthenticationError", "PermissionDeniedError"}:
        return ProviderUnavailable(
            f"Endpoint rejected the key: {message}. "
            "Likely cause: invalid or revoked API key. "
            "Next command: check the key and retry."
        )
    if name in {"APIConnectionError", "ConnectionError", "NotFoundError", "NotFound"}:
        return ProviderUnavailable(
            f"Could not reach the endpoint: {message}. "
            "Likely cause: wrong endpoint URL, or the host has no /models route. "
            "Next command: verify the Endpoint URL, then retry."
        )
    return ProviderResponseError(
        f"Discovery failed ({name}): {message}. "
        "Likely cause: the endpoint returned an unexpected error. "
        "Next command: retry; check the endpoint status if it persists."
    )
