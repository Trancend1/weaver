"""Provider registry tests."""

from __future__ import annotations

import pytest

from weaver.errors import ConfigError
from weaver.providers import build_provider
from weaver.providers.fake import FakeProvider


def test_build_provider_dispatches_to_fake() -> None:
    provider = build_provider({"type": "fake", "model": "fake-1"})

    assert isinstance(provider, FakeProvider)
    assert provider.name == "fake"


def test_build_provider_raises_for_missing_type() -> None:
    with pytest.raises(ConfigError):
        build_provider({"model": "deepseek-chat"})


def test_build_provider_raises_for_unknown_type() -> None:
    with pytest.raises(ConfigError):
        build_provider({"type": "imaginary"})
