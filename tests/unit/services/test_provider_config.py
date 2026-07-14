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


def _make_project(base: Path, name: str = "alpha") -> str:
    from weaver.services.project import initialize_project

    fixtures = Path(__file__).parent.parent.parent / "fixtures"
    epubs = list(fixtures.glob("*.epub"))
    if not epubs:
        pytest.skip("no EPUB fixture available")
    initialize_project(epubs[0], cwd=base, project_name=name)
    return name


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


def test_write_project_rejects_unbuildable_provider_without_persisting(
    tmp_path: Path,
) -> None:
    project = _make_project(tmp_path)

    with pytest.raises(ConfigError, match="Provider configuration is incomplete"):
        write_config(tmp_path, scope="project", project=project, provider_type="not-real")

    view = read_config(tmp_path, project=project)
    assert view.provider_type is None
    assert view.protocol is None


def test_write_project_accepts_custom_supported_protocol(tmp_path: Path) -> None:
    project = _make_project(tmp_path)

    view = write_config(
        tmp_path,
        scope="project",
        project=project,
        provider_type="not-real",
        protocol="openai_chat",
        model="custom-model",
        base_url="https://api.example.com/v1",
        api_key_env="MY_KEY",
    )

    assert view.provider_type == "not-real"
    assert view.protocol == "openai_chat"
    assert view.model == "custom-model"
    assert view.base_url == "https://api.example.com/v1"
    assert view.api_key_env == "MY_KEY"


@pytest.mark.parametrize("provider_type", ["deepseek", "gemini", "ollama", "fake"])
def test_write_project_preserves_legacy_aliases(tmp_path: Path, provider_type: str) -> None:
    project = _make_project(tmp_path, name=f"{provider_type}-project")

    view = write_config(
        tmp_path,
        scope="project",
        project=project,
        provider_type=provider_type,
    )

    # Audit A3: the legacy brand survives normalization (engine name + attempt
    # history record the real brand, not "custom").
    assert view.provider_type == provider_type
    assert view.protocol is not None


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
