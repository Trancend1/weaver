"""Unit tests for the local secret store (ADR ``0020``)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from weaver.core.secret_store import (
    apply_secrets_to_env,
    delete_secret,
    list_secret_names,
    load_secrets,
    set_secret,
)
from weaver.errors import ConfigError


def test_set_load_roundtrip(tmp_path: Path) -> None:
    store = tmp_path / "secrets.toml"
    set_secret("DEEPSEEK_API_KEY", "sk-123", path=store)
    set_secret("MY_API_KEY", 'has"quote\\and', path=store)

    secrets = load_secrets(store)
    assert secrets["DEEPSEEK_API_KEY"] == "sk-123"
    assert secrets["MY_API_KEY"] == 'has"quote\\and'  # escaping round-trips


def test_control_char_value_round_trips(tmp_path: Path) -> None:
    # Audit A2: the old escape left \n/\r/\t/C0 unescaped, corrupting the file.
    store = tmp_path / "secrets.toml"
    tricky = "line1\nline2\ttab\rret\x1besc"
    set_secret("TRICKY_KEY", tricky, path=store)
    set_secret("OTHER_KEY", "plain", path=store)

    secrets = load_secrets(store)
    assert secrets["TRICKY_KEY"] == tricky
    assert secrets["OTHER_KEY"] == "plain"


def test_write_over_corrupt_store_backs_up_never_destroys(tmp_path: Path) -> None:
    # Audit A7: tolerant read returns {} on a corrupt file; a write must not
    # silently rebuild from that empty view.
    store = tmp_path / "secrets.toml"
    store.write_text('[keys]\nOLD_KEY = "unterminated\n', encoding="utf-8")

    with pytest.raises(ConfigError) as exc_info:
        set_secret("NEW_KEY", "value", path=store)

    backups = list(tmp_path.glob("secrets.toml.corrupt-*"))
    assert len(backups) == 1
    assert "OLD_KEY" in backups[0].read_text(encoding="utf-8")
    assert str(backups[0]) in str(exc_info.value)

    # Retry after the move-aside succeeds with a fresh file.
    set_secret("NEW_KEY", "value", path=store)
    assert load_secrets(store) == {"NEW_KEY": "value"}


def test_list_returns_names_only(tmp_path: Path) -> None:
    store = tmp_path / "secrets.toml"
    set_secret("B_KEY", "2", path=store)
    set_secret("A_KEY", "1", path=store)
    assert list_secret_names(store) == ["A_KEY", "B_KEY"]
    # The value never appears in the names listing.
    assert "1" not in list_secret_names(store)


def test_delete_secret(tmp_path: Path) -> None:
    store = tmp_path / "secrets.toml"
    set_secret("A_KEY", "1", path=store)
    assert delete_secret("A_KEY", path=store) is True
    assert delete_secret("A_KEY", path=store) is False
    assert list_secret_names(store) == []


def test_apply_to_env_does_not_override_real_env(tmp_path: Path, monkeypatch) -> None:
    store = tmp_path / "secrets.toml"
    set_secret("WEAVER_TEST_KEY_A", "from-store", path=store)
    set_secret("WEAVER_TEST_KEY_B", "from-store", path=store)
    monkeypatch.setenv("WEAVER_TEST_KEY_A", "from-shell")
    monkeypatch.delenv("WEAVER_TEST_KEY_B", raising=False)

    apply_secrets_to_env(store)

    assert os.environ["WEAVER_TEST_KEY_A"] == "from-shell"  # shell wins
    assert os.environ["WEAVER_TEST_KEY_B"] == "from-store"  # filled from store


def test_invalid_name_and_empty_value_raise(tmp_path: Path) -> None:
    store = tmp_path / "secrets.toml"
    with pytest.raises(ConfigError):
        set_secret("1BAD NAME", "x", path=store)
    with pytest.raises(ConfigError):
        set_secret("OK_NAME", "", path=store)


def test_load_missing_file_is_empty(tmp_path: Path) -> None:
    assert load_secrets(tmp_path / "nope.toml") == {}


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX file mode")
def test_file_mode_is_owner_only(tmp_path: Path) -> None:
    store = tmp_path / "secrets.toml"
    set_secret("A_KEY", "1", path=store)
    assert (store.stat().st_mode & 0o777) == 0o600
