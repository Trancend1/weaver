"""Connection registry unit tests (ADR 018 D2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from weaver.core.connection_registry import (
    Connection,
    delete_connection,
    get_connection,
    list_connections,
    load_connections,
    register_connection,
)
from weaver.errors import ConfigError


@pytest.fixture
def conn_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "connections.toml"
    monkeypatch.setenv("WEAVER_CONNECTIONS_PATH", str(path))
    return path


def test_load_missing_file_returns_empty(conn_path: Path) -> None:
    assert load_connections() == {}
    assert list_connections() == []


def test_register_then_get_round_trips(conn_path: Path) -> None:
    register_connection(
        Connection(
            name="openrouter",
            base_url="https://openrouter.ai/api/v1",
            api_key_env="OPENROUTER_API_KEY",
            default_model="deepseek/deepseek-chat",
        )
    )
    got = get_connection("openrouter")
    assert got is not None
    assert got.base_url == "https://openrouter.ai/api/v1"
    assert got.api_key_env == "OPENROUTER_API_KEY"
    assert got.default_model == "deepseek/deepseek-chat"
    assert got.protocol == "openai_chat"
    assert got.requires_key is True
    assert conn_path.exists()


def test_register_is_upsert_not_duplicate(conn_path: Path) -> None:
    register_connection(Connection(name="c", base_url="https://a/v1", api_key_env="A_KEY"))
    register_connection(Connection(name="c", base_url="https://b/v1", api_key_env="B_KEY"))
    conns = list_connections()
    assert len(conns) == 1
    assert conns[0].base_url == "https://b/v1"


def test_list_is_sorted_by_name(conn_path: Path) -> None:
    register_connection(Connection(name="zeta", base_url="https://z/v1", api_key_env="Z"))
    register_connection(Connection(name="alpha", base_url="https://a/v1", api_key_env="A"))
    assert [c.name for c in list_connections()] == ["alpha", "zeta"]


def test_keyless_connection_does_not_require_key(conn_path: Path) -> None:
    register_connection(
        Connection(
            name="local_ollama",
            base_url="http://localhost:11434/v1",
            api_key_env="",
            requires_key=False,
        )
    )
    got = get_connection("local_ollama")
    assert got is not None
    assert got.requires_key is False
    assert got.api_key_env == ""


def test_delete_removes_and_reports(conn_path: Path) -> None:
    register_connection(Connection(name="c", base_url="https://a/v1", api_key_env="A"))
    assert delete_connection("c") is True
    assert get_connection("c") is None
    assert delete_connection("c") is False


def test_invalid_name_is_rejected(conn_path: Path) -> None:
    with pytest.raises(ConfigError):
        register_connection(Connection(name="Has Spaces", base_url="https://a/v1", api_key_env="A"))


def test_missing_base_url_is_rejected(conn_path: Path) -> None:
    with pytest.raises(ConfigError):
        register_connection(Connection(name="c", base_url="", api_key_env="A"))


def test_control_char_values_round_trip(conn_path: Path) -> None:
    # Audit A2: the old escape left \n/\r/\t/C0 unescaped, corrupting the file.
    register_connection(
        Connection(
            name="tricky",
            base_url="https://a/v1",
            api_key_env="A_KEY",
            default_model="model\nwith\tcontrols\x1b",
            headers={"X-Note": "line1\nline2"},
        )
    )
    got = get_connection("tricky")
    assert got is not None
    assert got.default_model == "model\nwith\tcontrols\x1b"
    assert got.headers == {"X-Note": "line1\nline2"}


def test_write_over_corrupt_registry_backs_up_never_destroys(conn_path: Path) -> None:
    # Audit A7: tolerant read returns {} on a corrupt file; a write must not
    # silently rebuild from that empty view.
    conn_path.write_text('[connections.old]\nbase_url = "unterminated\n', encoding="utf-8")

    with pytest.raises(ConfigError) as exc_info:
        register_connection(Connection(name="c", base_url="https://a/v1", api_key_env="A"))

    backups = list(conn_path.parent.glob("connections.toml.corrupt-*"))
    assert len(backups) == 1
    assert "connections.old" in backups[0].read_text(encoding="utf-8")
    assert str(backups[0]) in str(exc_info.value)

    # Retry after the move-aside succeeds with a fresh file.
    register_connection(Connection(name="c", base_url="https://a/v1", api_key_env="A"))
    assert get_connection("c") is not None


def test_round_trip_preserves_headers_and_timeout(conn_path: Path) -> None:
    register_connection(
        Connection(
            name="c",
            base_url="https://a/v1",
            api_key_env="A",
            headers={"X-Title": "Weaver"},
            timeout_seconds=45.0,
        )
    )
    got = get_connection("c")
    assert got is not None
    assert got.headers == {"X-Title": "Weaver"}
    assert got.timeout_seconds == 45.0
