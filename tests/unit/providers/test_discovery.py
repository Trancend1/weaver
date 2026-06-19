"""Model discovery unit tests with a stubbed OpenAI-compatible client."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from weaver.errors import ProviderTimeout, ProviderUnavailable
from weaver.providers.discovery import DiscoveryResult, list_models


class _StubModels:
    def __init__(self, result: object) -> None:
        self._result = result

    def list(self) -> object:
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


class _StubClient:
    def __init__(self, result: object) -> None:
        self.models = _StubModels(result)


def _page(ids: list[str]) -> object:
    return SimpleNamespace(data=[SimpleNamespace(id=i) for i in ids])


def test_list_models_returns_sorted_unique_ids() -> None:
    client = _StubClient(_page(["b-model", "a-model", "b-model"]))

    result = list_models(base_url="https://x/v1", api_key="k", client=client)

    assert isinstance(result, DiscoveryResult)
    assert result.models == ("a-model", "b-model")
    assert result.count == 2
    assert result.latency_ms >= 0


def test_list_models_handles_dict_items() -> None:
    client = _StubClient(SimpleNamespace(data=[{"id": "m1"}, {"id": "m2"}]))

    result = list_models(base_url="https://x/v1", api_key="k", client=client)

    assert result.models == ("m1", "m2")


def test_list_models_empty_endpoint_yields_empty() -> None:
    client = _StubClient(_page([]))

    result = list_models(base_url="https://x/v1", api_key="k", client=client)

    assert result.models == ()
    assert result.count == 0


def test_auth_error_maps_to_unavailable() -> None:
    class AuthenticationError(Exception):
        pass

    client = _StubClient(AuthenticationError("invalid key"))

    with pytest.raises(ProviderUnavailable):
        list_models(base_url="https://x/v1", api_key="bad", client=client)


def test_timeout_maps_to_provider_timeout() -> None:
    class APITimeoutError(Exception):
        pass

    client = _StubClient(APITimeoutError("slow"))

    with pytest.raises(ProviderTimeout):
        list_models(base_url="https://x/v1", api_key="k", client=client)


def test_discovery_error_never_leaks_key() -> None:
    class AuthenticationError(Exception):
        pass

    secret = "sk-DO-NOT-LEAK"
    client = _StubClient(AuthenticationError("invalid key"))

    with pytest.raises(ProviderUnavailable) as excinfo:
        list_models(base_url="https://x/v1", api_key=secret, client=client)
    assert secret not in str(excinfo.value)
