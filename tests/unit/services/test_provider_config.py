"""Tests for the framework-agnostic provider/secret config service (Sprint 10C)."""

from __future__ import annotations

from pathlib import Path

import pytest

from weaver.errors import ConfigError, SecretNotFoundError
from weaver.services.provider_config import (
    read_config,
    remove_secret,
    store_secret,
    write_config,
)


@pytest.fixture(autouse=True)
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    (home / ".weaver").mkdir(parents=True)
    monkeypatch.setenv("WEAVER_SECRETS_PATH", str(home / ".weaver" / "secrets.toml"))
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.delenv("MY_KEY", raising=False)


def test_read_config_empty(tmp_path: Path) -> None:
    view = read_config(tmp_path)
    assert view.project_name is None
    assert view.secret_names == ()
    assert view.api_key_set is False


def test_read_config_unknown_project_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        read_config(tmp_path, project="ghost")


def test_write_global_then_read_back(tmp_path: Path) -> None:
    view = write_config(tmp_path, scope="global", provider_type="fake", model="m1")
    assert view.default_provider == "fake"
    assert view.default_model == "m1"


def test_write_global_model_without_provider_raises(tmp_path: Path) -> None:
    # No hidden default provider: a global default model with no provider can never
    # route, so it is rejected rather than persisted as an orphan.
    with pytest.raises(ConfigError):
        write_config(tmp_path, scope="global", model="MiniMax-M3")


def test_write_global_model_allowed_when_provider_already_set(tmp_path: Path) -> None:
    # Partial update: provider already exists globally, so a model-only save is fine.
    write_config(tmp_path, scope="global", provider_type="fake")
    view = write_config(tmp_path, scope="global", model="m2")
    assert view.default_provider == "fake"
    assert view.default_model == "m2"


def test_write_global_provider_only_is_allowed(tmp_path: Path) -> None:
    view = write_config(tmp_path, scope="global", provider_type="fake")
    assert view.default_provider == "fake"
    assert view.default_model is None


def test_write_unknown_scope_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        write_config(tmp_path, scope="weird", provider_type="fake")


def test_write_project_scope_requires_project(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        write_config(tmp_path, scope="project", provider_type="fake")


def test_store_and_presence(tmp_path: Path) -> None:
    presence = store_secret("MY_KEY", "secret-value")
    assert presence == type(presence)(name="MY_KEY", is_set=True)
    view = read_config(tmp_path)
    assert "MY_KEY" in view.secret_names
    # the value is never surfaced by the view
    assert "secret-value" not in repr(view)


def test_store_rejects_empty(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        store_secret("MY_KEY", "")


def test_remove_secret(tmp_path: Path) -> None:
    store_secret("MY_KEY", "v")
    presence = remove_secret("MY_KEY")
    assert presence.is_set is False
    assert "MY_KEY" not in read_config(tmp_path).secret_names


def test_remove_unknown_raises(tmp_path: Path) -> None:
    with pytest.raises(SecretNotFoundError):
        remove_secret("NOPE")
