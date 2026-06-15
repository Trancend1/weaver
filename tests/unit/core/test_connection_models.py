"""Workspace model-discovery cache tests (ADR 018 S3)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from weaver.core.connection_models import (
    CachedModels,
    clear_cached,
    get_cached,
    load_all,
    save_cached,
)


@pytest.fixture(autouse=True)
def isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEAVER_CONNECTION_MODELS_PATH", str(tmp_path / "connection_models.json"))


def test_missing_cache_is_empty() -> None:
    assert load_all() == {}
    assert get_cached("openrouter") is None


def test_save_then_get_round_trips() -> None:
    save_cached("openrouter", ["b-model", "a-model"])
    cached = get_cached("openrouter")
    assert cached is not None
    assert cached.models == ("b-model", "a-model")  # order preserved as given
    assert cached.fetched_at  # stamped


def test_save_replaces_previous_snapshot() -> None:
    save_cached("openrouter", ["old"])
    save_cached("openrouter", ["new1", "new2"])
    cached = get_cached("openrouter")
    assert cached is not None
    assert cached.models == ("new1", "new2")


def test_multiple_connections_are_independent() -> None:
    save_cached("openrouter", ["m1"])
    save_cached("local_ollama", ["q1", "q2"])
    everything = load_all()
    assert set(everything) == {"openrouter", "local_ollama"}
    assert everything["local_ollama"].models == ("q1", "q2")


def test_clear_removes_one() -> None:
    save_cached("openrouter", ["m1"])
    assert clear_cached("openrouter") is True
    assert get_cached("openrouter") is None
    assert clear_cached("openrouter") is False


def test_is_stale_by_ttl() -> None:
    now = datetime.now(UTC)
    fresh = CachedModels(models=("m",), fetched_at=now.isoformat())
    old = CachedModels(models=("m",), fetched_at=(now - timedelta(hours=7)).isoformat())
    assert fresh.is_stale(ttl_seconds=21_600, now=now) is False
    assert old.is_stale(ttl_seconds=21_600, now=now) is True


def test_is_stale_on_bad_timestamp() -> None:
    assert CachedModels(models=("m",), fetched_at="not-a-date").is_stale() is True
