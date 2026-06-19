"""Connection orchestration facade tests (ADR 018 D2/D3/D7)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from weaver.core.connection_registry import get_connection
from weaver.core.secret_store import list_secret_names, load_secrets
from weaver.errors import ConfigError
from weaver.services.connections import (
    add_connection,
    derive_env_name,
    list_connection_views,
    probe_connection,
    remove_connection,
)


@pytest.fixture(autouse=True)
def isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEAVER_CONNECTIONS_PATH", str(tmp_path / "connections.toml"))
    monkeypatch.setenv("WEAVER_SECRETS_PATH", str(tmp_path / "secrets.toml"))


class _StubClient:
    def __init__(self, ids: list[str]) -> None:
        page = SimpleNamespace(data=[SimpleNamespace(id=i) for i in ids])
        self.models = SimpleNamespace(list=lambda: page)


def test_derive_env_name() -> None:
    assert derive_env_name("openrouter") == "WEAVER_CONN_OPENROUTER"
    assert derive_env_name("local_ollama") == "WEAVER_CONN_LOCAL_OLLAMA"
    assert derive_env_name("claude-work") == "WEAVER_CONN_CLAUDE_WORK"


def test_add_with_typed_key_stores_secret_under_derived_name() -> None:
    view = add_connection(name="openrouter", base_url="https://o/v1", api_key="sk-secret")

    assert view.api_key_env == "WEAVER_CONN_OPENROUTER"
    assert view.secret_present is True
    assert "WEAVER_CONN_OPENROUTER" in list_secret_names()
    assert load_secrets()["WEAVER_CONN_OPENROUTER"] == "sk-secret"
    # the key value never lives on the connection
    conn = get_connection("openrouter")
    assert conn is not None
    assert conn.api_key_env == "WEAVER_CONN_OPENROUTER"


def test_add_with_env_override_uses_that_name(monkeypatch: pytest.MonkeyPatch) -> None:
    view = add_connection(
        name="openrouter",
        base_url="https://o/v1",
        api_key="sk-x",
        api_key_env="OPENROUTER_API_KEY",
    )
    assert view.api_key_env == "OPENROUTER_API_KEY"
    assert "OPENROUTER_API_KEY" in list_secret_names()


def test_add_use_shell_env_records_name_without_storing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MY_SHELL_KEY", "sk-from-shell")
    view = add_connection(
        name="c", base_url="https://o/v1", api_key_env="MY_SHELL_KEY", use_shell_env=True
    )
    assert view.api_key_env == "MY_SHELL_KEY"
    assert view.secret_present is True
    assert "MY_SHELL_KEY" not in list_secret_names()  # not copied into the store


def test_add_use_shell_env_missing_raises() -> None:
    with pytest.raises(ConfigError):
        add_connection(
            name="c", base_url="https://o/v1", api_key_env="ABSENT_KEY", use_shell_env=True
        )


def test_add_keyless_records_empty_env_and_is_present() -> None:
    view = add_connection(
        name="local_ollama",
        base_url="http://localhost:11434/v1",
        requires_key=False,
    )
    assert view.api_key_env == ""
    assert view.requires_key is False
    assert view.secret_present is True


def test_add_requires_key_but_none_supplied_raises() -> None:
    with pytest.raises(ConfigError):
        add_connection(name="c", base_url="https://o/v1")


def test_probe_connection_returns_discovery_result() -> None:
    result = probe_connection(
        base_url="https://o/v1", api_key="sk-x", client=_StubClient(["m2", "m1"])
    )
    assert result.count == 2
    assert result.models == ("m1", "m2")


def test_list_views_reflects_secret_presence() -> None:
    add_connection(name="openrouter", base_url="https://o/v1", api_key="sk-x")
    views = list_connection_views()
    assert len(views) == 1
    assert views[0].name == "openrouter"
    assert views[0].secret_present is True


def test_remove_connection() -> None:
    add_connection(name="c", base_url="https://o/v1", api_key="sk-x")
    assert remove_connection("c") is True
    assert remove_connection("c") is False
